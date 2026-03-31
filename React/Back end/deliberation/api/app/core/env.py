from pathlib import Path

from dotenv import load_dotenv


def load_backend_env(base_dir: Path) -> list[Path]:
    root = Path(base_dir).resolve()
    loaded: list[Path] = []
    for candidate in (
        root / ".env",
        root / ".env.local",
        root / ".env.auth",
        root / ".env.auth.local",
    ):
        if candidate.exists():
            load_dotenv(dotenv_path=candidate, override=True)
            loaded.append(candidate)
    return loaded
