#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BASE_PACKAGES = ("Django", "gunicorn")
DEV_PACKAGES = ("black", "ruff")
SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = SCRIPT_DIR / "templates"
DOCKER_IMAGE = "python:3.12-slim-bookworm"
CONTAINER_PROJECT_DIR = "/app"
AUTO_COMMIT_MESSAGE = "Bootstrap Django project template"
FALLBACK_TEMPLATES: dict[str, str] = {
    "Dockerfile.template": """FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

CMD ["uv", "run", "python", "manage.py", "runserver", "0.0.0.0:8000"]
""",
    "compose.yml.template": """services:
  web:
    build: .
    command: python manage.py runserver 0.0.0.0:8000
    ports:
      - "8000:8000"
    volumes:
      - .:/app
""",
    "gitignore.template": """# Python
__pycache__/
*.py[cod]
*$py.class

# Virtual environments
.venv/
venv/
env/
ENV/

# Packaging/build artifacts
build/
dist/
*.egg-info/
.eggs/
pip-wheel-metadata/

# Tool caches
.mypy_cache/
.pytest_cache/
.ruff_cache/
.tox/
.nox/
.coverage
.coverage.*
htmlcov/

# Django
db.sqlite3
db.sqlite3-journal
media/
staticfiles/

# Environment files
.env
.env.*
!.env.example

# IDE/editor
.idea/
.vscode/

# OS files
.DS_Store
Thumbs.db
""",
    "dockerignore.template": """.git
.gitignore
.venv
venv
__pycache__
*.py[cod]
*.egg-info
.idea
.vscode
db.sqlite3
""",
}
CREATE_DJANGO_COMMAND = (
    "pip install --no-cache-dir Django gunicorn && django-admin startproject app ."
)
UV_SETUP_COMMAND_TEMPLATE = (
    "pip install --no-cache-dir uv && "
    "if [ ! -f pyproject.toml ]; then uv init --bare --python 3.12; fi && "
    "uv add {base_packages} && "
    "uv add --dev {dev_packages} && "
    "uv lock"
)


@dataclass(frozen=True)
class BootstrapConfig:
    root: Path
    docker_image: str = DOCKER_IMAGE
    container_project_dir: str = CONTAINER_PROJECT_DIR
    base_packages: tuple[str, ...] = BASE_PACKAGES
    dev_packages: tuple[str, ...] = DEV_PACKAGES
    auto_commit_message: str = AUTO_COMMIT_MESSAGE


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=check, text=True)


def run_probe(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True)


def build_uv_setup_command(config: BootstrapConfig) -> str:
    return UV_SETUP_COMMAND_TEMPLATE.format(
        base_packages=" ".join(config.base_packages),
        dev_packages=" ".join(config.dev_packages),
    )


def read_template(name: str) -> str:
    template_path = TEMPLATES_DIR / name
    if not template_path.exists():
        fallback_content = FALLBACK_TEMPLATES.get(name)
        if fallback_content is None:
            print(f"Error: template file is missing: {template_path}")
            sys.exit(1)
        print(
            f"Warning: template file is missing on disk, using built-in fallback for {name}."
        )
        return fallback_content
    return template_path.read_text(encoding="utf-8")


def write_file_if_missing(path: Path, content: str) -> None:
    if path.exists():
        print(f"{path.name} already exists. Skipping.")
        return
    path.write_text(content, encoding="utf-8")
    print(f"Created {path.name}.")


def run_in_project_container(config: BootstrapConfig, command: str) -> None:
    run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{config.root}:{config.container_project_dir}",
            "-w",
            config.container_project_dir,
            config.docker_image,
            "sh",
            "-c",
            command,
        ]
    )


def ensure_docker() -> None:
    if shutil.which("docker") is None:
        print("Error: docker is not installed or not found in PATH.")
        sys.exit(1)
    docker_running = run_probe(["docker", "info"])
    if docker_running.returncode != 0:
        print("Error: docker is installed, but Docker daemon is not running.")
        print("Start Docker Desktop (or docker service) and try again.")
        sys.exit(1)


def ensure_django_project(config: BootstrapConfig) -> None:
    config.root.mkdir(parents=True, exist_ok=True)
    if (config.root / "manage.py").exists() or (config.root / "app").is_dir():
        print(
            "Django project files already detected (manage.py/app). Skipping project creation."
        )
        return

    ensure_docker()
    print(f"Creating Django project in {config.root} via Docker...")
    run_in_project_container(config, CREATE_DJANGO_COMMAND)


def ensure_uv_project_files(config: BootstrapConfig) -> None:
    ensure_docker()
    print("Generating pyproject.toml and uv.lock via Docker...")
    run_in_project_container(config, build_uv_setup_command(config))


def ensure_docker_files(config: BootstrapConfig) -> None:
    write_file_if_missing(
        config.root / "Dockerfile",
        read_template("Dockerfile.template"),
    )

    write_file_if_missing(
        config.root / "compose.yml",
        read_template("compose.yml.template"),
    )

    write_file_if_missing(
        config.root / ".gitignore",
        read_template("gitignore.template"),
    )

    write_file_if_missing(
        config.root / ".dockerignore",
        read_template("dockerignore.template"),
    )


def try_auto_commit(config: BootstrapConfig) -> None:
    if shutil.which("git") is None:
        print("Git is not installed. Skipping auto-commit.")
        return

    inside_work_tree = run_probe(["git", "rev-parse", "--is-inside-work-tree"])
    if inside_work_tree.returncode != 0:
        print("Current directory is not a git repository. Initializing...")
        run(["git", "init"])

    status = run_probe(["git", "status", "--porcelain"])
    if status.returncode != 0:
        print("Unable to read git status. Skipping auto-commit.")
        return
    if not status.stdout.strip():
        print("No git changes detected. Skipping auto-commit.")
        return

    run(["git", "add", "."])
    run(["git", "commit", "-m", config.auto_commit_message])
    print(f"Created git commit: {config.auto_commit_message}")


def print_activation_hint() -> None:
    print("Run locally with: uv sync && uv run python manage.py runserver")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="create-django-app",
        description="Bootstrap a Django project in the target folder.",
    )
    parser.add_argument(
        "folder_name",
        help="Folder where the Django bootstrap will be created.",
    )
    return parser.parse_args()


def run_bootstrap(config: BootstrapConfig) -> None:
    print(f"Target folder: {config.root}")
    config.root.mkdir(parents=True, exist_ok=True)
    os.chdir(config.root)
    ensure_django_project(config)
    ensure_uv_project_files(config)
    ensure_docker_files(config)
    try_auto_commit(config)


def main() -> None:
    args = parse_args()
    config = BootstrapConfig(root=(Path.cwd() / args.folder_name).resolve())
    try:
        run_bootstrap(config)
    except subprocess.CalledProcessError as exc:
        cmd = " ".join(exc.cmd) if isinstance(exc.cmd, list) else str(exc.cmd)
        print(f"Error: command failed with exit code {exc.returncode}: {cmd}")
        sys.exit(exc.returncode or 1)

    print("Done. Django bootstrap complete.")
    print_activation_hint()


if __name__ == "__main__":
    main()
