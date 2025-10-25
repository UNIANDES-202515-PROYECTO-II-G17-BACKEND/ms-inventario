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
- GET  /health
- GET  /ready
- POST /v1/inventario/producto
- POST /v1/inventario/productos/upload-csv
- POST /v1/inventario/producto/{{producto_id}}/certificacion
- POST /v1/inventario/bodega
- POST /v1/inventario/ubicacion
- POST /v1/inventario/lote
- POST /v1/inventario/entrada
- POST /v1/inventario/salida/fefo?producto_id={{producto_id}}&cantidad=10
- GET  /v1/inventario/stock/{{producto_id}}
- GET  /v1/inventario/stock/{{producto_id}}/detalle
- GET  /v1/inventario/producto/{{producto_id}}/detalle
- GET  /v1/inventario/producto/{{producto_id}}/ubicaciones
- GET  /v1/inventario/productos/todos?limit=100&offset=0