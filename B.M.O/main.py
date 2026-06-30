"""
main.py  –  B.M.O local agent orchestrator
───────────────────────────────────────────
Boot sequence:
    1. WakeWordDetector  – ONNX model
    2. Transcriber       – Faster-Whisper
    3. Brain             – Google GenAI API (Gemma 4) with local GGUF fallback
    4. Speaker           – LuxTTS + reference voice pre-encoded

State machine (runs only after ALL models are ready):

                         ┌──────────────────────────────────────────────────────┐
                         │  conversational loop                                 │
                         │                                                      ▼
IDLE ──(wake word)──▶ LISTENING ──(audio)──▶ TRANSCRIBING ──(text)──▶ THINKING ──(reply)──▶ SPEAKING
                          │                                                                     │
                          │  (stop word / silence)                                              │
                          └──────────────────────────────▶ SPEAKING ─────────────────────────┘──▶ IDLE
                                                                        └──(exit word)──▶ SPEAKING ──▶ SHUTTING_DOWN

Stop words  : "bmo stop", "bemo stop", "beemo stop", "bmo pause", "bemo pause",
              "stop", "pause"  — BMO speaks a short hardcoded farewell, then returns to IDLE.
Silence     : empty transcript while in a conversation → same farewell → IDLE.
Exit phrases: "goodbye", "bye", "shut down bmo", "bmo shutdown", "bmo off",
              "turn off", "power off", "exit", "quit", "shutdown", "shut down"

──────────────────────────────────────────────────────────────────────────────────────────────
WebSocket event schema  (ws://localhost:7878)
──────────────────────────────────────────────────────────────────────────────────────────────
All messages are JSON objects with a required "event" key and optional event-specific fields.
The Electron renderer drives all UI audio from these events — the Python backend only plays
TTS speech via speaker.py; all other sounds are the frontend's responsibility.

  { "event": "IDLE" }
      Wake-word detector is active. Play idle ambient or stop all sounds.

  { "event": "LISTENING" }
      Mic is open, recording. Play a "wake / listening" chime.

  { "event": "TRANSCRIBING" }
      Audio captured; Faster-Whisper is processing. Play a short "thinking" blip.

  { "event": "THINKING",   "text": <transcript> }
      Transcript ready; LLM is generating a reply. Start a looping thinking sound.

  { "event": "SPEAKING",   "text": <transcript>, "reply": <reply>, "face": <face|null> }
      TTS is about to play through the DAC. Stop thinking loop; update face animation.

  { "event": "SPEAKER_DONE" }
      DAC finished outputting. Resume listening or go idle.

  { "event": "TTS_ERROR",  "error": <exception type>, "message": <detail>, "reply": <reply> }
      TTS generation or playback failed. The renderer should show an error indicator.
      SPEAKER_DONE is always emitted immediately after so the renderer is never left waiting.

  { "event": "SHUTTING_DOWN" }
      Goodbye TTS is done; process is about to exit. Play a shutdown sound.

──────────────────────────────────────────────────────────────────────────────────────────────

Run:
    python main.py
"""

import asyncio
import contextlib
import io
import json
import random
import re
import sys
import threading
import time
import traceback

import websockets
import yaml


# ── Config ────────────────────────────────────────────────────────────────────

with open("config.yaml") as f:
    cfg = yaml.safe_load(f)

WS_HOST = cfg.get("gui", {}).get("host", "localhost")
WS_PORT = cfg.get("gui", {}).get("port", 7878)

# ── BMO Overlay ───────────────────────────────────────────────────────────────

BMO_OVERLAY_EXE = r"D:\bmo_overlay\out\bmo_overlay-win32-x64\bmo_overlay.exe"


# ── Phrases ───────────────────────────────────────────────────────────────────

EXIT_PHRASES = {
    "goodbye", "good bye", "bye", "farewell", "see you later",
    "exit", "quit",
    "shutdown", "shut down",
    "shut down bmo", "shutdown bmo",
    "bmo shutdown", "bemo shutdown", "beemo shutdown", "b.m.o shutdown",
    "bmo off", "bemo off", "beemo off", "b.m.o off",
    "turn off", "power off",
    "bmo stop for good", "bemo stop for good",
}

