## Microservicio FastAPI en Python 3.13 con despliegue en Cloud Run (GCP).

# Requisitos

* Python 3.13
* poetry 1.8.3
```bash
  pip install poetry==1.8.3
```

## Desarrollo

```bash
    poetry install
    poetry run uvicorn src.app:app --reload --port 8080
```

## Tests

Requerido si aún no has inicializado el pryecto.

```bash
    poetry lock --no-update
    poetry install
```
En caso contrario solo ejecuta

```bash
    poetry run pytest -q
```

Endpoints:
- GET /health
- GET /ready
- 
