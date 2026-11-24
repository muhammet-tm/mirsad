"""Short links and redirects: find where a link really leads.

Scammers hide a destination behind a URL shortener or a redirect, so Mirsad scores the destination as
well as the link it was given, and keeps the higher risk. Two mechanisms, chosen for safety:

- Short links are expanded on the host only through known shortener services (bit.ly, tinyurl.com,
  and the others in `SHORTENERS`): each request asks the shortener where the link points and reads the
  Location header, without following it. The first host that is not a shortener is never contacted
  from the host machine.
- Every other redirect (HTTP, JavaScript, or meta refresh) is observed inside the sandbox VM, whose
  capture reports the full redirect chain and the final URL.
"""

from __future__ import annotations

from urllib.parse import urljoin

from ..config import http_client
from ..features.url import SHORTENERS, registered_domain

REDIRECT_CODES = {301, 302, 303, 307, 308}


def is_short_link(url: str) -> bool:
    return registered_domain(url) in SHORTENERS


def expand_short_link(url: str, max_hops: int = 5, timeout: float = 8.0, client=None) -> tuple[str, list[str]]:
    """Follow redirects only while the current host is a known shortener. Returns (destination, chain).

    The destination is the first URL outside the shortener services, or the input when nothing
    resolves. `client` lets tests pass an httpx client with a mock transport.
    """
    chain = [url]
    current = url
    own = client is None
    c = client or http_client(timeout=timeout, follow_redirects=False)
    try:
        for _ in range(max_hops):
            if not is_short_link(current):
                break
            try:
                r = c.head(current, follow_redirects=False)
                if r.status_code not in REDIRECT_CODES:  # some shorteners refuse HEAD
                    r = c.get(current, follow_redirects=False)
            except Exception:
                break
            location = r.headers.get("location")
            if r.status_code not in REDIRECT_CODES or not location:
                break
            current = urljoin(current, location)
            chain.append(current)
    finally:
        if own:
            c.close()
    return current, chain
