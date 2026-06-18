from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
import aiofiles
import os
from sqlalchemy import select

from .context_factory import get_db
from .models import FileRecord, StorageChannel, StoragePolicy
from .service import FileService
from .adapters.base import AdapterRegistry
from .exceptions import FileTooLargeError, InvalidContentTypeError


class PolicyCreate(BaseModel):
    adapter_name: str
    max_file_size: Optional[int] = None


class ChannelCreate(BaseModel):
    name: str
    adapter_name: str
    description: Optional[str] = None


router = APIRouter(prefix="/files")


@router.get("/adapters")
async def list_adapters():
    """List all registered adapters."""
    return {"adapters": list(AdapterRegistry._adapters.keys())}


@router.get("/adapters/{name}")
async def get_adapter(name: str):
    """Get adapter info by name."""
    if name not in AdapterRegistry._adapters:
        raise HTTPException(status_code=404, detail="Adapter not found")
    return {"name": name, "status": "registered"}


@router.get("/channels", response_model=List[dict])
async def list_channels(db=Depends(get_db)):
    """List all storage channels."""
    result = await db.execute(select(StorageChannel))
    channels = result.scalars().all()
    return [{"name": c.name, "adapter_name": c.adapter_name, "is_active": c.is_active} for c in channels]


@router.post("/channels", status_code=status.HTTP_201_CREATED)
async def create_channel(channel: ChannelCreate, db=Depends(get_db)):
    """Create a storage channel."""
    if channel.adapter_name not in AdapterRegistry._adapters:
        raise HTTPException(status_code=400, detail="Adapter not registered")
    db_channel = StorageChannel(
        name=channel.name,
        adapter_name=channel.adapter_name,
        description=channel.description,
    )
    db.add(db_channel)
    db.commit()
    return {"name": db_channel.name, "adapter_name": db_channel.adapter_name}


@router.get("/policies/{channel}", response_model=Optional[dict])
async def get_policy(channel: str, db=Depends(get_db)):
    """Get storage policy for a channel."""
    result = await db.execute(select(StoragePolicy).where(StoragePolicy.channel == channel))
    policy = result.scalar_one_or_none()
    if not policy:
        return None
    return {"channel": policy.channel, "adapter_name": policy.adapter_name, "max_file_size": policy.max_file_size}


@router.post("/policies/{channel}", status_code=status.HTTP_201_CREATED)
async def set_policy(channel: str, policy: PolicyCreate, db=Depends(get_db)):
    """Set or update storage policy for a channel."""
    if policy.adapter_name not in AdapterRegistry._adapters:
        raise HTTPException(status_code=400, detail="Adapter not registered")
    result = await db.execute(select(StoragePolicy).where(StoragePolicy.channel == channel))
    db_policy = result.scalar_one_or_none()
    if db_policy:
        db_policy.adapter_name = policy.adapter_name
        if policy.max_file_size is not None:
            db_policy.max_file_size = policy.max_file_size
    else:
        db_policy = StoragePolicy(
            channel=channel,
            adapter_name=policy.adapter_name,
            max_file_size=policy.max_file_size or 10485760,
        )
        db.add(db_policy)
    db.commit()
    return {"channel": db_policy.channel, "adapter_name": db_policy.adapter_name, "max_file_size": db_policy.max_file_size}


@router.delete("/policies/{channel}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(channel: str, db=Depends(get_db)):
    """Delete storage policy for a channel."""
    result = await db.execute(select(StoragePolicy).where(StoragePolicy.channel == channel))
    db_policy = result.scalar_one_or_none()
    if db_policy:
        db.delete(db_policy)
        db.commit()


@router.get("/{uuid}/content")
async def serve_file(
    uuid: str,
    request: Request,
    download: bool = False,
    db=Depends(get_db),
):
    service = FileService()
    record = await service.get_file(uuid, db)

    adapter = AdapterRegistry.get(record.adapter_name)
    storage_key = str(record.storage_key)

    if not os.path.exists(adapter.storage_dir / storage_key):
        raise HTTPException(status_code=404, detail="File not found")

    file_path = adapter.storage_dir / storage_key
    stat = os.stat(file_path)
    size = stat.st_size

    headers = {
        "Content-Type": record.content_type,
        "Content-Disposition": f'inline; filename="{record.filename}"' if not download else f'attachment; filename="{record.filename}"',
        "Cache-Control": "public, max-age=31536000, immutable",
        "ETag": f'"{record.checksum}"' if record.checksum else None,
    }

    range_header = request.headers.get("range")
    if range_header:
        start, end = 0, size - 1
        if range_header.startswith("bytes="):
            parts = range_header[6:].split("-")
            if len(parts) == 2:
                start = int(parts[0]) if parts[0] else 0
                end = int(parts[1]) if parts[1] else end

        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        headers["Accept-Ranges"] = "bytes"

        async def range_stream():
            async with aiofiles.open(file_path, "rb") as f:
                await f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk_size = min(8192, remaining)
                    data = await f.read(chunk_size)
                    yield data
                    remaining -= len(data)

        return StreamingResponse(
            range_stream(),
            status_code=206,
            headers=headers,
            media_type=record.content_type,
        )

    async def file_stream():
        async with aiofiles.open(file_path, "rb") as f:
            while True:
                chunk = await f.read(8192)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        file_stream(),
        headers=headers,
        media_type=record.content_type,
    )


@router.post("/", status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    db=Depends(get_db),
):
    service = FileService()
    form = await request.form()
    file = form.get("file")
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")

    content = await file.read()
    content_type = file.content_type or "application/octet-stream"

    try:
        record = await service.save_file(
            file_content=content,
            filename=file.filename,
            content_type=content_type,
            created_by_module="chacc_file_manager",
        )
        db.add(record)
        db.commit()
        return {"uuid": record.uuid, "filename": record.filename, "size": record.size}
    except (FileTooLargeError, InvalidContentTypeError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    uuid: str,
    db=Depends(get_db),
):
    service = FileService()
    deleted = await service.delete_file(uuid, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="File not found")