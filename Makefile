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
	uv sync

run: ## run the agent
	uv run python -m agent.main

test: ## run tests
	uv run pytest --subprocess-vcr=record
