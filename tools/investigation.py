"""G-0002.01 bounded A/B contract. No provider may supply measurement values.

All deadline_ms values use the initiating device's monotonic clock. The host
must echo them; it must never compare them to a Mac clock. This reducer is the
host reference for the device integration, not evidence of device responsiveness.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import time

VERSION = 1
SPEC_REVISION = '2026-09-21'
MAX_CAPTURE_BYTES = 48000 * 3 * 4 * 2
MAX_TEXT = 2048
SETTINGS = ('format', 'sample_rate_hz', 'channels', 'frames', 'gain_db',
            'source_slot', 'physical_slot')


class ProtocolError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ProtocolError(message)


def identity(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,96}', value),
            'invalid identity')
    return value


def bounded_text(value, limit):
    require(isinstance(value, str) and 0 < len(value.strip()) <= limit
            and len(value.encode('utf-8')) <= limit, 'text outside bounds')
    return value


def integer(value, minimum, maximum):
    require(type(value) is int and minimum <= value <= maximum, 'integer outside bounds')
    return value


@dataclass(frozen=True)
class Fixture:
    question: str
    variable: str
    placement_a: str
    placement_b: str
    expected: str
    sample_rate_hz: int = 48000
    frames: int = 144000
    channels: int = 4
    gain_db: float = 24
    source_slot: int = 0
    physical_slot: str = 'farther-hole'

    def __post_init__(self):
        for key in ('question', 'variable', 'placement_a', 'placement_b', 'expected', 'physical_slot'):
            bounded_text(getattr(self, key), 512)
        require(self.placement_a != self.placement_b, 'A/B placements must differ')
        integer(self.sample_rate_hz, 48000, 48000)
        integer(self.channels, 4, 4)
        integer(self.frames, 1, 144000)
        integer(self.source_slot, 0, 3)
        require(type(self.gain_db) in (int, float) and math.isfinite(self.gain_db)
                and 0 <= self.gain_db <= 48, 'invalid requested gain')

    def to_dict(self):
        return asdict(self)

    def check(self, item):
        expected = {key: getattr(self, key) for key in SETTINGS if key != 'format'}
        expected['format'] = 'pcm_s16le'
        require(item.to_dict()['settings'] == expected, 'capture settings differ from frozen fixture')


def verify_ingress(meta, raw):
    """When supplied, independently join complete firmware ingress proofs."""
    keys = {'ingress_before', 'ingress_after', 'ingress_blocks'}
    if not keys.intersection(meta):
        return  # Existing explicitly synthetic/legacy fixtures have no driver proof.
    require(keys <= meta.keys(), 'incomplete ingress proof')
    before, after = meta['ingress_before'], meta['ingress_after']
    require(isinstance(before, dict) and isinstance(after, dict), 'invalid ingress counters')
    counters = ('read_bytes', 'dma_bytes', 'overflows', 'overwritten_bytes', 'short_reads', 'read_errors')
    for key in counters:
        integer(before.get(key), 0, 2**53-1)
        integer(after.get(key), before[key], 2**53-1)
    warmup = 0
    if 'warmup_frames' in meta or 'epoch_start_us' in meta:
        warmup = integer(meta.get('warmup_frames'), 24000, 24000)
        integer(meta.get('epoch_start_us'), 0, meta['acquisition_start_us']-1)
    extent = len(raw)+warmup*8
    require(after['read_bytes']-before['read_bytes'] == extent, 'ingress byte extent')
    require(after['dma_bytes']-before['dma_bytes'] >= extent, 'ingress DMA extent')
    require(all(before[k] == after[k] for k in counters[2:]), 'ingress driver loss/error')
    blocks = meta['ingress_blocks']
    require(isinstance(blocks, list) and 0 < len(blocks) <= 144, 'ingress proof count')
    offset = 0
    previous = meta['acquisition_start_us']
    for block in blocks:
        require(isinstance(block, dict), 'invalid ingress block')
        integer(block.get('source_start_frame'), offset, offset)
        frames = integer(block.get('frames'), 1, 1024)
        previous = integer(block.get('read_end_us'), previous, meta['acquisition_end_us'])
        require(offset+frames <= meta['frames'], 'ingress block extent')
        require(hashlib.sha256(raw[offset*8:(offset+frames)*8]).hexdigest() == block.get('sha256'),
                'ingress block digest mismatch')
        offset += frames
    require(offset == meta['frames'], 'incomplete ingress frames')


class CaptureEvidence:
    """Own checked raw bytes and snapshots; accessors never expose mutable state."""
    def __init__(self, metadata, raw, measurement):
        self._metadata = deepcopy(metadata)
        self.raw = bytes(raw)
        self._measurement = deepcopy(measurement)

    @classmethod
    def from_pcm(cls, metadata, raw):
        require(isinstance(metadata, dict), 'metadata must be an object')
        meta = deepcopy(metadata)
        for key in ('capture_id', 'boot_id', 'session_id'):
            identity(meta.get(key))
        require(meta.get('status') == 'complete', 'capture incomplete')
        require(meta.get('format') == 'pcm_s16le', 'unsupported raw format')
        integer(meta.get('sample_rate_hz'), 48000, 48000)
        integer(meta.get('channels'), 4, 4)
        frames = integer(meta.get('frames'), 1, 144000)
        slot = integer(meta.get('source_slot'), 0, 3)
        bounded_text(meta.get('physical_slot'), 512)
        gain = meta.get('gain_db')
        require(type(gain) in (int, float) and math.isfinite(gain) and 0 <= gain <= 48,
                'invalid requested gain')
        require(isinstance(raw, bytes) and len(raw) == frames * 8
                and type(meta.get('size_bytes')) is int and meta['size_bytes'] == len(raw),
                'raw byte extent mismatch')
        require(hashlib.sha256(raw).hexdigest() == meta.get('sha256'), 'raw digest mismatch')
        require(meta.get('driver_epoch_integrity') is True, 'driver epoch integrity missing')
        require(meta.get('speaker_active') is False, 'speaker must be inactive throughout measurement')
        start = integer(meta.get('acquisition_start_us'), 0, 2**53-1)
        integer(meta.get('acquisition_end_us'), start+1, 2**53-1)
        verify_ingress(meta, raw)
        # Stream four-slot frames: do not expand a full capture to millions of Python objects.
        squared = peak = clipped = 0
        for frame in struct.iter_unpack('<hhhh', raw):
            value = frame[slot]
            squared += value * value
            peak = max(peak, abs(value))
            clipped += value in (-32768, 32767)
        rms = math.sqrt(squared / frames)
        return cls(meta, raw, dict(frames=frames, rms_counts=rms, peak_counts=peak,
                                  clipped_samples=clipped,
                                  rms_dbfs=20*math.log10(rms/32768) if rms else None))

    @property
    def metadata(self):
        return deepcopy(self._metadata)

    @property
    def measurement(self):
        return deepcopy(self._measurement)

    def to_dict(self):
        meta = self._metadata
        return {**{key: meta[key] for key in ('boot_id', 'session_id', 'capture_id', 'sha256',
                                            'acquisition_start_us', 'acquisition_end_us')},
                'settings': {key: meta[key] for key in SETTINGS},
                'measurement': self.measurement}


def comparison(captures):
    if len(captures) == 1:
        return None
    a, b = (item['measurement'] for item in captures)
    valid = a['rms_counts'] > 0 and b['rms_counts'] > 0 and not (
        a['clipped_samples'] or b['clipped_samples'])
    return {'rms_delta_db': 20*math.log10(b['rms_counts']/a['rms_counts']) if valid else None,
            'status': 'measured' if valid else 'inconclusive',
            'unit': 'digital RMS dB ratio; not calibrated SPL'}


MEASURED_NUMBER = re.compile(r'([-+\u2212]?\d+(?:\.\d+)?)\s*(dBFS|dB|kHz|Hz|counts?)\b')
_UNIT_FAMILY = {'dBFS': 'db', 'dB': 'db', 'kHz': 'hz', 'Hz': 'hz', 'count': 'counts', 'counts': 'counts'}
_KEY_FAMILY = (('_dbfs', 'db'), ('_db', 'db'), ('_hz', 'hz'), ('_counts', 'counts'))


def _measured(match):
    """(unit family, value in base unit, precision in base unit) of one match."""
    token = match.group(1).replace('\u2212', '-').lstrip('+-')
    scale = 1000 if match.group(2) == 'kHz' else 1
    decimals = len(token.split('.')[1]) if '.' in token else 0
    return _UNIT_FAMILY[match.group(2)], float(token)*scale, 0.5*10**-decimals*scale+1e-9


def unbacked_numbers(text, evidence):
    """Numbers stated with a measurement unit that no host-supplied value supports.

    Allowed values come from the evidence sent to the model: numeric fields whose
    name carries the unit (rms_dbfs, rms_delta_db, gain_db, sample_rate_hz,
    rms_counts, ...) and unit-bearing numbers inside its strings (fixture text).
    A stated value may be rounded to its precision; sign is ignored.
    """
    allowed = {'db': [], 'hz': [], 'counts': []}
    def collect(value, key=''):
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, (int, float)):
            family = next((f for suffix, f in _KEY_FAMILY if key.endswith(suffix)), None)
            if family:
                allowed[family].append(abs(float(value)))
        elif isinstance(value, str):
            for match in MEASURED_NUMBER.finditer(value):
                family, number, _ = _measured(match)
                allowed[family].append(number)
        elif isinstance(value, dict):
            for name, item in value.items():
                collect(item, str(name))
        elif isinstance(value, (list, tuple)):
            for item in value:
                collect(item, key)
    collect(evidence)
    unbacked = []
    for match in MEASURED_NUMBER.finditer(text):
        family, stated, tolerance = _measured(match)
        if not any(abs(stated-value) <= tolerance for value in allowed[family]):
            unbacked.append(match.group(0))
    return unbacked


def validate_request(request):
    require(isinstance(request, dict), 'request must be an object')
    require(type(request.get('version')) is int and request['version'] == VERSION, 'protocol version')
    require(request.get('type') in ('guide', 'compare'), 'unknown request type')
    for key in ('boot_id', 'session_id', 'request_id'):
        identity(request.get(key))
    integer(request.get('deadline_ms'), 1, 2**53-1)
    fixture = Fixture(**request['fixture'])
    items = request.get('captures')
    require(isinstance(items, list) and len(items) == (1 if request['type'] == 'guide' else 2),
            'wrong capture count')
    seen = set()
    for item in items:
        require(isinstance(item, dict), 'invalid capture reference')
        capture_id = identity(item.get('capture_id'))
        require(capture_id not in seen, 'duplicate capture reference')
        seen.add(capture_id)
        require(all(item.get(k) == request[k] for k in ('boot_id','session_id')), 'capture identity mismatch')
        require(isinstance(item.get('sha256'), str) and re.fullmatch('[a-f0-9]{64}', item['sha256']), 'digest missing')
        settings = {key: getattr(fixture, key) for key in SETTINGS if key != 'format'}
        require(item.get('settings') == {'format':'pcm_s16le', **settings}, 'fixture settings mismatch')
        m = item.get('measurement', {})
        require(set(m) == {'frames','rms_counts','peak_counts','clipped_samples','rms_dbfs'}, 'measurement fields')
        integer(m['frames'], fixture.frames, fixture.frames)
        integer(m['clipped_samples'], 0, fixture.frames)
        integer(m['peak_counts'], 0, 32768)
        require(type(m['rms_counts']) in (int,float) and math.isfinite(m['rms_counts'])
                and 0 <= m['rms_counts'] <= m['peak_counts'], 'invalid RMS')
        expected_db = 20*math.log10(m['rms_counts']/32768) if m['rms_counts'] else None
        require(m['rms_dbfs'] == expected_db, 'inconsistent dBFS')
    if len(items) == 2:
        bounded_text(request.get('adjustment'),512)
        require(items[1]['acquisition_start_us'] >= items[0]['acquisition_end_us'], 'A/B windows overlap')


def validate_reply(request, reply):
    """Same contract for mock and future providers; structured values are host-owned.

