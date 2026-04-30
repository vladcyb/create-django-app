# create-django-app

CLI tool that bootstraps a Django project and generates `pyproject.toml` and `uv.lock` inside Docker.

## Requirements

- Docker running locally
- `uv` installed (only for `uvx` one-command запуск)

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

## Run generated project with Docker

After bootstrap finishes:

```bash
cd my-project
docker compose up --build
```

Open `http://127.0.0.1:8000`.

Run migrations:

```bash
docker compose run --rm web uv run python manage.py migrate
```

Run tests:

```bash
docker compose run --rm web uv run python manage.py test
```

Create Django superuser (optional):

```bash
docker compose run --rm web uv run python manage.py createsuperuser
```

Stop containers:

```bash
docker compose down
```