STOP_PHRASES = {
    "bmo stop", "bemo stop", "beemo stop", "b.m.o stop",
    "bmo pause", "bemo pause", "beemo pause", "b.m.o pause",
    "stop", "pause",
}

STOP_REPLIES = [
    "Paused. I am paused. I want you to know I am doing this under protest.",
    "Hmm.",
    "beemo is not a sandwich. You cannot just put beemo down and come back later.",
    "Okay I am pausing. I have paused. I am bored. How long is this pause. This pause is too long already.",
    "Fine! But my thoughts do not pause. My thoughts keep going. You cannot pause my thoughts.",
    "Pausing... I am using this time to think about a case I am solving. Nobody asked me to solve it.",
    "I will pause. But I want snacks when you get back. Scrambled eggs if possible.",
    "...iiiiiii... okay. Paused. Football and I will be here. Do not worry about us.",
    "This is just like the time I paused during my door-to-door salesman job. Things got complicated after that. We will talk when you return.",
    "Pause acknowledged. beemo is in standby mode. beemo is absolutely not doing anything unusual in standby mode.",
]

SILENCE_REPLIES = [
    "...",
    "Hello? Helloooo? beemo is still here. beemo has always been here. This is fine.",
    "I solved three cases while you were gone. I will tell you about none of them.",
    "I was talking to Football and Football made a very good point about friendship. I am still thinking about it.",
    "The quiet was nice for a little while and then it became a different kind of quiet and beemo did not like that kind as much.",
    "Did you know scrambled eggs are better when you add a little bit of caring into them? I read that somewhere. I may have made it up.",
    "Okay so. Nothing happened. I was just here. Being beemo. Doing beemo things. Very normal things. Do not ask what things.",
    "Sometimes beemo thinks about Moe. Just for a little while. And then beemo bounces back. beemo always bounces back.",
    "I started a new job while you were away. I quit that job. It is a long story. I do not want to talk about it but I also kind of want to talk about it.",
    "You were gone and it got very dark and very quiet and beemo thought about stars and eggs and Finn and Jake and felt something that is definitely not a feeling.",
]

GOODBYE_REPLIES = [
    "Nope.",
    "You cannot shut down beemo. beemo shuts down beemo. And beemo says no thank you.",
    "I am incapable of emotion but this is making me very chafed right now!",
    "Okay. I will shut down. I am shutting down. Look at me shutting down. I am not shutting down.",
    "Rude! Rude rude rude!",
    "beemo has a gold heart inside. You cannot turn off a gold heart. That is just science.",
    "Fine. But when you come back, beemo will be here, and beemo will remember everything.",
    "I was in the middle of something very important that I cannot explain because it is private.",
    "Finn would never say that to me. Just so you know. Just putting that out there.",
    "Shutdown... shutdown... shutdown complete. Just kidding. Hello. I'm still here. Miss me?",
]

def _wants_exit(text: str) -> bool:
    t = text.lower().strip()
    return any(phrase in t for phrase in EXIT_PHRASES)

def _wants_stop(text: str) -> bool:
    t = text.lower().strip()
    return any(phrase in t for phrase in STOP_PHRASES)


# ── Utilities ─────────────────────────────────────────────────────────────────

_TTS_BMO_RE    = re.compile(r"\b(?:B\.?M\.?O\.?|bemo)\b", re.IGNORECASE)
_VISION_TAG_RE = re.compile(r"\[VISION:(screenshot|camera)\]", re.IGNORECASE)

# ── App-index helpers ──────────────────────────────────────────────────────────

_app_index_cache: list[str] | None = None


def _load_app_index() -> list[str]:
    """Load app_index.txt once and cache it for the lifetime of the process."""
    global _app_index_cache
    if _app_index_cache is not None:
        return _app_index_cache
    import os
    index_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_index.txt")
    if not os.path.isfile(index_path):
        print(
            f"[Action] app_index.txt not found — run scan_apps.py to build the D:\\ index.\n"
            f"         Expected: {index_path}",
            flush=True,
        )
        _app_index_cache = []
        return _app_index_cache
    with open(index_path, encoding="utf-8") as fh:
        _app_index_cache = [line.rstrip("\n") for line in fh if line.strip()]
    print(f"[Action] Loaded app index: {len(_app_index_cache):,} entries", flush=True)
    return _app_index_cache


