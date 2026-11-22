"""Mirsad sandbox service: page capture and Phishpedia logo checks inside the ScamShield-Sandbox VM.

Run by systemd (unit mirsad-sandbox) as:
    uvicorn sandbox_service:app --host 0.0.0.0 --port 8601 --no-access-log
The Windows host reaches it through the VirtualBox NAT forward 127.0.0.1:8601 -> guest 8601.

Endpoints
    GET  /health      {"ok", "phishpedia": bool, "chromium": bool, "phishpedia_state", "version"}
    POST /capture     {"url": str, "timeout_s": 15, "device": "desktop" | "mobile"}
    POST /phishpedia  {"url": str, "screenshot_b64": str}

Safety rules enforced in this file (README.md explains them):
1. One page load per request, in a brand-new browser context: no stored state, downloads refused,
   service workers blocked, popups closed. This code never types, clicks, or submits, and it aborts
   any non-GET navigation, so a form that the page submits by itself never leaves the browser.
2. No private networks. Every browser request is checked twice. A Playwright route handler resolves
   the host with socket.getaddrinfo (IPv4 and IPv6) and aborts the request if any address is private,
   loopback, link-local, multicast, reserved, or otherwise not global. All browser traffic then goes
   through a local SOCKS5 proxy that resolves the host again, applies the same rule, and connects to
   the exact address it checked. The second check closes the DNS-rebinding gap between the browser's
   lookup and ours. Chromium's own DNS is switched off so that nothing bypasses the proxy.
3. Each upstream connection may deliver at most MIRSAD_MAX_BODY_BYTES (5 MB by default), so no
   response body can be larger than that.
4. The request log holds the time, the URL host, and the outcome only, never a path or a query string.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import io
import ipaddress
import json
import logging
import logging.handlers
import os
import queue
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel

try:  # Imported lazily so that /health still answers if the Playwright install is broken.
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
except Exception:  # pragma: no cover - depends on the VM install
    async_playwright = None

    class PlaywrightError(Exception):  # type: ignore[no-redef]
        pass

    class PlaywrightTimeoutError(PlaywrightError):  # type: ignore[no-redef]
        pass

try:
    import tldextract

    # Bundled Public Suffix List snapshot only: no network fetch, no cache directory.
    _TLD = tldextract.TLDExtract(cache_dir=None, suffix_list_urls=())
except Exception:  # pragma: no cover - fallback when tldextract is missing
    _TLD = None

VERSION = "0.1.0"

# ----------------------------------------------------------------------------------------------
# Settings (environment variables set by the systemd unit; the defaults match setup.sh)
# ----------------------------------------------------------------------------------------------
ROOT = os.environ.get("MIRSAD_ROOT", "/srv/scamshield")
PHISHPEDIA_DIR = os.environ.get("PHISHPEDIA_DIR", os.path.join(ROOT, "Phishpedia"))
PHISHPEDIA_PYTHON = os.environ.get(
    "PHISHPEDIA_PYTHON", os.path.join(PHISHPEDIA_DIR, ".pixi", "envs", "default", "bin", "python"))
WORKER_SCRIPT = os.environ.get(
    "PHISHPEDIA_WORKER", os.path.join(os.path.dirname(os.path.abspath(__file__)), "phishpedia_worker.py"))
LOG_DIR = os.environ.get("MIRSAD_LOG_DIR", os.path.join(ROOT, "logs"))

MAX_BODY_BYTES = int(os.environ.get("MIRSAD_MAX_BODY_BYTES", str(5 * 1024 * 1024)))
MAX_URL_LEN = 4096
SCREENSHOT_MAX_W, SCREENSHOT_MAX_H = 1440, 2000
VISIBLE_TEXT_CHARS = 4000
MAX_FRAMES = 10
MAX_CHAIN = 25
BROWSER_RECYCLE_AFTER = int(os.environ.get("MIRSAD_BROWSER_RECYCLE", "50"))
CAPTURE_QUEUE_TIMEOUT_S = 90.0
DNS_TIMEOUT_S = 5.0
CONNECT_TIMEOUT_S = 10.0
PROXY_IDLE_TIMEOUT_S = 60.0
PHISHPEDIA_TIMEOUT_S = float(os.environ.get("PHISHPEDIA_TIMEOUT_S", "120"))
PHISHPEDIA_STARTUP_TIMEOUT_S = float(os.environ.get("PHISHPEDIA_STARTUP_TIMEOUT_S", "1800"))
MAX_SCREENSHOT_B64 = 20 * 1024 * 1024
PHISHPEDIA_MAX_W, PHISHPEDIA_MAX_H = 1920, 4000
Image.MAX_IMAGE_PIXELS = 40_000_000

DEVICES: Dict[str, Dict[str, Any]] = {
    "desktop": {
        "viewport": {"width": 1440, "height": 900},
        "device_scale_factor": 1,
        "is_mobile": False,
        "has_touch": False,
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/{major}.0.0.0 Safari/537.36",
    },
    "mobile": {
        "viewport": {"width": 412, "height": 915},
        "device_scale_factor": 2.625,
        "is_mobile": True,
        "has_touch": True,
        "ua": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/{major}.0.0.0 Mobile Safari/537.36",
    },
}

CAPTURE_NOTE = "Captured in sandbox, no form submitted"

# ----------------------------------------------------------------------------------------------
# Logging: one line per request with time, URL host, and outcome. Never a path or a query string.
# ----------------------------------------------------------------------------------------------
REQ_LOG = logging.getLogger("mirsad.sandbox.requests")
SVC_LOG = logging.getLogger("mirsad.sandbox")


def _setup_logging() -> None:
    if REQ_LOG.handlers:
        return
    fmt = logging.Formatter("%(message)s")
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    REQ_LOG.addHandler(stream)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            os.path.join(LOG_DIR, "sandbox_requests.log"), maxBytes=5_000_000, backupCount=5)
        fh.setFormatter(fmt)
        REQ_LOG.addHandler(fh)
    except OSError:
        pass  # journald still receives the lines through stdout
    REQ_LOG.setLevel(logging.INFO)
    REQ_LOG.propagate = False
    svc = logging.StreamHandler(sys.stderr)
    svc.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    SVC_LOG.addHandler(svc)
    SVC_LOG.setLevel(logging.INFO)
    SVC_LOG.propagate = False


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_host(url: Any) -> str:
    """The host of a URL for logging: lower case, no path, no query, no credentials."""
    try:
        host = urlsplit(str(url).strip()).hostname or ""
    except ValueError:
        return "invalid"
    host = host[:253]
    if not host:
        return "-"
    if all(c.isalnum() or c in ".-:_" for c in host):
        return host
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return "invalid"


def log_request(kind: str, url: Any, outcome: str, **fields: Any) -> None:
    extras = []
    for key, value in fields.items():
        if value is None:
            continue
        text = str(value)
        if any(c.isspace() for c in text) or '"' in text:
            text = json.dumps(text, ensure_ascii=False)
        extras.append(f"{key}={text}")
    host = safe_host(url) if url is not None else "-"
    REQ_LOG.info("%s %s host=%s outcome=%s%s", utcnow(), kind, host, outcome,
                 (" " + " ".join(extras)) if extras else "")


# ----------------------------------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------------------------------
class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, extra: Optional[dict] = None):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra or {}

    def body(self) -> dict:
        out = {"ok": False, "error": {"code": self.code, "message": self.message}}
        out.update(self.extra)
        return out


def _short(message: Any, limit: int = 300) -> str:
    """First line of an exception message, without Playwright's call log."""
    text = str(message).split("Call log:")[0].strip().splitlines()
    return (text[0] if text else "")[:limit]


