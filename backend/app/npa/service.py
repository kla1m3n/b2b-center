"""Версии базы НПА: создание, разбор, атомарная активация."""
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import NpaItem, NpaVersion, Okpd2Code
from app.npa.parser import NpaParseError, parse_npa


def create_version(session: Session, path: Path, title: str, source_url: str) -> NpaVersion:
    v = NpaVersion(title=title, source_url=source_url, file_path=str(path), status="parsing", warnings=[])
    session.add(v)
    session.commit()
    return v


def _unknown_codes(session: Session, codes: set[str]) -> list[str]:
    if session.scalar(select(Okpd2Code.code).limit(1)) is None:
        return []
    known = set(session.scalars(select(Okpd2Code.code).where(Okpd2Code.code.in_(codes))))
    return sorted(codes - known)


def process_version(session: Session, version_id: int) -> None:
    v = session.get(NpaVersion, version_id)
    try:
        doc = parse_npa(Path(v.file_path))
    except NpaParseError as e:
        v.status, v.error = "failed", str(e)
        session.commit()
        return
    except Exception as e:  # непредвиденная ошибка разбора не должна ломать активную версию
        v.status, v.error = "failed", f"Ошибка разбора файла: {e}"
        session.commit()
        return

    session.add_all(
        NpaItem(
            version_id=v.id, appendix=i.appendix, item_no=i.item_no, codes=i.codes, title=i.title,
            regime=i.regime.value, quota=i.quota, exclusions=i.exclusions, note=i.note,
            has_conditions=i.has_conditions,
        )
        for i in doc.items
    )
    unknown = _unknown_codes(session, {c for i in doc.items for c in i.codes})
    v.warnings = [f"Код {c} отсутствует в справочнике ОКПД2" for c in unknown]
    if doc.title and not v.title:
        v.title = doc.title
    if doc.source_url and not v.source_url:
        v.source_url = doc.source_url
    session.execute(update(NpaVersion).where(NpaVersion.id != v.id).values(is_active=False))
    v.is_active, v.status, v.error = True, "ready", None
    session.commit()


def get_active_version(session: Session) -> NpaVersion | None:
    return session.scalar(select(NpaVersion).where(NpaVersion.is_active.is_(True)))


def get_items(session: Session, version_id: int) -> list[NpaItem]:
    return list(session.scalars(select(NpaItem).where(NpaItem.version_id == version_id)))


def get_active_items(session: Session) -> list[NpaItem]:
    v = get_active_version(session)
    return get_items(session, v.id) if v else []
