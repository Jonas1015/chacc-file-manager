from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from chacc_api import BackboneContext
from typing import Optional
import os

from .routes import router as chacc_file_manager_router
from .context_factory import get_context, set_module_context
from .adapters.local import LocalAdapter
from .adapters.base import AdapterRegistry
from .config import get_config


health_router = APIRouter()


@health_router.get("/health")
async def health_check():
    """Health check endpoint for the module."""
    config = get_config()
    storage_path = config.STORAGE_DIR

    if not os.path.exists(storage_path):
        return JSONResponse(
            {"status": "warning", "message": "Storage directory not created"},
            status_code=200,
        )

    if not os.access(storage_path, os.W_OK):
        return JSONResponse(
            {"status": "error", "message": "Storage directory not writable"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return {"status": "healthy", "adapter": "local"}


def setup_plugin(context: Optional[BackboneContext] = None):
    """
    This function is called by the ChaCC API backbone to initialize your module.
    It can also be called in development mode without a context.
    """
    _module_context = get_context(context)
    set_module_context(_module_context)

    _module_context.logger.info("chacc_file_manager: Setup initiated!")

    config = get_config()
    try:
        local_adapter = LocalAdapter(storage_dir=config.STORAGE_DIR)
        AdapterRegistry.register(local_adapter, name="local", set_default=True)
        _module_context.logger.info("chacc_file_manager: Local adapter registered")
    except Exception as e:
        _module_context.logger.warning(f"chacc_file_manager: Failed to init storage: {e}")

    _module_context.register_service("file_service", lambda: None)

    chacc_file_manager_router.include_router(health_router)
    return chacc_file_manager_router


def get_plugin_info():
    """
    Provides essential information about this module to the ChaCC API backbone.
    """
    return {
        "name": "chacc_file_manager",
        "display_name": "ChaccFileManager Module",
        "version": "0.1.0",
        "author": "Your Name/Organization",
        "description": "A new ChaCC API module for chacc_file_manager functionality.",
        "status": "enabled"
    }
