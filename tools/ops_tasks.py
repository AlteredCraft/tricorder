"""Operator workflows for the Tab5 bench: discovery, validation and commands.

Standard library only, so host tests cover it; `tools/ops.py` is the TUI on top.
Each task wraps an existing tool rather than reimplementing it.
"""
from dataclasses import dataclass, field
from datetime import datetime
import ipaddress
import json
from pathlib import Path
import socket
import subprocess

from tools.provision_device import load_config

TAB5_USB_SERIAL = 'E8:F6:0A:E2:E0:0E'
SERVICE_PORT = 8765


@dataclass(frozen=True)
class Task:
    key: str
    title: str
    summary: str


TASKS = [
    Task('wifi', 'Wi-Fi: set up the Tab5',
         'Save a Wi-Fi network and the Mac service address to the Tab5 SD card over USB, '
         'then check that the Mac can reach it.'),
]


@dataclass(frozen=True)
class WifiEnvFile:
    path: Path
    ssid: str | None
    error: str | None = None  # Never holds the password.


def wifi_env_files(root):
    """`.env.local.*` files that configure Wi-Fi (others, e.g. API keys, are skipped)."""
    found = []
    for path in sorted(Path(root).glob('.env.local.*')):
        keys = [line.split('=', 1)[0].strip() for line in path.read_text().splitlines()
                if '=' in line and not line.lstrip().startswith('#')]
        if not any(key.startswith('WIFI_') for key in keys):
            continue
        try:
            found.append(WifiEnvFile(path, load_config(path)['ssid']))
        except ValueError as error:
            found.append(WifiEnvFile(path, None, str(error)))
    return found


def tab5_port(ports):
    """Device path of the Tab5 among (device, usb_serial_number) pairs."""
    return next((device for device, serial in ports if serial == TAB5_USB_SERIAL), None)


def serial_ports():
    """(device, serial) pairs from the repo's pinned pyserial environment."""
    python = Path(__file__).resolve().parents[1]/'.tools/python-env/bin/python'
    script = ('from serial.tools.list_ports import comports\n'
              'for p in comports(): print(p.device, p.serial_number or "")')
    result = subprocess.run([str(python), '-c', script], capture_output=True, text=True, timeout=10)
    return [tuple((line.split(' ', 1)+[''])[:2]) for line in result.stdout.splitlines() if line]


def _ipconfig(interface):
    result = subprocess.run(['ipconfig', 'getifaddr', interface], capture_output=True, text=True)
    return result.stdout


def mac_ipv4(lookup=_ipconfig, interfaces=('en0', 'en1', 'en2')):
    for interface in interfaces:
        address = lookup(interface).strip()
        if address:
            return address
    return None


@dataclass
class ProvisionPlan:
    endpoint: str | None
    output: Path
    argv: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def provision_plan(root, *, env_file, port, mac_ip, service_port=SERVICE_PORT, when=None):
    root = Path(root)
    stamp = (when or datetime.now()).strftime('%Y%m%d-%H%M%S')
    output = root/'.local/runs'/f'{stamp}-provision'
    errors = []
    if not env_file:
        errors.append('Choose a Wi-Fi env file')
    if not port:
        errors.append('Tab5 not found on USB')
    endpoint = None
    if not mac_ip:
        errors.append('Mac has no LAN IPv4 address')
    elif not ipaddress.ip_address(mac_ip).is_private:
        errors.append(f'Mac address {mac_ip} is not a private LAN address')
    else:
        endpoint = f'ws://{mac_ip}:{service_port}/'
    plan = ProvisionPlan(endpoint, output, errors=errors)
    if not errors:
        plan.argv = [str(root/'.tools/python-env/bin/python'), '-m', 'tools.provision_device',
                     '--env', str(env_file), '--port', port, '--endpoint', endpoint,
                     '--output', str(output)]
    return plan


def tcp_reachable(ip, port=80, timeout=3.0):
    """The Tab5 serves captures over HTTP; a refused or timed-out connect means no route."""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


@dataclass
class ProvisionResult:
    tab5_ip: str | None
    same_subnet: bool | None
    reachable: bool | None
    problems: list


def provision_result(lines, *, mac_ip, reachable=tcp_reachable):
    """Interpret provision_device's JSON event lines (it never prints secrets)."""
    saved, tab5_ip = False, None
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get('event') == 'storage_config' and event.get('source') == 'usb':
            saved = event.get('result') == 'pass'
        if event.get('event') == 'wifi_address' and saved:
            tab5_ip = event.get('ipv4')
    problems = []
    if not saved:
        problems.append('Tab5 did not confirm the new settings')
        return ProvisionResult(None, None, None, problems)
    if not tab5_ip:
        problems.append('Tab5 saved the settings but did not report a Wi-Fi address; '
                        'check the network name, password and 2.4 GHz')
        return ProvisionResult(None, None, None, problems)
    # A /24 comparison is a heuristic; hotspots and home routers normally fit it.
    same = bool(mac_ip) and (ipaddress.ip_network(f'{tab5_ip}/24', strict=False)
                             == ipaddress.ip_network(f'{mac_ip}/24', strict=False))
    if not same:
        problems.append(f'Tab5 ({tab5_ip}) and Mac ({mac_ip}) are on different subnets; '
                        'join the Mac to the same network')
    ok = reachable(tab5_ip)
    if same and not ok:
        problems.append(f'Mac cannot reach the Tab5 at {tab5_ip} '
                        '(the network may block device-to-device traffic; try a hotspot)')
    return ProvisionResult(tab5_ip, same, ok, problems)
