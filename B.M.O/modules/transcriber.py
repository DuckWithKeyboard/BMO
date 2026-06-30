"""
transcriber.py
--------------
Records from the mic until either:
• silence is held for `silence_duration` seconds, OR
• the hard `max_duration` cap is hit.

Then hands the buffer to Faster-Whisper and returns the transcript string.
The WhisperModel is loaded once at construction time so the hot path is fast.

record_and_transcribe() accepts an optional `on_audio_captured` callback that
fires immediately after the recording loop ends (silence / max-duration hit),
BEFORE Faster-Whisper processes the buffer.  main.py uses this to emit the
TRANSCRIBING WebSocket event so the Electron frontend can play a "processing"
sound while the model runs.
"""

import time
import numpy as np
import pyaudio
from faster_whisper import WhisperModel

_INT16_SCALE   = 1.0 / 32768.0  # pre-computed — avoids division inside the hot loop
_MIN_AUDIO_RMS = 0.001           # below this the buffer is silence; skip model call


class Transcriber:
    def __init__(self, cfg: dict):
        tr_cfg  = cfg["transcriber"]
        aud_cfg = cfg["audio"]

        self.rate              = aud_cfg["rate"]
        self.chunk             = aud_cfg["chunk"]
        self.max_duration      = tr_cfg["max_duration"]
        self.silence_threshold = tr_cfg["silence_threshold"]
        self.silence_duration  = tr_cfg["silence_duration"]
        self.language          = tr_cfg.get("language", "en")

        # VAD params — synced to silence_duration so the recording loop and
        # Whisper's internal Silero VAD agree on what counts as silence.
        # threshold=0.35 is more sensitive than the default 0.5, which misses
        # normal mic input. speech_pad_ms=300 prevents clipping the first syllable
        # and gives abrupt utterance onsets a bit more leading context.
        self._vad_params = dict(
            threshold               = tr_cfg.get("vad_threshold", 0.35),
            min_silence_duration_ms = int(self.silence_duration * 1000),
            speech_pad_ms           = tr_cfg.get("vad_speech_pad_ms", 300),
            min_speech_duration_ms  = 100,
        )

        self._model = WhisperModel(
            tr_cfg["model_size"],
            device=tr_cfg["device"],
            compute_type=tr_cfg["compute_type"],
        )

        # Number of consecutive silent chunks required to end recording.
        # Derived from silence_duration so the threshold is always in sync with
        # the config value — no separate knob to keep in sync.
        self._silence_chunks = int(self.silence_duration * self.rate / aud_cfg["chunk"])

        self._pa   = pyaudio.PyAudio()
        self._ring = np.empty(int(self.max_duration * self.rate), dtype=np.float32)

        # Force CTranslate2 to allocate CUDA memory and load the Silero VAD
        # model now, during init, so the first real call pays no setup cost.
        self._warmup()

    # ── public API ────────────────────────────────────────────────────────

    def record_and_transcribe(self, on_audio_captured=None) -> str:
        """
        Open the mic, capture audio, transcribe, return text.
        Mic is opened and closed on every call so it never conflicts
        with the wake-word stream.

        on_audio_captured : optional zero-argument callable.
            Fired immediately after the recording loop exits (silence or
            max-duration), BEFORE Faster-Whisper processes the buffer.
            Use this to emit a TRANSCRIBING event so the frontend can play
            a processing sound while the model runs.
            If the buffer is empty (nothing recorded), this callback is
            NOT called — there is nothing to transcribe.
        """
        write_pos     = 0
        speech_seen   = False  # silence counter only starts after first speech detected
        silent_chunks = 0      # consecutive below-threshold chunks since last speech
        deadline      = time.monotonic() + self.max_duration
        ring          = self._ring

        stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk,
        )

        try:
            while time.monotonic() < deadline:
                raw   = stream.read(self.chunk, exception_on_overflow=False)
                frame = np.frombuffer(raw, dtype=np.int16)
                rms   = _rms(frame)

                end = min(write_pos + len(frame), len(ring))
                ring[write_pos:end] = (frame * _INT16_SCALE)[:end - write_pos]
                write_pos = end

                if rms > self.silence_threshold:
                    speech_seen   = True
                    silent_chunks = 0                      # reset on any speech chunk
                elif speech_seen:
                    silent_chunks += 1
                    if silent_chunks >= self._silence_chunks:  # N consecutive silent chunks → done
                        break

                if write_pos >= len(ring):
                    break

        finally:
            stream.stop_stream()
            stream.close()

        if write_pos == 0:
            return ""

        full_audio = ring[:write_pos]

        # Skip model call entirely if the buffer is essentially silent.
        # Also guards against the faster-whisper ValueError that occurs when
        # VAD removes all audio and language detection runs on an empty sequence.
        if float(np.sqrt(np.mean(full_audio.astype(np.float64) ** 2))) < _MIN_AUDIO_RMS:
            return ""

        # ── Notify caller that audio is captured and Whisper is about to run ──
        # This is the right moment for the frontend to play a "processing" sound:
        # recording is done, model inference is starting.
        if on_audio_captured is not None:
            try:
                on_audio_captured()
            except Exception:
                pass   # never let a callback crash the transcription path

        try:
            segments, _ = self._model.transcribe(
                full_audio,
                language                   = self.language,
                beam_size                  = 2,
                best_of                    = 1,
                vad_filter                 = True,
                vad_parameters             = self._vad_params,
                condition_on_previous_text = False,
                word_timestamps            = False,
                temperature                = 0.0,
                suppress_blank             = True,
                log_prob_threshold         = -1.0,
                no_speech_threshold        = 0.45,
                initial_prompt             = "Casual conversation with BMO.",
            )
            return " ".join(seg.text.strip() for seg in segments)

        except ValueError:
            # VAD stripped everything (e.g. noise-only buffer) — return empty
            # rather than propagating the crash.
            return ""

    def close(self):
        self._pa.terminate()

    # ── private ───────────────────────────────────────────────────────────

    def _warmup(self) -> None:
        """
        Run one silent inference during init so the first real call is fast.

        Two things are lazy on the very first transcribe() call:
          1. CTranslate2 CUDA memory allocation + kernel compilation (~1-2 s)
          2. Silero VAD model load into GPU memory (~200-500 ms)

        A 0.5 s 440 Hz tone is used because pure silence gets filtered by VAD
        before the encoder ever runs — the tone is loud enough to pass the VAD
        threshold and exercise the full encoder → decoder path.
        """
        t     = np.linspace(0, 0.5, int(self.rate * 0.5), endpoint=False)
        dummy = (np.sin(2 * np.pi * 440 * t) * 0.8).astype(np.float32)

        try:
            segs, _ = self._model.transcribe(
                dummy,
                language                   = self.language,
                beam_size                  = 2,
                best_of                    = 1,
                vad_filter                 = True,
                vad_parameters             = self._vad_params,
                condition_on_previous_text = False,
                word_timestamps            = False,
                temperature                = 0.0,
                suppress_blank             = True,
                log_prob_threshold         = -1.0,
                no_speech_threshold        = 0.45,
                initial_prompt             = "Casual conversation with BMO.",
            )
            list(segs)  # drain the generator — transcribe() is lazy
        except ValueError:
            pass        # VAD filtered the tone anyway; CUDA warmup still happened


# ── helpers ───────────────────────────────────────────────────────────────

def _rms(frame: np.ndarray) -> float:
    return float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)))