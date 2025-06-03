.PHONY: help install run dev test lint format clean docker-build docker-run docker-stop

# Default target
.DEFAULT_GOAL := help

# Variables
PYTHON := python3
PIP := $(PYTHON) -m pip
PROJECT_NAME := clore-bot-pro
DOCKER_IMAGE := $(PROJECT_NAME):latest

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

install: ## Install dependencies
	$(PIP) install -r requirements.txt

install-dev: ## Install development dependencies
	$(PIP) install -r requirements.txt
	$(PIP) install black flake8 pytest pytest-asyncio pytest-cov

run: ## Run the bot
	$(PYTHON) main.py

dev: ## Run in development mode with auto-reload
	export DEBUG=true && $(PYTHON) main.py

test: ## Run tests
	pytest tests/ -v --cov=. --cov-report=html

lint: ## Run linting
	flake8 . --max-line-length=120 --exclude=venv,__pycache__,.git
	black --check .

format: ## Format code with black
	black .

clean: ## Clean up cache and temporary files
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	rm -rf htmlcov/
	rm -rf .pytest_cache/

db-init: ## Initialize database
	$(PYTHON) -c "from database.session import init_db; import asyncio; asyncio.run(init_db())"

db-upgrade: ## Run database migrations
	alembic upgrade head

db-migrate: ## Create new migration
	alembic revision --autogenerate -m "$(message)"

docker-build: ## Build Docker image
	docker build -t $(DOCKER_IMAGE) .

docker-run: ## Run bot in Docker
	docker-compose up -d

docker-stop: ## Stop Docker containers
	docker-compose down

docker-logs: ## Show Docker logs
	docker-compose logs -f bot

docker-shell: ## Open shell in bot container
	docker-compose exec bot /bin/bash

backup: ## Backup database and logs
	mkdir -p backups
	tar -czf backups/backup-$(shell date +%Y%m%d-%H%M%S).tar.gz data/ logs/

env-check: ## Check if all required environment variables are set
	@echo "Checking environment variables..."
	@test -n "$$BOT_TOKEN" || (echo "ERROR: BOT_TOKEN not set" && exit 1)
	@test -n "$$OPENAI_API_KEY" || (echo "ERROR: OPENAI_API_KEY not set" && exit 1)
	@echo "All required environment variables are set!"