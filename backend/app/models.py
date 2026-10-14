from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.config import get_settings
from app.db import Base


class Okpd2Code(Base):
    __tablename__ = "okpd2_code"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    parent_code: Mapped[str | None] = mapped_column(String(16))
    is_leaf: Mapped[bool] = mapped_column(Boolean, default=False)


class Okpd2Text(Base):
    __tablename__ = "okpd2_text"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(ForeignKey("okpd2_code.code"), index=True)
    text: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16))  # official | synonym
    embedding: Mapped[list[float]] = mapped_column(Vector(get_settings().embed_dim))


class NpaVersion(Base):
    __tablename__ = "npa_version"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[str] = mapped_column(Text, default="")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="parsing")  # parsing | ready | failed
    error: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)


class NpaItem(Base):
    __tablename__ = "npa_item"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("npa_version.id", ondelete="CASCADE"), index=True)
    appendix: Mapped[int] = mapped_column(Integer)
    item_no: Mapped[str] = mapped_column(String(16))
    codes: Mapped[list[str]] = mapped_column(ARRAY(String(16)))
    title: Mapped[str] = mapped_column(Text)
    regime: Mapped[str] = mapped_column(String(16))
    quota: Mapped[int | None] = mapped_column(Integer)
    exclusions: Mapped[list[str]] = mapped_column(ARRAY(String(16)), default=list)
    note: Mapped[str] = mapped_column(Text, default="")
    has_conditions: Mapped[bool] = mapped_column(Boolean, default=False)


class ClassificationCache(Base):
    __tablename__ = "classification_cache"
    norm_name: Mapped[str] = mapped_column(Text, primary_key=True)
    npa_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    result: Mapped[dict] = mapped_column(JSONB)


class Job(Base):
    __tablename__ = "job"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued | running | done | failed
    total: Mapped[int] = mapped_column(Integer)
    done: Mapped[int] = mapped_column(Integer, default=0)
    npa_version_id: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobItem(Base):
    __tablename__ = "job_item"
    job_id: Mapped[str] = mapped_column(ForeignKey("job.id", ondelete="CASCADE"), primary_key=True)
    idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    input: Mapped[str] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSONB)
