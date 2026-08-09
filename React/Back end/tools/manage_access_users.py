from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from deliberation.api.app.core.access_users import hash_password, normalize_email


def load(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("The access file must contain a JSON array.")
    return payload


def save(path: Path, users: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(users, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    os.replace(temporary, path)


def add_user(path: Path, raw_email: str) -> None:
    email = normalize_email(raw_email)
    password = getpass.getpass("Password (minimum 12 characters): ")
    confirmation = getpass.getpass("Repeat password: ")
    if password != confirmation:
        raise ValueError("Passwords do not match.")
    password_hash = hash_password(password)
    users = load(path)
    remaining = [item for item in users if normalize_email(item.get("email", "")) != email]
    remaining.append({"email": email, "password_hash": password_hash})
    remaining.sort(key=lambda item: item["email"])
    save(path, remaining)
    print(f"Access saved for {email}.")


def remove_user(path: Path, raw_email: str) -> None:
    email = normalize_email(raw_email)
    users = load(path)
    remaining = [item for item in users if normalize_email(item.get("email", "")) != email]
    if len(remaining) == len(users):
        raise ValueError("That email is not in the access file.")
    save(path, remaining)
    print(f"Access removed for {email}. Existing sessions should also be revoked.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the private FS access-user file.")
    parser.add_argument(
        "--file",
        type=Path,
        default=BACKEND_ROOT / "access_users.local.json",
        help="Path to the private JSON file.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    add = subcommands.add_parser("add", help="Add or replace one exact email.")
    add.add_argument("email")
    remove = subcommands.add_parser("remove", help="Remove one exact email.")
    remove.add_argument("email")
    subcommands.add_parser("list", help="List approved emails without password hashes.")
    args = parser.parse_args()
    path = args.file.expanduser().resolve()
    if args.command == "add":
        add_user(path, args.email)
    elif args.command == "remove":
        remove_user(path, args.email)
    else:
        for item in load(path):
            print(normalize_email(item.get("email", "")))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Error: {exc}") from exc
