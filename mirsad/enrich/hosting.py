"""Where a suspicious site is hosted: its addresses and the network that announces them.

Every lookup goes through a public DNS-over-HTTPS resolver (Cloudflare first, Google second), so
neither the site nor its name servers see Mirsad's own address. The network owner comes from Team
Cymru's IP-to-ASN service, which answers DNS TXT queries. Hosting changes, so each result is stored
as a dated observation, and two cases are linked only when they were seen on the same address.
"""

from __future__ import annotations

import functools
import ipaddress
from datetime import datetime, timezone

from ..config import http_client
from .passive import _reserved

RESOLVERS = (("https://cloudflare-dns.com/dns-query", {"accept": "application/dns-json"}),
             ("https://dns.google/resolve", {}))

# Content delivery networks put thousands of unrelated sites behind the same few addresses, so a
# shared address there says nothing about who runs a site. These networks never link cases.
CDN_ASNS = {13335: "Cloudflare", 209242: "Cloudflare", 54113: "Fastly", 20940: "Akamai", 16625: "Akamai",
            15169: "Google", 396982: "Google", 8075: "Microsoft", 19551: "Imperva", 60068: "CDN77"}


def _ask(name: str, rtype: str) -> list[str] | None:
    """Answers of one type for a name, or None when no resolver answered."""
    code = {"A": 1, "TXT": 16}[rtype]
    for url, headers in RESOLVERS:
        try:
            with http_client(timeout=8) as c:
                j = c.get(url, params={"name": name, "type": rtype}, headers=headers).json()
        except Exception:
            continue
        if j.get("Status") == 0 and j.get("Answer"):
            return [a["data"].strip('"') for a in j["Answer"] if a.get("type") == code]
        if j.get("Status") == 3:  # NXDOMAIN: the name does not exist
            return []
    return None


@functools.lru_cache(maxsize=4096)
def network_of(ip: str) -> dict | None:
    """ASN, announced prefix, country, and owner name for a public IPv4 address."""
    try:
        if not ipaddress.ip_address(ip).is_global or ipaddress.ip_address(ip).version != 4:
            return None
    except ValueError:
        return None
    origin = _ask(".".join(reversed(ip.split("."))) + ".origin.asn.cymru.com", "TXT")
    if not origin:
        return None
    parts = [p.strip() for p in origin[0].split("|")]
    try:
        asn = int(parts[0].split()[0])  # an address announced by several networks lists them all
    except (ValueError, IndexError):
        return None
    name = _ask(f"AS{asn}.asn.cymru.com", "TXT")
    owner = [p.strip() for p in name[0].split("|")][-1] if name else ""
    return {"asn": asn, "prefix": parts[1] if len(parts) > 1 else "", "cc": parts[2] if len(parts) > 2 else "",
            "as_name": owner}


def short_owner(as_name: str) -> str:
    """'CLOUDFLARENET - Cloudflare, Inc., US' becomes 'Cloudflare, Inc.'."""
    s = as_name.split(" - ", 1)[-1] if " - " in as_name else as_name
    s = s.rsplit(",", 1)[0] if s.count(",") >= 1 and len(s.rsplit(",", 1)[-1].strip()) == 2 else s
    return s.strip()


@functools.lru_cache(maxsize=4096)
def lookup(host: str) -> dict | None:
    """The host's IPv4 addresses and the network of the first one, with the time of the lookup."""
    if not host or _reserved(host):
        return None
    try:
        ipaddress.ip_address(host)
        ips = [host]  # the link already names an address
    except ValueError:
        ips = _ask(host, "A")
    if not ips:
        return None
    ips = sorted(set(ips), key=lambda a: tuple(int(x) for x in a.split(".")))[:4]
    net = network_of(ips[0]) or {}
    return {"host": host, "ips": ips, "ip": ips[0], **net, "cdn": net.get("asn") in CDN_ASNS,
            "resolved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def label(h: dict) -> str:
    """Evidence line, for example 'Resolves to 203.0.113.7, AS64500 Example Hosting (NL)'."""
    s = f"Resolves to {h['ip']}"
    if len(h.get("ips", [])) > 1:
        s += f" and {len(h['ips']) - 1} more"
    if h.get("asn"):
        s += f", AS{h['asn']} {short_owner(h.get('as_name', ''))}"
        if h.get("cc"):
            s += f" ({h['cc']})"
    if h.get("cdn"):
        s += ", a content delivery network"
    return s
