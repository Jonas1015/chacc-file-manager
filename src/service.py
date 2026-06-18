import uuid
import hashlib
import asyncio
from typing import Optional, Any
from fastapi import Request, HTTPException
from sqlalchemy import select

from .models import FileRecord, ModuleAdapterMapping
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

    def _resolve_adapter_for_module(self, module_name: str, db_session) -> Any:
        result = db_session.execute(
            select(ModuleAdapterMapping).where(ModuleAdapterMapping.module_name == module_name)
        )
        mapping = result.scalar_one_or_none()
        if mapping and mapping.adapter_name in AdapterRegistry._adapters:
            return AdapterRegistry.get(mapping.adapter_name), mapping.use_module_dir
        adapter = AdapterRegistry.get_default()
        if not adapter:
            raise ValueError(f"No default adapter registered for module '{module_name}'")
        return adapter, False

    async def save_file(
        self,
        file_content: bytes,
        filename: str,
        content_type: str,
        created_by_module: str,
        channel: Optional[str] = None,
        db_session=None,
        adapter_name: Optional[str] = None,
    ) -> FileRecord:
        if adapter_name and adapter_name in AdapterRegistry._adapters:
            adapter = AdapterRegistry.get(adapter_name)
            use_module_dir = False
        elif db_session:
            adapter, use_module_dir = self._resolve_adapter_for_module(created_by_module, db_session)
        else:
            adapter = AdapterRegistry.get_default()
            if not adapter:
                raise ValueError("No adapter registered")
            use_module_dir = False

        file_uuid = str(uuid.uuid4())
        safe_filename = sanitize_filename(filename)
        checksum = generate_checksum(file_content)

        storage_key = file_uuid
        if use_module_dir:
            storage_key = f"{created_by_module}/{storage_key}"
            if channel:
                storage_key = f"{created_by_module}/{channel}/{storage_key}"

        await adapter.save(
            file_uuid=storage_key,
            content=file_content,
            content_type=content_type,
        )

        try:
            record = FileRecord(
                uuid=file_uuid,
                adapter_name=adapter.name,
                module_dir=created_by_module if use_module_dir else None,
                channel=channel if use_module_dir else None,
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