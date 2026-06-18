from chacc_api import ChaCCBaseModel, register_model
from sqlalchemy import Column, String, Integer, Boolean, Enum as SQLAEnum
from typing import Optional
from enum import Enum


class FileStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DELETED = "DELETED"
    QUARANTINED = "QUARANTINED"


@register_model
class FileRecord(ChaCCBaseModel):
    __tablename__ = "file_records"

    uuid = Column(String(36), primary_key=True, index=True)
    adapter_name = Column(String(100), nullable=False)
    channel = Column(String(100), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    size = Column(Integer, nullable=False)
    storage_key = Column(String, nullable=False)
    created_by_module = Column(String(100), nullable=False)
    checksum = Column(String(64), nullable=True)
    status = Column(SQLAEnum(FileStatus), nullable=False, default=FileStatus.ACTIVE)


@register_model
class StorageChannel(ChaCCBaseModel):
    __tablename__ = "file_storage_channels"

    name = Column(String(100), primary_key=True)
    adapter_name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)


@register_model
class StoragePolicy(ChaCCBaseModel):
    __tablename__ = "file_storage_policies"

    channel = Column(String(100), primary_key=True)
    adapter_name = Column(String(100), nullable=False)
    max_file_size = Column(Integer, default=10485760)
    priority = Column(Integer, default=10)