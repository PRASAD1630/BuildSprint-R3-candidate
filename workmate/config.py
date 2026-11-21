from pathlib import Path
import os

ROOT = Path(os.getenv("R3_PACK", Path(__file__).resolve().parents[1])).resolve()
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
except Exception:
    pass
DATA = ROOT / "data"
DB_PATH = Path(os.getenv("WORKMATE_DB", ROOT / "workmate.sqlite3"))
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "none").lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