# ----------------------------------------------------------------------------------------------
# Address policy: private, loopback, link-local, multicast, reserved, and non-global addresses
# ----------------------------------------------------------------------------------------------
BLOCKED_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}
BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".home.arpa", ".lan")
_NAT64 = ipaddress.ip_network("64:ff9b::/96")


def ip_block_reason(value: Any) -> Optional[str]:
    """Why an address is off limits, or None for a public (global unicast) address."""
    try:
        ip = ipaddress.ip_address(str(value).split("%", 1)[0].strip("[]"))
    except ValueError:
        return "unparseable address"
    candidates: List[Any] = [ip]
    if ip.version == 6:
        if ip.ipv4_mapped is not None:
            candidates.append(ip.ipv4_mapped)
        if ip.sixtofour is not None:
            candidates.append(ip.sixtofour)
        if ip.teredo is not None:
            candidates.extend(ip.teredo)
        if ip in _NAT64:
            candidates.append(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
        if int(ip) >> 32 == 0 and int(ip) > 1:  # deprecated IPv4-compatible form ::a.b.c.d
            candidates.append(ipaddress.IPv4Address(int(ip)))
    for c in candidates:
        if c.is_loopback:
            return "loopback"
        if c.is_link_local:
            return "link-local"
        if c.is_multicast:
            return "multicast"
        if c.is_unspecified:
            return "unspecified"
        if c.is_private:
            return "private"
        if c.is_reserved:
            return "reserved"
        if not c.is_global:
            return "non-global"
    return None


_NUMERIC_LABEL = re.compile(r"^(0x[0-9a-f]*|[0-9]+)$")


def _ip_literal(host: str) -> Optional[str]:
    """Canonical IP for an IP-literal host, including the shorthand IPv4 forms that browsers accept
    (2130706433, 0x7f.1, 0177.0.0.1, 127.1 all mean 127.0.0.1). None for a host name."""
    h = host.strip("[]").split("%", 1)[0].rstrip(".")
    try:
        return str(ipaddress.ip_address(h))
    except ValueError:
        pass
    if _NUMERIC_LABEL.match(h.rsplit(".", 1)[-1].lower()):
        try:
            return socket.inet_ntoa(socket.inet_aton(h))
        except OSError:
            return None
    return None


async def resolve_and_check(host: str, port: int) -> Tuple[List[str], Optional[str]]:
    """Resolve a host (IPv4 and IPv6). Returns (addresses, None) if every address is public,
    or ([], reason) if the host is local, fails to resolve, or has any non-public address."""
    host = (host or "").strip().rstrip(".").lower()
    if not host:
        return [], "empty host"
    if host in BLOCKED_NAMES or host.endswith(BLOCKED_SUFFIXES):
        return [], "local host name"
    literal = _ip_literal(host)
    if literal is not None:
        reason = ip_block_reason(literal)
        return ([], f"{reason} address {literal}") if reason else ([literal], None)
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(host, port, type=socket.SOCK_STREAM), DNS_TIMEOUT_S)
    except (socket.gaierror, asyncio.TimeoutError, UnicodeError, OSError):
        return [], "dns lookup failed"
    addrs: List[str] = []
    for _family, _type, _proto, _canon, sockaddr in infos:
        ip = str(sockaddr[0])
        reason = ip_block_reason(ip)
        if reason:
            return [], f"{reason} address {ip}"
        if ip not in addrs:
            addrs.append(ip)
    if not addrs:
        return [], "dns lookup returned no address"
    return addrs, None


def registered_domain(host: Optional[str]) -> Optional[str]:
    """eTLD+1 of a host (salik-topup-uae.top, adpolice.gov.ae), or the IP itself."""
    if not host:
        return None
    host = host.strip().rstrip(".").lower().strip("[]")
    if not host:
        return None
    if _ip_literal(host) is not None:
        return host
    if _TLD is not None:
        try:
            r = _TLD(host)
            if r.domain and r.suffix:
                return f"{r.domain}.{r.suffix}"
            return host
        except Exception:
            pass
    labels = host.split(".")
    if len(labels) >= 3 and labels[-2] in {"gov", "co", "com", "net", "org", "ac", "sch", "mil"}:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


# ----------------------------------------------------------------------------------------------
# Per-capture event record, shared by the route guard and the egress proxy
# ----------------------------------------------------------------------------------------------
@dataclass
class CaptureEvents:
    blocked: List[Dict[str, str]] = field(default_factory=list)
    capped_hosts: List[str] = field(default_factory=list)
    connected_ips: Dict[str, str] = field(default_factory=dict)
    _seen: set = field(default_factory=set)

    def block(self, host: str, reason: str, layer: str) -> None:
        key = (host, reason, layer)
        if key in self._seen or len(self.blocked) >= 50:
            return
        self._seen.add(key)
        self.blocked.append({"host": host[:253], "reason": reason, "layer": layer})

    def capped(self, host: str) -> None:
        if host not in self.capped_hosts and len(self.capped_hosts) < 50:
            self.capped_hosts.append(host[:253])

    def connected(self, host: str, ip: str) -> None:
        if len(self.connected_ips) < 200:
            self.connected_ips.setdefault(host.lower(), ip)


