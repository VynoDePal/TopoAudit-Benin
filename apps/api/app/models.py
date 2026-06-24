from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, event, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

try:
    from geoalchemy2 import Geometry, WKTElement
except ModuleNotFoundError:
    Geometry = None

    class WKTElement(str):
        def __new__(cls, data: str, srid: int = 4326) -> "WKTElement":
            element = str.__new__(cls, data)
            element.srid = srid
            return element

from app.workflow import ProjectWorkflowState


class Base(DeclarativeBase):
    pass


@event.listens_for(Base.metadata, "before_create")
def _create_postgis_extension(target: Any, connection: Any, **kw: Any) -> None:
    if connection.dialect.name == "postgresql":
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))


def _uuid() -> str:
    return str(uuid4())


def _geometry_column(geometry_type: str) -> Any:
    if Geometry is None:
        return Text
    return Geometry(geometry_type=geometry_type, srid=4326, spatial_index=True)


def geojson_point_to_wkt_element(point: dict[str, Any], srid: int = 4326) -> WKTElement:
    """Convert a GeoJSON Point to a PostGIS-ready WKT element."""
    if point.get("type") != "Point":
        raise ValueError("GeoJSON geometry must be a Point")

    coordinates = point.get("coordinates")
    if not isinstance(coordinates, (list, tuple)) or len(coordinates) < 2:
        raise ValueError("GeoJSON Point coordinates must contain longitude and latitude")

    longitude, latitude = coordinates[:2]
    return WKTElement(f"POINT({float(longitude)} {float(latitude)})", srid=srid)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str | None] = mapped_column(String(32), default=ProjectWorkflowState.UPLOADED.value)
    # Propriétaire (P1.1) ; nullable pour rétro-compat + mode démo (projets sans owner).
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    documents: Mapped[list["Document"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    levees: Mapped[list["Levee"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    parcels: Mapped[list["Parcel"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Levee(Base):
    __tablename__ = "levees"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str | None] = mapped_column(String(100))
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    detected_crs: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    project: Mapped[Project] = relationship(back_populates="levees")
    source_document: Mapped["Document"] = relationship(back_populates="levees")
    parcels: Mapped[list["Parcel"]] = relationship(back_populates="levee", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    project: Mapped[Project] = relationship(back_populates="documents")
    levees: Mapped[list[Levee]] = relationship(back_populates="source_document")


class Parcel(Base):
    __tablename__ = "parcels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    levee_id: Mapped[str | None] = mapped_column(ForeignKey("levees.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    declared_surface_m2: Mapped[int | None] = mapped_column(Integer)
    detected_crs: Mapped[str | None] = mapped_column(String(32))
    geom: Mapped[Any | None] = mapped_column(_geometry_column("POLYGON"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    project: Mapped[Project] = relationship(back_populates="parcels")
    levee: Mapped[Levee | None] = relationship(back_populates="parcels")
    points: Mapped[list["SurveyPoint"]] = relationship(back_populates="parcel", cascade="all, delete-orphan")


class SurveyPoint(Base):
    __tablename__ = "survey_points"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    parcel_id: Mapped[str] = mapped_column(ForeignKey("parcels.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    # Ordre du point dans le contour de la parcelle (0..n) : indispensable pour
    # reconstruire un polygone simple à l'audit (le tri par label est alphabétique).
    point_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_x: Mapped[float | None]
    source_y: Mapped[float | None]
    # Confiance OCR machine (None si non fournie — jamais 0 par défaut).
    confidence: Mapped[float | None] = mapped_column(Float)
    # Validation HUMAINE de la borne — indicateur SÉPARÉ de la confiance OCR ; n'est
    # jamais utilisé comme confiance ni pour calculer extraction_score.
    human_validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # Nullable : un point dont le CRS n'est PAS géoréférencé (LOCAL_ONLY/UNKNOWN/
    # NEEDS_GEOREFERENCING) n'a pas de géométrie WGS84 — on conserve source_x/source_y.
    geom: Mapped[Any | None] = mapped_column(_geometry_column("POINT"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    parcel: Mapped[Parcel] = relationship(back_populates="points")

    @classmethod
    def from_geojson(cls, *, label: str, point: dict[str, Any], **kwargs: Any) -> "SurveyPoint":
        return cls(label=label, geom=geojson_point_to_wkt_element(point), **kwargs)


@event.listens_for(SurveyPoint.geom, "set", retval=True)
def _coerce_survey_point_geom(target: SurveyPoint, value: Any, oldvalue: Any, initiator: Any) -> Any:
    if isinstance(value, dict):
        return geojson_point_to_wkt_element(value)
    return value

