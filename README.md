## Microservicio FastAPI en Python 3.13 con despliegue en Cloud Run (GCP).

# Requisitos

* Python 3.13
* poetry 1.8.3

## Desarrollo
```bash
    pip install poetry==1.8.3
    poetry install
    poetry run uvicorn src.app:app --reload --port 8080
```

## Tests
```bash
    poetry run pytest -q
```

Endpoints:
- GET /health
- GET /ready