# ----------------------------------------------------------------------------------------------
# Egress proxy: SOCKS5 (no auth, CONNECT only) on 127.0.0.1, used by Chromium for all traffic
# ----------------------------------------------------------------------------------------------
class EgressProxy:
    def __init__(self, max_bytes: int):
        self.max_bytes = max_bytes
        self.server: Optional[asyncio.AbstractServer] = None
        self.port: Optional[int] = None
        self.events = CaptureEvents()
        self._sem: Optional[asyncio.Semaphore] = None

    @property
    def url(self) -> str:
        return f"socks5://127.0.0.1:{self.port}"

    async def start(self) -> None:
        self._sem = asyncio.Semaphore(256)
        self.server = await asyncio.start_server(self._handle, host="127.0.0.1", port=0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self.server is not None:
            self.server.close()
            try:
                await asyncio.wait_for(self.server.wait_closed(), 5)
            except Exception:
                pass

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        assert self._sem is not None
        async with self._sem:
            upstream: Optional[asyncio.StreamWriter] = None
            try:
                upstream = await self._serve(reader, writer)
            except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError, OSError,
                    UnicodeError, ValueError):
                pass
            except Exception:  # never let one connection take the proxy down
                SVC_LOG.exception("egress proxy connection error")
            finally:
                for w in (upstream, writer):
                    if w is not None:
                        try:
                            w.close()
                        except Exception:
                            pass

    @staticmethod
    async def _read(reader: asyncio.StreamReader, n: int) -> bytes:
        return await asyncio.wait_for(reader.readexactly(n), 15)

    @staticmethod
    async def _reply(writer: asyncio.StreamWriter, code: int) -> None:
        writer.write(bytes([5, code, 0, 1, 0, 0, 0, 0, 0, 0]))
        await writer.drain()

    async def _serve(self, reader: asyncio.StreamReader,
                     writer: asyncio.StreamWriter) -> Optional[asyncio.StreamWriter]:
        ver, nmethods = await self._read(reader, 2)
        if ver != 5:
            return None
        methods = await self._read(reader, nmethods)
        if 0 not in methods:
            writer.write(b"\x05\xff")
            await writer.drain()
            return None
        writer.write(b"\x05\x00")
        await writer.drain()
        ver, cmd, _rsv, atyp = await self._read(reader, 4)
        if atyp == 1:
            host = socket.inet_ntop(socket.AF_INET, await self._read(reader, 4))
        elif atyp == 3:
            length = (await self._read(reader, 1))[0]
            host = (await self._read(reader, length)).decode("ascii")
        elif atyp == 4:
            host = socket.inet_ntop(socket.AF_INET6, await self._read(reader, 16))
        else:
            await self._reply(writer, 8)  # address type not supported
            return None
        port = int.from_bytes(await self._read(reader, 2), "big")
        if ver != 5 or cmd != 1:
            await self._reply(writer, 7)  # only CONNECT
            return None
        addrs, reason = await resolve_and_check(host, port)
        if reason:
            self.events.block(host, reason, "egress-proxy")
            await self._reply(writer, 2)  # connection not allowed by ruleset
            return None
        up_reader = up_writer = None
        for ip in addrs:  # connect to the exact address that was checked
            try:
                up_reader, up_writer = await asyncio.wait_for(
                    asyncio.open_connection(ip, port), CONNECT_TIMEOUT_S)
                self.events.connected(host, ip)
                break
            except (OSError, asyncio.TimeoutError):
                continue
        if up_writer is None or up_reader is None:
            await self._reply(writer, 5)  # connection refused
            return None
        await self._reply(writer, 0)
        await self._splice(reader, writer, up_reader, up_writer, host)
        return up_writer

    async def _pump(self, src: asyncio.StreamReader, dst: asyncio.StreamWriter,
                    cap: Optional[int], host: str) -> None:
        total = 0
        while True:
            data = await asyncio.wait_for(src.read(65536), PROXY_IDLE_TIMEOUT_S)
            if not data:
                return
            total += len(data)
            if cap is not None and total > cap:
                self.events.capped(host)
                return
            dst.write(data)
            await dst.drain()

    async def _splice(self, c_reader, c_writer, u_reader, u_writer, host: str) -> None:
        tasks = [asyncio.ensure_future(self._pump(c_reader, u_writer, None, host)),
                 asyncio.ensure_future(self._pump(u_reader, c_writer, self.max_bytes, host))]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in tasks:
                t.cancel()
            for t in tasks:
                try:
                    await t
                except BaseException:
                    pass


# ----------------------------------------------------------------------------------------------
# Route guard (first check, per request, inside Playwright)
# ----------------------------------------------------------------------------------------------
class RouteGuard:
    PASS_SCHEMES = ("data", "blob", "about")
    NET_SCHEMES = ("http", "https", "ws", "wss")

    def __init__(self, events: CaptureEvents):
        self.events = events
        self.cache: Dict[Tuple[str, int], Optional[str]] = {}

    async def verdict(self, request: Any) -> Tuple[str, Optional[str]]:
        try:
            parts = urlsplit(request.url)
            scheme = parts.scheme.lower()
            host = (parts.hostname or "").lower()
            port = parts.port or (443 if scheme in ("https", "wss") else 80)
        except ValueError:
            return "-", "unparseable url"
        if scheme in self.PASS_SCHEMES:
            return host, None
        if scheme not in self.NET_SCHEMES:
            return host or scheme, f"scheme {scheme} not allowed"
        try:
            if request.is_navigation_request() and request.method.upper() not in ("GET", "HEAD"):
                return host, f"form submission blocked ({request.method.upper()} navigation)"
        except Exception:
            pass
        key = (host, port)
        if key not in self.cache:
            _addrs, reason = await resolve_and_check(host, port)
            self.cache[key] = reason
        return host, self.cache[key]

    async def handle(self, route: Any) -> None:
        try:
            host, reason = await self.verdict(route.request)
        except Exception as exc:  # fail closed
            host, reason = "-", f"guard error {type(exc).__name__}"
        try:
            if reason:
                self.events.block(host, reason, "route")
                await route.abort("blockedbyclient")
            else:
                await route.continue_()
        except Exception:
            pass  # the page or context closed while the request was in flight


