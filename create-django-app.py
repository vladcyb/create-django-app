#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
BASE_PACKAGES = ("Django", "gunicorn")
DEV_PACKAGES = ("black", "ruff")


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=check, text=True)


def venv_dir() -> Path:
    return ROOT / ".venv"


def write_file_if_missing(path: Path, content: str) -> None:
    if path.exists():
        print(f"{path.name} already exists. Skipping.")
        return
    path.write_text(content, encoding="utf-8")
    print(f"Created {path.name}.")


def ensure_docker() -> None:
    if shutil.which("docker") is None:
        print("Error: docker is not installed or not found in PATH.")
        sys.exit(1)
    docker_running = subprocess.run(
        ["docker", "info"],
        text=True,
        capture_output=True,
    )
    if docker_running.returncode != 0:
        print("Error: docker is installed, but Docker daemon is not running.")
        print("Start Docker Desktop (or docker service) and try again.")
        sys.exit(1)


def ensure_django_project() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    if (ROOT / "manage.py").exists() or (ROOT / "app").is_dir():
        print(
            "Django project files already detected (manage.py/app). Skipping project creation."
        )
        return

    ensure_docker()
    print(f"Creating Django project in {ROOT} via Docker...")
    run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{ROOT}:/app",
            "-w",
            "/app",
            "python:3.12-slim-bookworm",
            "sh",
            "-c",
            "pip install Django gunicorn && django-admin startproject app .",
        ]
    )
    requirements_file = ROOT / "requirements.txt"
    if not requirements_file.exists():
        requirements_file.write_text("Django\ngunicorn\n", encoding="utf-8")
        print("Created requirements.txt with base dependencies (Django, gunicorn).")


def venv_python_path() -> Path:
    venv = venv_dir()
    windows_python = venv / "Scripts" / "python.exe"
    unix_python = venv / "bin" / "python"
    if windows_python.exists():
        return windows_python
    return unix_python


def create_or_reuse_venv() -> Path:
    venv = venv_dir()
    if not venv.exists():
        print(f"Creating virtual environment in {venv}...")
        run([sys.executable, "-m", "venv", str(venv)])
    else:
        print("Virtual environment .venv already exists. Reusing it.")

    vpython = venv_python_path()
    if not vpython.exists():
        print("Error: could not find venv python interpreter in .venv.")
        sys.exit(1)

    pip_check = subprocess.run([str(vpython), "-m", "pip", "--version"], text=True)
    if pip_check.returncode != 0:
        print("Existing .venv is incomplete (pip not available). Recreating...")
        shutil.rmtree(venv, ignore_errors=True)
        run([sys.executable, "-m", "venv", str(venv)])
        vpython = venv_python_path()
        if not vpython.exists():
            print("Error: could not find venv python interpreter after recreation.")
            sys.exit(1)

    return vpython


def install_dev_tools(vpython: Path) -> None:
    print("Installing project and developer dependencies into .venv...")
    run(
        [
            str(vpython),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
            *BASE_PACKAGES,
            *DEV_PACKAGES,
        ]
    )


def installed_version(vpython: Path, package: str) -> str:
    result = subprocess.run(
        [str(vpython), "-m", "pip", "show", package],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        print(f"Error: could not detect installed version for {package}.")
        sys.exit(1)
    for line in result.stdout.splitlines():
        if line.startswith("Version: "):
            return line.split(": ", 1)[1].strip()
    print(f"Error: no version information found for {package}.")
    sys.exit(1)


def write_pinned_requirements(vpython: Path) -> None:
    base_lines = [
        f"{name}=={installed_version(vpython, name)}" for name in BASE_PACKAGES
    ]
    dev_lines = [f"{name}=={installed_version(vpython, name)}" for name in DEV_PACKAGES]

    (ROOT / "requirements.txt").write_text(
        "\n".join(base_lines) + "\n", encoding="utf-8"
    )
    print("Updated requirements.txt with pinned Django and gunicorn versions.")

    (ROOT / "requirements.dev.txt").write_text(
        "\n".join(dev_lines) + "\n", encoding="utf-8"
    )
    print("Updated requirements.dev.txt with pinned black and ruff versions.")


def ensure_docker_files() -> None:
    write_file_if_missing(
        ROOT / "Dockerfile",
        """FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
""",
    )

    write_file_if_missing(
        ROOT / "compose.yml",
        """services:
  web:
    build: .
    command: python manage.py runserver 0.0.0.0:8000
    ports:
      - "8000:8000"
    volumes:
      - .:/app
""",
    )

    write_file_if_missing(
        ROOT / ".gitignore",
        """# Python
__pycache__/
*.py[cod]
*.egg-info/

# Virtual environments
.venv/
venv/

# Django
db.sqlite3
staticfiles/
media/

# Environment files
.env
.env.*

# IDE/editor
.idea/
.vscode/
""",
    )

    write_file_if_missing(
        ROOT / ".dockerignore",
        """.git
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
    )


def try_auto_commit() -> None:
    if shutil.which("git") is None:
        print("Git is not installed. Skipping auto-commit.")
        return

    # Ensure we are inside a git work tree before running git commands.
    # If repository is missing, initialize it automatically.
    inside_work_tree = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        text=True,
        capture_output=True,
    )
    if inside_work_tree.returncode != 0:
        print("Current directory is not a git repository. Initializing...")
        run(["git", "init"])

    status = subprocess.run(
        ["git", "status", "--porcelain"], text=True, capture_output=True
    )
    if status.returncode != 0:
        print("Unable to read git status. Skipping auto-commit.")
        return
    if not status.stdout.strip():
        print("No git changes detected. Skipping auto-commit.")
        return

    run(["git", "add", "."])
    run(["git", "commit", "-m", "Bootstrap Django project template"])
    print("Created git commit: Bootstrap Django project template")


def print_activation_hint() -> None:
    if os.name == "nt":
        print(r"Activate environment with: .\.venv\Scripts\activate")
    else:
        print("Activate environment with: source .venv/bin/activate")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="create-django-app.py",
        description="Bootstrap a Django project in the target folder.",
    )
    parser.add_argument(
        "folder_name",
        help="Folder where the Django bootstrap will be created.",
    )
    return parser.parse_args()


def main() -> None:
    global ROOT
    args = parse_args()
    target_folder = Path(args.folder_name)
    ROOT = (Path.cwd() / target_folder).resolve()
    print(f"Target folder: {ROOT}")
    ROOT.mkdir(parents=True, exist_ok=True)
    os.chdir(ROOT)
    try:
        ensure_django_project()
        vpython = create_or_reuse_venv()
        install_dev_tools(vpython)
        write_pinned_requirements(vpython)
        ensure_docker_files()
        try_auto_commit()
    except subprocess.CalledProcessError as exc:
        cmd = " ".join(exc.cmd) if isinstance(exc.cmd, list) else str(exc.cmd)
        print(f"Error: command failed with exit code {exc.returncode}: {cmd}")
        sys.exit(exc.returncode or 1)

    print("Done. Django bootstrap complete.")
    print_activation_hint()


if __name__ == "__main__":
    main()
