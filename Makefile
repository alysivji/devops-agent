#########
# General
#########
help: ## this help
	@echo "Makefile for managing application:\n"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

#########
# General
#########
install: ## install requirements
	uv sync --all-groups

install-pre-commit: ## install the git pre-commit hook
	uv run pre-commit install

run: ## run the agent
	uv run python -m agent.main

lint: ## run lint checks
	uv run ruff check .

format: ## format code and auto-fix simple issues
	uv run ruff check --fix .
	uv run ruff format .

typecheck: ## run mypy
	uv run mypy

test: ## run tests
	uv run pytest --subprocess-vcr=record

check: ## run local CI checks
	uv run pre-commit run --all-files
	uv run mypy
	uv run pytest --subprocess-vcr=record