# ----------------------------------------------------------------------------------------------
# Browser manager: one Chromium process, a new context per capture, recycled every N captures
# ----------------------------------------------------------------------------------------------
class BrowserManager:
    def __init__(self, proxy: EgressProxy):
        self.proxy = proxy
        self._pw = None
        self._browser = None
        self._lock = asyncio.Lock()
        self.served = 0
        self.last_error: Optional[str] = None
        self.major = "131"

    def is_ready(self) -> bool:
        try:
            return self._browser is not None and self._browser.is_connected()
        except Exception:
            return False

    async def _launch(self):
        args = [
            # Chromium does no DNS of its own: every host goes to the SOCKS5 proxy for resolution.
            "--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1",
            # WebRTC may not send UDP outside the proxy (this also stops STUN to local addresses).
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            # Many phishing kits show a harmless page when navigator.webdriver is true.
            "--disable-blink-features=AutomationControlled",
        ]
        # chromium_sandbox=True matters: Playwright passes --no-sandbox unless it is set.
        kwargs = dict(headless=True, chromium_sandbox=True, args=args, proxy={"server": self.proxy.url})
        try:  # the full Chromium build in new headless mode looks like a normal browser
            return await self._pw.chromium.launch(channel="chromium", **kwargs)
        except PlaywrightError:
            return await self._pw.chromium.launch(**kwargs)

    async def get(self):
        async with self._lock:
            if self.is_ready() and self.served < BROWSER_RECYCLE_AFTER:
                return self._browser
            await self._close_browser()
            if async_playwright is None:
                self.last_error = "playwright is not installed"
                raise ApiError(503, "chromium_unavailable", self.last_error)
            try:
                if self._pw is None:
                    self._pw = await async_playwright().start()
                self._browser = await self._launch()
                self.major = (self._browser.version or "131").split(".")[0]
                self.served = 0
                self.last_error = None
                return self._browser
            except Exception as exc:
                self.last_error = _short(exc)
                SVC_LOG.error("Chromium launch failed: %s", self.last_error)
                raise ApiError(503, "chromium_unavailable", "Chromium could not start: " + self.last_error)

    async def warm(self) -> None:
        try:
            await self.get()
        except ApiError:
            pass

    async def _close_browser(self) -> None:
        if self._browser is not None:
            try:
                await asyncio.wait_for(self._browser.close(), 15)
            except Exception:
                pass
            self._browser = None

    async def close(self) -> None:
        async with self._lock:
            await self._close_browser()
            if self._pw is not None:
                try:
                    await asyncio.wait_for(self._pw.stop(), 15)
                except Exception:
                    pass
                self._pw = None


# ----------------------------------------------------------------------------------------------
# Page extraction helpers
# ----------------------------------------------------------------------------------------------
FORMS_JS = r"""
() => {
  const CARD = /(card.?(num|no\b|number|holder|code)|cc.?(num|no\b|number)|credit.?card|debit.?card|\bpan\b|\bcvv|\bcvc|\bcsc\b|\bcvn\b|security.?code|expir|exp.?(date|month|year|mm|yy)|\bmm\s*\/\s*yy|valid.?thru|بطاقة|الائتمان)/i;
  const OTP = /(\botp\b|one.?time|verification.?code|verify.?code|sms.?code|auth.?code|passcode|رمز.?التحقق|رمز.?التفعيل)/i;
  const PASS = /(password|passwd|\bpwd\b|كلمة.?المرور|كلمة.?السر)/i;
  const NONTEXT = ['hidden', 'checkbox', 'radio', 'submit', 'button', 'image', 'reset', 'file', 'range', 'color'];
  const getAttr = (el, n) => { try { return String(Element.prototype.getAttribute.call(el, n) || ''); } catch (e) { return ''; } };
  const clip = (s, n) => String(s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  let base = '';
  try { base = Object.getOwnPropertyDescriptor(Node.prototype, 'baseURI').get.call(document); } catch (e) { base = String(location.href); }
  const qsa = (sel) => { try { return Array.from(Document.prototype.querySelectorAll.call(document, sel)); } catch (e) { return []; } };
  const all = qsa('input,select,textarea');
  const describe = (el) => {
    const tag = String(el.tagName || '').toLowerCase();
    const type = tag === 'input' ? (getAttr(el, 'type').toLowerCase() || 'text') : tag;
    const name = clip(getAttr(el, 'name') || getAttr(el, 'id'), 80);
    const ac = clip(getAttr(el, 'autocomplete'), 60).toLowerCase();
    let label = '';
    try { if (el.labels && el.labels.length) label = el.labels[0].innerText; } catch (e) {}
    label = clip(label || getAttr(el, 'aria-label') || getAttr(el, 'placeholder'), 80);
    const inputmode = getAttr(el, 'inputmode').toLowerCase();
    const maxlength = parseInt(getAttr(el, 'maxlength'), 10) || 0;
    const hay = [name, label, ac, getAttr(el, 'placeholder')].join(' ');
    const texty = NONTEXT.indexOf(type) < 0;
    const password = type === 'password' || ac.indexOf('current-password') >= 0 || ac.indexOf('new-password') >= 0 || (texty && PASS.test(hay));
    const card = texty && (/\bcc-/.test(ac) || CARD.test(hay) || (inputmode === 'numeric' && maxlength >= 15 && maxlength <= 23));
    const otp = texty && (ac.indexOf('one-time-code') >= 0 || OTP.test(hay));
    return { type, name: name || null, autocomplete: ac || null, label: label || null, password, card_like: card, otp_like: otp };
  };
  const out = [];
  for (const f of qsa('form').slice(0, 30)) {
    const fields = all.filter(e => { try { return e.form === f; } catch (x) { return false; } }).slice(0, 60).map(describe);
    const raw = getAttr(f, 'action');
    let action = null;
    try { action = new URL(raw || base, base).href; } catch (e) { action = raw || null; }
    out.push({ formless: false, action, method: (getAttr(f, 'method') || 'get').toLowerCase(), fields });
  }
  const loose = all.filter(e => { try { return !e.form; } catch (x) { return true; } }).slice(0, 60);
  if (loose.length) out.push({ formless: true, action: null, method: null, fields: loose.map(describe) });
  return out;
}
"""

PAGE_INFO_JS = r"""
() => {
  const de = document.documentElement;
  const b = document.body;
  let lang = '';
  try { lang = String(Element.prototype.getAttribute.call(de, 'lang') || ''); } catch (e) {}
  return {
    lang: lang.slice(0, 35),
    width: Math.max(de ? de.scrollWidth : 0, b ? b.scrollWidth : 0),
    height: Math.max(de ? de.scrollHeight : 0, b ? b.scrollHeight : 0),
  };
}
"""

_ARABIC_RANGES = ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))


def detect_script(text: str) -> Optional[str]:
    """Dominant script of the visible text: 'arabic', 'latin', 'mixed', or None if too little text."""
    arabic = latin = 0
    for ch in text[:VISIBLE_TEXT_CHARS]:
        cp = ord(ch)
        if any(lo <= cp <= hi for lo, hi in _ARABIC_RANGES):
            arabic += 1
        elif ("a" <= ch <= "z") or ("A" <= ch <= "Z"):
            latin += 1
    total = arabic + latin
    if total < 20:
        return None
    if arabic / total >= 0.7:
        return "arabic"
    if latin / total >= 0.7:
        return "latin"
    return "mixed"