Free text still needs transcript/operator review for semantic hallucinations.
"""
    validate_request(request)
    require(isinstance(reply, dict) and set(reply) == {
        'version','type','boot_id','session_id','request_id','deadline_ms',
        'capture_ids','measurements','comparison','text'}, 'reply fields')
    for key in ('version','boot_id','session_id','request_id','deadline_ms'):
        require(type(reply[key]) is type(request[key]) and reply[key] == request[key], 'reply identity/deadline mismatch')
    require(reply['type'] == ('guidance' if request['type']=='guide' else 'comparison'), 'reply type')
    require(reply['capture_ids'] == [c['capture_id'] for c in request['captures']], 'unknown capture reference')
    # JSON booleans compare equal to 0/1 in Python; compare their typed encoding.
    def encoded(value):
        try:
            return json.dumps(value, sort_keys=True, allow_nan=False)
        except (ValueError, TypeError) as error:
            raise ProtocolError('invalid structured result') from error
    require(encoded(reply['measurements']) == encoded([c['measurement'] for c in request['captures']]),
            'unbacked measurement')
    require(encoded(reply['comparison']) == encoded(comparison(request['captures'])), 'unbacked comparison')
    bounded_text(reply['text'], MAX_TEXT)
    json.dumps(reply, allow_nan=False)


class MockProvider:
    name = 'scripted-mock-v1'

    def respond(self, request):
        validate_request(request)
        captures = request['captures']
        result = comparison(captures)
        if result is None:
            a = captures[0]
            text = (f"A ({a['capture_id']}): RMS {a['measurement']['rms_counts']:.2f} digital counts. "
                    f"Now move to {request['fixture']['placement_b']}. Keep gain, source and orientation fixed. "
                    'Confirm the adjustment before recording B.')
        elif result['status'] == 'inconclusive':
            text = 'A/B retained, but clipping or silence prevents a useful RMS ratio. Repeat with a suitable signal.'
        else:
            text = (f"B versus A ({captures[1]['capture_id']} / {captures[0]['capture_id']}): "
                    f"{result['rms_delta_db']:+.2f} dB digital RMS change. "
                    'This is not calibrated sound pressure. Repeat the same positions to check consistency.')
        reply = {key: request[key] for key in ('version','boot_id','session_id','request_id','deadline_ms')}
        reply.update(type='guidance' if result is None else 'comparison',
                     capture_ids=[c['capture_id'] for c in captures],
                     measurements=[deepcopy(c['measurement']) for c in captures],
                     comparison=result, text=text)
        validate_reply(request, reply)
        return reply


class Investigation:
    """One session, two captures, one outstanding turn, no automatic retry.

