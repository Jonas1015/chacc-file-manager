import uuid
import hashlib
import asyncio
from typing import Optional, Any
from fastapi import Request, HTTPException
from sqlalchemy import select

from .models import FileRecord
from .adapters.base import AdapterRegistry
from .config import get_config, FileManagerConfig
from .exceptions import (
    FileTooLargeError,
    InvalidContentTypeError,
    FileNotFoundError as FileNotFound,
)


def generate_checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sanitize_filename(filename: str) -> str:
    safe = "".join(c for c in filename if c.isalnum() or c in "._-")
    return safe or f"file_{uuid.uuid4().hex}"


class FileService:
    def __init__(self, config: Optional[FileManagerConfig] = None):
        self.config = config or get_config()

    async def save_file(
        self,
        file_content: bytes,
        filename: str,
        content_type: str,
        created_by_module: str,
        channel: Optional[str] = None,
    ) -> FileRecord:
        channel = channel or self.config.DEFAULT_CHANNEL

        adapter = AdapterRegistry.get_default()
        file_uuid = str(uuid.uuid4())
        safe_filename = sanitize_filename(filename)
        checksum = generate_checksum(file_content)

        storage_key = file_uuid
        await adapter.save(
            file_uuid=storage_key,
            content=file_content,
            content_type=content_type,
        )

        try:
            record = FileRecord(
                uuid=file_uuid,
                adapter_name=adapter.name,
                channel=channel,
                filename=safe_filename,
                content_type=content_type,
                size=len(file_content),
                storage_key=storage_key,
                created_by_module=created_by_module,
                checksum=checksum,
            )
            return record
        except Exception:
            try:
                await adapter.delete(storage_key)
            except Exception:
                pass
            raise

    async def get_file(self, file_uuid: str, db_session) -> FileRecord:
        def _do():
            result = db_session.execute(
                select(FileRecord).where(FileRecord.uuid == file_uuid)
            )
            return result.scalar_one_or_none()
        record = await asyncio.to_thread(_do)
        if record is None:
            raise FileNotFound(f"File {file_uuid} not found")
        return record

    async def delete_file(self, file_uuid: str, db_session) -> bool:
        record = await self.get_file(file_uuid, db_session)
        if record is None:
            return False

        adapter = AdapterRegistry.get(record.adapter_name)
        try:
            await adapter.delete(str(record.storage_key))
            db_session.delete(record)
            db_session.commit()
            return True
        except Exception:
            record.status = "DELETED"
            return False

    async def get_download_url(
        self,
        file_uuid: str,
        request: Request,
        db_session,
        download: bool = False,
    ) -> str:
        record = await self.get_file(file_uuid, db_session)
        adapter = AdapterRegistry.get(record.adapter_name)
        return await adapter.get_url(record.storage_key, request)