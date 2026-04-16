from pathlib import Path

from dotenv import load_dotenv

CONFIG_DIR = Path(__file__).resolve().parent
BASE_DIR = CONFIG_DIR.parent
ENV_PATH = CONFIG_DIR / "KEYS.env"


def load_env_file(*, override: bool = False) -> Path:
    """Load environment variables from config/KEYS.env."""
    load_dotenv(ENV_PATH, override=override)
    return ENV_PATH
