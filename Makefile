.PHONY: setup seed dev test eval demo-reset

setup:
	cd backend && uv sync

seed:
	cd backend && uv run python scripts/01_create_indexes.py
	cd backend && uv run python scripts/02_seed.py

dev:
	cd backend && uv run uvicorn app.main:app --reload --host $${API_HOST:-0.0.0.0} --port $${API_PORT:-8000}

test:
	cd backend && uv run pytest

eval:
	cd backend && uv run python scripts/03_eval_retrieval.py

demo-reset:
	cd backend && uv run python scripts/02_seed.py --reset
