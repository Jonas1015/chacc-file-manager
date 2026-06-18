from typing import Optional
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .context_factory import get_module_context, get_db, security


async def get_file_service():
    return get_module_context().get_service("file_service") if get_module_context() else None