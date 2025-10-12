from __future__ import annotations
import uuid
from datetime import datetime, date
from enum import Enum
from typing import Optional, List


from sqlalchemy import (
    CheckConstraint, Column, Date, DateTime, Enum as SAEnum, ForeignKey,
    Index, Integer, String, Boolean, UniqueConstraint, Table, Float
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, NUMRANGE


class Base(DeclarativeBase):
    pass

# ---------- Enums ----------
class PaisEnum(str, Enum):
    CO = "co"
    EC = "ec"
    MX = "mx"
    PE = "pe"

class CertificacionTipoEnum(str, Enum):
    INVIMA = "INVIMA"
    FDA = "FDA"
    EMA = "EMA"
    LOCAL = "LOCAL"

class InventarioEstadoEnum(str, Enum):
    DISPONIBLE = "DISPONIBLE"
    BLOQUEADO = "BLOQUEADO"
    VENCIDO = "VENCIDO"
    DANIADO = "DANIADO"

# ---------- Tabla de asociación N-M ----------
producto_certificacion = Table(
    "producto_certificacion",
    Base.metadata,
    Column("producto_id", UUID(as_uuid=True), ForeignKey("producto.id", ondelete="CASCADE"), primary_key=True),
    Column("certificacion_id", UUID(as_uuid=True), ForeignKey("certificacion_sanitaria.id", ondelete="CASCADE"), primary_key=True),
    UniqueConstraint("producto_id", "certificacion_id", name="uq_prod_cert"),
)

# ---------- Entidades principales ----------
class Bodega(Base):
    __tablename__ = "bodega"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    direccion: Mapped[str] = mapped_column(String(200), nullable=False)
    ciudad: Mapped[str] = mapped_column(String(80), nullable=False)
    pais: Mapped[PaisEnum] = mapped_column(SAEnum(PaisEnum, name="pais_enum"), nullable=False)

    ubicaciones: Mapped[List[Ubicacion]] = relationship("Ubicacion", back_populates="bodega", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("pais", "ciudad", "direccion", name="uq_bodega_direccion"),
        Index("ix_bodega_ciudad", "ciudad"),
    )


class Ubicacion(Base):
    __tablename__ = "ubicacion"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bodega_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bodega.id", ondelete="CASCADE"), nullable=False)
    pasillo: Mapped[str] = mapped_column(String(30), nullable=False)
    estante: Mapped[str] = mapped_column(String(30), nullable=False)
    posicion: Mapped[str] = mapped_column(String(30), nullable=False)

    bodega: Mapped[Bodega] = relationship("Bodega", back_populates="ubicaciones")
    inventarios: Mapped[List[Inventario]] = relationship("Inventario", back_populates="ubicacion")

    __table_args__ = (
        UniqueConstraint("bodega_id", "pasillo", "estante", "posicion", name="uq_ubicacion_slot"),
        Index("ix_ubicacion_bodega", "bodega_id"),
    )


class Producto(Base):
    __tablename__ = "producto"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    categoria: Mapped[Optional[str]] = mapped_column(String(80))
    temp_min: Mapped[Optional[float]] = mapped_column(Float)
    temp_max: Mapped[Optional[float]] = mapped_column(Float)
    controlado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    certificaciones: Mapped[List[CertificacionSanitaria]] = relationship(
        "CertificacionSanitaria", secondary=producto_certificacion, back_populates="productos"
    )
    lotes: Mapped[List[Lote]] = relationship("Lote", back_populates="producto", cascade="all, delete-orphan")


class CertificacionSanitaria(Base):
    __tablename__ = "certificacion_sanitaria"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    autoridad: Mapped[str] = mapped_column(String(120), nullable=False)
    tipo: Mapped[CertificacionTipoEnum] = mapped_column(SAEnum(CertificacionTipoEnum, name="certificacion_tipo_enum"), nullable=False)
    vigencia: Mapped[date] = mapped_column(Date, nullable=False)

    productos: Mapped[List[Producto]] = relationship("Producto", secondary=producto_certificacion, back_populates="certificaciones")

    __table_args__ = (Index("ix_certificacion_vigencia", "vigencia"),)


class Lote(Base):
    __tablename__ = "lote"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    producto_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("producto.id", ondelete="RESTRICT"), nullable=False)
    codigo: Mapped[str] = mapped_column(String(80), nullable=False)
    vencimiento: Mapped[Optional[date]] = mapped_column(Date)

    producto: Mapped[Producto] = relationship("Producto", back_populates="lotes")
    inventarios: Mapped[List[Inventario]] = relationship("Inventario", back_populates="lote")

    __table_args__ = (
        UniqueConstraint("producto_id", "codigo", name="uq_lote_codigo_por_producto"),
        Index("ix_lote_vencimiento", "vencimiento"),
    )


class Inventario(Base):
    __tablename__ = "inventario"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lote_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lote.id", ondelete="RESTRICT"), nullable=False)
    ubicacion_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ubicacion.id", ondelete="RESTRICT"), nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fecha_ingreso: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    estado: Mapped[InventarioEstadoEnum] = mapped_column(SAEnum(InventarioEstadoEnum, name="inventario_estado_enum"), default=InventarioEstadoEnum.DISPONIBLE, nullable=False)

    lote: Mapped[Lote] = relationship("Lote", back_populates="inventarios")
    ubicacion: Mapped[Ubicacion] = relationship("Ubicacion", back_populates="inventarios")

    __table_args__ = (
        CheckConstraint("cantidad >= 0", name="ck_inventario_cantidad_no_negativa"),
        Index("ix_inventario_ubicacion", "ubicacion_id"),
    )