def summarize_forms(raw_forms: List[dict], frame_label: str, page_domain: Optional[str]) -> List[dict]:
    out = []
    for f in raw_forms:
        fields = f.get("fields") or []
        action = f.get("action")
        posts_to_host = posts_to = None
        action_scheme = None
        if action:
            try:
                parts = urlsplit(action)
                action_scheme = parts.scheme.lower() or None
                if action_scheme in ("http", "https"):
                    posts_to_host = (parts.hostname or "").lower() or None
                    posts_to = registered_domain(posts_to_host)
            except ValueError:
                pass
        out.append({
            "frame": frame_label,
            "formless": bool(f.get("formless")),
            "method": f.get("method"),
            "action": action,
            "action_scheme": action_scheme,
            "posts_to": posts_to,
            "posts_to_host": posts_to_host,
            "posts_to_other_domain": bool(posts_to and page_domain and posts_to != page_domain),
            "has_password": any(x.get("password") for x in fields),
            "has_card_like": any(x.get("card_like") for x in fields),
            "has_otp_like": any(x.get("otp_like") for x in fields),
            "fields": [{"type": x.get("type"), "name": x.get("name"), "autocomplete": x.get("autocomplete"),
                        "label": x.get("label"), "password": bool(x.get("password")),
                        "card_like": bool(x.get("card_like")), "otp_like": bool(x.get("otp_like"))}
                       for x in fields],
        })
    return out


def classify_nav_error(message: str, events: CaptureEvents) -> str:
    m = message.upper()
    if "ERR_BLOCKED_BY_CLIENT" in m:
        return "blocked_private_address"
    if "DOWNLOAD IS STARTING" in m:
        return "download_blocked"
    if "ERR_NAME_NOT_RESOLVED" in m:
        return "dns_failed"
    if "ERR_SOCKS_CONNECTION_FAILED" in m or "ERR_PROXY_CONNECTION_FAILED" in m:
        if any(b["layer"] == "egress-proxy" and "dns" not in b["reason"] for b in events.blocked):
            return "blocked_private_address"
        if any("dns" in b["reason"] for b in events.blocked):
            return "dns_failed"
        return "connection_failed"
    if "ERR_CERT" in m or "ERR_SSL" in m:
        return "tls_error"
    if "ERR_CONNECTION" in m or "ERR_ADDRESS" in m or "ERR_EMPTY_RESPONSE" in m:
        return "connection_failed"
    if "ERR_TOO_MANY_REDIRECTS" in m:
        return "too_many_redirects"
    if "ERR_ABORTED" in m:
        return "navigation_aborted"
    return "navigation_failed"


def cap_png(png: bytes) -> Tuple[bytes, int, int]:
    """Re-encode a screenshot no larger than 1440 x 2000 pixels (crop, never upscale)."""
    with Image.open(io.BytesIO(png)) as im:
        im.load()
        w, h = im.size
        if w > SCREENSHOT_MAX_W or h > SCREENSHOT_MAX_H:
            im = im.crop((0, 0, min(w, SCREENSHOT_MAX_W), min(h, SCREENSHOT_MAX_H)))
            buf = io.BytesIO()
            im.save(buf, format="PNG", optimize=True)
            return buf.getvalue(), im.size[0], im.size[1]
        return png, w, h


# ----------------------------------------------------------------------------------------------
# Capture
# ----------------------------------------------------------------------------------------------
class CaptureRequest(BaseModel):
    url: str
    timeout_s: float = 15
    device: str = "desktop"


class PhishpediaRequest(BaseModel):
    url: str
    screenshot_b64: str


def validate_target(url: Any) -> Tuple[str, str, int]:
    if not isinstance(url, str) or not url.strip() or len(url) > MAX_URL_LEN:
        raise ApiError(422, "bad_url", f"url must be a non-empty string of at most {MAX_URL_LEN} characters")
    url = url.strip()
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise ApiError(422, "bad_url", "url could not be parsed")
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise ApiError(422, "bad_url", "only http and https URLs can be captured")
    host = (parts.hostname or "").lower()
    if not host:
        raise ApiError(422, "bad_url", "url has no host")
    return url, host, port or (443 if scheme == "https" else 80)


async def _settle(page: Any, deadline: float) -> bool:
    """Wait for load, then network idle, until the deadline. True if the network went idle."""
    for state in ("load", "networkidle"):
        remaining_ms = int((deadline - time.monotonic()) * 1000)
        if remaining_ms <= 0:
            return False
        try:
            await page.wait_for_load_state(state, timeout=remaining_ms)
        except PlaywrightTimeoutError:
            return False
        except PlaywrightError:
            return False
    return True


async def _retry(coro_factory, attempts: int = 2, delay: float = 0.7):
    last: Optional[BaseException] = None
    for _ in range(attempts):
        try:
            return await coro_factory()
        except PlaywrightError as exc:  # e.g. "Execution context was destroyed" during a JS redirect
            last = exc
            await asyncio.sleep(delay)
    raise last  # type: ignore[misc]


