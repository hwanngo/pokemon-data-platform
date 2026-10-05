"""Keep the Airflow image tag and hashed requirements aligned with uv.lock."""

import argparse
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "uv.lock"
DOCKERFILE = ROOT / "docker" / "Dockerfile.airflow"
REQUIREMENTS = ROOT / "docker" / "airflow-requirements.txt"


def locked_airflow_version() -> str:
    packages = tomllib.loads(LOCK.read_text())["package"]
    matches = {package["version"] for package in packages if package["name"] == "apache-airflow"}
    if len(matches) != 1:
        raise ValueError(f"Expected one locked Airflow version; got {sorted(matches)}")
    return matches.pop()


def render(dockerfile: str, airflow_version: str) -> str:
    base = re.compile(r"(?m)^FROM apache/airflow:slim-[^\s@]+-python3\.14$")
    dockerfile, count = base.subn(
        f"FROM apache/airflow:slim-{airflow_version}-python3.14", dockerfile
    )
    if count != 1:
        raise ValueError("Expected one Airflow base image reference")
    return dockerfile


def exported_requirements() -> str:
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv is required to export Airflow requirements")
    result = subprocess.run(  # noqa: S603 - fixed arguments, no shell
        [
            uv,
            "export",
            "--locked",
            "--offline",
            "--extra",
            "airflow",
            "--no-dev",
            "--no-emit-project",
            "--no-header",
            "--no-annotate",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Fail if Airflow image files differ from uv.lock"
    )
    args = parser.parse_args()
    current = DOCKERFILE.read_text()
    expected = render(current, locked_airflow_version())
    requirements = exported_requirements()
    if args.check and (
        current != expected or not REQUIREMENTS.exists() or REQUIREMENTS.read_text() != requirements
    ):
        parser.error("Airflow image differs from uv.lock; run docker/sync_airflow_pins.py")
    if current != expected:
        DOCKERFILE.write_text(expected)
    if not args.check and (not REQUIREMENTS.exists() or REQUIREMENTS.read_text() != requirements):
        REQUIREMENTS.write_text(requirements)
    print(
        "Airflow image matches uv.lock" if args.check else "Synchronized Airflow image from uv.lock"
    )


if __name__ == "__main__":
    main()
