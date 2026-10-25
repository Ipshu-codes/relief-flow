import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import make_url


load_dotenv(Path(__file__).resolve().parents[1] / '.env')

DATABASE_URL = os.getenv(
    'DATABASE_URL', f"sqlite:///{Path(__file__).resolve().parents[1] / 'relief.db'}"
)
_database = make_url(DATABASE_URL)
if _database.drivername.startswith('sqlite') and _database.database not in (None, '', ':memory:'):
    _database_path = Path(_database.database)
    if not _database_path.is_absolute():
        _database_path = Path(__file__).resolve().parents[1] / _database_path
    DATABASE_URL = _database.set(database=str(_database_path.resolve())).render_as_string(hide_password=False)
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434').rstrip('/')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'qwen2.5:3b')
OLLAMA_TIMEOUT_SECONDS = float(os.getenv('OLLAMA_TIMEOUT_SECONDS', '2'))
AI_GENERATE_TIMEOUT_SECONDS = float(os.getenv('AI_GENERATE_TIMEOUT_SECONDS', '30'))
REPORT_AI_TIMEOUT_SECONDS = float(os.getenv('REPORT_AI_TIMEOUT_SECONDS', '90'))
SOS_AI_TIMEOUT_SECONDS = float(os.getenv('SOS_AI_TIMEOUT_SECONDS', '2'))
EXTERNAL_DATA_TIMEOUT_SECONDS = float(os.getenv('EXTERNAL_DATA_TIMEOUT_SECONDS', '10'))
_snapshot_dir = Path(os.getenv('EXTERNAL_DATA_SNAPSHOT_DIR', 'data/raw'))
if not _snapshot_dir.is_absolute():
    _snapshot_dir = Path(__file__).resolve().parents[1] / _snapshot_dir
EXTERNAL_DATA_SNAPSHOT_DIR = str(_snapshot_dir.resolve())
EXPOSURE_AI_TIMEOUT_SECONDS = float(os.getenv('EXPOSURE_AI_TIMEOUT_SECONDS', '120'))
ROAD_UPDATE_AI_TIMEOUT_SECONDS = float(os.getenv('ROAD_UPDATE_AI_TIMEOUT_SECONDS', '120'))
MATCH_CHOICE_AI_TIMEOUT_SECONDS = float(os.getenv('MATCH_CHOICE_AI_TIMEOUT_SECONDS', '120'))
ALLOCATION_CHOICE_AI_TIMEOUT_SECONDS = float(os.getenv('ALLOCATION_CHOICE_AI_TIMEOUT_SECONDS', '120'))
BOTTLENECK_DISPATCH_HOURS = float(os.getenv('BOTTLENECK_DISPATCH_HOURS', '6'))
BOTTLENECK_UNSTAFFED_HOURS = float(os.getenv('BOTTLENECK_UNSTAFFED_HOURS', '2'))
BOTTLENECK_STALE_REPORT_HOURS = float(os.getenv('BOTTLENECK_STALE_REPORT_HOURS', '24'))
DUPLICATE_REPORT_SIMILARITY = float(os.getenv('DUPLICATE_REPORT_SIMILARITY', '0.9'))
BOTTLENECK_SCAN_INTERVAL_MINUTES = max(1, int(os.getenv('BOTTLENECK_SCAN_INTERVAL_MINUTES', '30')))
JWT_SECRET = os.getenv('JWT_SECRET', '')
JWT_ALGORITHM = 'HS256'
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRE_MINUTES', '60'))
SMS_PROVIDER = os.getenv('SMS_PROVIDER', 'disabled').strip().lower()
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID', '').strip()
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN', '').strip()
TWILIO_FROM_NUMBER = os.getenv('TWILIO_FROM_NUMBER', '').strip()
