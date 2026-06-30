"""
modules/speaker.py  –  B.M.O voice output
──────────────────────────────────────────
Wraps LuxTTS (zipvoice) so the state machine can call:

    speaker = Speaker(cfg)   # loads model + prompt cache, warms up CUDA kernels
    speaker.speak(text)      # generates + plays audio, blocks until done
    speaker.close()          # frees GPU memory

All performance knobs live in config.yaml under the `speaker:` key.

config.yaml reference (all optional, defaults shown):
─────────────────────────────────────────────────────
speaker:
  device:       cuda          # or cpu
  model_id:     YatharthS/LuxTTS
  prompt_cache: path/to/cache.pkl
  num_steps:    4             # diffusion steps (4 is the sweet spot for distilled LuxTTS)
  t_shift:      0.7           # ← IMPORTANT: 0.7 is the official ZipVoice-distill baseline.
                              #   Values above ~0.8 front-load the ODE trajectory and leave
                              #   the Vocos vocoder reading a poorly resolved high-freq
                              #   spectrogram — the root cause of metallic / ringing artifacts.
  speed:        1.0           # playback speed multiplier (< 1 = slower / longer)
  samplerate:   48000

  # naturalness / envelope
  fade_in_ms:   25            # linear ramp-up  (eliminates hard click at start)
  fade_out_ms:  60            # cosine ramp-down (soft landing at end)
  # short-text guard
  min_tts_chars: 35           # texts shorter than this are right-padded with "..."
                              # LuxTTS uses character-level tokenisation (one char = one
                              # token), so each "." counts separately.  The ZipVoice
                              # duration estimator computes:
                              #   T_synthesis = T_prompt_frames × N_synth / N_prompt
                              # With a dense reference prompt (200 chars, 3 s audio),
                              # the minimum safe N_synth to clear the Vocos Conv1d kernel
                              # (size 7-8) is ~26 chars.  35 gives a comfortable margin.
                              # This was previously 12, which was insufficient.

  short_text_speed: 0.5       # speed used when the (pre-padding) text is shorter than
                              # min_tts_chars.  The official ZipVoice repo recommends
                              # --speed 0.3 for one-or-two-word utterances to guarantee
                              # enough duration for coherent synthesis.  0.5 is a gentler
                              # value that avoids the speech sounding excessively drawn-out
                              # on very short replies like "Rude." or "Okay!".

  # playback reliability
  peak_headroom: 0.95         # normalise audio so the loudest sample is at this fraction
                              # of full scale; prevents downstream clipping without
                              # changing perceived loudness meaningfully.

  # text preprocessing (Gemma/BMO model output cleaning)
  max_letter_repeat: 3        # cap consecutive identical letters at this count.
                              # "Eeeeeeeh" → "Eeh" (3 = sweet spot: the tokeniser
                              # still reads it as elongated, but never sees a run
                              # long enough to produce a degenerate token embedding).
                              # Word-level repetition ("Let's go! Let's go!") is
                              # intentional and is NOT affected by this setting.

  # expressiveness
  num_steps: 8                # raise from the distill-baseline 4 to 6–8 for noticeably
                              # richer prosody. 4 is the speed floor; 8 roughly doubles
                              # synthesis time but is still real-time on a modern GPU.
                              # Raises have no effect on t_shift safety.
"""

import pickle
import re
import threading
import time

import numpy as np
import sounddevice as sd
import torch

from zipvoice.luxvoice import LuxTTS