async def run_capture(req: CaptureRequest, url: str, browser: Any, events: CaptureEvents) -> dict:
    t0 = time.monotonic()
    timeout_s = max(3.0, min(float(req.timeout_s), 60.0))
    profile = DEVICES[req.device]
    user_agent = profile["ua"].format(major=BROWSERS.major)
    timing: Dict[str, int] = {}
    result: Dict[str, Any] = {
        "ok": False, "requested_url": url, "device": req.device, "user_agent": user_agent,
        "captured_at": utcnow(), "note": CAPTURE_NOTE,
    }

    ctx = await browser.new_context(
        user_agent=user_agent,
        viewport=profile["viewport"],
        device_scale_factor=profile["device_scale_factor"],
        is_mobile=profile["is_mobile"],
        has_touch=profile["has_touch"],
        locale="en-AE",
        timezone_id="Asia/Dubai",
        accept_downloads=False,
        service_workers="block",
        java_script_enabled=True,
        ignore_https_errors=False,
        extra_http_headers={"Accept-Language": "en-AE,en;q=0.9,ar-AE;q=0.8,ar;q=0.7"},
    )
    try:
        guard = RouteGuard(events)
        await ctx.route("**/*", guard.handle)
        page = await ctx.new_page()

        async def _close_popup(p: Any) -> None:
            if p is not page:
                try:
                    await p.close()
                except Exception:
                    pass

        ctx.on("page", _close_popup)

        nav_requests: List[Any] = []
        sub_requests: List[str] = []

        def _on_request(r: Any) -> None:
            try:
                if r.is_navigation_request() and r.frame == page.main_frame:
                    if len(nav_requests) < MAX_CHAIN:
                        nav_requests.append(r)
                    return
            except Exception:
                pass
            if len(sub_requests) < 2000:
                sub_requests.append(r.url)

        ctx.on("request", _on_request)

        deadline = t0 + timeout_s
        nav_error: Optional[str] = None
        nav_code: Optional[str] = None
        t_nav = time.monotonic()
        try:
            await page.goto(url, wait_until="commit", timeout=int(timeout_s * 1000))
        except PlaywrightTimeoutError:
            nav_code, nav_error = "navigation_timeout", f"no response within {timeout_s:g} s"
        except PlaywrightError as exc:
            nav_error = _short(exc)
            nav_code = classify_nav_error(nav_error, events)
        timing["navigation_ms"] = int((time.monotonic() - t_nav) * 1000)

        # Redirect chain: every main-frame navigation request in order (HTTP redirects and JS/meta hops).
        async def _chain() -> Tuple[List[dict], Any]:
            hops, last_resp = [], None
            for i, r in enumerate(nav_requests):
                resp = None
                try:
                    resp = await asyncio.wait_for(r.response(), 3)
                except Exception:
                    pass
                via = "initial" if i == 0 else ("http_redirect" if r.redirected_from is not None else "navigation")
                hops.append({"url": r.url, "status": resp.status if resp else None, "via": via})
                if resp is not None:
                    last_resp = resp
            return hops, last_resp

        if nav_code is not None:
            chain, _ = await _chain()
            result.update({
                "error": {"code": nav_code, "message": nav_error},
                "redirect_chain": chain,
                "blocked_requests": events.blocked,
            })
            timing["total_ms"] = int((time.monotonic() - t0) * 1000)
            result["timing"] = timing
            return result

        t_settle = time.monotonic()
        network_idle = await _settle(page, deadline)
        timing["settle_ms"] = int((time.monotonic() - t_settle) * 1000)

        t_extract = time.monotonic()
        chain, final_resp = await _chain()
        final_url = page.url
        final_host = (urlsplit(final_url).hostname or "").lower()
        page_domain = registered_domain(final_host)

        title = ""
        try:
            title = (await _retry(lambda: page.title()))[:500]
        except Exception:
            pass
        info: Dict[str, Any] = {}
        try:
            info = await _retry(lambda: page.evaluate(PAGE_INFO_JS))
        except Exception:
            pass
        visible = ""
        try:
            visible = await _retry(lambda: page.inner_text("body", timeout=3000))
        except Exception:
            pass
        visible = "\n".join(line.strip() for line in visible.splitlines() if line.strip())

        forms: List[dict] = []
        for frame in page.frames[:MAX_FRAMES]:
            try:
                if frame.is_detached():
                    continue
                raw = await asyncio.wait_for(frame.evaluate(FORMS_JS), 4)
            except Exception:
                continue
            label = "main" if frame == page.main_frame else (safe_host(frame.url) or "frame")
            forms.extend(summarize_forms(raw or [], label, page_domain))

        external = total = 0
        for u in sub_requests:
            try:
                parts = urlsplit(u)
            except ValueError:
                continue
            if parts.scheme.lower() not in ("http", "https", "ws", "wss"):
                continue
            total += 1
            if registered_domain(parts.hostname) != page_domain:
                external += 1

        tls = None
        if final_resp is not None:
            try:
                tls = await asyncio.wait_for(final_resp.security_details(), 3)
            except Exception:
                tls = None
        timing["extract_ms"] = int((time.monotonic() - t_extract) * 1000)

        t_shot = time.monotonic()
        shot_b64 = None
        shot_meta: Dict[str, Any] = {"format": "png"}
        try:
            w = int(info.get("width") or 0)
            h = int(info.get("height") or 0)
            if w > 0 and h > 0:
                clip = {"x": 0, "y": 0, "width": min(w, SCREENSHOT_MAX_W), "height": min(h, SCREENSHOT_MAX_H)}
                png = await page.screenshot(type="png", full_page=True, clip=clip, scale="css",
                                            animations="disabled", timeout=15000)
            else:
                png = await page.screenshot(type="png", scale="css", animations="disabled", timeout=15000)
            png, sw, sh = cap_png(png)
            shot_b64 = base64.b64encode(png).decode("ascii")
            shot_meta.update({"width": sw, "height": sh, "page_width": w, "page_height": h,
                              "truncated": bool(w > SCREENSHOT_MAX_W or h > SCREENSHOT_MAX_H)})
        except Exception as exc:
            shot_meta["error"] = _short(exc)
        timing["screenshot_ms"] = int((time.monotonic() - t_shot) * 1000)

        status = None
        if final_resp is not None:
            status = final_resp.status
        result.update({
            "ok": True,
            "final_url": final_url,
            "final_ip": events.connected_ips.get(final_host),
            "redirect_chain": chain,
            "status": status,
            "title": title,
            "language": {"declared": info.get("lang") or None, "script": detect_script(title + "\n" + visible)},
            "forms": forms,
            "has_password_field": any(f["has_password"] for f in forms),
            "has_card_field": any(f["has_card_like"] for f in forms),
            "has_otp_field": any(f["has_otp_like"] for f in forms),
            "external_resource_ratio": round(external / total, 3) if total else 0.0,
            "resources": {"total": total, "external": external, "blocked": len(events.blocked)},
            "blocked_requests": events.blocked,
            "bodies_capped_hosts": events.capped_hosts,
            "visible_text": visible[:VISIBLE_TEXT_CHARS],
            "screenshot_b64": shot_b64,
            "screenshot": shot_meta,
            "tls": tls,
            "network_idle": network_idle,
        })
        timing["total_ms"] = int((time.monotonic() - t0) * 1000)
        result["timing"] = timing
        return result
    finally:
        try:
            await asyncio.wait_for(ctx.close(), 10)
        except Exception:
            pass


# ----------------------------------------------------------------------------------------------
# Phishpedia worker (a child process inside Phishpedia's own pixi environment)
# ----------------------------------------------------------------------------------------------
class PhishpediaUnavailable(Exception):
    pass


