"""Antivirus scanning (P04-T03, EC-DOC-06).

``settings.DOCUMENT_SCANNER``:
* ``clamd`` (default, staging/production) - ClamAV daemon over TCP using ``INSTREAM``.
* ``fake`` (tests) - flags the EICAR test signature only; no network.
* ``skip`` (local development without the clamav container) - nothing is scanned and documents are
  marked ``skipped``. Never valid outside DEBUG; the pipeline refuses it otherwise.
"""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass

from django.conf import settings

EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
CHUNK = 64 * 1024


class ScannerUnavailableError(Exception):
    """The scanner could not give a verdict (network/daemon error). Retry; never accept."""


@dataclass(frozen=True)
class Verdict:
    clean: bool
    signature: str = ""
    engine: str = ""
    skipped: bool = False


def _clamd_command(command: bytes, payload: bytes | None = None) -> bytes:
    host, port = settings.CLAMAV_HOST, settings.CLAMAV_PORT
    timeout = getattr(settings, "CLAMAV_TIMEOUT", 30)
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.sendall(b"z" + command + b"\0")
            if payload is not None:
                for i in range(0, len(payload), CHUNK):
                    chunk = payload[i : i + CHUNK]
                    sock.sendall(struct.pack("!L", len(chunk)) + chunk)
                sock.sendall(struct.pack("!L", 0))
            reply = b""
            while not reply.endswith(b"\0"):
                part = sock.recv(4096)
                if not part:
                    break
                reply += part
    except OSError as exc:
        raise ScannerUnavailableError(str(exc)) from exc
    return reply.rstrip(b"\0").strip()


def clamd_scan(data: bytes) -> Verdict:
    version = _clamd_command(b"VERSION").decode(errors="replace")
    reply = _clamd_command(b"INSTREAM", data).decode(errors="replace")
    # "stream: OK" | "stream: Eicar-Test-Signature FOUND" | "INSTREAM size limit exceeded. ERROR"
    if reply.endswith("OK"):
        return Verdict(clean=True, engine=version)
    if reply.endswith("FOUND"):
        signature = reply.split(":", 1)[-1].rsplit(" ", 1)[0].strip()
        return Verdict(clean=False, signature=signature, engine=version)
    raise ScannerUnavailableError(reply)


def scan(data: bytes) -> Verdict:
    mode = getattr(settings, "DOCUMENT_SCANNER", "clamd")
    if mode == "fake":
        if EICAR in data:
            return Verdict(clean=False, signature="Eicar-Test-Signature", engine="fake")
        return Verdict(clean=True, engine="fake")
    if mode == "skip":
        if not settings.DEBUG:
            raise ScannerUnavailableError("DOCUMENT_SCANNER=skip is only allowed when DEBUG is on")
        return Verdict(clean=True, engine="none", skipped=True)
    return clamd_scan(data)