class Speaker:
    """Thin wrapper around LuxTTS for use inside the B.M.O state machine."""

    # ── Construction & warm-up ────────────────────────────────────────────

    def __init__(self, cfg: dict) -> None:
        scfg = cfg.get("speaker", {})

        # ── Device ────────────────────────────────────────────────────────
        self._device: str = scfg.get(
            "device", "cuda" if torch.cuda.is_available() else "cpu"
        )
        print(f"      device       : {self._device}", flush=True)

        # ── Generation hyper-params ───────────────────────────────────────
        self._num_steps:  int   = scfg.get("num_steps",  4)
        # NOTE: t_shift default is 0.7, matching the ZipVoice-distill paper baseline.
        # Do NOT raise above ~0.75 — higher values cause metallic vocoder artifacts
        # on short utterances by concentrating ODE mass at the first diffusion step.
        self._t_shift:    float = scfg.get("t_shift",    0.7)
        self._speed:      float = scfg.get("speed",      1.0)
        self._samplerate: int   = scfg.get("samplerate", 48_000)
        print(
            f"      num_steps    : {self._num_steps}  t_shift: {self._t_shift}  "
            f"speed: {self._speed}  samplerate: {self._samplerate}",
            flush=True,
        )

        # ── Envelope / naturalness params ─────────────────────────────────
        self._fade_in_ms:       float = scfg.get("fade_in_ms",       25.0)
        self._fade_out_ms:      float = scfg.get("fade_out_ms",       60.0)
        self._min_tts_chars:    int   = scfg.get("min_tts_chars",      35)
        self._short_text_speed: float = scfg.get("short_text_speed",   0.5)
        self._peak_headroom:    float = scfg.get("peak_headroom",      0.95)
        self._max_letter_repeat: int  = scfg.get("max_letter_repeat",   3)
        print(
            f"      fade_in_ms   : {self._fade_in_ms}  "
            f"fade_out_ms: {self._fade_out_ms}\n"
            f"      min_tts_chars: {self._min_tts_chars}  "
            f"short_text_speed: {self._short_text_speed}  "
            f"peak_headroom: {self._peak_headroom}  "
            f"max_letter_repeat: {self._max_letter_repeat}",
            flush=True,
        )

        # ── Model ─────────────────────────────────────────────────────────
        model_id: str = scfg.get("model_id", "YatharthS/LuxTTS")
        print(f"      loading LuxTTS ({model_id}) …", flush=True)
        self._tts = LuxTTS(model_id, device=self._device)
        torch.cuda.empty_cache()
        if torch.cuda.is_available():
            free_gb = torch.cuda.mem_get_info()[0] / 1e9
            print(f"      VRAM free after model load : {free_gb:.2f} GB", flush=True)

        # ── Reference-voice prompt ────────────────────────────────────────
        prompt_cache: str = scfg["prompt_cache"]
        print(f"      loading prompt cache : {prompt_cache}", flush=True)
        with open(prompt_cache, "rb") as fh:
            self._encoded_prompt = pickle.load(fh)
        print(
            f"      prompt cache loaded  : {type(self._encoded_prompt).__name__}",
            flush=True,
        )

        # ── CUDA kernel warm-up (output discarded) ────────────────────────
        print("      running warmup inference …", flush=True)
        with torch.inference_mode():
            _wav = self._tts.generate_speech(
                "BMO is ready.",
                self._encoded_prompt,
                num_steps=self._num_steps,
                t_shift=self._t_shift,
                speed=self._speed,
                return_smooth=True,
            )
        torch.cuda.empty_cache()
        print("      warmup done", flush=True)

        # ── Active stream handle (protected by lock for thread-safe stop) ─
        self._active_stream: sd.OutputStream | None = None
        self._stream_lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────

    def speak(self, text: str, on_playback_start=None, on_playback_end=None) -> None:
        """
        Synthesise *text* (brain output) and play it through the default
        audio device.  Blocks until the hardware DAC has finished outputting
        the last sample.

        on_playback_start: optional zero-argument callable invoked immediately
        before audio leaves the DAC.
        on_playback_end:   optional zero-argument callable invoked only after
        Pa_StopStream() has returned AND the finished_callback has fired —
        the two strongest guarantees PortAudio provides that the DAC is done.

        ── Why NOT sd.play() + sd.wait() ───────────────────────────────────
        sd.play() creates an internal callback-based stream.  When data runs
        out the callback raises CallbackStop; PortAudio marks the stream
        stopped.  sd.wait() polls Pa_IsStreamStopped() every ~10 ms and
        returns as soon as it flips True.  On Windows WASAPI that flag can
        flip while the hardware DAC still has the last buffer in flight,
        causing the tail to be physically cut off before the next state
        transition, app launch, or process exit.

        ── What we do instead ──────────────────────────────────────────────
        We open an explicit OutputStream in write mode (no user callback).
        stream.write(audio) copies ALL samples into PortAudio's ring buffer
        and returns once they have been accepted.  Exiting the 'with' block
        calls stream.stop() which maps directly to Pa_StopStream() — the
        only PortAudio primitive that "waits until all pending audio buffers
        have been played" before returning.  The finished_callback event is
        a belt-and-suspenders confirmation: per the PortAudio spec it fires
        only after all generated sample data has actually been played.

        ── Short-text speed reduction ───────────────────────────────────────
        The ZipVoice duration estimator computes synthesis length from the
        ratio of target-text tokens to prompt tokens.  Very short texts
        (< min_tts_chars) produce so few tokens that the estimated duration
        can fall below the Vocos vocoder's minimum Conv1d kernel size, yielding
        a degenerate mel-spectrogram (NaN / static).  Following the official
        ZipVoice recommendation, we set speed = short_text_speed (≤ 0.5) for
        these inputs, which multiplies the estimated duration by 1/speed and
        guarantees coherent synthesis even for single-word replies.
        """
        if not text or not text.strip():
            return

        text = self._preprocess_text(text)
        if not text:          # can be empty after stripping e.g. a bare [action]
            return

        # Decide speed BEFORE padding so we test the natural text length.
        # Any text that needs padding is by definition short enough to risk
        # degenerate synthesis; use the slower speed to extend its duration.
        _is_short = len(text) < self._min_tts_chars
        effective_speed = self._short_text_speed if _is_short else self._speed

        text = self._pad_short_text(text)

        if _is_short:
            print(
                f"[Speaker] Short text ({len(text.rstrip())} chars before pad) — "
                f"using speed={effective_speed} for coherent synthesis.",
                flush=True,
            )

        with torch.inference_mode():
            wav = self._tts.generate_speech(
                text,
                self._encoded_prompt,
                num_steps=self._num_steps,
                t_shift=self._t_shift,
                speed=effective_speed,
                return_smooth=True,
            )

        audio = self._process_audio(wav.numpy().squeeze())
        del wav
        torch.cuda.empty_cache()

        # Event set by finished_callback — fired by PortAudio only after
        # Pa_StopStream() has confirmed all buffers have been output.
        _drained = threading.Event()

        # latency='high' keeps the WASAPI host buffer large so Pa_StopStream
        # has plenty of margin to drain cleanly without glitches.
        stream = sd.OutputStream(
            samplerate=self._samplerate,
            channels=1,
            dtype="float32",
            latency="high",
            finished_callback=_drained.set,
        )

        with self._stream_lock:
            self._active_stream = stream

        try:
            stream.start()

            if on_playback_start is not None:
                on_playback_start()

            stream.write(audio)
            # All samples are now queued in PortAudio's ring buffer and the
            # hardware is actively playing them out.  This is the earliest
            # reliable signal that audio is "done" from the user's perspective —
            # fire the end callback here so SPEAKER_DONE reaches the renderer
            # in sync with the audible end of speech.
            #
            # stream.stop() (Pa_StopStream) is still called below to drain the
            # hardware buffer cleanly, but that blocking wait is intentionally
            # decoupled from the notification.
            if on_playback_end is not None:
                on_playback_end()

            # Pa_StopStream() — blocks until every queued sample has been
            # output by the hardware.  finished_callback fires before this
            # returns, so _drained is already set when we reach .wait().
            stream.stop()

        finally:
            stream.close()
            with self._stream_lock:
                self._active_stream = None

        # Belt-and-suspenders: should be a no-op since Pa_StopStream() waited,
        # but guards against any driver that fires the callback asynchronously.
        _drained.wait(timeout=5.0)

    def stop(self) -> None:
        """
        Immediately abort any in-progress audio output.

        Uses Pa_AbortStream() (via stream.abort()) which drops pending
        buffers instantly — correct behaviour for a user-initiated stop
        where we want silence now, not a graceful drain.
        """
        with self._stream_lock:
            stream = self._active_stream
        if stream is not None:
            try:
                stream.abort()
            except Exception:
                pass  # stream may have already finished naturally

    def close(self) -> None:
        """Release GPU memory held by the TTS model."""
        # Abort any stream still in progress before tearing down.
        # Note: if speak() has already returned the stream is already closed
        # and _active_stream is None, so this is a safe no-op in that case.
        with self._stream_lock:
            stream = self._active_stream
        if stream is not None:
            try:
                stream.abort()
            except Exception:
                pass
        del self._tts
        torch.cuda.empty_cache()

    def _preprocess_text(self, text: str) -> str:
        """
        Clean Gemma/BMO model output so the TTS engine only receives
        natural, speakable prose.

        Transformations applied in order
        ─────────────────────────────────
        1. Strip stage directions  [BMO tumbles down a hillside…]
           These are narrative descriptions that the model writes but should
           never be spoken.  Nested brackets are NOT expected from this model
           (the system prompt forbids them), so a non-greedy single-level
           strip is correct and avoids over-stripping.

        2. Strip XML control tags  <OPEN>spotify</OPEN>
           The BMO system prompt uses these for app-launch intents.  The
           spoken part (e.g. "Opening it right now!") is already on its own
           line before the tag and is preserved.

        3. Strip music-note symbols  ♪ ♫
           The ♪ wrapper marks sung lyrics in the model output.  The lyric
           text itself is kept — LuxTTS handles it as emphatic speech, which
           is the closest analogue without a dedicated singing model.

        4. Cap consecutive identical letters at max_letter_repeat.
           "Eeeeeeeh!" → "Eeh!"  (default cap: 3)
           The text encoder tokenises long same-letter runs into unusual
           sub-word tokens it rarely saw during training, producing flat or
           glitchy prosody.  Capping at 3 preserves the "elongated" reading
           cue without producing a degenerate token embedding.
           Word-level repetition ("Let's go! Let's go!") is a different
           linguistic structure and is intentionally left untouched.

        5. Collapse whitespace introduced by the above stripping.
        """
        # 1. Stage directions: [anything, including newlines, but not nested]
        text = re.sub(r'\[.*?\]', '', text, flags=re.DOTALL)

        # 2. XML control tags + their content  e.g. <OPEN>spotify</OPEN>
        #    The spoken part ("Opening it right now!") sits on its own line
        #    before the tag and is preserved by step 5's whitespace collapse.
        text = re.sub(r'<\w+>.*?</\w+>', '', text, flags=re.DOTALL)
        # Also strip any lone self-closing or unclosed tags the model might emit
        text = re.sub(r'<[^>]+>', '', text)

        # 3. Music-note glyphs
        text = re.sub(r'[♪♫♬♩]', '', text)

        # 4. Cap letter runs: match 4-or-more of the same letter (case-insensitive),
        #    keep only max_letter_repeat of that letter.
        cap = self._max_letter_repeat
        text = re.sub(
            r'([A-Za-z])\1{' + str(cap) + r',}',
            lambda m: m.group(1) * cap,
            text,
        )

        # 5. Normalise whitespace
        text = re.sub(r'[ \t]+', ' ', text)          # collapse horizontal space
        text = re.sub(r'\n{2,}', '\n', text)          # collapse blank lines
        text = text.strip()

        return text

    # ── Private helpers ───────────────────────────────────────────────────

    def _pad_short_text(self, text: str) -> str:
        """
        Right-pad *text* with ellipsis characters until it meets the minimum
        character threshold required for coherent ZipVoice synthesis.

        ── Why character padding works here ────────────────────────────────
        LuxTTS uses CHARACTER-LEVEL tokenisation (one char = one token).
        This is confirmed by the ZipVoice paper: "We use characters tokens
        for LibriTTS."  Each "." therefore counts as exactly one token —
        "..." produces 3 tokens, not a collapsed BPE ligature.

        The ZipVoice duration estimator computes:
            T_synthesis = T_prompt_frames × (N_synthesis / N_prompt)

        Low N_synthesis → tiny T_synthesis → the Vocos/linacodec Conv1d
        kernel (size 7–8) crashes, or the degenerate spectrogram produces
        NaN waveform samples that reach the DAC as loud static.

        The default min_tts_chars of 35 ensures N_synthesis is large enough
        to clear the kernel minimum even with a high-density reference prompt
        (e.g. 200 chars, 3 s audio → minimum safe chars ≈ 26).

        ── Why "..." rather than commas ────────────────────────────────────
        Ellipsis signals sentence-end to the text encoder, producing clean
        trailing silence.  Comma-padding distorts the prosody model's silence
        prediction on short utterances and can introduce a trailing gasp
        or click artifact.

        Note: for the padded section to sound natural rather than rushed,
        speak() also reduces the synthesis speed to short_text_speed whenever
        it detects that padding was needed.  The two levers work together:
        padding adds tokens; slower speed multiplies the per-token duration.
        """
        while len(text) < self._min_tts_chars:
            text += "..."
        return text

    def _process_audio(self, audio: np.ndarray) -> np.ndarray:
        """
        Apply peak normalisation and envelope shaping, in that order.

        Order matters:
          1. Normalise first so downstream steps operate on scaled signal.
          2. Fade-out smooths the end to zero.
        """
        audio = audio.astype(np.float32)
        audio = self._normalize_peak(audio)
        audio = self._apply_envelope(audio)
        return audio

    def _normalize_peak(self, audio: np.ndarray) -> np.ndarray:
        """
        Scale audio so the loudest sample sits at *peak_headroom* of full
        scale.  This prevents occasional hot outputs from the vocoder from
        clipping the DAC and introducing distortion, without audibly changing
        the perceived volume of normal outputs.

        ── NaN / Inf guard ─────────────────────────────────────────────────
        Degenerate synthesis (too-short spectrogram, near-zero input) can
        cause the Vocos iSTFT to emit NaN or Inf samples.  Without an
        explicit check, np.abs(NaN).max() == NaN and NaN > 1e-6 evaluates
        to False, so the raw NaN array bypasses normalisation entirely and
        hits the DAC — producing loud static.

        We intercept this by testing np.isfinite() before the peak check.
        If non-finite samples are found, a zero-filled buffer is returned
        and a warning is printed.  This makes the failure silent (literally)
        rather than catastrophic.  The underlying cause (synthesis too short)
        is addressed by the padding + short_text_speed mechanism in speak().
        """
        if not np.isfinite(audio).all():
            n_bad = int((~np.isfinite(audio)).sum())
            print(
                f"[Speaker] ⚠  {n_bad} non-finite sample(s) (NaN/Inf) in vocoder "
                f"output — substituting silence.  "
                f"(Synthesis duration was likely still too short; consider raising "
                f"min_tts_chars or lowering short_text_speed in config.yaml.)",
                flush=True,
            )
            # Return a short silence rather than nothing so the DAC
            # receives a valid buffer and the stream drains normally.
            return np.zeros(
                max(len(audio), int(self._samplerate * 0.2)), dtype=np.float32
            )

        peak = np.abs(audio).max()
        if peak > 1e-6:  # skip normalisation on effectively-silent buffers
            audio = audio * (self._peak_headroom / peak)
        return audio


    def _apply_envelope(self, audio: np.ndarray) -> np.ndarray:
        """
        Apply a linear fade-in and a cosine fade-out so playback neither
        clicks on the first sample nor cuts off abruptly at the end.

        Fade lengths are capped at 25 % of total audio so short utterances
        never produce overlapping ramps.
        """
        audio = audio.copy()
        n = len(audio)

        in_samples  = min(int(self._samplerate * self._fade_in_ms  / 1000), n // 4)
        out_samples = min(int(self._samplerate * self._fade_out_ms / 1000), n // 4)

        # linear ramp up — simple and click-free
        audio[:in_samples] *= np.linspace(0.0, 1.0, in_samples)

        # cosine ramp down — smoother than linear for the tail
        audio[n - out_samples:] *= (
            0.5 + 0.5 * np.cos(np.linspace(0.0, np.pi, out_samples))
        )

        return audio