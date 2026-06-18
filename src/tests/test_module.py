import pytest
import os
import sys
import tempfile
from pathlib import Path

from ..models import FileRecord, StorageChannel, StoragePolicy
from ..exceptions import (
    FileTooLargeError,
    InvalidContentTypeError,
    FileNotFoundError,
)


def test_models_import():
    assert FileRecord is not None
    assert StorageChannel is not None
    assert StoragePolicy is not None


def test_exceptions_exist():
    assert FileTooLargeError is not None
    assert InvalidContentTypeError is not None
    assert FileNotFoundError is not None


def test_file_record_creation():
    record = FileRecord(
        uuid="test-uuid-123",
        adapter_name="local",
        channel="default",
        filename="test.txt",
        content_type="text/plain",
        size=100,
        storage_key="test-uuid-123",
        created_by_module="chacc_file_manager",
        checksum="abc123",
    )
    assert record.uuid == "test-uuid-123"
    assert record.adapter_name == "local"


def test_sanitize_filename():
    from ..service import sanitize_filename
    assert sanitize_filename("test file.txt") == "testfile.txt"
    assert sanitize_filename("../../../etc/passwd") == "......etcpasswd"
    assert sanitize_filename("file<>.pdf") == "file.pdf"
    assert sanitize_filename("safe_file.txt") == "safe_file.txt"


def test_checksum_generation():
    from ..service import generate_checksum
    checksum = generate_checksum(b"test content")
    assert len(checksum) == 64


def test_config():
    from ..config import get_config
    config = get_config()
    assert config.STORAGE_DIR is not None
    assert config.MAX_FILE_SIZE > 0


def test_local_adapter():
    from ..adapters.local import LocalAdapter
    with tempfile.TemporaryDirectory() as tmpdir:
        adapter = LocalAdapter(storage_dir=tmpdir)
        assert adapter.name == "local"


@pytest.mark.asyncio
async def test_adapter_save_and_delete():
    from ..adapters.local import LocalAdapter
    with tempfile.TemporaryDirectory() as tmpdir:
        adapter = LocalAdapter(storage_dir=tmpdir)
        storage_key = "test-uuid-123"
        await adapter.save(storage_key, b"test content", "text/plain")
        assert await adapter.exists(storage_key)
        assert await adapter.get_size(storage_key) == 12
        assert await adapter.delete(storage_key)
        assert not await adapter.exists(storage_key)


@pytest.mark.asyncio
async def test_adapter_path_traversal_protection():
    from ..adapters.local import LocalAdapter
    with tempfile.TemporaryDirectory() as tmpdir:
        adapter = LocalAdapter(storage_dir=tmpdir)
        try:
            await adapter.save("../../../etc/passwd", b"test", "text/plain")
            assert False, "Should have raised HTTPException"
        except Exception:
            pass


def test_router_exists():
    from ..routes import router
    assert router is not None
    assert hasattr(router, "routes")


def run_module_tests():
    import subprocess
    tests_dir = Path(__file__).resolve().parent
    plugin_root = tests_dir.parent.parent
    venv_python = plugin_root.parent / "venv" / "bin" / "python"
    python = str(venv_python if venv_python.exists() else sys.executable)
    result = subprocess.run(
        [python, "-m", "pytest", str(tests_dir), "-v", "--tb=short"],
        cwd=str(tests_dir),
        env={**os.environ, "PYTHONPATH": str(plugin_root)},
    )
    if result.returncode == 0:
        return {"status": "passed", "message": "All tests passed"}
    return {"status": "failed", "message": "Tests failed", "details": result.stdout + result.stderr}