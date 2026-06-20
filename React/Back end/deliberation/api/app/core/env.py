from pathlib import Path

from dotenv import load_dotenv


def load_backend_env(base_dir: Path) -> list[Path]:
    root = Path(base_dir).resolve()
    loaded: list[Path] = []
    env_names = (".env", ".env.local", ".env.auth", ".env.auth.local")
    search_roots = (root, *root.parents[:2])
    for search_root in reversed(search_roots):
        for env_name in env_names:
            candidate = search_root / env_name
            if candidate.exists() and candidate not in loaded:
                load_dotenv(dotenv_path=candidate, override=True)
                loaded.append(candidate)
    return loaded