Cancel/disconnect/timeout invalidate the pending request. Reconnect creates a
new instance with a fresh session ID; completed/failed sessions cannot restart.
"""
    def __init__(self, boot_id, session_id, fixture, *, clock=None, timeout_ms=15000):
        self.boot_id, self.session_id = identity(boot_id), identity(session_id)
        require(isinstance(fixture, Fixture), 'fixture required')
        self.fixture = fixture
        self.clock = clock or (lambda: time.monotonic_ns()//1000000)
        self.timeout_ms = integer(timeout_ms, 1, 60000)
        self.captures = []
        self.transitions = []
        self.adjustment = None
        self.pending = self.result = None
        self._set('idle')

    def _set(self, state):
        self.state = state
        self.transitions.append({'state':state, 'device_ms':self.clock()})

    def _state(self, *states):
        require(self.state in states, 'action invalid in current state')

    def ask(self):
        self._state('idle'); self._set('ready_a')

    def start_capture(self):
        self._state('ready_a','ready_b')
        self._set('recording_a' if self.state=='ready_a' else 'recording_b')

    def finish_capture(self, item):
        self._state('recording_a','recording_b')
        require(isinstance(item,CaptureEvidence), 'verified evidence required')
        item = CaptureEvidence.from_pcm(item.metadata, item.raw)
        meta = item.metadata
        require(meta['boot_id']==self.boot_id and meta['session_id']==self.session_id, 'capture session mismatch')
        self.fixture.check(item)
        require(len(self.captures)<2 and all(c.metadata['capture_id']!=meta['capture_id'] for c in self.captures),
                'capture capacity/duplicate')
        if self.captures:
            require(meta['acquisition_start_us']>=self.captures[0].metadata['acquisition_end_us'], 'A/B windows overlap')
        self.captures.append(item)
        self.pending = dict(version=VERSION, type='guide' if len(self.captures)==1 else 'compare',
                            boot_id=self.boot_id, session_id=self.session_id,
                            request_id=f'r{len(self.captures)}',
                            deadline_ms=self.clock()+self.timeout_ms,
                            fixture=self.fixture.to_dict(), adjustment=self.adjustment,
                            captures=[c.to_dict() for c in self.captures])
        self._set('waiting')
        return deepcopy(self.pending)

    def accept(self, reply):
        self.tick()
        self._state('waiting')
        validate_reply(self.pending, reply)
        ack = {key:reply[key] for key in ('version','boot_id','session_id','request_id')}
        ack['type'] = 'ack'
        self.result = deepcopy(reply)
        self.pending = None
        self._set('adjust' if len(self.captures)==1 else 'complete')
        return ack

    def adjust(self, text):
        self._state('adjust')
        self.adjustment = bounded_text(text,512)
        self._set('ready_b')

    def tick(self):
        if self.pending and self.clock() >= self.pending['deadline_ms']:
            self.pending = None
            self._set('incomplete')

    def cancel(self):
        self._state('idle','ready_a','recording_a','waiting','adjust','ready_b','recording_b','offline','incomplete')
        self.pending = None
        self._set('cancelled')

    def disconnect(self):
        if self.state not in ('complete','cancelled','offline','incomplete'):
            self.pending = None
            self._set('offline')


class RunArchive:
    """Exclusive private run directory; explicit two-capture and transcript budgets.

