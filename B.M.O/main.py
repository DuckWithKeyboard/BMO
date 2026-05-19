"""
main.py  –  B.M.O local agent orchestrator
───────────────────────────────────────────
Boot sequence:
    1. WakeWordDetector  – ONNX model
    2. Transcriber       – Faster-Whisper
    3. Brain             – Gemma 4 GGUF via llama-cpp
    4. Speaker           – LuxTTS + reference voice pre-encoded

State machine (runs only after ALL models are ready):

IDLE ──(wake word)──▶ LISTENING ──(transcript)──▶ THINKING ──(reply)──▶ SPEAKING ──▶ IDLE
                                                              └──(exit word)──▶ SPEAKING ──▶ SHUTDOWN

GUI bridge:
    A WebSocket server runs on ws://localhost:7878
    Every state transition broadcasts a JSON payload:
        { "state": "IDLE"|"LISTENING"|"THINKING"|"SPEAKING",
          "text":  "<user transcript or empty>",
          "reply": "<bmo reply or empty>" }
    The Electron renderer (or any browser tab) can connect and react.

Run:
    python main.py
"""

import asyncio
import json
import sys
import threading
import time
import traceback

import websockets
import yaml



# ── Load config ───────────────────────────────────────────────────────────

with open("config.yaml") as f:
    cfg = yaml.safe_load(f)

WS_HOST = cfg.get("gui", {}).get("host", "localhost")
WS_PORT = cfg.get("gui", {}).get("port", 7878)

# ── Exit triggers ─────────────────────────────────────────────────────────

EXIT_WORDS = {"exit", "quit", "goodbye", "bye", "shutdown", "shut down"}

def _wants_exit(text: str) -> bool:
    return any(word in text.lower() for word in EXIT_WORDS)

# ── Helpers ───────────────────────────────────────────────────────────────

def _divider(char: str = "─", width: int = 52) -> str:
    return char * width


def _boot_step(label: str):
    """
    Context manager that wraps a boot step with clear pass / fail output.
    On failure it prints the full traceback and exits with code 1 so the
    terminal never silently disappears.
    """
    import contextlib

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
            # Keep window open if launched by double-click
            input("Press ENTER to close …")
            sys.exit(1)

    return _ctx()


# ── WebSocket broadcast layer ─────────────────────────────────────────────

_ws_clients: set = set()
_ws_loop: asyncio.AbstractEventLoop | None = None


async def _ws_handler(websocket):
    _ws_clients.add(websocket)
    try:
        await websocket.wait_closed()
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


def emit(state: str, text: str = "", reply: str = "") -> None:
    _broadcast({"state": state, "text": text, "reply": reply})


# ── Boot sequence ─────────────────────────────────────────────────────────

print(_divider("═"), flush=True)
print("  B.M.O  –  loading all models, please wait …", flush=True)
print(_divider("═"), flush=True)

with _boot_step("\n[0/4] Starting GUI WebSocket bridge …"):
    _ws_thread = threading.Thread(target=_ws_thread_target, daemon=True)
    _ws_thread.start()
    time.sleep(0.5)

# DELETE the four from-imports at the top, then change the boot steps to:

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

with _boot_step("[4/4] Brain (Gemma 4 GGUF) …"):
    from modules.brain import Brain
    brain = Brain(cfg)
    print("      ✓ Ready\n", flush=True)

print(_divider("═"), flush=True)
print("  All systems go.  Say 'Hey BeMo' to start.", flush=True)
print(_divider("═") + "\n", flush=True)

# ── State machine ─────────────────────────────────────────────────────────

IDLE      = "IDLE"
LISTENING = "LISTENING"
THINKING  = "THINKING"
SPEAKING  = "SPEAKING"

state       = IDLE
text        = ""
reply       = ""
should_exit = False

emit(IDLE)

try:
    while True:

        # ── IDLE ─────────────────────────────────────────────────────────
        if state == IDLE:
            print("Waiting …", flush=True)
            detector.listen()
            time.sleep(cfg["wake_word"]["cooldown"])
            print("\n[Wake word detected]", flush=True)
            state = LISTENING
            emit(LISTENING)

        # ── LISTENING ────────────────────────────────────────────────────
        elif state == LISTENING:
            print("Listening …", flush=True)
            text = transcriber.record_and_transcribe()

            if text:
                print(f"You : {text}", flush=True)
                should_exit = _wants_exit(text)
                state = THINKING
                emit(THINKING, text=text)
            else:
                print("(Nothing heard — back to sleep)\n", flush=True)
                state = IDLE
                emit(IDLE)

        # ── THINKING ─────────────────────────────────────────────────────
        elif state == THINKING:
            print("B.M.O : …", end=" ", flush=True)
            reply = brain.respond(text)
            print(f"\rB.M.O : {reply}", flush=True)
            state = SPEAKING
            emit(SPEAKING, text=text, reply=reply)

        # ── SPEAKING ─────────────────────────────────────────────────────
        elif state == SPEAKING:
            speaker.speak(reply)

            if should_exit:
                print("\n" + _divider() + "\nB.M.O signing off. Goodbye!\n" + _divider(), flush=True)
                emit(IDLE)
                break

            print(_divider() + "\n", flush=True)
            state = IDLE
            emit(IDLE)

except KeyboardInterrupt:
    print("\nInterrupted — shutting down.", flush=True)

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