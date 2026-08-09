from __future__ import annotations

import base64
import hashlib
import json
import secrets
from pathlib import Path

MIN_ITERATIONS = 600_000


def normalize_email(value: str) -> str:
    candidate = str(value or "").strip().lower()
    if not candidate or len(candidate) > 320 or candidate.count("@") != 1:
        raise ValueError("A valid exact email is required.")
    local, domain = candidate.rsplit("@", 1)
    if (
        not local
        or len(local) > 64
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
        or any(char.isspace() or ord(char) < 32 for char in candidate)
    ):
        raise ValueError("A valid exact email is required.")
    try:
        domain = domain.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("A valid exact email is required.") from exc
    labels = domain.split(".")
    if len(labels) < 2 or any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        or not all(char.isalnum() or char == "-" for char in label)
        for label in labels
    ):
        raise ValueError("A valid exact email is required.")
    return f"{local}@{domain}"


def hash_password(password: str, *, iterations: int = MIN_ITERATIONS) -> str:
    if len(str(password or "")) < 12:
        raise ValueError("Passwords must contain at least 12 characters.")
    salt = secrets.token_bytes(32)
    derived = hashlib.pbkdf2_hmac(
        "sha256", str(password).encode("utf-8"), salt, iterations
    )
    encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip("=")
    return f"pbkdf2_sha256${iterations}${encode(salt)}${encode(derived)}"


def verify_password(password_hash: str, password: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, expected_text = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        if iterations < MIN_ITERATIONS:
            return False
        decode = lambda value: base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        salt = decode(salt_text)
        expected = decode(expected_text)
        derived = hashlib.pbkdf2_hmac(
            "sha256", str(password or "").encode("utf-8"), salt, iterations
        )
        return secrets.compare_digest(derived, expected)
    except (TypeError, ValueError):
        return False


def validate_password_hash(password_hash: str) -> None:
    try:
        algorithm, iterations_text, salt_text, expected_text = password_hash.split("$", 3)
        iterations = int(iterations_text)
        decode = lambda value: base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        salt = decode(salt_text)
        expected = decode(expected_text)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid password hash format.") from exc
    if algorithm != "pbkdf2_sha256" or iterations < MIN_ITERATIONS:
        raise ValueError("Invalid password hash parameters.")
    if len(salt) < 16 or len(expected) != hashlib.sha256().digest_size:
        raise ValueError("Invalid password hash data.")


def load_access_users(file_path: str) -> list[dict[str, str]]:
    path = Path(file_path).expanduser().resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Access user file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("Access user file must contain valid JSON.") from exc
    if not isinstance(payload, list) or not payload:
        raise ValueError("Access user file must contain a non-empty JSON array.")
    users: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in payload:
        if not isinstance(entry, dict) or set(entry) - {"email", "password_hash"}:
            raise ValueError("Each access user may contain only email and password_hash.")
        email = normalize_email(entry.get("email", ""))
        password_hash = str(entry.get("password_hash") or "").strip()
        if email in seen:
            raise ValueError("Access user file contains a duplicate email.")
        try:
            validate_password_hash(password_hash)
        except ValueError as exc:
            raise ValueError(f"Access user {email} has an invalid password hash.") from exc
        seen.add(email)
        users.append({"email": email, "password_hash": password_hash})
    return users


def authenticate_access_user(file_path: str, email: str, password: str) -> str | None:
    try:
        candidate = normalize_email(email)
    except ValueError:
        candidate = "invalid@example.invalid"
    matched_email: str | None = None
    for user in load_access_users(file_path):
        email_matches = secrets.compare_digest(candidate, user["email"])
        password_matches = verify_password(user["password_hash"], password)
        if email_matches and password_matches:
            matched_email = user["email"]
    return matched_email


def is_access_email_listed(file_path: str, email: str) -> bool:
    try:
        candidate = normalize_email(email)
    except ValueError:
        return False
    return any(
        secrets.compare_digest(candidate, user["email"])
        for user in load_access_users(file_path)
    )
