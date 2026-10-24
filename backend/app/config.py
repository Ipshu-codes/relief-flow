import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / '.env')

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./relief.db')
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434').rstrip('/')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'qwen2.5:3b')
OLLAMA_TIMEOUT_SECONDS = float(os.getenv('OLLAMA_TIMEOUT_SECONDS', '2'))
AI_GENERATE_TIMEOUT_SECONDS = float(os.getenv('AI_GENERATE_TIMEOUT_SECONDS', '30'))
SOS_AI_TIMEOUT_SECONDS = float(os.getenv('SOS_AI_TIMEOUT_SECONDS', '2'))
BOTTLENECK_DISPATCH_HOURS = float(os.getenv('BOTTLENECK_DISPATCH_HOURS', '6'))
BOTTLENECK_UNSTAFFED_HOURS = float(os.getenv('BOTTLENECK_UNSTAFFED_HOURS', '2'))
BOTTLENECK_STALE_REPORT_HOURS = float(os.getenv('BOTTLENECK_STALE_REPORT_HOURS', '24'))
DUPLICATE_REPORT_SIMILARITY = float(os.getenv('DUPLICATE_REPORT_SIMILARITY', '0.9'))
BOTTLENECK_SCAN_INTERVAL_MINUTES = max(1, int(os.getenv('BOTTLENECK_SCAN_INTERVAL_MINUTES', '30')))
JWT_SECRET = os.getenv('JWT_SECRET', '')
JWT_ALGORITHM = 'HS256'
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRE_MINUTES', '60'))
