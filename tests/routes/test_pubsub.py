# tests/test_pubsub.py
import base64
import json
from uuid import uuid4
import uuid
from unittest.mock import patch, MagicMock

def _mk_pubsub_envelope(event: dict) -> dict:
    data_json = json.dumps(event).encode("utf-8")
    data_b64 = base64.b64encode(data_json).decode("utf-8")
    return {
        "message": {
            "data": data_b64,
            "messageId": "1234567890",
            "publishTime": "2025-11-22T00:00:00Z",
        },
        "subscription": "projects/test/subscriptions/test-sub",
    }

@patch("src.routes.pubsub.svc.procesar_csv_productos")
@patch("src.routes.pubsub.session_for_schema")
def test_pubsub_creacion_masiva_producto_ok(mock_session_for_schema, mock_procesar, client):
    fake_session = MagicMock(name="session")
    mock_session_for_schema.return_value.__enter__.return_value = fake_session

    proveedor_id = str(uuid4())
    raw_csv = b"sku,nombre\nSKU-1,Prod 1\n"
    csv_b64 = base64.b64encode(raw_csv).decode("utf-8")

    event = {
        "event": "creacion_masiva_producto",
        "csv_base64": csv_b64,
        "proveedor_id": proveedor_id,
        "filename": "productos.csv",
        "ctx": {
            "country": "co",
            "trace_id": "trace-test",
        },
    }

    envelope = _mk_pubsub_envelope(event)

    resp = client.post("/pubsub", json=envelope)
    assert resp.status_code == 204

    mock_session_for_schema.assert_called_once_with("co")
    mock_procesar.assert_called_once()

    # 👇 Aquí cambiamos: ignoramos args y solo miramos kwargs
    _, kwargs = mock_procesar.call_args

    assert kwargs["session"] is fake_session
    assert kwargs["country"] == "co"
    assert str(kwargs["proveedor_id"]) == proveedor_id
    assert kwargs["csv_bytes"] == raw_csv
    # si agregaste trace_id como kwarg en el router:
    assert kwargs.get("trace_id") == "trace-test"

@patch("src.routes.pubsub.svc.procesar_csv_productos")
def test_pubsub_evento_sin_event_no_llama_servicio(mock_procesar, client):
    proveedor_id = str(uuid4())
    raw_csv = b"sku,nombre\nSKU-1,Prod 1\n"
    csv_b64 = base64.b64encode(raw_csv).decode("utf-8")

    # SIN "event"
    event = {
        "csv_base64": csv_b64,
        "proveedor_id": proveedor_id,
        "ctx": {"country": "co"},
    }
    envelope = _mk_pubsub_envelope(event)

    resp = client.post("/pubsub", json=envelope)
    assert resp.status_code == 204
    mock_procesar.assert_not_called()


@patch("src.routes.pubsub.svc.procesar_csv_productos")
def test_pubsub_evento_no_manejado_no_llama_servicio(mock_procesar, client):
    proveedor_id = str(uuid4())
    raw_csv = b"sku,nombre\nSKU-1,Prod 1\n"
    csv_b64 = base64.b64encode(raw_csv).decode("utf-8")

    event = {
        "event": "otro_evento",
        "csv_base64": csv_b64,
        "proveedor_id": proveedor_id,
        "ctx": {"country": "co"},
    }
    envelope = _mk_pubsub_envelope(event)

    resp = client.post("/pubsub", json=envelope)
    assert resp.status_code == 204
    mock_procesar.assert_not_called()


@patch("src.routes.pubsub.svc.procesar_csv_productos")
def test_pubsub_data_base64_invalida(mock_procesar, client):
    envelope = {
        "message": {
            "data": "NO-ES-BASE64!!!",
            "messageId": "x",
            "publishTime": "2025-11-22T00:00:00Z",
        }
    }

    resp = client.post("/pubsub", json=envelope)
    assert resp.status_code == 204
    mock_procesar.assert_not_called()