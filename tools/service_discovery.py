"""Let the device find the service on a shared Wi-Fi network without a typed address.

The device broadcasts REQUEST on UDP (the service port) after it joins a network; the
service answers from its own address on that network with the WebSocket port. Hotspot
mode does not need this: there the device takes the Mac's address from its DHCP lease.
Mirror of firmware/main/service_discovery.h.
"""
import asyncio
import re
import socket
import subprocess

REQUEST = b'TRICORDER_DISCOVER 1'
REPLY = 'TRICORDER_SERVICE 1 {port}\n'


def reply(datagram, port):
    """The answer to one datagram, or None when it is not a discovery request."""
    return REPLY.format(port=port).encode() if datagram.strip() == REQUEST else None


def local_address(peer):
    """This Mac's address on the network that reaches peer (no packet is sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect((peer, 9))
        return probe.getsockname()[0]


def mac_addresses():
    """This Mac's IPv4 addresses other than loopback, for typing one in by hand."""
    try:
        text = subprocess.run(['ifconfig'], capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        text = ''
    found = [a for a in re.findall(r'\binet (?:addr:)?(\d+\.\d+\.\d+\.\d+)', text) if not a.startswith('127.')]
    if not found:
        try:
            found = [local_address('192.0.2.1')]  # the default route's interface
        except OSError:
            pass
    return list(dict.fromkeys(found))


class Responder(asyncio.DatagramProtocol):
    def __init__(self, port, allowed, log=print):
        self.port, self.allowed, self.log = port, allowed, log
        self.transport, self.answered = None, {}

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, address):
        answer = reply(data, self.port)
        if answer is None or not self.allowed(address[0]):
            return
        self.transport.sendto(answer, address)
        try:
            mine = local_address(address[0])
        except OSError:
            mine = '?'
        # Log once per device address: it asks every few seconds until it hears back.
        if self.answered.get(address[0]) != mine:
            self.answered[address[0]] = mine
            self.log(f'Device {address[0]} found this service at ws://{mine}:{self.port}/', flush=True)


async def start_responder(port, allowed, log=print):
    """Listen on every interface: a socket bound to one address does not receive broadcasts."""
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(lambda: Responder(port, allowed, log),
                                                       local_addr=('0.0.0.0', port), family=socket.AF_INET)
    return transport
