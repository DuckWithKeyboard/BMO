"""
test_speaker.py  –  verbose smoke-test for modules/speaker.py
──────────────────────────────────────────────────────────────
Run from the project root:
    python test_speaker.py

Prints every step so a silent exit / crash can be pinpointed.
"""

import sys
import traceback

print("=" * 60)
print("  B.M.O  Speaker – verbose test")
print("=" * 60)

# ── Step 1 : stdlib imports ───────────────────────────────────
print("\n[1/8] Importing stdlib … ", end="", flush=True)
import os, pickle
print("OK")

# ── Step 2 : torch ────────────────────────────────────────────
print("[2/8] Importing torch … ", end="", flush=True)
try:
    import torch
    print(f"OK  (version {torch.__version__})")
except Exception:
    print("FAILED")
    traceback.print_exc()
    sys.exit(1)

print(f"      CUDA available : {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"      GPU            : {torch.cuda.get_device_name(0)}")
    print(f"      VRAM free      : {torch.cuda.mem_get_info()[0] / 1e9:.2f} GB")

# ── Step 3 : sounddevice ──────────────────────────────────────
print("[3/8] Importing sounddevice … ", end="", flush=True)
try:
    import sounddevice as sd
    print("OK")
    print(f"      Default output : {sd.query_devices(kind='output')['name']}")
except Exception:
    print("FAILED")
    traceback.print_exc()
    sys.exit(1)

# ── Step 4 : zipvoice / LuxTTS ────────────────────────────────
print("[4/8] Importing zipvoice.luxvoice.LuxTTS … ", end="", flush=True)
try:
    from zipvoice.luxvoice import LuxTTS
    print("OK")
except Exception:
    print("FAILED")
    traceback.print_exc()
    sys.exit(1)

# ── Step 5 : load config ──────────────────────────────────────
print("[5/8] Loading config.yaml … ", end="", flush=True)
try:
    import yaml
    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)
    scfg = cfg.get("speaker", {})
    print("OK")
    print(f"      model_id     : {scfg.get('model_id', 'YatharthS/LuxTTS')}")
    print(f"      device       : {scfg.get('device', 'auto')}")
    print(f"      prompt_cache : {scfg.get('prompt_cache', '(not set)')}")
    print(f"      num_steps    : {scfg.get('num_steps', 3)}")
    print(f"      samplerate   : {scfg.get('samplerate', 48000)}")
except Exception:
    print("FAILED")
    traceback.print_exc()
    sys.exit(1)

# ── Step 6 : load prompt cache ────────────────────────────────
print("[6/8] Loading prompt cache … ", end="", flush=True)
try:
    prompt_path = scfg["prompt_cache"]
    if not os.path.exists(prompt_path):
        raise FileNotFoundError(f"File not found: {prompt_path}")
    with open(prompt_path, "rb") as fh:
        encoded_prompt = pickle.load(fh)
    print(f"OK  (type: {type(encoded_prompt).__name__})")
except Exception:
    print("FAILED")
    traceback.print_exc()
    sys.exit(1)

# ── Step 7 : load LuxTTS model ────────────────────────────────
device = scfg.get("device", "cuda" if torch.cuda.is_available() else "cpu")
model_id = scfg.get("model_id", "YatharthS/LuxTTS")
print(f"[7/8] Loading LuxTTS model on {device} … ", flush=True)
try:
    tts = LuxTTS(model_id, device=device)
    torch.cuda.empty_cache()
    print("      Model loaded OK")
    if torch.cuda.is_available():
        print(f"      VRAM free after load : {torch.cuda.mem_get_info()[0] / 1e9:.2f} GB")
except Exception:
    print("FAILED")
    traceback.print_exc()
    sys.exit(1)

# ── Step 8 : generate + play ──────────────────────────────────
num_steps  = scfg.get("num_steps",  3)
t_shift    = scfg.get("t_shift",    0.9)
speed      = scfg.get("speed",      1.0)
samplerate = scfg.get("samplerate", 48_000)

TEST_LINES = [
    "BMO is ready.",
    "Hello! I am BMO. The test is working.",
]

for i, line in enumerate(TEST_LINES, 1):
    print(f'\n[8/8 – line {i}/{len(TEST_LINES)}] Synthesising: "{line}"', flush=True)
    try:
        print("      generate_speech … ", end="", flush=True)
        with torch.inference_mode():
            wav = tts.generate_speech(
                line, encoded_prompt,
                num_steps=num_steps,
                t_shift=t_shift,
                speed=speed,
                return_smooth=True,
            )
        print("OK")

        audio = wav.numpy().squeeze()
        print(f"      audio shape    : {audio.shape}  dtype: {audio.dtype}")
        print(f"      duration       : {len(audio) / samplerate:.2f} s")

        print("      Playing …", end="", flush=True)
        sd.play(audio, samplerate=samplerate)
        sd.wait()
        print(" done")

    except Exception:
        print("FAILED")
        traceback.print_exc()
        sys.exit(1)

    torch.cuda.empty_cache()

# ── Cleanup ───────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  All tests passed — speaker is working correctly.")
print("=" * 60)
del tts
torch.cuda.empty_cache()