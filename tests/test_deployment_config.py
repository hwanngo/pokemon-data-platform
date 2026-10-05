"""Bootstrap must not accept template credentials in production."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PREPARE = REPO / "docker" / "prepare_env.py"


def run_prepare(tmp_path: Path, mode: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed interpreter and repository script
        [sys.executable, str(PREPARE), mode],
        cwd=tmp_path,
        env={key: value for key, value in os.environ.items() if not key.startswith("POSTGRES_")},
        capture_output=True,
        text=True,
        check=False,
    )


def test_dev_generates_missing_credentials_once(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text((REPO / ".env.example").read_text())

    first = run_prepare(tmp_path, "dev")
    assert first.returncode == 0, first.stderr
    contents = (tmp_path / ".env.dev").read_text()
    assert "POSTGRES_PASSWORD=\n" not in contents
    assert "AIRFLOW_ADMIN_PASSWORD=\n" not in contents

    second = run_prepare(tmp_path, "dev")
    assert second.returncode == 0, second.stderr
    assert (tmp_path / ".env.dev").read_text() == contents


def test_prod_rejects_blank_and_known_passwords(tmp_path: Path) -> None:
    template = (REPO / ".env.example").read_text()
    (tmp_path / ".env.example").write_text(template)
    path = tmp_path / ".env.prod"
    path.write_text(template)
    assert run_prepare(tmp_path, "prod").returncode != 0

    generated = run_prepare(tmp_path, "dev")
    assert generated.returncode == 0, generated.stderr
    path.write_text(
        (tmp_path / ".env.dev")
        .read_text()
        .replace(
            next(
                line
                for line in (tmp_path / ".env.dev").read_text().splitlines()
                if line.startswith("AIRFLOW_ADMIN_PASSWORD=")
            ),
            "AIRFLOW_ADMIN_PASSWORD=admin",
        )
    )
    assert run_prepare(tmp_path, "prod").returncode != 0

    generated_text = (tmp_path / ".env.dev").read_text()
    reader_password = next(
        line.split("=", 1)[1]
        for line in generated_text.splitlines()
        if line.startswith("APP_READER_PASSWORD=")
    )
    path.write_text(
        generated_text.replace(
            next(
                line
                for line in generated_text.splitlines()
                if line.startswith("APP_WRITER_PASSWORD=")
            ),
            f"APP_WRITER_PASSWORD={reader_password}",
        )
    )
    assert run_prepare(tmp_path, "prod").returncode != 0


@pytest.mark.parametrize("mode", ["dev", "prod"])
def test_postgres_entrypoint_only_runs_init_script(mode: str) -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker CLI unavailable")

    dummy = dict.fromkeys(
        (
            "POSTGRES_PASSWORD",
            "APP_READER_PASSWORD",
            "APP_WRITER_PASSWORD",
            "AIRFLOW_DB_PASSWORD",
            "AIRFLOW_ADMIN_PASSWORD",
        ),
        "DummyPassword1234567890",
    )
    dummy.update(dict.fromkeys(("AIRFLOW_FERNET_KEY", "AIRFLOW_JWT_SECRET"), "DummyValue"))
    result = subprocess.run(  # noqa: S603 - fixed Docker CLI and repository Compose files
        [
            docker,
            "compose",
            "-f",
            str(REPO / "docker" / f"docker-compose.{mode}.yml"),
            "--env-file",
            str(REPO / ".env.example"),
            "config",
            "--format",
            "json",
        ],
        cwd=REPO,
        env={**os.environ, **dummy},
        capture_output=True,
        text=True,
        check=True,
    )
    config = json.loads(result.stdout)
    assert config["name"] == f"pokedata-{mode}"
    assert config["services"]["airflow-init"]["environment"]["MIRROR_POOL_SLOTS"] == "1"
    postgres_health = config["services"]["postgres"]["healthcheck"]["test"]
    assert "-h 127.0.0.1" in postgres_health[1]
    assert "-d pokemon_data" in postgres_health[1]
    targets = [volume["target"] for volume in config["services"]["postgres"]["volumes"]]
    assert [target for target in targets if target.startswith("/docker-entrypoint-initdb.d")] == [
        "/docker-entrypoint-initdb.d/01-init.sh"
    ]
    assert config["services"]["app"]["ports"][0]["host_ip"] == "127.0.0.1"
    assert (
        config["services"]["airflow-scheduler"]["depends_on"]["airflow-init"]["condition"]
        == "service_completed_successfully"
    )
    assert (
        config["services"]["app"]["depends_on"]["app-migrate"]["condition"]
        == "service_completed_successfully"
    )
