"""
modules/speaker.py  –  B.M.O voice output
──────────────────────────────────────────
Wraps LuxTTS (zipvoice) so the state machine can call:

    speaker = Speaker(cfg)   # loads model + prompt cache, warms up CUDA kernels
    speaker.speak(text)      # generates + plays audio, blocks until done
    speaker.close()          # frees GPU memory

All performance knobs live in config.yaml under the `speaker:` key.
"""

import pickle

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
        self._num_steps:  int   = scfg.get("num_steps",   3)
        self._t_shift:    float = scfg.get("t_shift",     0.9)
        self._speed:      float = scfg.get("speed",       1.0)
        self._samplerate: int   = scfg.get("samplerate",  48_000)
        print(f"      num_steps    : {self._num_steps}  t_shift: {self._t_shift}  "
              f"speed: {self._speed}  samplerate: {self._samplerate}", flush=True)

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
        print(f"      prompt cache loaded  : {type(self._encoded_prompt).__name__}", flush=True)

        # ── CUDA kernel warm-up + startup announcement ────────────────────
        print("      running warmup inference …", flush=True)
        with torch.inference_mode():
            _wav = self._tts.generate_speech(
                "BMO is ready.", self._encoded_prompt, num_steps=self._num_steps,
                t_shift=self._t_shift, speed=self._speed, return_smooth=True,
            )
        torch.cuda.empty_cache()
        print("      warmup done — playing startup announcement …", flush=True)
        sd.play(_wav.numpy().squeeze(), samplerate=self._samplerate)
        sd.wait()
        print("      playback complete", flush=True)

    # ── Public API ────────────────────────────────────────────────────────

    def speak(self, text: str) -> None:
        """
        Synthesise *text* (brain output) and play it through the default
        audio device.  Blocks until playback is complete.
        """
        if not text or not text.strip():
            return

        with torch.inference_mode():
            wav = self._tts.generate_speech(
                text,
                self._encoded_prompt,
                num_steps=self._num_steps,
                t_shift=self._t_shift,
                speed=self._speed,
                return_smooth=True,
            )

        audio = wav.numpy().squeeze()
        sd.play(audio, samplerate=self._samplerate)
        sd.wait()   # blocks until the speaker finishes

    def close(self) -> None:
        """Release GPU memory held by the TTS model."""
        del self._tts
        torch.cuda.empty_cache()