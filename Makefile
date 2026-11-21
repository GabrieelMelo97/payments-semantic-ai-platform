.PHONY: setup data ingest dbt run test lint infra-validate api ui clean

PYTHON ?= uv run python
DBT ?= uv run dbt

setup:
	uv sync --extra dev

data:
	$(PYTHON) -m payments_platform.cli generate

ingest:
	$(PYTHON) -m payments_platform.cli ingest

dbt:
	$(DBT) build --project-dir dbt_project --profiles-dir dbt_project --target local

run: data ingest dbt
	$(PYTHON) -m payments_platform.cli report

test:
	uv run pytest

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests
	uv run sqlfluff lint dbt_project/models --dialect duckdb

infra-validate:
	terraform fmt -check -recursive infra/terraform
	terraform -chdir=infra/terraform/environments/dev init -backend=false
	terraform -chdir=infra/terraform/environments/dev validate

api:
	uv run uvicorn payments_platform.api.main:app --host 0.0.0.0 --port 8000 --reload

ui:
	uv run streamlit run src/payments_platform/app/streamlit_app.py

clean:
	rm -rf data dbt_project/target dbt_project/logs .pytest_cache .ruff_cache
