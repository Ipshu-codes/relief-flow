from contextlib import asynccontextmanager

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
from .routers import admin, assignments, auth, contributions, coverage, intelligence, reports, resources, routing, situation, sos, volunteers
from .services.scheduler import scan_active_incidents


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
    allow_origins=['http://localhost:3000'],
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(contributions.router)
app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(volunteers.router)
app.include_router(routing.router)
app.include_router(assignments.router)
app.include_router(coverage.router)
app.include_router(intelligence.router)
app.include_router(reports.router)
app.include_router(resources.router)
app.include_router(situation.router)
app.include_router(sos.router)


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