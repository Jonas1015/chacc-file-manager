import uuid_utils
import hashlib
import asyncio
from typing import Optional
from abc import ABC, abstractmethod
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import FileRecord, ModuleAdapterMapping
from .adapters.base import AdapterRegistry, BaseAdapter
from .exceptions import (
    FileNotFoundError as FileNotFound,
)


def generate_checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sanitize_filename(filename: str) -> str:
    safe = "".join(c for c in filename if c.isalnum() or c in "._-")
    return safe or f"file_{uuid_utils.uuid7().hex}"


class BaseFileService(ABC):
    @abstractmethod
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
        pass

    @abstractmethod
    async def get_file(self, file_uuid: str, db_session: Session) -> FileRecord:
        pass

    @abstractmethod
    async def delete_file(self, file_uuid: str, db_session: Session) -> bool:
        pass

    @abstractmethod
    async def get_download_url(
        self,
        file_uuid: str,
        request: Request,
        db_session,
        download: bool = False,
    ) -> str:
        pass


class FileService(BaseFileService):
    def __init__(self):
        pass

    async def _resolve_adapter(self, module_name: str, adapter_name: Optional[str], db_session: Session):
        if adapter_name and adapter_name in AdapterRegistry._adapters:
            return AdapterRegistry.get(adapter_name), None

        def _query():
            if db_session:
                result = db_session.execute(
                    select(ModuleAdapterMapping).where(ModuleAdapterMapping.module_name == module_name)
                )
                return result.scalar_one_or_none()
            return None

        mapping = await asyncio.to_thread(_query)
        if mapping and mapping.adapter_name in AdapterRegistry._adapters:
            return AdapterRegistry.get(mapping.adapter_name), mapping

        adapter = AdapterRegistry.get_default()
        if not adapter:
            raise ValueError(f"No adapter registered for module '{module_name}'")
        return adapter, None

    async def save_file(
        self,
        file_content: bytes,
        filename: str,
        content_type: str,
        created_by_module: str,
        channel: Optional[str] = None,
        db_session: Session = None,
        adapter_name: Optional[str] = None,
    ) -> FileRecord:
        if db_session is None:
            raise ValueError("Database session is required to save file record")

        adapter, mapping = await self._resolve_adapter(created_by_module, adapter_name, db_session)
        file_uuid = str(uuid_utils.uuid7())
        safe_filename = sanitize_filename(filename)
        checksum = generate_checksum(file_content)

        use_module_dir = bool(mapping and mapping.use_module_dir)
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

        def _commit_and_refresh():
            db_session.add(record)
            db_session.commit()
            db_session.refresh(record)
            return record

        try:
            saved_record = await asyncio.to_thread(_commit_and_refresh)
            return saved_record
        except Exception:
            try:
                await adapter.delete(storage_key)
            except Exception:
                pass
            db_session.rollback()
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

    async def delete_file(self, file_uuid: str, db_session: Session) -> bool:
        def _get_record():
            result = db_session.execute(
                select(FileRecord).where(FileRecord.uuid == file_uuid)
            )
            return result.scalar_one_or_none()

        record = await asyncio.to_thread(_get_record)
        if record is None:
            return False

        try:
            await AdapterRegistry.get(record.adapter_name).delete(str(record.storage_key))
        except Exception:
            pass

        def _delete_and_commit(target_uuid: str):
            target = db_session.execute(
                select(FileRecord).where(FileRecord.uuid == target_uuid)
            ).scalar_one_or_none()
            if target:
                db_session.delete(target)
                db_session.commit()
            return True

        return await asyncio.to_thread(_delete_and_commit, file_uuid)

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
