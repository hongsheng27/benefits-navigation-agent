.DEFAULT_GOAL := help
.PHONY: help install format check check-frontend check-backend backend frontend

help:
	@echo "make install    安裝前後端相依套件"
	@echo "make backend    清埠後啟動後端（避免殭屍 uvicorn；預設 :8000）"
	@echo "make frontend   清埠後啟動前端（預設 :5173）"
	@echo "make format     格式化前後端所有檔案"
	@echo "make check      跑完前後端所有檢查（提交前執行）"

install:
	cd frontend && npm install
	cd backend && uv sync

# Always free the port first. Do not start a second raw `uvicorn` / `npm run dev`.
backend:
	python scripts/dev_backend.py

frontend:
	python scripts/dev_frontend.py

format:
	cd frontend && npm run format
	cd backend && uv run ruff format .

check: check-frontend check-backend

check-frontend:
	cd frontend && npm run format:check
	cd frontend && npm run lint
	cd frontend && npm run typecheck
	cd frontend && npm test

check-backend:
	cd backend && uv run ruff format --check .
	cd backend && uv run ruff check .
	cd backend && uv run pytest
