from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from backend.app.api.profile import read_valid_image


def upload(data: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        file=BytesIO(data),
        filename="untrusted-name.webp",
        headers=Headers({"content-type": content_type}),
    )


@pytest.mark.asyncio
async def test_webp_magic_header_is_accepted() -> None:
    data = b"RIFF" + (12).to_bytes(4, "little") + b"WEBP" + b"VP8 "
    content, extension = await read_valid_image(upload(data, "image/webp"), 2 * 1024 * 1024, "头像")
    assert content == data
    assert extension == ".webp"


@pytest.mark.asyncio
async def test_spoofed_image_mime_type_is_rejected() -> None:
    with pytest.raises(HTTPException) as rejected:
        await read_valid_image(upload(b"not an image", "image/png"), 2 * 1024 * 1024, "头像")
    assert rejected.value.status_code == 415


@pytest.mark.asyncio
async def test_image_over_two_megabytes_is_rejected() -> None:
    oversized = b"\x89PNG\r\n\x1a\n" + b"0" * (2 * 1024 * 1024)
    with pytest.raises(HTTPException) as rejected:
        await read_valid_image(upload(oversized, "image/png"), 2 * 1024 * 1024, "头像")
    assert rejected.value.status_code == 413
