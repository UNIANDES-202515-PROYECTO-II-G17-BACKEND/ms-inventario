from __future__ import annotations
from typing import Optional, List, Tuple
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from src.domain.models import (
    Producto, Lote, Inventario, Ubicacion, Bodega, CertificacionSanitaria,
    CertificacionTipoEnum, InventarioEstadoEnum
)
from typing import List, Dict, Any, Optional
import csv
import io
import codecs
from uuid import UUID
from fastapi import HTTPException
from src.domain.schemas import (ProductoCreate, AsociacionProveedor)
import logging
from src.config import settings
from src.infrastructure.http import MsClient

log = logging.getLogger(__name__)

# ---------- Producto ----------
def crear_producto(session: Session, *, sku: str, nombre: str,
                   categoria: Optional[str], temp_min: Optional[float],
                   temp_max: Optional[float], controlado: bool) -> Producto:
    p = Producto(
        sku=sku,
        nombre=nombre,
        categoria=categoria,
        temp_min=temp_min,
        temp_max=temp_max,
        controlado=controlado,
    )
    session.add(p)
    try:
        session.commit()
    except IntegrityError as e:
        session.rollback()
        # sku es único
        raise ValueError("SKU ya existe") from e
    session.refresh(p)
    return p

def asociar_certificacion(session: Session, *, producto_id: str, autoridad: str,
                          tipo: CertificacionTipoEnum, vigencia) -> CertificacionSanitaria:
    prod = session.get(Producto, producto_id)
    if not prod:
        raise ValueError("Producto no existe")
    cert = CertificacionSanitaria(autoridad=autoridad, tipo=tipo, vigencia=vigencia)
    prod.certificaciones.append(cert)
    session.commit()
    session.refresh(cert)
    return cert

# ---------- Bodega / Ubicación ----------
def crear_bodega(session: Session, *, direccion: str, ciudad: str, pais) -> Bodega:
    b = Bodega(direccion=direccion, ciudad=ciudad, pais=pais)
    session.add(b)
    try:
        session.commit()
    except IntegrityError as e:
        session.rollback()
        raise ValueError("La bodega ya existe") from e
    session.refresh(b)
    return b

def crear_ubicacion(session: Session, *, bodega_id: str, pasillo: str, estante: str, posicion: str) -> Ubicacion:
    u = Ubicacion(bodega_id=bodega_id, pasillo=pasillo, estante=estante, posicion=posicion)
    session.add(u)
    try:
        session.commit()
    except IntegrityError as e:
        session.rollback()
        # uq_ubicacion_slot: (bodega_id, pasillo, estante, posicion)
        raise ValueError("La ubicación ya existe en la bodega (pasillo/estante/posición)") from e
    session.refresh(u)
    return u

# ---------- Lote ----------
def crear_lote(session: Session, *, producto_id: str, codigo: str, vencimiento) -> Lote:
    prod = session.get(Producto, producto_id)
    if not prod:
        raise ValueError("Producto no existe")
    l = Lote(producto_id=producto_id, codigo=codigo, vencimiento=vencimiento)
    session.add(l)
    try:
        session.commit()
    except IntegrityError as e:
        session.rollback()
        # uq_lote_codigo_por_producto: (producto_id, codigo)
        raise ValueError("El código de lote ya existe para este producto") from e
    session.refresh(l)
    return l

# ---------- Inventario ----------
def recibir_entrada(session: Session, *, lote_id: str, ubicacion_id: str, cantidad: int,
                    estado: InventarioEstadoEnum = InventarioEstadoEnum.DISPONIBLE) -> Inventario:
    if cantidad <= 0:
        raise ValueError("Cantidad debe ser positiva")
    
    lote = session.get(Lote, lote_id)
    if not lote:
        raise ValueError("Lote no existe")

    ubicacion = session.get(Ubicacion, ubicacion_id)
    if not ubicacion:
        raise ValueError("Ubicación no existe")

    inv = session.scalar(select(Inventario).where(
        Inventario.lote_id == lote_id,
        Inventario.ubicacion_id == ubicacion_id,
        Inventario.estado == estado
    ))
    if inv:
        inv.cantidad += cantidad
    else:
        inv = Inventario(lote_id=lote_id, ubicacion_id=ubicacion_id,
                         cantidad=cantidad, estado=estado)
        session.add(inv)
    session.commit()
    session.refresh(inv)
    return inv

