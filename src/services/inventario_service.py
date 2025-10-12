from __future__ import annotations
from typing import Optional, List, Tuple
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from src.domain.models import (
    Producto, Lote, Inventario, Ubicacion, Bodega, CertificacionSanitaria,
    CertificacionTipoEnum, InventarioEstadoEnum
)

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