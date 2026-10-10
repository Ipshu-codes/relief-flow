from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  (lets SQLAlchemy know about the tables)
from .db import Base, engine
from .routers import admin, contributions

Base.metadata.create_all(bind=engine)

app = FastAPI(title='Rahat API')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:3000'],
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(contributions.router)
app.include_router(admin.router)


@app.get('/api/health')
def health():
    return {'status': 'ok'}