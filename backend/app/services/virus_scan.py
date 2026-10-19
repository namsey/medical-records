"""Optional virus scan of uploads with ClamAV (clamd), switched on by setting CLAMAV_SOCKET.

Uses clamd's INSTREAM command over its Unix socket, so no extra package is needed. When the scanner is switched
on but cannot answer, the upload is refused: files are never let through unscanned. File names and contents are
never logged.
"""

import logging
import socket
from pathlib import Path

from fastapi import HTTPException, status

from app.config import get_settings

logger = logging.getLogger(__name__)

CHUNK = 64 * 1024
TIMEOUT_SECONDS = 60


class ScannerUnavailable(Exception):
    pass


def scan(socket_path: str, path: Path) -> bool:
    """True if clamd says the file is clean, False if it found something. Raises ScannerUnavailable otherwise."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(TIMEOUT_SECONDS)
            connection.connect(socket_path)
            connection.sendall(b"zINSTREAM\0")
            with open(path, "rb") as source:
                while chunk := source.read(CHUNK):
                    connection.sendall(len(chunk).to_bytes(4, "big") + chunk)
            connection.sendall((0).to_bytes(4, "big"))
            reply = b""
            while not reply.endswith(b"\0"):
                part = connection.recv(4096)
                if not part:
                    break
                reply += part
    except OSError as error:
        raise ScannerUnavailable(type(error).__name__) from error
    answer = reply.rstrip(b"\0").decode(errors="replace")
    if answer.endswith(" OK"):
        return True
    if answer.endswith(" FOUND"):
        return False
    raise ScannerUnavailable("unexpected reply")


def check(path: Path, display_name: str) -> None:
    """Raise an HTTPException unless the file is clean (or scanning is switched off)."""
    socket_path = get_settings().clamav_socket.strip()
    if not socket_path:
        return
    try:
        clean = scan(socket_path, path)
    except ScannerUnavailable as error:
        logger.error("Virus scanner unavailable (%s); upload refused", error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The virus scanner is not available, so the file was not saved. Try again later.",
        ) from error
    if not clean:
        logger.warning("Virus scanner refused an upload")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"'{display_name}' was refused by the virus scanner.",
        )
