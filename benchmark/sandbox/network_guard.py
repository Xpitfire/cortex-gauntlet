"""Install a fail-closed container egress policy, drop privileges, then run the evaluator."""

from __future__ import annotations

import ipaddress
import os
import socket
import subprocess
import sys

_UID = 1000
_MAX_ALLOWED_HOSTS = 8


def _addresses(hosts: list[str]) -> tuple[list[str], list[str], list[tuple[str, str]]]:
    ipv4, ipv6, entries = set(), set(), set()
    for host in hosts:
        if not host or any(character.isspace() for character in host):
            raise ValueError("invalid allowlisted hostname")
        for family, _, _, _, sockaddr in socket.getaddrinfo(host, None):
            address = str(ipaddress.ip_address(sockaddr[0]))
            if family == socket.AF_INET:
                ipv4.add(address)
            elif family == socket.AF_INET6:
                ipv6.add(address)
            else:
                continue
            entries.add((address, host))
    return sorted(ipv4), sorted(ipv6), sorted(entries)


def _run(*argv: str) -> None:
    subprocess.run(argv, check=True, capture_output=True, text=True)


def _policy(binary: str, addresses: list[str]) -> None:
    _run(binary, "-F", "OUTPUT")
    _run(binary, "-P", "OUTPUT", "DROP")
    _run(binary, "-A", "OUTPUT", "-o", "lo", "-j", "ACCEPT")
    for address in addresses:
        _run(binary, "-A", "OUTPUT", "-d", address, "-j", "ACCEPT")


    _run(binary, "-A", "OUTPUT", "-j", "REJECT")


def _verify_egress_denied() -> None:
    with socket.socket() as probe:
        probe.settimeout(0.5)
        if probe.connect_ex(("1.1.1.1", 80)) == 0:
            raise OSError("container egress policy did not block an external connection")


def main(argv: list[str]) -> None:
    separator = argv.index("--")
    options, command = argv[:separator], argv[separator + 1 :]
    if not command or len(options) % 2 or len(options) // 2 > _MAX_ALLOWED_HOSTS:
        raise ValueError("invalid network-guard arguments")
    hosts = []
    for index in range(0, len(options), 2):
        if options[index] != "--allow-host":
            raise ValueError("unknown network-guard option")
        hosts.append(options[index + 1])
    ipv4, ipv6, entries = _addresses(hosts)
    if entries:
        with open("/etc/hosts", "a", encoding="utf-8") as hosts_file:
            hosts_file.writelines(f"{address} {host}\n" for address, host in entries)
    _policy("iptables", ipv4)
    _policy("ip6tables", ipv6)
    _verify_egress_denied()
    os.setgroups([])
    os.setgid(_UID)
    os.setuid(_UID)
    os.execvp(command[0], command)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"network guard unavailable: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(125) from exc
