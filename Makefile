.PHONY: up down logs build test lint fmt

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

build:
	docker compose build

test:
	pytest -q

lint:
	ruff check .

fmt:
	ruff format .
