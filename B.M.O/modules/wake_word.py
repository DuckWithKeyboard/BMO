"""
wake_word.py
------------
Lightweight wake-word detector backed by OpenWakeWord.
Streams mic audio in 80 ms chunks (1280 samples @ 16 kHz) – the frame
size OpenWakeWord expects – and returns True the moment the score for
our model crosses the configured threshold.
"""

import numpy as np
import pyaudio
from openwakeword.model import Model


class WakeWordDetector:
    def __init__(self, cfg: dict):
        ww_cfg  = cfg["wake_word"]
        aud_cfg = cfg["audio"]

        self.threshold  = ww_cfg["threshold"]
        self.cooldown   = ww_cfg["cooldown"]
        self.rate       = aud_cfg["rate"]
        self.chunk      = aud_cfg["chunk"]   # must be 1280

        # Load the ONNX (or TFLite) model – OWW auto-detects by extension
        self.model = Model(
            wakeword_models=[ww_cfg["model_path"]],
            inference_framework="onnx",
        )

        self._pa     = pyaudio.PyAudio()
        self._stream = None

    # ── public API ────────────────────────────────────────────────────────

    def open(self):
        """Open the mic stream."""
        self._stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk,
        )

    def close(self):
        """Release mic + PortAudio resources."""
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
        self._pa.terminate()

    def listen(self) -> bool:
        """
        Block until the wake word is detected, then return True.
        Call open() before this and close() when completely done.
        """
        self.model.reset()   # clear any stale state from a previous session

        while True:
            raw   = self._stream.read(self.chunk, exception_on_overflow=False)
            frame = np.frombuffer(raw, dtype=np.int16)

            # predict() returns {model_name: score}
            scores = self.model.predict(frame)

            if any(s >= self.threshold for s in scores.values()):
                return True
