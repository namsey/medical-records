"""sec-2: the body-size limit also holds for streamed (chunked) requests that send no Content-Length."""

import asyncio
import uuid
from pathlib import Path

from starlette.middleware.exceptions import ExceptionMiddleware

from app.config import get_settings
from app.middleware import MaxBodySizeMiddleware
from app.main import UPLOAD_OVERHEAD_BYTES
from tests.conftest import PDF_BYTES

MB = 1024 * 1024


def _stored_files() -> list[Path]:
    return [p for p in get_settings().files_path.rglob("*") if p.is_file()]


def _chunked_multipart(name: str, content: bytes, chunk: int = MB):
    """A multipart upload sent as a generator, so httpx streams it chunked with no Content-Length."""
    boundary = uuid.uuid4().hex
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode()
    tail = f"\r\n--{boundary}--\r\n".encode()

    def body():
        yield head
        for start in range(0, len(content), chunk):
            yield content[start : start + chunk]
        yield tail

    return body(), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def _call(middleware, chunks):
    """Run the middleware on a request streamed in `chunks`; return the response status and how much the app read."""
    messages = [{"type": "http.request", "body": c, "more_body": i < len(chunks) - 1} for i, c in enumerate(chunks)]
    sent: list[dict] = []
    read = 0

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    async def app(scope, receive, send):
        nonlocal read
        while True:
            message = await receive()
            read += len(message["body"])
            if not message["more_body"]:
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    wrapped = middleware(ExceptionMiddleware(app))
    scope = {"type": "http", "method": "POST", "path": "/", "headers": [(b"transfer-encoding", b"chunked")]}
    asyncio.run(wrapped(scope, receive, send))
    return sent[0]["status"], read


def test_streamed_body_over_the_limit_is_stopped_with_413():
    status, read = _call(lambda app: MaxBodySizeMiddleware(app, max_bytes=10), [b"12345", b"67890", b"abcde", b"fghij"])
    assert status == 413
    assert read == 10  # the third chunk never reaches the app


def test_streamed_body_at_the_limit_passes():
    status, read = _call(lambda app: MaxBodySizeMiddleware(app, max_bytes=10), [b"12345", b"67890"])
    assert (status, read) == (200, 10)


def test_chunked_upload_over_the_limit_gets_413_and_stores_nothing(client, make_record):
    record = make_record()
    limit = get_settings().max_upload_bytes + UPLOAD_OVERHEAD_BYTES
    content = PDF_BYTES + b"0" * (limit + MB)
    body, headers = _chunked_multipart("big.pdf", content)
    response = client.post(f"/api/records/{record['id']}/documents", content=body, headers=headers)
    assert response.status_code == 413
    assert response.json() == {"detail": "The upload is too large."}
    assert _stored_files() == []
    assert client.get(f"/api/records/{record['id']}").json()["documents"] == []


def test_chunked_upload_under_the_limit_still_works(client, make_record):
    record = make_record()
    body, headers = _chunked_multipart("small.pdf", PDF_BYTES)
    response = client.post(f"/api/records/{record['id']}/documents", content=body, headers=headers)
    assert response.status_code == 201
    assert len(_stored_files()) == 1
