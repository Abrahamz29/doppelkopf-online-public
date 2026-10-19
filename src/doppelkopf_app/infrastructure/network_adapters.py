import platform
import subprocess
from dataclasses import dataclass
from ipaddress import IPv4Address

from pydantic import BaseModel, TypeAdapter, ValidationError


@dataclass(frozen=True)
class LanAddress:
    """A connected physical network and its phone-accessible server address."""

    name: str
    address: str


class _Adapter(BaseModel):
    name: str
    address: IPv4Address
    connected: bool
    physical: bool
    peers: int
    metric: int


_WINDOWS_NETWORKS = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$neighbors = @(Get-NetNeighbor -AddressFamily IPv4)
$interfaces = @(Get-NetIPInterface -AddressFamily IPv4)
$addresses = @(Get-NetIPAddress -AddressFamily IPv4)
$gateways = @(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' |
    Select-Object -ExpandProperty NextHop)
$result = @(foreach ($adapter in Get-NetAdapter -Physical) {
    if ($adapter.Status -ne 'Up') { continue }
    $iface = $interfaces | Where-Object InterfaceIndex -eq $adapter.ifIndex |
        Select-Object -First 1
    $peers = @($neighbors | Where-Object {
        $_.InterfaceIndex -eq $adapter.ifIndex -and
        $_.State -in @('Reachable', 'Stale', 'Delay', 'Probe') -and
        $_.IPAddress -notin $gateways
    }).Count
    foreach ($address in $addresses | Where-Object {
        $_.InterfaceIndex -eq $adapter.ifIndex -and $_.AddressState -eq 'Preferred'
    }) {
        [pscustomobject]@{
            name = $adapter.Name; address = $address.IPAddress
            connected = ($iface.ConnectionState -eq 'Connected'); physical = $true
            peers = $peers; metric = [int]$iface.InterfaceMetric
        }
    }
})
ConvertTo-Json -InputObject $result -Compress
"""


def parse_windows_networks(payload: str) -> tuple[LanAddress, ...]:
    """Prefer active LAN/WLAN networks with known peers, then Windows priority."""
    adapters = TypeAdapter(list[_Adapter]).validate_json(payload)
    candidates = sorted(
        (item for item in adapters
         if item.connected and item.physical and not (
             item.address.is_loopback or item.address.is_unspecified
             or item.address.is_link_local or item.address.is_multicast
         )),
        key=lambda item: (-item.peers, item.metric, item.name, str(item.address)),
    )
    return tuple(LanAddress(item.name, str(item.address)) for item in candidates)


def windows_lan_addresses() -> tuple[LanAddress, ...] | None:
    """Read connected adapters and cached neighbors without scanning the network.

    None means discovery is unavailable; an empty tuple means no suitable adapter.
    """
    if platform.system() != "Windows":
        return None
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _WINDOWS_NETWORKS],
            capture_output=True, text=True, encoding="utf-8-sig", check=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return parse_windows_networks(result.stdout)
    except (OSError, subprocess.SubprocessError, ValidationError):
        return None