class PhishpediaWorker:
    """Runs phishpedia_worker.py with Phishpedia's Python and talks JSON lines over stdin/stdout.

    Keeping Detectron2 and PyTorch in a separate process means a crash or a memory spike in the model
    cannot take the capture service down, and the two Python environments never mix."""

    REQUIRED = ("models/rcnn_bet365.pth", "models/faster_rcnn.yaml", "models/resnetv2_rgb_new.pth.tar",
                "models/domain_map.pkl", "models/expand_targetlist", "configs.py")

    def __init__(self) -> None:
        self.state = "not_started"
        self.reason: Optional[str] = None
        self.info: Dict[str, Any] = {}
        self.proc: Optional[subprocess.Popen] = None
        self._q: "queue.Queue[dict]" = queue.Queue()
        self._lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._seq = 0
        self._restarts: List[float] = []
        self._stopping = False

    def missing(self) -> Optional[str]:
        if not os.path.isfile(PHISHPEDIA_PYTHON):
            return f"Phishpedia Python not found at {PHISHPEDIA_PYTHON}"
        if not os.path.isfile(WORKER_SCRIPT):
            return f"worker script not found at {WORKER_SCRIPT}"
        for rel in self.REQUIRED:
            if not os.path.exists(os.path.join(PHISHPEDIA_DIR, rel)):
                return f"Phishpedia file missing: {rel}"
        return None

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> None:
        with self._start_lock:
            if self.alive() and self.state in ("starting", "ready"):
                return
            reason = self.missing()
            if reason:
                self.state, self.reason = "unavailable", reason
                SVC_LOG.warning("Phishpedia unavailable: %s", reason)
                return
            self.state, self.reason = "starting", None
            self._q = queue.Queue()
            env = dict(os.environ)
            env.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
            threads = env.get("PHISHPEDIA_THREADS", "2")
            env.setdefault("OMP_NUM_THREADS", threads)
            env.setdefault("MKL_NUM_THREADS", threads)
            env["PATH"] = os.path.dirname(PHISHPEDIA_PYTHON) + os.pathsep + env.get("PATH", "")
            try:
                self.proc = subprocess.Popen(
                    [PHISHPEDIA_PYTHON, "-u", WORKER_SCRIPT], cwd=PHISHPEDIA_DIR, env=env,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None,
                    text=True, encoding="utf-8", bufsize=1)
            except OSError as exc:
                self.state, self.reason = "failed", f"could not start worker: {exc}"
                return
            proc, q = self.proc, self._q
            threading.Thread(target=self._reader, args=(proc, q, self._on_exit), daemon=True).start()
        try:
            msg = q.get(timeout=PHISHPEDIA_STARTUP_TIMEOUT_S)
        except queue.Empty:
            msg = {"ready": False, "error": "timed out while loading models"}
        if msg.get("ready"):
            self.state, self.info = "ready", msg
            SVC_LOG.info("Phishpedia ready: %s reference logos, %s brands",
                         msg.get("reference_logos"), msg.get("brands"))
        else:
            self.state = "failed"
            self.reason = str(msg.get("error") or "worker exited during start-up")[:500]
            SVC_LOG.error("Phishpedia failed to start: %s", self.reason)
            self._kill()

    @staticmethod
    def _reader(proc: subprocess.Popen, q: "queue.Queue[dict]", on_exit) -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                q.put(json.loads(line))
            except ValueError:
                continue
        q.put({"eof": True, "ready": False, "error": f"worker exited (code {proc.wait()})"})
        on_exit(proc)

    def _on_exit(self, proc: subprocess.Popen) -> None:
        """Restart a worker that died on its own while it was serving (not one we stopped or replaced)."""
        if self._stopping or proc is not self.proc or self.state != "ready":
            return
        SVC_LOG.warning("Phishpedia worker exited unexpectedly (code %s); restarting", proc.returncode)
        self._restart_later()

    def _kill(self) -> None:
        proc = self.proc
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _restart_later(self) -> None:
        now = time.monotonic()
        self._restarts = [t for t in self._restarts if now - t < 600]
        if len(self._restarts) >= 5:
            self.state, self.reason = "failed", "worker crashed 5 times in 10 minutes; restart the service"
            return
        self._restarts.append(now)
        self.state = "starting"
        threading.Thread(target=self.start, daemon=True).start()

    def stop(self) -> None:
        self._stopping = True
        self._kill()
        self.state = "stopped"

    def infer(self, url: str, shot_path: str) -> dict:
        with self._lock:
            if self.state != "ready" or not self.alive():
                raise PhishpediaUnavailable(self.reason or "worker is restarting")
            self._seq += 1
            rid = self._seq
            q = self._q  # this worker's queue; a restart creates a new one
            try:
                assert self.proc is not None and self.proc.stdin is not None
                self.proc.stdin.write(json.dumps({"id": rid, "url": url, "shot_path": shot_path}) + "\n")
                self.proc.stdin.flush()
            except (OSError, ValueError, AssertionError) as exc:
                self.state = "restarting"
                self._kill()
                self._restart_later()
                raise PhishpediaUnavailable(f"worker pipe error: {exc}")
            deadline = time.monotonic() + PHISHPEDIA_TIMEOUT_S
            while True:
                remaining = deadline - time.monotonic()
                try:
                    if remaining <= 0:
                        raise queue.Empty
                    msg = q.get(timeout=remaining)
                except queue.Empty:
                    self.state = "restarting"
                    self._kill()
                    self._restart_later()
                    raise PhishpediaUnavailable(f"no answer within {PHISHPEDIA_TIMEOUT_S:g} s; worker restarted")
                if msg.get("eof"):  # _on_exit schedules the restart
                    raise PhishpediaUnavailable("worker exited during inference; restarting")
                if msg.get("id") == rid:
                    return msg


def decode_screenshot(b64: str) -> Image.Image:
    if len(b64) > MAX_SCREENSHOT_B64:
        raise ApiError(413, "screenshot_too_large", f"screenshot_b64 is larger than {MAX_SCREENSHOT_B64} characters")
    if b64.startswith("data:"):
        b64 = b64.split(",", 1)[-1]
    try:
        raw = base64.b64decode(b64, validate=False)
    except (binascii.Error, ValueError):
        raise ApiError(422, "bad_screenshot", "screenshot_b64 is not valid base64")
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            probe.verify()
        im = Image.open(io.BytesIO(raw))
        im.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError, ValueError):
        raise ApiError(422, "bad_screenshot", "screenshot_b64 is not a readable image")
    if im.mode != "RGB":
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        im = bg
    w, h = im.size
    if w > PHISHPEDIA_MAX_W or h > PHISHPEDIA_MAX_H:  # crop keeps logo coordinates valid
        im = im.crop((0, 0, min(w, PHISHPEDIA_MAX_W), min(h, PHISHPEDIA_MAX_H)))
    return im


# ----------------------------------------------------------------------------------------------
# FastAPI app
# ----------------------------------------------------------------------------------------------
PROXY = EgressProxy(MAX_BODY_BYTES)
BROWSERS = BrowserManager(PROXY)
WORKER = PhishpediaWorker()
_CAPTURE_LOCK: Optional[asyncio.Lock] = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _CAPTURE_LOCK
    _setup_logging()
    _CAPTURE_LOCK = asyncio.Lock()
    await PROXY.start()
    SVC_LOG.info("egress proxy on 127.0.0.1:%s, body cap %s bytes per connection", PROXY.port, MAX_BODY_BYTES)
    warm = asyncio.ensure_future(BROWSERS.warm())
    threading.Thread(target=WORKER.start, daemon=True).start()
    try:
        yield
    finally:
        warm.cancel()
        WORKER.stop()
        await BROWSERS.close()
        await PROXY.stop()


app = FastAPI(title="Mirsad sandbox", version=VERSION, lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)


