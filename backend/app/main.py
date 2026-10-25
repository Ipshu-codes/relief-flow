from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import models  # noqa: F401  (lets SQLAlchemy know about the tables)
from .config import (
    BOTTLENECK_SCAN_INTERVAL_MINUTES,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT_SECONDS,
    OLLAMA_URL,
)
from .db import get_db
from .routers import (
    admin,
    assignments,
    auth,
    command_station,
    contributions,
    coordination,
    coverage,
    exposure,
    external_data,
    intelligence,
    reports,
    resources,
    routing,
    situation,
    sos,
    volunteers,
)
from .services.scheduler import scan_active_incidents
from .routers import community, mesh, organizations, workspace


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        scan_active_incidents,
        'interval',
        minutes=BOTTLENECK_SCAN_INTERVAL_MINUTES,
        id='bottleneck-scan',
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    app.state.bottleneck_scheduler = scheduler
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title='Rahat API', lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:3000', 'http://127.0.0.1:3000'],
    allow_origin_regex=(
        r'http://(?:localhost|127\.0\.0\.1|10\.\d{1,3}\.\d{1,3}\.\d{1,3}'
        r'|192\.168\.\d{1,3}\.\d{1,3}'
        r'|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}):\d+'
    ),
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(contributions.router)
app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(command_station.router)
app.include_router(coordination.router)
app.include_router(volunteers.router)
app.include_router(routing.router)
app.include_router(assignments.router)
app.include_router(coverage.router)
app.include_router(exposure.router)
app.include_router(external_data.router)
app.include_router(intelligence.router)
app.include_router(reports.router)
app.include_router(resources.router)
app.include_router(situation.router)
app.include_router(sos.router)
app.include_router(workspace.router)
app.include_router(organizations.router)
app.include_router(mesh.router)
app.include_router(community.router)

frontend_build = Path(__file__).resolve().parents[2] / 'frontend' / 'build' / 'web'


@app.get('/api/health')
async def health(db: Session = Depends(get_db)):
    database_status = 'connected'
    try:
        db.execute(text('SELECT 1'))
    except SQLAlchemyError:
        db.rollback()
        database_status = 'unavailable'

    return {
        'status': 'ok' if database_status == 'connected' else 'error',
        'database': database_status,
        'ollama': await check_ollama(),
    }


@app.get('/health')
async def health_alias(db: Session = Depends(get_db)):
    """Compatibility alias for external probes that poll ``/health``.

    The canonical route is ``/api/health``; this alias returns the same payload
    so uptime checkers and browser tabs pointed at ``/health`` do not log 404s.
    """
    return await health(db)


async def check_ollama():
    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_SECONDS) as client:
            response = await client.get(f'{OLLAMA_URL}/api/tags')
            response.raise_for_status()
        payload = response.json()
        models = payload.get('models', []) if isinstance(payload, dict) else []
        model_available = any(
            isinstance(model, dict) and model.get('name') == OLLAMA_MODEL
            for model in models
        )
        return {
            'reachable': True,
            'model': OLLAMA_MODEL,
            'model_available': model_available,
            'fallback_active': not model_available,
        }
    except (httpx.HTTPError, ValueError):
        return {
            'reachable': False,
            'model': OLLAMA_MODEL,
            'model_available': False,
            'fallback_active': True,
        }


@app.get('/ai/status')
async def ai_status():
    return await check_ollama()


if frontend_build.is_dir():
    app.mount('/', StaticFiles(directory=frontend_build, html=True), name='frontend')