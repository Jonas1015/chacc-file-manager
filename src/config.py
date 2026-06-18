from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import Optional
import os


class FileManagerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CHACC_FILE_MANAGER_")

    STORAGE_DIR: str = Field(
        default="/tmp/chacc_file_storage",
        description="Base directory for file storage"
    )
    MAX_FILE_SIZE: int = Field(
        default=10485760,
        description="Default max file size in bytes (default 10MB)"
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