@app.exception_handler(ApiError)
async def _api_error(_request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status, content=exc.body())


@app.exception_handler(RequestValidationError)
async def _validation_error(_request: Request, exc: RequestValidationError):
    fields = sorted({".".join(str(p) for p in e.get("loc", ())[1:]) or "body" for e in exc.errors()})
    return JSONResponse(status_code=422, content={
        "ok": False, "error": {"code": "bad_request", "message": "invalid or missing fields: " + ", ".join(fields)}})


@app.exception_handler(Exception)
async def _unexpected(_request: Request, exc: Exception):
    SVC_LOG.exception("unexpected error")
    return JSONResponse(status_code=500, content={
        "ok": False, "error": {"code": "internal_error", "message": type(exc).__name__}})


@app.get("/health")
async def health():
    out = {
        "ok": True,
        "phishpedia": WORKER.state == "ready" and WORKER.alive(),
        "chromium": BROWSERS.is_ready(),
        "phishpedia_state": WORKER.state,
        "version": VERSION,
    }
    if WORKER.reason and not out["phishpedia"]:
        out["phishpedia_reason"] = WORKER.reason
    if BROWSERS.last_error and not out["chromium"]:
        out["chromium_reason"] = BROWSERS.last_error
    log_request("health", None, "ok", chromium=out["chromium"], phishpedia=out["phishpedia"])
    return out


@app.post("/capture")
async def capture(req: CaptureRequest):
    t0 = time.monotonic()
    try:
        url, host, port = validate_target(req.url)
        if req.device not in DEVICES:
            raise ApiError(422, "bad_device", "device must be 'desktop' or 'mobile'")
        _addrs, reason = await resolve_and_check(host, port)
        if reason and "dns" in reason:
            body = {"ok": False, "requested_url": url, "error": {"code": "dns_failed", "message": reason},
                    "captured_at": utcnow(), "note": CAPTURE_NOTE,
                    "timing": {"total_ms": int((time.monotonic() - t0) * 1000)}}
            log_request("capture", url, "dns_failed", ms=body["timing"]["total_ms"])
            return body
        if reason:
            raise ApiError(403, "blocked_private_address", f"target refused: {reason}",
                           {"requested_url": url})
        assert _CAPTURE_LOCK is not None
        try:
            await asyncio.wait_for(_CAPTURE_LOCK.acquire(), CAPTURE_QUEUE_TIMEOUT_S)
        except asyncio.TimeoutError:
            raise ApiError(503, "busy", "another capture is still running; try again shortly")
        try:
            browser = await BROWSERS.get()
            BROWSERS.served += 1
            events = CaptureEvents()
            PROXY.events = events
            hard_limit = max(3.0, min(float(req.timeout_s), 60.0)) + 30.0
            try:
                body = await asyncio.wait_for(run_capture(req, url, browser, events), hard_limit)
            except asyncio.TimeoutError:
                body = {"ok": False, "requested_url": url, "captured_at": utcnow(), "note": CAPTURE_NOTE,
                        "error": {"code": "capture_timeout", "message": f"capture exceeded {hard_limit:g} s"},
                        "blocked_requests": events.blocked}
            except PlaywrightError as exc:
                await BROWSERS.close()  # a crashed browser is relaunched on the next capture
                body = {"ok": False, "requested_url": url, "captured_at": utcnow(), "note": CAPTURE_NOTE,
                        "error": {"code": "browser_error", "message": _short(exc)},
                        "blocked_requests": events.blocked}
        finally:
            PROXY.events = CaptureEvents()
            _CAPTURE_LOCK.release()
        body.setdefault("timing", {})["total_ms"] = int((time.monotonic() - t0) * 1000)
        outcome = "ok" if body.get("ok") else body.get("error", {}).get("code", "error")
        log_request("capture", url, outcome, status=body.get("status"), device=req.device,
                    blocked=len(body.get("blocked_requests") or []), ms=body["timing"]["total_ms"])
        return body
    except ApiError as exc:
        log_request("capture", req.url, exc.code, ms=int((time.monotonic() - t0) * 1000))
        raise


@app.post("/phishpedia")
async def phishpedia(req: PhishpediaRequest):
    t0 = time.monotonic()
    try:
        url, _host, _port = validate_target(req.url)
        def _recovering() -> bool:  # loading after boot, or restarting after a crash
            return WORKER.state in ("starting", "restarting") or (WORKER.state == "ready" and not WORKER.alive())

        for _ in range(60):
            if not _recovering():
                break
            await asyncio.sleep(1)
        if WORKER.state != "ready" or not WORKER.alive():
            reason = WORKER.reason or ("worker is restarting" if _recovering() else WORKER.state)
            log_request("phishpedia", url, "unavailable", state=WORKER.state)
            return {"available": False, "reason": reason, "state": WORKER.state}
        image = decode_screenshot(req.screenshot_b64)
        fd, path = tempfile.mkstemp(prefix="pp-", suffix=".png")
        try:
            with os.fdopen(fd, "wb") as fh:
                image.save(fh, format="PNG")
            try:
                msg = await asyncio.to_thread(WORKER.infer, url, path)
            except PhishpediaUnavailable as exc:
                log_request("phishpedia", url, "unavailable", ms=int((time.monotonic() - t0) * 1000))
                return {"available": False, "reason": str(exc)[:300], "state": WORKER.state}
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        elapsed = int((time.monotonic() - t0) * 1000)
        if not msg.get("ok"):
            log_request("phishpedia", url, "error", ms=elapsed)
            return {"available": True, "ok": False,
                    "error": {"code": "phishpedia_error", "message": str(msg.get("error"))[:300]},
                    "brand": None, "confidence": 0.0, "logo_box": None, "domain_matches_brand": False,
                    "elapsed_ms": elapsed}
        body = {
            "available": True,
            "ok": True,
            "brand": msg.get("brand"),
            "confidence": float(msg.get("confidence") or 0.0),
            "logo_box": msg.get("logo_box"),
            "domain_matches_brand": bool(msg.get("domain_matches_brand")),
            "phishpedia_consistent": msg.get("phishpedia_consistent"),
            "brand_domains": msg.get("brand_domains") or [],
            "verdict": msg.get("verdict"),
            "logos_detected": msg.get("logos_detected", 0),
            "threshold": msg.get("threshold"),
            "model_ms": msg.get("elapsed_ms"),
            "elapsed_ms": elapsed,
        }
        log_request("phishpedia", url, body["verdict"] or "ok", brand=body["brand"],
                    conf=round(body["confidence"], 3), ms=elapsed)
        return body
    except ApiError as exc:
        log_request("phishpedia", req.url, exc.code, ms=int((time.monotonic() - t0) * 1000))
        raise