def salida_por_fefo(session: Session, *, producto_id: str, cantidad: int,
                    ubicacion_id: Optional[str] = None) -> List[Tuple[Inventario, int]]:
    if cantidad <= 0:
        raise ValueError("Cantidad debe ser positiva")

    q = (select(Inventario)
         .join(Inventario.lote)
         .where(Lote.producto_id == producto_id,
                Inventario.estado == InventarioEstadoEnum.DISPONIBLE))
    if ubicacion_id:
        q = q.where(Inventario.ubicacion_id == ubicacion_id)
    q = q.order_by(Lote.vencimiento.is_(None), Lote.vencimiento.asc(), Inventario.fecha_ingreso.asc())

    registros = list(session.scalars(q))
    restante = cantidad
    consumos: List[Tuple[Inventario,int]] = []

    for inv in registros:
        if restante == 0:
            break
        toma = min(inv.cantidad, restante)
        if toma <= 0:
            continue
        if inv.cantidad < toma:
            raise ValueError("Stock insuficiente en registro")
        inv.cantidad -= toma
        consumos.append((inv, toma))
        restante -= toma

    if restante > 0:
        raise ValueError("Stock insuficiente total")

    for inv, _ in consumos:
        if inv.cantidad == 0:
            session.delete(inv)
    session.commit()
    return consumos

def stock_por_producto(session: Session, producto_id: str) -> int:
    total = session.scalar(
        select(func.coalesce(func.sum(Inventario.cantidad), 0))
        .join(Inventario.lote)
        .where(Lote.producto_id == producto_id,
               Inventario.estado == InventarioEstadoEnum.DISPONIBLE)
    )
    return total or 0

def stock_detallado(session: Session, producto_id: str):
    q = (select(Lote.codigo, Lote.vencimiento, Ubicacion.id.label("ubicacion_id"),
                func.sum(Inventario.cantidad).label("cantidad"))
         .join(Inventario.lote)
         .join(Inventario.ubicacion)
         .where(Lote.producto_id == producto_id)
         .group_by(Lote.codigo, Lote.vencimiento, Ubicacion.id)
         .order_by(Lote.vencimiento))
    rows = session.execute(q)
    return [dict(r._mapping) for r in rows.all()]



def producto_detalle(session: Session, producto_id: UUID) -> dict:
    """Devuelve dict con detalle del producto, certificaciones, stock total y lotes (cantidades)."""
    prod = session.get(Producto, producto_id)
    if not prod:
        raise ValueError("Producto no encontrado")

    # Certificaciones
    certs = [
        {
            "id": c.id,
            "autoridad": c.autoridad,
            "tipo": c.tipo.value if hasattr(c.tipo, "value") else str(c.tipo),
            "vigencia": c.vigencia,
        }
        for c in (prod.certificaciones or [])
    ]

    # Stock total
    stock_total = session.scalar(
        select(func.coalesce(func.sum(Inventario.cantidad), 0))
        .join(Inventario.lote)
        .where(Lote.producto_id == producto_id)
    ) or 0

    # Lotes con cantidad (orden por vencimiento ASC NULLS LAST)
    lotes_rows = session.execute(
        select(
            Lote.id, Lote.codigo, Lote.vencimiento,
            func.coalesce(func.sum(Inventario.cantidad), 0).label("cantidad_total")
        )
        .join(Inventario, Inventario.lote_id == Lote.id, isouter=True)
        .where(Lote.producto_id == producto_id)
        .group_by(Lote.id, Lote.codigo, Lote.vencimiento)
        .order_by(Lote.vencimiento.asc().nulls_last())
    ).all()

    lotes = [
        {
            "id": r.id,
            "codigo": r.codigo,
            "vencimiento": r.vencimiento,
            "cantidad_total": int(r.cantidad_total or 0),
        }
        for r in lotes_rows
    ]

    return {
        "id": prod.id,
        "sku": prod.sku,
        "nombre": prod.nombre,
        "categoria": prod.categoria,
        "controlado": prod.controlado,
        "stock_total": int(stock_total),
        "certificaciones": certs,
        "lotes": lotes,
    }

def ubicaciones_con_stock_por_producto(session: Session, producto_id: UUID) -> List[dict]:
    """
    Lista de ubicaciones con cantidad disponible (>0) para el producto.
    Ordena ubicaciones por ciudad (A-Z), y luego pasillo/estante/posicion.
    """
    rows = session.execute(
        select(
            Ubicacion.id.label("ubicacion_id"),
            Bodega.id.label("bodega_id"),
            Bodega.ciudad,
            Ubicacion.pasillo,
            Ubicacion.estante,
            Ubicacion.posicion,
            func.sum(Inventario.cantidad).label("cantidad")
        )
        .join(Bodega, Bodega.id == Ubicacion.bodega_id)
        .join(Inventario, Inventario.ubicacion_id == Ubicacion.id)
        .join(Lote, Lote.id == Inventario.lote_id)
        .where(Lote.producto_id == producto_id)
        .group_by(Ubicacion.id, Bodega.id, Bodega.ciudad, Ubicacion.pasillo, Ubicacion.estante, Ubicacion.posicion)
        .having(func.sum(Inventario.cantidad) > 0)
        .order_by(Bodega.ciudad.asc(), Ubicacion.pasillo.asc(), Ubicacion.estante.asc(), Ubicacion.posicion.asc())
    ).all()

    return [
        {
            "ubicacion_id": r.ubicacion_id,
            "bodega_id": r.bodega_id,
            "ciudad": r.ciudad,
            "pasillo": r.pasillo,
            "estante": r.estante,
            "posicion": r.posicion,
            "cantidad": int(r.cantidad or 0)
        }
        for r in rows
    ]