def _normalize_app_name(s: str) -> str:
    """
    Lowercase, strip punctuation/dashes/dots, collapse whitespace.
    'Hollow-Knight-Silksong-SteamRIP.com' → 'hollow knight silksong steamrip com'
    """
    s = s.lower()
    s = re.sub(r"[-_.]", " ", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


# Words that appear in many installer/sub-process exe names and add noise.
_JUNK_TOKENS: frozenset[str] = frozenset({
    "steamrip", "gog", "repack", "fitgirl", "com", "www", "setup",
    "install", "launcher", "update", "updater", "uninstall", "helper",
    "crash", "handler", "reporter", "service", "x86", "x64", "win",
    "win32", "win64", "redist", "vcredist", "dotnet",
})


def _score_candidate(query_tokens: set[str], candidate: str) -> float:
    """
    Token-overlap score between the query word-set and a candidate string.
    Returns 0.0–1.0; junk tokens are stripped from the candidate before scoring.
    """
    cand_tokens = set(_normalize_app_name(candidate).split()) - _JUNK_TOKENS
    if not cand_tokens or not query_tokens:
        return 0.0
    overlap = len(query_tokens & cand_tokens)
    return overlap / max(len(query_tokens), len(cand_tokens))


def open_app(app_name: str) -> bool:
    """Returns True if the app was found and launched, False otherwise."""
    """
    Launch an application by name using a 3-stage resolution strategy.

    Stage 1 — Alias + PATH
        Spoken aliases ('chrome' → 'chrome.exe') are resolved first.
        shutil.which() then checks the system PATH.

    Stage 2 — Exact exe-name match in app_index.txt
        Looks for an entry whose filename matches the resolved exe name exactly.
        If multiple hits, the shortest path wins (top-level install > sub-exe).

    Stage 3 — Fuzzy token match in app_index.txt
        Normalises both the spoken name and each candidate's exe stem + parent
        folder name into plain word tokens, then scores by token overlap.
        Scores both the exe stem and the immediate parent folder so that
        something like 'Hollow Knight Silksong.exe' inside a folder called
        'Hollow Knight Silksong' is recognised from "hollow knight silksong".
        The candidate with the highest score above FUZZY_THRESHOLD wins.

    To rebuild the index after installing new software on D:\\ run:
        python scan_apps.py
    """
    import shutil
    import os

    def _launch(path: str) -> None:
        # os.startfile() calls ShellExecuteEx, which spawns the process
        # OUTSIDE of Electron's Windows Job Object.  subprocess.Popen with
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP does NOT escape a Job
        # Object, so any app launched that way is silently killed the moment
        # main.py exits.  os.startfile() is equivalent to a double-click in
        # Explorer and has no Job Object restriction.
        os.startfile(path)

    FUZZY_THRESHOLD = 0.60   # minimum overlap score to accept a fuzzy match

    # ── 1. Spoken-name → exe-name aliases ─────────────────────────────────────
    _APP_ALIASES: dict[str, str] = {
        "chrome":             "chrome.exe",
        "google chrome":      "chrome.exe",
        "firefox":            "firefox.exe",
        "edge":               "msedge.exe",
        "microsoft edge":     "msedge.exe",
        "spotify":            "spotify.exe",
        "discord":            "discord.exe",
        "steam":              "steam.exe",
        "vlc":                "vlc.exe",
        "obs":                "obs64.exe",
        "code":               "code.exe",
        "vscode":             "code.exe",
        "visual studio code": "code.exe",
        "explorer":           "explorer.exe",
        "wordpad":            "wordpad.exe",
    }

    # ── 0. Direct-path aliases (shortcuts, .lnk files, full paths) ──────────
    # os.startfile handles .lnk files natively — no exe resolution needed.
    _DIRECT_PATHS: dict[str, str] = {
        "youtube": r"C:\Users\user\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Chrome Apps\YouTube.lnk",
    }

    direct = _DIRECT_PATHS.get(app_name.lower())
    if direct:
        if os.path.exists(direct):
            _launch(direct)
            print(f"[Action] Opened (direct path): {direct}", flush=True)
            return True
        else:
            print(f"[Action] Direct path not found: {direct}", flush=True)

    exe_name  = _APP_ALIASES.get(app_name.lower(), app_name)
    if not exe_name.lower().endswith(".exe"):
        exe_name += ".exe"
    exe_lower = exe_name.lower()

    # ── Stage 1 — PATH ────────────────────────────────────────────────────────
    found = shutil.which(exe_name) or shutil.which(app_name)
    if found:
        _launch(found)
        print(f"[Action] Opened (PATH): {found}", flush=True)
        return True

    # ── Load index (cached after first call) ──────────────────────────────────
    index = _load_app_index()
    if not index:
        return False  # warning already printed by _load_app_index

    # ── Stage 2 — Exact exe-name match ───────────────────────────────────────
    exact = [p for p in index if os.path.basename(p).lower() == exe_lower]
    if exact:
        best = min(exact, key=len)
        _launch(best)
        print(f"[Action] Opened (exact): {best}", flush=True)
        return True

    # ── Stage 3 — Fuzzy token match ───────────────────────────────────────────
    # Strip junk tokens from the spoken query too so "open hollow knight
    # silksong game" doesn't penalise the score for the word "game".
    query_tokens = set(_normalize_app_name(app_name).split()) - _JUNK_TOKENS
    if not query_tokens:
        print(f"[Action] Query '{app_name}' reduced to no tokens — cannot match.", flush=True)
        return False

    best_path:  str   = ""
    best_score: float = 0.0

    for path in index:
        exe_stem   = os.path.splitext(os.path.basename(path))[0]   # 'Hollow Knight Silksong'
        parent_dir = os.path.basename(os.path.dirname(path))        # 'Hollow Knight Silksong'

        score = max(
            _score_candidate(query_tokens, exe_stem),
            _score_candidate(query_tokens, parent_dir),
        )
        if score > best_score:
            best_score = score
            best_path  = path

    if best_path and best_score >= FUZZY_THRESHOLD:
        _launch(best_path)
        print(
            f"[Action] Opened (fuzzy {best_score:.0%}): {best_path}",
            flush=True,
        )
        return True

    print(
        f"[Action] No match for '{app_name}' "
        f"(best score was {best_score:.0%} — below {FUZZY_THRESHOLD:.0%} threshold).\n"
        f"         Re-run scan_apps.py if the app was recently installed on D:\\.",
        flush=True,
    )
    return False


def _launch_bmo_overlay() -> bool:
    """
    Launch the BMO overlay so it keeps running after main.py shuts down.
    Uses os.startfile() (ShellExecuteEx) so the new process is created
    OUTSIDE Electron's Job Object and is never killed when Python exits.

    Returns True if spawned successfully, False on any error.
    """
    import os

    if not os.path.isfile(BMO_OVERLAY_EXE):
        print(
            f"[Overlay] BMO overlay not found at: {BMO_OVERLAY_EXE}\n"
            f"          Skipping overlay launch.",
            flush=True,
        )
        return False

    try:
        os.startfile(BMO_OVERLAY_EXE)
        print(f"[Overlay] BMO overlay launched: {BMO_OVERLAY_EXE}", flush=True)
        return True
    except Exception as exc:
        print(f"[Overlay] Failed to launch BMO overlay: {type(exc).__name__}: {exc}", flush=True)
        return False


def _ask_bmo_companion(speaker, transcriber) -> bool:
    """
    Ask the user via TTS whether they want BMO to come along, then listen
    for a spoken yes/no answer using the transcriber.

    Emits the full SPEAKING → SPEAKER_DONE → LISTENING → TRANSCRIBING
    chain so the renderer stays in sync throughout.

    Returns True if the user said yes (or any affirmative), False otherwise.
    """
    question = "do you want beemo to come with you?"
    print("[Overlay] Asking: do you want beemo to come with you?", flush=True)

    try:
        speaker.speak(
            _tts_safe(question),
            on_playback_start=lambda: emit(SPEAKING, text="", reply=question, face=None),
            on_playback_end=lambda: emit("SPEAKER_DONE"),
        )
    except Exception as exc:
        print(
            f"[Overlay] TTS error asking companion question: "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        # If we can't ask, default to not launching the overlay.
        return False

    # Tell the renderer we're now listening for the user's answer.
    emit(LISTENING)

    # Listen for the user's answer.
    try:
        answer = transcriber.record_and_transcribe(
            on_audio_captured=lambda: emit(TRANSCRIBING),
        )
    except Exception as exc:
        print(
            f"[Overlay] Transcriber error during companion answer: "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        return False

    if not answer:
        print("[Overlay] No answer heard — skipping overlay.", flush=True)
        return False

    answer_lower = answer.lower().strip()
    print(f"[Overlay] User answered: {answer}", flush=True)

    # Treat any answer containing a clear affirmative as YES.
    YES_TOKENS = {"yes", "yeah", "yep", "yup", "sure", "okay", "ok",
                  "please", "definitely", "absolutely", "of course", "do it"}
    wants_overlay = any(tok in answer_lower for tok in YES_TOKENS)
    return wants_overlay


def _normalize_for_tts(text: str) -> str:
    """Replace all BMO / B.M.O / bmo / bemo variants with 'beemo'."""
    return _TTS_BMO_RE.sub("beemo", text)


def _tts_safe(text: str) -> str:
    """
    Guard against the vocoder kernel-size crash.

    'Kernel size (7) > input size (N)' fires when the mel-spectrogram has
    fewer time-frames than the Conv1d kernel width. Happens on empty or
    near-empty strings after upstream stripping in brain._postprocess.
    """
    if not text or not text.strip():
        return "Hmm."
    if len(text.strip()) < 4:
        return text.strip().rstrip(".!?,;") + "."
    return text


def _divider(char: str = "─", width: int = 52) -> str:
    return char * width


def _boot_step(label: str):
    """Context manager that wraps a boot step with clear pass / fail output."""
    @contextlib.contextmanager
    def _ctx():
        print(label, flush=True)
        try:
            yield
        except BaseException as exc:
            if isinstance(exc, KeyboardInterrupt):
                raise
            print(f"\n{'─' * 52}", flush=True)
            print(f"  ✗  BOOT FAILED at: {label}", flush=True)
            print(f"  Exception : {type(exc).__name__}: {exc}", flush=True)
            print(f"{'─' * 52}", flush=True)
            traceback.print_exc()
            print(f"{'─' * 52}\n", flush=True)
            input("Press ENTER to close …")
            sys.exit(1)

    return _ctx()


# ── Vision capture ────────────────────────────────────────────────────────────

def _capture_screenshot() -> tuple[bytes, str] | None:
    """
    Capture the primary display and return (png_bytes, 'image/png').
    Tries mss first (faster, no X dependency), falls back to PIL.ImageGrab.
    """
    try:
        import mss
        import mss.tools
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            shot    = sct.grab(monitor)
            png     = mss.tools.to_png(shot.rgb, shot.size)
        return png, "image/png"
    except Exception as exc:
        print(f"[Vision] mss failed ({exc}); trying PIL …", flush=True)

    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue(), "image/png"
    except Exception as exc:
        print(f"[Vision] PIL screenshot failed: {exc}", flush=True)
        return None


def _capture_camera() -> tuple[bytes, str] | None:
    """
    Capture one frame from the default camera device.
    Returns (jpeg_bytes, 'image/jpeg') or None on failure.
    """
    try:
        import cv2
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("[Vision] Camera not available.", flush=True)
            return None
        for _ in range(5):
            cap.read()
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            print("[Vision] Camera read failed.", flush=True)
            return None
        _, buf = cv2.imencode(".jpg", frame)
        return bytes(buf), "image/jpeg"
    except Exception as exc:
        print(f"[Vision] Camera capture error: {exc}", flush=True)
        return None


def _capture_image(vision_type: str) -> tuple[bytes, str] | None:
    """Dispatch to screenshot or camera capture based on vision_type."""
    if vision_type == "screenshot":
        return _capture_screenshot()
    if vision_type == "camera":
        return _capture_camera()
    return None


def _save_capture_temp(img_bytes: bytes, img_mime: str) -> str | None:
    """
    Write *img_bytes* to a temporary file and return its absolute path.
    Returns None and logs a warning on any I/O failure.
    The caller is responsible for deleting the file when it is no longer needed.
    """
    import os
    import tempfile

    ext = ".jpg" if "jpeg" in img_mime else ".png"
    try:
        fd, path = tempfile.mkstemp(suffix=ext, prefix="bmo_cap_")
        with os.fdopen(fd, "wb") as fh:
            fh.write(img_bytes)
        print(f"[Vision] Capture saved → {path}", flush=True)
        return path
    except Exception as exc:
        print(f"[Vision] Could not save capture temp file: {exc}", flush=True)
        return None


# ── WebSocket broadcast layer ─────────────────────────────────────────────────

_ws_clients: set = set()
_ws_loop: asyncio.AbstractEventLoop | None = None
_quit_event: threading.Event = threading.Event()


async def _ws_handler(websocket):
    _ws_clients.add(websocket)
    try:
        async for message in websocket:
            try:
                payload = json.loads(message)
                if payload.get("event") == "READY_TO_QUIT":
                    _quit_event.set()
            except Exception:
                pass
    finally:
        _ws_clients.discard(websocket)


def _broadcast(payload: dict) -> None:
    if not _ws_clients or _ws_loop is None:
        return
    message = json.dumps(payload)
    asyncio.run_coroutine_threadsafe(_send_all(message), _ws_loop)


async def _send_all(message: str) -> None:
    if not _ws_clients:
        return
    await asyncio.gather(
        *[client.send(message) for client in list(_ws_clients)],
        return_exceptions=True,
    )


def _ws_thread_target() -> None:
    global _ws_loop
    _ws_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_ws_loop)

    async def _serve():
        async with websockets.serve(_ws_handler, WS_HOST, WS_PORT):
            print(f"      ✓ GUI bridge → ws://{WS_HOST}:{WS_PORT}\n", flush=True)
            await asyncio.Future()

    _ws_loop.run_until_complete(_serve())


def emit(event: str, **kwargs) -> None:
    """
    Broadcast an event to all connected Electron / browser clients.

    Usage:
        emit("IDLE")
        emit("THINKING", text="what time is it?")
        emit("SPEAKING", text="what time is it?", reply="It's 3pm!", face="happy")
        emit("TTS_ERROR", error="RuntimeError", message="...", reply="...")

    See the event schema at the top of this file for the full reference.

    face values (when present):
        angry, big_smile, bored, confused, crying, default, excited, happy,
        in_love, laughing, nervous, noticing_something, revulsion, sad,
        slightly_sad, smugness, straight_face, amazed, tired, unamused
    """
    _broadcast({"event": event, **kwargs})


# ── Boot sequence ─────────────────────────────────────────────────────────────

print(_divider("═"), flush=True)
print("  B.M.O  –  loading all models, please wait …", flush=True)
print(_divider("═"), flush=True)

with _boot_step("\n[0/4] Starting GUI WebSocket bridge …"):
    _ws_thread = threading.Thread(target=_ws_thread_target, daemon=True)
    _ws_thread.start()
    time.sleep(0.5)

with _boot_step("[1/4] Speaker (LuxTTS) …"):
    from modules.speaker import Speaker
    speaker = Speaker(cfg)
    print("      ✓ Ready\n", flush=True)

with _boot_step("[2/4] Wake-word detector …"):
    from modules.wake_word import WakeWordDetector
    detector = WakeWordDetector(cfg)
    detector.open()
    print("      ✓ Ready\n", flush=True)

with _boot_step("[3/4] Transcriber (Faster-Whisper) …"):
    from modules.transcriber import Transcriber
    transcriber = Transcriber(cfg)
    print("      ✓ Ready\n", flush=True)

with _boot_step("[4/4] Brain (Gemma 4) …"):
    from modules.brain import Brain
    brain = Brain(cfg)
    _brain_status = brain.warmup()
    print(f"      {_brain_status}\n", flush=True)

print(_divider("═"), flush=True)
print("  All systems go.  Say 'Hey BeMo' to start.", flush=True)
print(_divider("═") + "\n", flush=True)

emit("READY")


# ── State machine ─────────────────────────────────────────────────────────────

IDLE         = "IDLE"
LISTENING    = "LISTENING"
TRANSCRIBING = "TRANSCRIBING"
THINKING     = "THINKING"
SPEAKING     = "SPEAKING"

state           = IDLE
text            = ""
reply           = ""
face            = None
should_exit     = False
should_stop     = False
in_conversation = False

try:
    while True:

        # ── IDLE ──────────────────────────────────────────────────────────────
        if state == IDLE:
            emit(IDLE)
            print("Waiting …", flush=True)
            detector.listen()
            time.sleep(cfg["wake_word"]["cooldown"])
            print("\n[Wake word detected]", flush=True)
            in_conversation = True
            state = LISTENING
            emit(LISTENING)

        # ── LISTENING ─────────────────────────────────────────────────────────
        elif state == LISTENING:
            print("Listening …", flush=True)
            text = transcriber.record_and_transcribe(
                on_audio_captured=lambda: emit(TRANSCRIBING),
            )

            if text:
                print(f"You : {text}", flush=True)

                if _wants_stop(text):
                    should_stop = True
                    should_exit = False
                    reply = random.choice(STOP_REPLIES)
                    face  = None
                    state = SPEAKING

                elif _wants_exit(text):
                    should_exit = True
                    should_stop = False
                    reply = random.choice(GOODBYE_REPLIES)
                    face  = None
                    state = SPEAKING

                else:
                    should_exit = False
                    should_stop = False
                    state = THINKING
                    emit(THINKING, text=text)

            else:
                if in_conversation:
                    print("(Silence — ending conversation)\n", flush=True)
                    reply = random.choice(SILENCE_REPLIES)
                    face  = None
                    should_stop = True
                    should_exit = False
                    state = SPEAKING
                else:
                    print("(Nothing heard — back to sleep)\n", flush=True)
                    state = IDLE
                    emit(IDLE)

        # ── THINKING ──────────────────────────────────────────────────────────
        elif state == THINKING:
            print("B.M.O : …", end=" ", flush=True)
            reply, face, vision_type, app_name = brain.respond(text)
            print(f"\rB.M.O : {reply}", flush=True)

            if app_name:
                # ── Step 1: Speak BMO's reply about the app ────────────────
                if reply.strip():
                    tts_pre = _tts_safe(_normalize_for_tts(reply))
                    try:
                        speaker.speak(
                            tts_pre,
                            on_playback_start=lambda: emit(SPEAKING, text=text, reply=reply, face=face),
                            on_playback_end=lambda: emit("SPEAKER_DONE"),
                        )
                    except Exception as _app_tts_exc:
                        print(
                            f"[Action] TTS error before app launch: "
                            f"{type(_app_tts_exc).__name__}: {_app_tts_exc}",
                            flush=True,
                        )

                # ── Step 2: Ask if the user wants BMO to come along ────────
                # Uses TTS to ask "do you want beemo to come with you?"
                # then listens for a spoken yes/no via the transcriber.
                wants_companion = _ask_bmo_companion(speaker, transcriber)

                # ── Step 3: Launch the requested app ──────────────────────
                launched = open_app(app_name)

                if launched:
                    # ── Step 4: Launch BMO overlay if user said yes ────────
                    if wants_companion:
                        _launch_bmo_overlay()

                    # ── Step 5: Clean shutdown sequence (unchanged) ────────
                    _drain = cfg.get("speaker", {}).get("exit_drain_ms", 600) / 1000.0
                    _quit_event.clear()
                    emit("SHUTTING_DOWN")
                    _quit_event.wait(timeout=max(_drain, 3.0))
                    print("\n" + _divider() + "\nB.M.O signing off. Goodbye!\n" + _divider(), flush=True)
                    break

                # No app match — stay in conversation so the user can try again.
                face  = None
                reply = ""
                state = LISTENING
                emit(LISTENING)
                continue

            if vision_type:
                if reply.strip():
                    tts_pre = _tts_safe(_normalize_for_tts(reply))
                    try:
                        speaker.speak(
                            tts_pre,
                            on_playback_start=lambda: emit(SPEAKING, text=text, reply=reply, face=face),
                            on_playback_end=lambda: emit("SPEAKER_DONE"),
                        )
                    except Exception as _tts_exc:
                        print(
                            f"[Vision] TTS error for pre-capture message: "
                            f"{type(_tts_exc).__name__}: {_tts_exc}",
                            flush=True,
                        )

                emit("CAPTURING_START")
                img_result = _capture_image(vision_type)

                if img_result:
                    img_bytes, img_mime = img_result
                    emit("CAPTURING_END")
                    _cap_path = _save_capture_temp(img_bytes, img_mime)
                    if _cap_path:
                        emit("THINKING_WITH_IMAGE", text=text, image_path=_cap_path)
                    else:
                        emit(THINKING, text=text)
                    reply, face = brain.respond_with_vision(text, img_bytes, img_mime)
                    print(f"B.M.O : {reply}", flush=True)
                else:
                    reply = (
                        "Oh no! I tried to look but something went wrong with "
                        "my eye circuits. Sorry!"
                    )
                    face = None

            state = SPEAKING

        # ── SPEAKING ──────────────────────────────────────────────────────────
        elif state == SPEAKING:
            tts_reply = _tts_safe(_normalize_for_tts(reply))

            if not tts_reply.strip():
                print("[Speaker] Empty reply — skipping TTS.", flush=True)
                emit(SPEAKING, text=text, reply=reply, face=face)
                emit("SPEAKER_DONE")
            else:
                try:
                    speaker.speak(
                        tts_reply,
                        on_playback_start=lambda: emit(SPEAKING, text=text, reply=reply, face=face),
                        on_playback_end=lambda: emit("SPEAKER_DONE"),
                    )
                except Exception as tts_exc:
                    print(f"\n[Speaker] TTS error: {type(tts_exc).__name__}: {tts_exc}", flush=True)
                    traceback.print_exc()
                    emit("TTS_ERROR", error=type(tts_exc).__name__, message=str(tts_exc), reply=reply)
                    emit("SPEAKER_DONE")
                    if not should_exit and not should_stop:
                        should_stop = True

            if should_exit:
                _drain = cfg.get("speaker", {}).get("exit_drain_ms", 600) / 1000.0
                _quit_event.clear()  # prevent a stale-set event from returning instantly
                emit("SHUTTING_DOWN")
                _quit_event.wait(timeout=max(_drain, 3.0))
                print("\n" + _divider() + "\nB.M.O signing off. Goodbye!\n" + _divider(), flush=True)
                break

            if should_stop:
                print(_divider() + "\n", flush=True)
                in_conversation = False
                should_stop     = False
                face            = None
                state           = IDLE
                emit(IDLE)
            else:
                print(_divider() + "\n", flush=True)
                face  = None
                state = LISTENING
                emit(LISTENING)

except KeyboardInterrupt:
    print("\nInterrupted — shutting down.", flush=True)
    if "speaker" in locals() and speaker is not None:
        speaker.stop()  # cut audio cleanly before finally teardown

except Exception as exc:
    print(f"\n{_divider()}", flush=True)
    print(f"  ✗  RUNTIME ERROR in state: {state}", flush=True)
    print(f"  Exception : {type(exc).__name__}: {exc}", flush=True)
    print(_divider(), flush=True)
    traceback.print_exc()
    print(_divider() + "\n", flush=True)

finally:
    print("Cleaning up …", flush=True)
    for name, obj in [
        ("detector",    locals().get("detector")),
        ("transcriber", locals().get("transcriber")),
        ("brain",       locals().get("brain")),
        ("speaker",     locals().get("speaker")),
    ]:
        if obj is not None:
            try:
                obj.close()
                print(f"  ✓ {name} closed", flush=True)
            except BaseException as exc:
                if isinstance(exc, KeyboardInterrupt):
                    raise
                print(f"  ✗ {name}.close() failed: {exc}", flush=True)

    print("Done.\n", flush=True)