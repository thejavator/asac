"""Connection test for a project URL (git forge, Jira, Confluence).

Refuses non-http(s) schemes and addresses that are loopback, private or link-local, so a
project owner cannot use the portal to reach internal services (SSRF). Returns a plain
diagnosis a person can act on.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx


def _blocked(host: str) -> bool:
    try:
        addresses = [ipaddress.ip_address(host)]  # an IP literal needs no DNS lookup
    except ValueError:
        try:
            addresses = [ipaddress.ip_address(i[4][0]) for i in socket.getaddrinfo(host, None)]
        except socket.gaierror:
            return False  # reported as unreachable by the request itself
    for ip in addresses:
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return True
    return False


def probe_url(url: str) -> tuple[bool, str]:
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False, "Not a valid http or https URL."
    if _blocked(parts.hostname):
        return False, "This address is private or local; the portal does not call it."
    try:
        r = httpx.head(url, timeout=5.0, follow_redirects=False)
    except httpx.ConnectError:
        return False, "Cannot connect: check the host name and that the service is reachable."
    except httpx.TimeoutException:
        return False, "No answer within 5 seconds."
    except httpx.HTTPError as exc:
        return False, f"Request failed: {type(exc).__name__}."
    if r.status_code >= 500:
        return False, f"The service answered with an error ({r.status_code})."
    return True, f"Reachable (HTTP {r.status_code})."
