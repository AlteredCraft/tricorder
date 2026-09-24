"""Mac-side speech-to-text for the spoken ask (ADR-0013), behind one interface.

A transcriber has a `name` and `async transcribe(pcm) -> str`, where pcm is
16 kHz mono s16le question audio. The default engine is local Parakeet TDT v3
(parakeet-mlx, Apple Silicon only, `tools/stt-requirements.txt`). Sending
question audio to a cloud provider needs an explicit `--stt` engine added here;
none is configured yet. Tests use fakes: importing this module loads no model.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor

DEFAULT_ENGINE = 'parakeet'
ENGINES = ('parakeet', 'none')
PARAKEET_MODEL = 'mlx-community/parakeet-tdt-0.6b-v3'


class ParakeetTranscriber:
    """Local Parakeet TDT v3. Loading and every MLX call run on one dedicated thread,
    because MLX streams are per thread and the service loop must stay free for cancel."""

    def __init__(self, model_id=PARAKEET_MODEL):
        self.model_id = model_id
        self.name = f'parakeet-mlx:{model_id.rsplit("/", 1)[-1]}'
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='stt')
        self._model = None

    def _load(self):
        if self._model is None:
            from parakeet_mlx import from_pretrained
            self._model = from_pretrained(self.model_id)
        return self._model

    def _run(self, pcm):
        import mlx.core as mx
        import numpy as np
        from parakeet_mlx.audio import get_logmel
        model = self._load()
        audio = mx.array(np.frombuffer(pcm, '<i2').astype(np.float32) / 32768)
        mel = get_logmel(audio, model.preprocessor_config)
        return model.generate(mel)[0].text.strip()

    def load(self):
        """Load and warm the model before the first question (a few seconds once)."""
        self._executor.submit(self._run, bytes(3200)).result()

    async def transcribe(self, pcm):
        return await asyncio.get_running_loop().run_in_executor(self._executor, self._run, bytes(pcm))


def load_transcriber(engine):
    if engine == 'none':
        return None
    if engine == 'parakeet':
        transcriber = ParakeetTranscriber()
        transcriber.load()
        return transcriber
    raise ValueError(f'unknown speech-to-text engine {engine!r}; choose from {ENGINES}')
