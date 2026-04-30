# create-django-app

CLI tool that bootstraps a Django project and generates `pyproject.toml` and `uv.lock` inside Docker.

## Requirements

- Docker running locally
- `uv` installed (for `uvx` usage)

## One-command run from GitHub

```bash
py -m uv tool run --from "git+https://github.com/vladcyb/create-django-app.git@master" create-django-app my-project
```

## Local development usage

```bash
python create-django-app.py my-project
```

or

```bash
python create_django_app.py my-project
```
