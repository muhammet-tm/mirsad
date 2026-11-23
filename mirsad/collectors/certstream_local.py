"""Run certstream-server-go on this machine for the length of one certificate run.

The live Certificate Transparency stream is heavy: the server follows every log that Chrome trusts and
received about 3,500 certificates a second when we first ran it. Inside the sandbox VM that traffic
saturated VirtualBox's NAT, and the sandbox and Falcon ports stopped answering until it was stopped
(23 November 2026). The server therefore runs on the host, bound to 127.0.0.1, and only while a
certificate run listens; it starts at the live head of each log, so no backlog is fetched.

The binary is the project's official release (certstream-server-go v1.10.1, MIT,
https://github.com/d-Rickyy-b/certstream-server-go), downloaded once and checked against the SHA-256
pinned below before it is ever run.
"""

from __future__ import annotations

import contextlib
import hashlib
import platform
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

from ..config import DATA_DIR, http_client

VERSION = "1.10.1"
RELEASE = f"https://github.com/d-Rickyy-b/certstream-server-go/releases/download/v{VERSION}"
# From certstream-server-go_1.10.1_checksums.txt of the release, read 23 November 2026.
SHA256 = {
    ("Windows", "AMD64"): ("windows_amd64.exe", "25f8deaf8f4ccabae2a6addbeb7ea5ef8b6f06b1a5bc2388329090500856c073"),
    ("Linux", "x86_64"): ("linux_amd64", "8dc88f299520e29f0691c2c5047c38888b6799852dc6efc767c5f8d332691279"),
    ("Darwin", "arm64"): ("macOS_arm64", "f2b79697c073bc4f3a6ebbdf1eaed03e820c6409ed6248ebdf34876576425aad"),
}
BIN_DIR = DATA_DIR / "certstream"


def is_local(url: str) -> bool:
    return (urlsplit(url).hostname or "") in ("127.0.0.1", "localhost", "::1")


def _target() -> tuple[str, str]:
    key = (platform.system(), platform.machine())
    if key not in SHA256:
        raise RuntimeError(f"no pinned certstream-server-go build for {key[0]} {key[1]}")
    return SHA256[key]


def ensure_binary() -> Path:
    """The verified server binary, downloading it on first use."""
    suffix, digest = _target()
    path = BIN_DIR / f"certstream-server-go_{VERSION}_{suffix}"
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
        return path
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    with http_client(timeout=180, follow_redirects=True) as c:
        r = c.get(f"{RELEASE}/certstream-server-go_{VERSION}_{suffix}")
        r.raise_for_status()
    if hashlib.sha256(r.content).hexdigest() != digest:
        raise RuntimeError("certstream-server-go download does not match the pinned SHA-256; not running it")
    part = path.with_suffix(path.suffix + ".part")
    part.write_bytes(r.content)
    part.replace(path)
    path.chmod(0o755)
    return path


def write_config(port: int) -> Path:
    """Loopback only, no metrics port, no recovery file (start at the live head of each log)."""
    cfg = BIN_DIR / "config.yaml"
    cfg.write_text(f"""webserver:
  listen_addr: "127.0.0.1"
  listen_port: {port}
  real_ip: false
  whitelist:
    - "127.0.0.1/8"
  full_url: "/full-stream"
  lite_url: "/"
  domains_only_url: "/domains-only"
  cert_path: ""
  cert_key_path: ""
  compression_enabled: false
prometheus:
  enabled: false
  listen_addr: "127.0.0.1"
  listen_port: {port + 1}
  metrics_url: "/metrics"
general:
  drop_old_logs: true
  recovery:
    enabled: false
""", encoding="utf-8")
    return cfg


def _answers(port: int, timeout: float = 2.0) -> bool:
    """True when a certstream server answers HTTP on the port (a bare TCP accept is not enough)."""
    try:
        with http_client(timeout=timeout) as c:
            return c.get(f"http://127.0.0.1:{port}/example.json").status_code == 200
    except Exception:
        return False


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


@contextlib.contextmanager
def running(url: str, wait_s: int = 30):
    """Start a local server for the duration of the block when `url` points at this machine.

    Yields a note for the run's stats. A server that already answers on the port is reused and left
    running; one started here is stopped when the block ends.
    """
    port = urlsplit(url).port or 80
    if not is_local(url):
        yield "remote stream"
        return
    if _answers(port):
        yield "local stream already running"
        return
    if not _port_free(port):
        raise RuntimeError(f"port {port} is taken by another program (a VirtualBox port forward?)")
    binary = ensure_binary()
    cfg = write_config(port)
    log = open(BIN_DIR / "server.log", "ab")
    flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
    proc = subprocess.Popen([str(binary), "--config", str(cfg)], cwd=BIN_DIR, stdout=log, stderr=log,
                            creationflags=flags)
    try:
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline and proc.poll() is None and not _answers(port, 1.0):
            time.sleep(0.5)
        if proc.poll() is not None or not _answers(port, 2.0):
            raise RuntimeError(f"local certstream server did not start; see {BIN_DIR / 'server.log'}")
        yield f"local stream started for this run (pid {proc.pid})"
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        log.close()