def list_productos(
    session: Session,
    ids: Optional[List[UUID]] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> List[Producto]:
    stmt = select(Producto).order_by(Producto.nombre.asc())
    if ids:
        stmt = stmt.where(Producto.id.in_(ids))
    if offset:
        stmt = stmt.offset(offset)
    if limit:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))


REQUIRED_HEADERS = {"sku", "nombre", "categoria", "temp_min", "temp_max", "controlado", "precio", "moneda", "lead_time_dias", "lote_minimo", "activo"}

def _to_bool(v: str) -> bool:
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in {"true", "1", "si", "sí", "y", "yes", "t"}

def _to_float(v: str) -> float:
    if v is None or str(v).strip() == "":
        return None
    # admite coma decimal
    s = str(v).strip().replace(",", ".")
    return float(s)

def _validate_headers(reader: csv.DictReader):
    headers = {h.strip().lower() for h in (reader.fieldnames or [])}
    missing = REQUIRED_HEADERS - headers
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Faltan columnas en el CSV: {', '.join(sorted(missing))}. "
                   f"Cabeceras requeridas: {', '.join(sorted(REQUIRED_HEADERS))}"
        )

def _iter_dict_reader(stream: io.TextIOBase) -> csv.DictReader:
    # Detecta delimitador ; o , automáticamente
    sample = stream.read(4096)
    stream.seek(0)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(stream, dialect=dialect)
    if reader.fieldnames:
        reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]
    return reader

def _row_to_payload(row: Dict[str, Any]) -> ProductoCreate:
    try:
        return ProductoCreate(
            sku=str(row.get("sku", "")).strip(),
            nombre=str(row.get("nombre", "")).strip(),
            categoria=str(row.get("categoria", "")).strip(),
            temp_min=_to_float(row.get("temp_min")),
            temp_max=_to_float(row.get("temp_max")),
            controlado=_to_bool(row.get("controlado")),
        )
    except Exception as e:
        raise ValueError(f"Error convirtiendo tipos: {e}")

def _row_to_payload_asociar_proveedor_producto(sku_proveedor: str, producto_id: UUID, row: Dict[str, Any]) -> AsociacionProveedor:
    try:
        return AsociacionProveedor(
            producto_id=producto_id,
            sku_proveedor=sku_proveedor,
            precio=_to_float(row.get("precio", "")),
            moneda=str(row.get("moneda", "")).strip(),
            lead_time_dias=_to_float(row.get("lead_time_dias", "")),
            lote_minimo=_to_float(row.get("lote_minimo", "")),
            activo=_to_bool(row.get("activo")),
        )
    except Exception as e:
        raise ValueError(f"Error convirtiendo tipos: {e}")



def _process_rows(reader: csv.DictReader, session: Session, proveedor_uuid: UUID, x_country: str):
    inserted = 0
    errors: List[Dict[str, Any]] = []
    client = MsClient(x_country)

    for idx, row in enumerate(reader, start=2):
        try:
            payload = _row_to_payload(row)
            if not payload.sku or not payload.nombre or not payload.categoria:
                raise ValueError("sku, nombre y categoria son obligatorios")


            newProduct = crear_producto(
                session,
                sku=payload.sku,
                nombre=payload.nombre,
                categoria=payload.categoria,
                temp_min=payload.temp_min,
                temp_max=payload.temp_max,
                controlado=payload.controlado,
            )

            proveedor_id = proveedor_uuid
            sku_proveedor = "SKU-AND-1234"
            payloadAsociar = _row_to_payload_asociar_proveedor_producto(sku_proveedor,  newProduct.id, row)
            #Enviamos la asociacion proveedor producto
            payloadEnv = {
                    "producto_id": str(payloadAsociar.producto_id),
                    "sku_proveedor": sku_proveedor,
                    "precio": payloadAsociar.precio,
                    "moneda": payloadAsociar.moneda,
                    "lead_time_dias": payloadAsociar.lead_time_dias,
                    "lote_minimo": payloadAsociar.lote_minimo,
                    "activo": payloadAsociar.activo,
            }
            try:
                vincular = client.post(f"/v1/proveedores/{proveedor_id}/productos", json=payloadEnv)
            except Exception as e:
                log.info(f"Error creando relacion proveedor/producto: {e}")



            inserted += 1

        except ValueError as e:
            errors.append({
                "linea": idx,
                "sku": (row.get("sku") or "").strip(),
                "error": str(e)
            })
        except Exception as e:
            errors.append({
                "linea": idx,
                "sku": (row.get("sku") or "").strip(),
                "error": f"Excepción inesperada: {e}"
            })

    return inserted, errors
