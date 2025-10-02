FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=1.8.3 POETRY_VIRTUALENVS_CREATE=true POETRY_VIRTUALENVS_IN_PROJECT=true \
    PATH="/root/.local/bin:$PATH"

WORKDIR /app

RUN pip install --upgrade pip && pip install "poetry==${POETRY_VERSION}"

COPY scripts/sanitize_pyproject.py ./scripts/
COPY pyproject.toml poetry.lock* ./

RUN python ./scripts/sanitize_pyproject.py \
 && poetry check

RUN poetry install --no-root --without dev

COPY ./src ./src

ENV PORT=8080
EXPOSE 8080

CMD ["poetry","run","uvicorn","src.app:app","--host","0.0.0.0","--port","8080","--proxy-headers","--forwarded-allow-ips","*"]
