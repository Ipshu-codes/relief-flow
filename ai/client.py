import json
import asyncio
import time
from weakref import WeakKeyDictionary
from datetime import datetime, timezone
from typing import Callable, TypeVar

import ollama
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import AI_GENERATE_TIMEOUT_SECONDS, OLLAMA_MODEL, OLLAMA_URL
from app.models import AICallLog

OutputModel = TypeVar('OutputModel', bound=BaseModel)
_inference_slots: WeakKeyDictionary = WeakKeyDictionary()


async def generate_json(
    db: Session,
    *,
    task: str,
    prompt_version: str,
    prompt: str,
    input_summary: str,
    schema: type[OutputModel],
    fallback: Callable[[], dict],
    validate: Callable[[OutputModel], None] | None = None,
    timeout_seconds: float | None = None,
    max_output_tokens: int | None = None,
) -> tuple[OutputModel, str]:
    attempts = []
    client = ollama.AsyncClient(
        host=OLLAMA_URL,
        timeout=timeout_seconds or AI_GENERATE_TIMEOUT_SECONDS,
    )
    generation_options = {'temperature': 0.1}
    if max_output_tokens is not None:
        generation_options['num_predict'] = max_output_tokens
    for _ in range(2):
        started = time.perf_counter()
        raw_output = ''
        validation_result = 'invalid'
        try:
            loop = asyncio.get_running_loop()
            slot = _inference_slots.setdefault(loop, asyncio.Semaphore(1))
            async with slot:
                response = await client.generate(
                    model=OLLAMA_MODEL,
                    prompt=prompt,
                    format=schema.model_json_schema(),
                    options=generation_options,
                )
            raw_output = response.response
            parsed = schema.model_validate_json(raw_output)
            if validate is not None:
                validate(parsed)
            validation_result = 'valid'
            attempts.append((round((time.perf_counter() - started) * 1000), raw_output, validation_result))
            for latency, output, result in attempts:
                db.add(
                    AICallLog(
                        task=task,
                        prompt_version=prompt_version,
                        model=OLLAMA_MODEL,
                        latency_ms=latency,
                        input_summary=input_summary[:1000],
                        output=output[:10000],
                        validation_result=result,
                        fallback_used=False,
                        created_at=datetime.now(timezone.utc),
                    )
                )
            return parsed, 'ai'
        except Exception as exc:
            if not raw_output:
                raw_output = f'{type(exc).__name__}: {exc}'
            validation_result = f'{type(exc).__name__}: {exc}'[:300]
            attempts.append((round((time.perf_counter() - started) * 1000), raw_output, validation_result))

    parsed_fallback = schema.model_validate(fallback())
    for latency, output, result in attempts:
        db.add(
            AICallLog(
                task=task,
                prompt_version=prompt_version,
                model=OLLAMA_MODEL,
                latency_ms=latency,
                input_summary=input_summary[:1000],
                output=output[:10000],
                validation_result=result,
                fallback_used=True,
                created_at=datetime.now(timezone.utc),
            )
        )
    db.add(
        AICallLog(
            task=task,
            prompt_version=prompt_version,
            model=OLLAMA_MODEL,
            latency_ms=0,
            input_summary=input_summary[:1000],
            output=json.dumps(parsed_fallback.model_dump(), sort_keys=True),
            validation_result='fallback_valid',
            fallback_used=True,
            created_at=datetime.now(timezone.utc),
        )
    )
    return parsed_fallback, 'fallback'
