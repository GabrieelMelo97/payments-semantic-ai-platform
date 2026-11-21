FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN pip install --upgrade pip uv

COPY pyproject.toml README.md ./
COPY src ./src
COPY contracts ./contracts
COPY dbt_project ./dbt_project

RUN uv pip install --system ".[gcp]"

EXPOSE 8080

CMD ["uvicorn", "payments_platform.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
