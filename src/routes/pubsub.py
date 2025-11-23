import logging
import json
import base64
from uuid import UUID

from fastapi import APIRouter, Request, Response
from src.config import settings
from src.infrastructure.infrastructure import session_for_schema
from src.services import inventario_service as svc

log = logging.getLogger(__name__)
router = APIRouter(prefix="/pubsub", tags=["pubSub"])

@router.post("", status_code=204)
async def handle_pubsub_push(request: Request):
    """
    Endpoint receptor de Pub/Sub (Push).

    Envelope estándar:
    {
      "message": {
        "data": "<base64(JSON)>",
        "attributes": {},
        "messageId": "...",
        "publishTime": "..."
      },
      "subscription": "projects/.../subscriptions/..."
    }

    JSON del evento para este ms:
    {
      "event": "creacion_masiva_producto",
      "csv_base64": "<base64 del csv>",
      "proveedor_id": "...",
      "filename": "...",
      "ctx": {
        "country": "co",
        "trace_id": "..."
      }
    }
    """
    trace_id: str | None = None
    log_prefix = "[PUBSUB]"  # se actualizará cuando tengamos trace_id/messageId

    try:
        envelope = await request.json()
    except Exception as e:
        log.error("%s Envelope inválido: %s", log_prefix, e)
        return Response(status_code=204)

    message = envelope.get("message")
    if not message:
        log.warning("%s Envelope sin 'message': %s", log_prefix, envelope)
        return Response(status_code=204)

    message_id = message.get("messageId")
    publish_time = message.get("publishTime")

    # ---------------------------
    # 1. Decodificar data base64
    # ---------------------------
    data_b64 = message.get("data")
    if not data_b64:
        log.warning("%s message.data faltante. message_id=%s", log_prefix, message_id)
        return Response(status_code=204)

    try:
        raw = base64.b64decode(data_b64).decode("utf-8")
        event = json.loads(raw)
    except Exception as e:
        log.error("%s Error decodificando data. message_id=%s error=%s",
                  log_prefix, message_id, e)
        return Response(status_code=204)

    ctx_dict = event.get("ctx") or {}
    event_type = event.get("event")

    # trace_id: ctx.trace_id > event.trace_id > messageId
    trace_id = ctx_dict.get("trace_id") or event.get("trace_id") or message_id
    log_prefix = f"[PUBSUB][{trace_id}]" if trace_id else "[PUBSUB]"

    if not event_type:
        log.warning("%s Evento sin 'event': %s", log_prefix, event)
        return Response(status_code=204)

    country = (
        ctx_dict.get("country")
        or event.get("country")
        or settings.DEFAULT_SCHEMA
    )

    log.info(
        "%s Mensaje recibido: event=%s country=%s message_id=%s publishTime=%s",
        log_prefix,
        event_type,
        country,
        message_id,
        publish_time,
    )

    # ===========================
    # 2. Dispatch por tipo evento
    # ===========================
    try:
        if event_type == "creacion_masiva_producto":
            csv_b64 = event.get("csv_base64")
            proveedor_id_str = event.get("proveedor_id")
            filename = event.get("filename")

            if not csv_b64 or not proveedor_id_str:
                log.warning(
                    "%s Evento creacion_masiva_producto inválido: csv_base64/proveedor_id faltantes. event=%s",
                    log_prefix,
                    event,
                )
                return Response(status_code=204)

            try:
                csv_bytes = base64.b64decode(csv_b64)
            except Exception as e:
                log.warning("%s csv_base64 inválido: %s", log_prefix, e)
                return Response(status_code=204)

            try:
                proveedor_id = UUID(proveedor_id_str)
            except Exception:
                log.warning("%s proveedor_id inválido: %s", log_prefix, proveedor_id_str)
                return Response(status_code=204)

            log.info(
                "%s Inicio procesamiento CSV productos: proveedor_id=%s country=%s filename=%s tamaño=%d bytes",
                log_prefix,
                proveedor_id,
                country,
                filename,
                len(csv_bytes),
            )

            # Sesión por schema y llamada a servicio de dominio
            with session_for_schema(country) as session:
                result = svc.procesar_csv_productos(
                    session=session,
                    country=country,
                    proveedor_id=proveedor_id,
                    csv_bytes=csv_bytes,
                    trace_id=trace_id,  # <- nuevo parámetro opcional
                )

            total = result.get("total", 0)
            insertados = result.get("insertados", 0)
            errores = result.get("errores") or []

            log.info(
                "%s Procesamiento CSV finalizado: total=%d insertados=%d errores=%d",
                log_prefix,
                total,
                insertados,
                len(errores),
            )

            if errores:
                # No rompemos el flujo, pero dejamos evidencia de líneas fallidas
                log.warning(
                    "%s Errores encontrados en procesamiento CSV: %s",
                    log_prefix,
                    errores,
                )

        else:
            log.info("%s Evento no manejado: %s", log_prefix, event_type)

    except ValueError as e:
        # Error de negocio → NO reintentar
        log.warning("%s Error de negocio en %s: %s", log_prefix, event_type, e)

    except Exception as e:
        # Error inesperado → igual devolvemos 204 para evitar loops infinitos
        log.error("%s Error procesando %s: %s", log_prefix, event_type, e)

    log.debug("%s Handler /pubsub completado", log_prefix)
    return Response(status_code=204)