# ms-api-gateway

Microservicio FastAPI en Python 3.13 con despliegue en Cloud Run (GCP).

## Desarrollo
`ash
poetry install
cp .env.example .env
poetry run uvicorn app:app --reload --port 8080
`

## Tests
`ash
poetry run pytest -q
`

Endpoints:
- GET /health
- GET /ready