A failed write leaves partial evidence and poisons the archive. Never recycle a
run directory or silently discard a failed attempt to recover capacity.
"""
    def __init__(self, root, boot_id, session_id, fixture, *, max_bytes=2*MAX_CAPTURE_BYTES, max_events=256):
        self.boot_id, self.session_id = identity(boot_id),identity(session_id)
        self.fixture = fixture
        self.max_bytes = integer(max_bytes,1,2*MAX_CAPTURE_BYTES)
        self.max_events = integer(max_events,1,1024)
        self.used_bytes = self.events = 0
        self.seen = set()
        self.failed = False
        self.root = Path(root)
        self.root.mkdir(parents=True,exist_ok=False,mode=0o700)
        (self.root/'captures').mkdir(mode=0o700)
        manifest = dict(spec_id='G-0002.01',spec_revision=SPEC_REVISION,protocol_version=VERSION,
                        run_id=self.root.name,boot_id=boot_id,session_id=session_id,
                        created_utc=datetime.now(timezone.utc).isoformat(),fixture=fixture.to_dict(),
                        max_capture_bytes=max_bytes,max_captures=2,max_transcript_events=max_events,
                        workload='explicit-turn raw audio; camera/IMU/playback inactive during A/B',
                        scope='mock development; no handheld/live-provider acceptance',
                        clocks='device_ms/device_us are device monotonic; host_receipt_ns is Mac monotonic; do not subtract')
        (self.root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

    def store(self, item):
        require(not self.failed, 'archive has failed')
        # Reverify even if a caller retained and modified a CaptureEvidence instance.
        item = CaptureEvidence.from_pcm(item.metadata,item.raw)
        meta = item.metadata
        self.fixture.check(item)
        require(meta['boot_id']==self.boot_id and meta['session_id']==self.session_id, 'archive session mismatch')
        key = meta['capture_id']
        require(key not in self.seen and len(self.seen)<2, 'capture count capacity/duplicate')
        require(self.used_bytes+len(item.raw)<=self.max_bytes, 'capture byte capacity')
        try:
            partial = self.root/'captures'/f'{key}.partial'
            with partial.open('xb') as stream:stream.write(item.raw)
            with partial.with_suffix('.json').open('x') as stream:
                json.dump(meta,stream,allow_nan=False,indent=2)
            partial.rename(partial.with_suffix('.bin'))
        except Exception:
            self.failed = True
            raise
        self.seen.add(key);self.used_bytes+=len(item.raw)

    def load(self, capture_id):
        identity(capture_id)
        require(capture_id in self.seen, 'unknown capture')
        path = self.root/'captures'/f'{capture_id}.json'
        return CaptureEvidence.from_pcm(json.loads(path.read_text()),path.with_suffix('.bin').read_bytes())

    def record(self, event):
        require(not self.failed and self.events<self.max_events, 'transcript capacity/archive failure')
        data = json.dumps({'host_receipt_ns':time.monotonic_ns(), 'message':event},allow_nan=False)
        require(len(data.encode())<=32768, 'transcript event size')
        try:
            with (self.root/'transcript.jsonl').open('a') as stream:stream.write(data+'\n')
        except Exception:
            self.failed = True
            raise
        self.events+=1
