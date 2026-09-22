"""Provision SD-backed Wi-Fi over the verified Tab5 USB connection; never log secrets."""
import argparse
import json
from pathlib import Path
import time


def load_config(path):
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            raise ValueError('Invalid environment assignment')
        key, value = line.split('=', 1)
        key, value = key.strip(), value.strip()
        if key in values:
            raise ValueError('Duplicate environment key')
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    ssid = values.get('WIFI_SSID', values.get('WIFI_NAME', ''))
    password = values.get('WIFI_PASSWORD')
    if not 1 <= len(ssid.encode()) <= 32 or password is None or len(password.encode()) > 63:
        raise ValueError('Expected WIFI_NAME/WIFI_SSID (1–32 bytes) and WIFI_PASSWORD (0–63 bytes)')
    return {'ssid': ssid, 'password': password}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env', type=Path, required=True)
    parser.add_argument('--port', required=True)
    parser.add_argument('--endpoint')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    config = load_config(args.env)
    if args.endpoint:
        config['endpoint'] = args.endpoint
    import serial
    from serial.tools.list_ports import comports
    if not any(p.device == args.port and p.serial_number == 'E8:F6:0A:E2:E0:0E' for p in comports()):
        raise SystemExit('Port does not match the verified Tab5 identity')
    args.output.mkdir(parents=True, exist_ok=False)
    command = b'TRICORDER_CONFIG ' + json.dumps(config).encode() + b'\n'
    if len(command) > 1024:
        raise SystemExit('Configuration exceeds the USB message bound')
    # Retain structured, non-secret events only; never raw console traffic here.
    events = []; sent = False; provisioned = False; address = None
    port = serial.Serial()
    port.port, port.baudrate, port.timeout = args.port, 115200, 0.2
    port.dtr = port.rts = False
    try:
        port.open()
        deadline = time.monotonic() + 65
        next_send = time.monotonic() + 15
        buffer = b''
        while time.monotonic() < deadline:
            if time.monotonic() >= next_send and not provisioned:
                address = None  # A boot address predating this update is not proof.
                port.write(command); port.flush(); sent = True
                next_send = time.monotonic() + 12
            buffer += port.read(4096)
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                if not line.startswith(b'TRICORDER '):
                    continue
                try:
                    event = json.loads(line[10:])
                except (ValueError, UnicodeDecodeError):
                    continue
                if event.get('event') in {'storage_ready','storage_config','wifi_address','wifi_disconnected','storage_archive','storage_selftest'}:
                    events.append(event)
                    print(json.dumps(event), flush=True)
                    if event.get('event') == 'storage_config' and sent:
                        if event.get('result') != 'pass':
                            raise RuntimeError('Device rejected SD provisioning; check the SD card and configuration format')
                        provisioned = True
                    if event.get('event') == 'wifi_address':
                        address = event
            if provisioned and address:
                break
            if len(buffer) > 65536:
                buffer = b''
        if not provisioned or not address:
            raise RuntimeError('Timed out waiting for SD provisioning and Wi-Fi address')
    finally:
        port.close()
        (args.output/'events.json').write_text(json.dumps(events, indent=2)+'\n')


if __name__ == '__main__':
    main()
