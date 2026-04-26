default:
    @just --list

# Show available recipes.
help:
    @just --list

# Install requirements.
install:
    uv sync --all-groups
    npm install

# Install the git pre-commit hook.
install-pre-commit:
    uv run pre-commit install

# Run the agent.
run:
    uv run devops-agent

# Run lint checks.
lint:
    uv run ruff check .
    npm run markdown:lint

# Format code and auto-fix simple issues.
format:
    uv run ruff check --fix .
    uv run ruff format .
    npm run markdown:format

# Run mypy.
typecheck:
    uv run mypy

# Run tests.
test:
    uv run pytest --subprocess-vcr=record

# Run git HTTP integration tests.
test-git-http:
    uv run pytest -m git_http_integration

# Run local CI checks.
check:
    uv run pre-commit run --all-files
    uv run mypy
    uv run pytest --subprocess-vcr=record

# Open an ipython shell with the dependency environment loaded.
shell:
    uv run ipython --ipython-dir=.ipython

# Run the CLI.
cli:
    uv run devops-agent --help

# Run Django management commands.
django-manage *args:
    uv run python apps/api/manage.py {{args}}

# Create or apply Django migrations.
django-makemigrations:
    uv run python apps/api/manage.py makemigrations

django-migrate:
    uv run python apps/api/manage.py migrate

# Run the Django API server.
django-runserver:
    uv run python apps/api/manage.py runserver

# Run the Celery worker for backend jobs.
celery-worker:
    uv run celery -A apps.api.project worker --loglevel=info

# Submit a conversation through the Django backend.
conversation-run prompt:
    uv run python apps/api/manage.py runconversation "{{prompt}}" --wait
