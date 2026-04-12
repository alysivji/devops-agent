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

# Format code and auto-fix simple issues.
format:
    uv run ruff check --fix .
    uv run ruff format .

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

# Start local MinIO and create the sessions bucket.
local-s3-up:
    docker compose up -d minio
    docker compose run --rm minio-client

# Stop local MinIO without deleting stored session data.
local-s3-down:
    docker compose down

# Tail local MinIO logs.
local-s3-logs:
    docker compose logs -f minio
