"""Regla `database-destination-v1` (Fase 32, ADR-050): a qué servidor de base de datos se puede
conectar DataFlow.

Quien conecta es el servidor de DataFlow, así que un destino cualquiera serviría para llegar a
su red interna, a su propia base o a los metadatos de la nube (SSRF). `decide` es pura: recibe
el servidor, sus direcciones ya resueltas y la política, y devuelve la dirección a la que hay
que conectar o el motivo del rechazo. `resolve` es la única parte con red y la usan, por
separado, la API (para responder rápido) y el subproceso de ingesta justo antes de conectar
(la que cuenta: la resolución de la API puede haber cambiado).
"""

import ipaddress
import socket
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

RULE = "database-destination-v1"
Access = Literal["allowlist", "public"]
Refusal = Literal["DISABLED", "HOST_NOT_ALLOWED", "HOST_UNKNOWN", "HOST_PRIVATE"]
Address = ipaddress.IPv4Address | ipaddress.IPv6Address
Network = ipaddress.IPv4Network | ipaddress.IPv6Network
# IPv6 que llevan una IPv4 dentro: se juzga la IPv4 (NAT64 y 6to4; las mapeadas ::ffff:0:0/96
# las da `ipv4_mapped`).
NAT64 = ipaddress.IPv6Network("64:ff9b::/96")
SIX_TO_FOUR = ipaddress.IPv6Network("2002::/16")


@dataclass(frozen=True)
class DestinationPolicy:
    """Servidores de la lista (de confianza, aunque sean privados), modo público y redes que
    nunca se conectan (la base de DataFlow y `DATAFLOW_DATABASE_DENIED_HOSTS`, ya resueltas)."""

    allowed_hosts: tuple[str, ...] = ()
    public: bool = False
    denied: tuple[str, ...] = ()

    @property
    def enabled(self) -> bool:
        return self.public or any(h.strip() for h in self.allowed_hosts)

    def listed(self, server: str) -> bool:
        wanted = server.strip().lower()
        return any(h.strip().lower() == wanted for h in self.allowed_hosts if h.strip())

    def as_json(self) -> dict[str, Any]:
        return {
            "allowed_hosts": list(self.allowed_hosts),
            "public": self.public,
            "denied": list(self.denied),
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "DestinationPolicy":
        return cls(
            tuple(str(h) for h in data.get("allowed_hosts", [])),
            bool(data.get("public", False)),
            tuple(str(d) for d in data.get("denied", [])),
        )


@dataclass(frozen=True)
class Allowed:
    address: str
    access: Access


@dataclass(frozen=True)
class Denied:
    reason: Refusal


def embedded_ipv4(address: Address) -> ipaddress.IPv4Address | None:
    if isinstance(address, ipaddress.IPv4Address):
        return None
    if address.ipv4_mapped is not None:
        return address.ipv4_mapped
    if address in NAT64:
        return ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
    if address in SIX_TO_FOUR:
        return address.sixtofour
    return None


def is_public(value: str) -> bool:
    """Global y, si es una IPv6 con una IPv4 dentro, también esa IPv4. Lo que no se puede leer
    como dirección no es público."""
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    inner = embedded_ipv4(address)
    if inner is not None and not inner.is_global:
        return False
    return address.is_global and not address.is_multicast


def networks(values: Iterable[str]) -> list[Network]:
    found: list[Network] = []
    for value in values:
        try:
            found.append(ipaddress.ip_network(value.strip(), strict=False))
        except ValueError:
            continue
    return found


def is_denied(value: str, denied: Sequence[Network]) -> bool:
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return True
    candidates: list[Address] = [address]
    inner = embedded_ipv4(address)
    if inner is not None:
        candidates.append(inner)
    return any(c.version == n.version and c in n for c in candidates for n in denied)


def decide(server: str, addresses: Sequence[str], policy: DestinationPolicy) -> Allowed | Denied:
    """`database-destination-v1`, en este orden:

    1. sin lista ni modo público → desactivado;
    2. servidor de la lista → permitido (de confianza: no se mira el tipo de dirección);
    3. fuera de la lista sin modo público → no permitido;
    4. sin direcciones → desconocido;
    5. **alguna** dirección no pública o denegada → privado (se rechaza el nombre entero, para
       que no pueda alternar entre una dirección pública y una interna);
    6. permitido, fijado a la primera dirección."""
    if not policy.enabled:
        return Denied("DISABLED")
    if policy.listed(server):
        return Allowed(addresses[0], "allowlist") if addresses else Denied("HOST_UNKNOWN")
    if not policy.public:
        return Denied("HOST_NOT_ALLOWED")
    if not addresses:
        return Denied("HOST_UNKNOWN")
    denied = networks(policy.denied)
    if any(not is_public(a) or is_denied(a, denied) for a in addresses):
        return Denied("HOST_PRIVATE")
    return Allowed(addresses[0], "public")


def resolve(server: str, port: int) -> list[str]:
    """Direcciones A y AAAA del servidor, sin repetir y en el orden del sistema. Una dirección
    escrita tal cual se devuelve sin consultar el DNS. Sin respuesta: lista vacía."""
    try:
        return [str(ipaddress.ip_address(server))]
    except ValueError:
        pass
    try:
        found = socket.getaddrinfo(server, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        return []
    unique: list[str] = []
    for *_, sockaddr in found:
        address = str(sockaddr[0])
        if address not in unique:
            unique.append(address)
    return unique


def denied_networks(hosts: Iterable[str]) -> tuple[str, ...]:
    """Nombres o rangos CIDR propios → redes que nunca se conectan. Un nombre se resuelve (todas
    sus direcciones); uno que no se resuelve no aporta nada."""
    found: list[str] = []
    for host in hosts:
        value = host.strip()
        if not value:
            continue
        try:
            found.append(str(ipaddress.ip_network(value, strict=False)))
            continue
        except ValueError:
            pass
        for address in resolve(value, 0):
            found.append(str(ipaddress.ip_network(address.split("%", 1)[0])))
    return tuple(dict.fromkeys(found))
