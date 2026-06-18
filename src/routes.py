from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from typing import Optional
import aiofiles
import os

from .context_factory import get_db
from .models import FileRecord
from .service import FileService
from .adapters.base import AdapterRegistry
from .exceptions import FileTooLargeError, InvalidContentTypeError

router = APIRouter(prefix="/files")


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