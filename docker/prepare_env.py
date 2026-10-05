"""Create safe development credentials and validate Compose configuration."""

import argparse
import base64
import binascii
import os
import re
import secrets
from pathlib import Path

REQUIRED_SECRETS = (
    "POSTGRES_PASSWORD",
    "APP_READER_PASSWORD",
    "APP_WRITER_PASSWORD",
    "AIRFLOW_DB_PASSWORD",
    "AIRFLOW_FERNET_KEY",
    "AIRFLOW_JWT_SECRET",
    "AIRFLOW_ADMIN_PASSWORD",
)
URL_SAFE = re.compile(r"^[A-Za-z0-9._~-]+$")
WEAK = {"postgres", "admin", "password", "changeme", "secret"}
PASSWORD_KEYS = tuple(key for key in REQUIRED_SECRETS if key.endswith("PASSWORD"))


def read_values(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("environment", choices=("dev", "prod"))
    args = parser.parse_args()
    path = Path(f".env.{args.environment}")
    if not path.exists():
        if args.environment == "prod":
            parser.error("create .env.prod with unique credentials before production startup")
        path.write_text(Path(".env.example").read_text())
        path.chmod(0o600)

    values = read_values(path)
    if args.environment == "dev":
        replacements = {}
        for key in REQUIRED_SECRETS:
            if not values.get(key):
                value = (
                    base64.urlsafe_b64encode(os.urandom(32)).decode()
                    if key == "AIRFLOW_FERNET_KEY"
                    else secrets.token_urlsafe(36)
                )
                replacements[key] = value
                values[key] = value
        if replacements:
            lines = path.read_text().splitlines()
            lines = [
                f"{key}={replacements[key]}"
                if (key := line.split("=", 1)[0]) in replacements
                else line
                for line in lines
            ]
            path.write_text("\n".join(lines) + "\n")
            print(f"Generated missing secrets in {path}.")

    for key in REQUIRED_SECRETS:
        value = values.get(key, "")
        if not value or value.lower() in WEAK:
            parser.error(f"{key} must be a unique non-template value")
        if key.endswith("PASSWORD") and (len(value) < 20 or not URL_SAFE.fullmatch(value)):
            parser.error(f"{key} must have at least 20 URL-safe characters")

    if len({values[key] for key in PASSWORD_KEYS}) != len(PASSWORD_KEYS):
        parser.error("database and administrator passwords must be distinct")

    try:
        fernet_bytes = base64.b64decode(values["AIRFLOW_FERNET_KEY"], altchars=b"-_", validate=True)
    except ValueError, binascii.Error:
        parser.error("AIRFLOW_FERNET_KEY must be a base64-encoded 32-byte key")
    if len(fernet_bytes) != 32:
        parser.error("AIRFLOW_FERNET_KEY must be a base64-encoded 32-byte key")
    if len(values["AIRFLOW_JWT_SECRET"]) < 32:
        parser.error("AIRFLOW_JWT_SECRET must have at least 32 characters")

    for key, low, high in (
        ("API_RATE_LIMIT", 1, 600),
        ("API_CONCURRENCY", 1, 64),
        ("MIRROR_POOL_SLOTS", 1, 32),
    ):
        try:
            number = int(values.get(key, ""))
        except ValueError:
            parser.error(f"{key} must be an integer from {low} to {high}")
        if not low <= number <= high:
            parser.error(f"{key} must be an integer from {low} to {high}")


if __name__ == "__main__":
    main()
