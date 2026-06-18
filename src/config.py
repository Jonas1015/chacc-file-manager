from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import Dict, List, Optional
import os


class StorageChannelConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FILE_MANAGER_")
    adapter_name: str = "local"
    max_file_size: int = Field(default=10485760, description="Max file size in bytes (default 10MB)")
    allowed_mime_types: List[str] = Field(default_factory=lambda: ["image/*", "application/pdf", "text/plain"])


class FileManagerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FILE_MANAGER_")
    STORAGE_DIR: str = Field(
        default="/uploads",
        description="Base directory for file storage"
    )
    MAX_FILE_SIZE: int = Field(
        default=10485760,
        description="Default max file size in bytes (default 10MB)"
    )
    ALLOWED_MIME_TYPES: Dict[str, List[str]] = Field(
        default_factory=lambda: {},
        description="Per-channel MIME type allowlists"
    )
    DEFAULT_CHANNEL: str = Field(
        default="default",
        description="Default storage channel for uploads"
    )
    SERVE_PATH_PREFIX: Optional[str] = Field(
        default=None,
        description="Optional prefix for URL generation (e.g., '/files' for sub-path deployments)"
    )

    @field_validator("STORAGE_DIR", mode="before")
    @classmethod
    def validate_storage_dir(cls, v):
        os.makedirs(v, exist_ok=True)
        return v


def get_config() -> FileManagerConfig:
    return FileManagerConfig()