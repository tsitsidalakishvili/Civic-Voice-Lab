from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from deliberation.api.app.core.env import load_backend_env

load_backend_env(ROOT_DIR)

from deliberation.api.app.main import app  # noqa: F401
