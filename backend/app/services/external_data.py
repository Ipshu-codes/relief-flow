import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from ..config import EXTERNAL_DATA_SNAPSHOT_DIR, EXTERNAL_DATA_TIMEOUT_SECONDS


FORECAST_URL = 'https://api.open-meteo.com/v1/forecast'
FLOOD_URL = 'https://flood-api.open-meteo.com/v1/flood'


class ExternalDataUnavailable(Exception):
    pass


class OpenMeteoClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = EXTERNAL_DATA_TIMEOUT_SECONDS,
        snapshot_dir: str | Path = EXTERNAL_DATA_SNAPSHOT_DIR,
    ):
        self.timeout_seconds = timeout_seconds
        self.snapshot_dir = Path(snapshot_dir)

    async def fetch_rainfall(self, latitude: float, longitude: float) -> dict:
        return await self._fetch(
            dataset='open_meteo_rainfall',
            url=FORECAST_URL,
            params={
                'latitude': latitude,
                'longitude': longitude,
                'hourly': 'precipitation',
                'forecast_days': 1,
            },
            series_key='precipitation',
            series_group='hourly',
        )

    async def fetch_river_discharge(self, latitude: float, longitude: float) -> dict:
        return await self._fetch(
            dataset='open_meteo_river_discharge',
            url=FLOOD_URL,
            params={
                'latitude': latitude,
                'longitude': longitude,
                'daily': 'river_discharge',
                'forecast_days': 1,
            },
            series_key='river_discharge',
            series_group='daily',
        )

    async def _fetch(
        self,
        *,
        dataset: str,
        url: str,
        params: dict,
        series_key: str,
        series_group: str,
    ) -> dict:
        requested_at = datetime.now(timezone.utc)
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
            self._validate_series(payload, series_group, series_key)
            fetched_at = datetime.now(timezone.utc)
            self._save_snapshot(dataset, params, payload, fetched_at)
            return self._result(dataset, payload, source='live', fetched_at=fetched_at)
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            snapshot = self._latest_snapshot(dataset, params)
            if snapshot is None:
                raise ExternalDataUnavailable(
                    f'Open-Meteo {dataset} unavailable and no saved snapshot exists'
                ) from exc
            payload, fetched_at = snapshot
            self._validate_series(payload, series_group, series_key)
            result = self._result(dataset, payload, source='snapshot', fetched_at=fetched_at)
            result['requested_at'] = requested_at.isoformat()
            result['live_error'] = type(exc).__name__
            return result

    @staticmethod
    def _validate_series(payload: Any, group: str, series_key: str) -> None:
        if not isinstance(payload, dict):
            raise ValueError('External response must be a JSON object')
        series = payload.get(group)
        if not isinstance(series, dict):
            raise ValueError(f'External response is missing {group}')
        times = series.get('time')
        values = series.get(series_key)
        if not isinstance(times, list) or not isinstance(values, list) or not times:
            raise ValueError(f'External response is missing {group}.{series_key} data')
        if len(times) != len(values):
            raise ValueError(f'External response has mismatched {group} series lengths')
        if any(value is not None and not isinstance(value, (int, float)) for value in values):
            raise ValueError(f'External response has invalid {series_key} values')

    def _save_snapshot(self, dataset: str, params: dict, payload: dict, fetched_at: datetime) -> None:
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        timestamp = fetched_at.strftime('%Y%m%dT%H%M%S%fZ')
        snapshot = {
            'dataset': dataset,
            'fetched_at': fetched_at.isoformat(),
            'request': params,
            'response': payload,
        }
        path = self.snapshot_dir / f'{dataset}_{timestamp}.json'
        temporary_path = path.with_suffix('.tmp')
        temporary_path.write_text(json.dumps(snapshot, separators=(',', ':')), encoding='utf-8')
        temporary_path.replace(path)

    def _latest_snapshot(self, dataset: str, request: dict) -> tuple[dict, datetime] | None:
        if not self.snapshot_dir.exists():
            return None
        for path in sorted(
            self.snapshot_dir.glob(f'{dataset}_*.json'),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        ):
            try:
                snapshot = json.loads(path.read_text(encoding='utf-8'))
                if (
                    snapshot.get('dataset') != dataset
                    or snapshot.get('request') != request
                    or not isinstance(snapshot.get('response'), dict)
                ):
                    continue
                fetched_at = datetime.fromisoformat(snapshot['fetched_at'])
                if fetched_at.tzinfo is None:
                    fetched_at = fetched_at.replace(tzinfo=timezone.utc)
                return snapshot['response'], fetched_at
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return None

    @staticmethod
    def _result(dataset: str, payload: dict, *, source: str, fetched_at: datetime) -> dict:
        return {
            'provider': 'open-meteo',
            'dataset': dataset,
            'source': source,
            'verification_status': 'estimated',
            'confidence': 'low',
            'fetched_at': fetched_at.isoformat(),
            'latitude': payload.get('latitude'),
            'longitude': payload.get('longitude'),
            'data': payload,
        }