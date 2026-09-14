"""A tiny stdlib CONNECT proxy with a host allowlist — the sandbox's controlled egress for Stripe test.

Runs as a sidecar container on the sandbox's private network (copied in like the probe; stdlib only).
The candidate app reaches it via HTTPS_PROXY; it only tunnels CONNECT to allowlisted hosts (Stripe
test endpoints), refusing everything else — so the payment journey works while the app otherwise has
no egress. The allowlist matcher is pure + unit-tested; the socket tunnel is exercised in a container.
"""

from __future__ import annotations

import os
import select
import socket
import threading

# Stripe test surface needed for Stripe.js + test PaymentIntents (no real charges in test mode).
STRIPE_TEST_HOSTS = ("js.stripe.com", "api.stripe.com", "m.stripe.com", "checkout.stripe.com")


def host_allowed(host: str, allowlist: tuple[str, ...]) -> bool:
    """Exact host or dotted-suffix match (so 'api.stripe.com' allows 'api.stripe.com', not 'evil-stripe.com')."""

    host = host.strip().lower().split(":")[0]
    return any(host == a or host.endswith("." + a) for a in allowlist)


def _tunnel(a: socket.socket, b: socket.socket) -> None:
    try:
        while True:
            r, _, _ = select.select([a, b], [], [], 30)
            if not r:
                break
            for src in r:
                data = src.recv(65536)
                if not data:
                    return
                (b if src is a else a).sendall(data)
    finally:
        for s in (a, b):
            try:
                s.close()
            except OSError:
                pass


def _handle(client: socket.socket, allowlist: tuple[str, ...]) -> None:
    try:
        request = client.recv(8192).decode(errors="replace")
        line = request.split("\r\n", 1)[0]
        if not line.startswith("CONNECT "):
            client.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
            return
        target = line.split(" ")[1]
        host, _, port = target.partition(":")
        if not host_allowed(host, allowlist):
            client.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")  # egress denied (not on the allowlist)
            return
        upstream = socket.create_connection((host, int(port or 443)), timeout=10)
        client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        _tunnel(client, upstream)
    except (OSError, ValueError):
        try:
            client.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        except OSError:
            pass
        client.close()


def serve(port: int = 8888, allowlist: tuple[str, ...] = STRIPE_TEST_HOSTS) -> None:
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("0.0.0.0", port))  # noqa: S104 — sidecar on a private docker network only
    listener.listen(16)
    while True:
        client, _ = listener.accept()
        threading.Thread(target=_handle, args=(client, allowlist), daemon=True).start()


if __name__ == "__main__":
    serve(int(os.environ.get("PROXY_PORT", "8888")))
