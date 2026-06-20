import hashlib
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.workflow import mark_project_uploaded

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "application/pdf": ".pdf",
}
CHUNK_SIZE = 1024 * 1024


class DocumentUploadResponse(BaseModel):
    id: str
    project_id: str
    filename: str
    content_type: str
    size_bytes: int = Field(ge=0)
    sha256: str
    storage_path: str


def _safe_project_segment(project_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", project_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid project id")
    return project_id


def _safe_filename(filename: str | None) -> str:
    name = Path(filename or "document").name.strip()
    return name or "document"


def _extension_for_upload(file: UploadFile) -> str:
    content_type = (file.content_type or "").lower()
    extension = ALLOWED_CONTENT_TYPES.get(content_type)
    if extension is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only JPG, PNG and PDF files are accepted",
        )
    return extension


def _content_matches_mime(content_type: str, first_chunk: bytes) -> bool:
    if content_type == "image/jpeg":
        return first_chunk.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return first_chunk.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "application/pdf":
        return first_chunk.startswith(b"%PDF-")
    return False



def _ensure_project_exists(project_id: str, db: Session) -> None:
    project = db.execute(text("SELECT id FROM projects WHERE id = :project_id"), {"project_id": project_id}).first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


def _store_upload(project_id: str, file: UploadFile) -> tuple[str, int, str]:
    project_segment = _safe_project_segment(project_id)
    extension = _extension_for_upload(file)
    content_type = (file.content_type or "").lower()
    storage_dir = Path(settings.local_storage_path) / project_segment
    storage_dir.mkdir(parents=True, exist_ok=True)

    document_id = str(uuid4())
    final_path = storage_dir / f"{document_id}{extension}"
    temporary_path = storage_dir / f".{document_id}.uploading"

    digest = hashlib.sha256()
    size = 0
    checked_signature = False

    try:
        with temporary_path.open("wb") as output:
            while True:
                chunk = file.file.read(CHUNK_SIZE)
                if not chunk:
                    break

                if not checked_signature:
                    checked_signature = True
                    if not _content_matches_mime(content_type, chunk):
                        raise HTTPException(
                            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail="File content does not match the declared MIME type",
                        )

                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    # 413 en littéral : la constante starlette a été renommée selon les
                    # versions (HTTP_413_CONTENT_TOO_LARGE vs _REQUEST_ENTITY_TOO_LARGE) —
                    # l'entier est insensible à la version installée.
                    raise HTTPException(
                        status_code=413,
                        detail="File exceeds the 25 MB limit",
                    )

                digest.update(chunk)
                output.write(chunk)

        if not checked_signature:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")

        shutil.move(str(temporary_path), final_path)
        return str(final_path), size, digest.hexdigest()
    except Exception:
        temporary_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise


def create_document_from_upload(project_id: str, file: UploadFile, db: Session) -> DocumentUploadResponse:
    _ensure_project_exists(project_id, db)
    filename = _safe_filename(file.filename)
    content_type = (file.content_type or "").lower()
    storage_path, size, sha256 = _store_upload(project_id, file)
    document_id = Path(storage_path).stem

    try:
        db.execute(
            text(
                """
                INSERT INTO documents (id, project_id, filename, content_type, size_bytes, sha256, storage_path, created_at)
                VALUES (:id, :project_id, :filename, :content_type, :size_bytes, :sha256, :storage_path, :created_at)
                """
            ),
            {
                "id": document_id,
                "project_id": project_id,
                "filename": filename,
                "content_type": content_type,
                "size_bytes": size,
                "sha256": sha256,
                "storage_path": storage_path,
                "created_at": datetime.now(UTC),
            },
        )
        mark_project_uploaded(project_id, db)
    except Exception:
        db.rollback()
        Path(storage_path).unlink(missing_ok=True)
        raise

    return DocumentUploadResponse(
        id=document_id,
        project_id=project_id,
        filename=filename,
        content_type=content_type,
        size_bytes=size,
        sha256=sha256,
        storage_path=storage_path,
    )
