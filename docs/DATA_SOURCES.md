# Data Sources and Attribution

The app distinguishes estimated baselines, reported requests and verified
field evidence. A point on the map is not automatically a confirmed disaster
location, and a forecast is not an official warning.

This inventory was reviewed on **25 October 2026**. That is a documentation
review date, not a dataset download date. Exact dataset licences and snapshot
dates must come from the files used in a demonstration or deployment; they
must not be inferred from the build brief.

## Current Sources and Planned Imports

| Source | Current Use | Licence/Attribution Status | Snapshot Date |
|---|---|---|---|
| Local demo seed | Synthetic incidents, locations, needs, volunteers, stock and baseline examples | Application fixtures, not official observations or census extracts | Generated when demo setup runs; not a government snapshot |
| Open-Meteo forecast API: https://api.open-meteo.com/v1/forecast | Rainfall adapter with timeout and saved-response fallback | Check https://open-meteo.com/en/licence and current service terms before publishing data or commercial use; retain required attribution | Each successful fetch stores `fetched_at`; no particular downloaded snapshot is certified by these docs |
| Open-Meteo Flood API: https://flood-api.open-meteo.com/v1/flood | Modelled discharge adapter with the same snapshot mechanism | Check the provider's current licence, Flood API terms and underlying model attribution; this is not a DHM gauge observation | Stored per fetch, if one has been made |
| Nepal NSO Census 2021: https://data.nsonepal.gov.np/ | Intended source for population/household baseline imports; demo values must not be passed off as census data | Record the exact table, year, source URL and reuse terms before importing or redistributing | No verified district-wide census download date recorded here |
| BIPAD: https://bipadportal.gov.np/ | Incident import support; not proof of a live, complete government feed | Public endpoint availability does not establish a redistribution licence. Confirm official terms and endpoint behavior | Record the original export/fetch timestamp when real data is imported |
| DHM: https://hydrology.gov.np/ | River observation import support; not a certified live gauge integration | Confirm source, units, warning thresholds, publication time and reuse terms | No verified current gauge snapshot asserted |
| OpenStreetMap / HOT: https://www.openstreetmap.org/copyright | Potential source for roads/facilities; current routes do not use an OSM road graph | OSM data uses ODbL; attribute OpenStreetMap contributors and review derivative-database obligations | No current road-network extract is claimed |
| HDX administrative boundaries: https://data.humdata.org/ | Candidate ward-boundary source, not a certified bundled ward dataset | Licence is dataset-specific; record the actual dataset page, publisher and version | Not established for a production ward import |
| Nepal Police / Department of Roads notices | A coordinator can paste notice text for AI parsing and review | Keep the original publication URL, time and issuer. Do not infer permission to republish entire notices | Use the notice's publication time and the import time separately |
| Bundled Nepal GeoJSON | Province/district context in the Flutter clients | The current files alone do not establish complete upstream provenance/licensing. Verify and retain original attribution before redistribution | Original download date not established in this review |

The map files are [../frontend/assets/nepal_states.geojson](../frontend/assets/nepal_states.geojson)
and [../frontend/assets/nepal_hq.geojson](../frontend/assets/nepal_hq.geojson),
with station copies under its assets directory. They are a basemap, not
ward-level population data or evidence of current disaster impact.

## Snapshot Behavior

`OpenMeteoClient` in
[../backend/app/services/external_data.py](../backend/app/services/external_data.py)
saves successful JSON responses with dataset, request coordinates and
`fetched_at`. The default directory is `backend/data/raw`, configurable with
`EXTERNAL_DATA_SNAPSHOT_DIR`. When a request fails, it uses the newest saved
response for that dataset and matching request parameters. Without one, the
adapter reports unavailability rather than inventing data.

Returned metadata distinguishes `live` from `snapshot` and labels these
forecasts `estimated`. Snapshot fallback is not a freshness guarantee; an old
matching snapshot can still be stale. Before an offline demo, fetch the exact
coordinates to be used and check the saved timestamp. Do not assume snapshots
are bundled merely because the directory is configured.

BIPAD/DHM import endpoints are not equivalent to automatic timed fetchers with
the same cache contract. A full, audited district data package remains work
to do.

## Import Record to Keep

For each real dataset, retain the publisher, exact source URL, dataset version,
coverage area, observation/reference date, download time, units, licence text
or link, required attribution, and whether records were modified or verified.
Store raw originals without personal SOS messages in public demo artifacts.

Where this record is incomplete, label the demo as synthetic or the data as
unverified. Census 2021 remains a historical estimate even after an import;
current occupancy and verified impact require separate evidence.