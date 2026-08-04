.PHONY: install dev test lint docker-up docker-down

install:
	python -m pip install -r requirements.txt

dev:
	uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

test:
	pytest

lint:
	ruff check .

docker-up:
	docker compose up --build

docker-down:
	docker compose down
