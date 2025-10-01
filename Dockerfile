FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 
    PYTHONUNBUFFERED=1 
    PIP_NO_CACHE_DIR=1 
    POETRY_VERSION=1.8.3 
    PATH="/root/.local/bin:$PATH"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends 
    build-essential 
    curl 
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip 
    && pip install "poetry==$POETRY_VERSION"

COPY pyproject.toml poetry.lock* ./
RUN poetry install --no-root --without dev

COPY ./src ./src

ENV PORT=8080
EXPOSE 8080

CMD ["poetry", "run", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
