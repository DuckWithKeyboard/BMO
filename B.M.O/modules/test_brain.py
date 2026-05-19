"""
test_brain.py
-------------
Standalone test for brain.py.
Does NOT require any other BMO module (wake word, transcriber, speaker).

Usage:
    python test_brain.py                  # interactive REPL
    python test_brain.py --backend google # force Google API only
    python test_brain.py --backend local  # force local GGUF only
    python test_brain.py --smoke          # non-interactive smoke test (CI)
"""

import argparse
import sys
import time

# ── Minimal config that mirrors config.yaml ───────────────────────────────

BASE_CFG = {
    "brain": {
        # --- Google API ---
        "google_api_key":  "AIzaSyBye2MRAceYOcfHdR5eJHF2sJezpFUmgyo",                      # or set GOOGLE_API_KEY env var
        "google_model":    "gemma-4-26b-a4b-it",
        "thinking_level":  "high",

        # --- Local GGUF fallback ---
        "model_path":      "D:\\Users\\user\\Documents\\B.M.O\\assets\\gemma-4-E2B-it-Q4_K_M.gguf",    # adjust to your path
        "modelfile_path":  "D:\\Users\\user\\Documents\\B.M.O\\assets\\modelfile.txt",          # adjust to your path
        "n_ctx":           8192,
        "n_gpu_layers":    -1,
        "thinking_tokens": 1024,
        "reply_tokens":    512,
    }
}

# ── Backend override helpers ───────────────────────────────────────────────

def _force_google_only(brain) -> None:
    """Monkey-patch: disable local fallback so only the API is exercised."""
    def _no_local():
        print("[test] Local GGUF disabled by --backend google flag.")
        return "(local model disabled)"
    brain._respond_local = _no_local


def _force_local_only(brain) -> None:
    """Monkey-patch: pretend Google client was never initialised."""
    brain._google_client = None
    print("[test] Google API disabled by --backend local flag.")


# ── Smoke test (non-interactive, good for CI) ─────────────────────────────

SMOKE_TURNS = [
    "Hello! What is your name?",
    "What did I just ask you?",   # tests history / context
    "exit",
]

def run_smoke(brain) -> bool:
    print("\n── Smoke test ──────────────────────────────────────────")
    all_ok = True
    for turn in SMOKE_TURNS:
        print(f"\n  You  : {turn}")
        t0 = time.perf_counter()
        try:
            reply = brain.respond(turn)
            elapsed = time.perf_counter() - t0
            print(f"  BMO  : {reply}")
            print(f"  ({elapsed:.2f}s)")
            if not reply or reply.startswith("(Error"):
                print("  ✗ Empty or error reply!")
                all_ok = False
            else:
                print("  ✓")
        except Exception as exc:
            print(f"  ✗ Exception: {exc}")
            all_ok = False

    print("\n── Result:", "PASS ✓" if all_ok else "FAIL ✗")
    return all_ok


# ── Interactive REPL ──────────────────────────────────────────────────────

def run_repl(brain) -> None:
    print("\n── Interactive REPL  (type 'exit' to quit, 'reset' to clear history) ──")
    while True:
        try:
            user = input("\nYou  : ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nInterrupted.")
            break

        if not user:
            continue
        if user.lower() == "reset":
            brain.reset_history()
            print("  [history cleared]")
            continue
        if user.lower() in {"exit", "quit", "bye"}:
            print("  BMO  : Goodbye!")
            break

        t0 = time.perf_counter()
        reply = brain.respond(user)
        elapsed = time.perf_counter() - t0
        print(f"BMO  : {reply}")
        print(f"       ({elapsed:.2f}s)")


# ── Entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Test brain.py in isolation.")
    parser.add_argument(
        "--backend", choices=["google", "local", "auto"], default="auto",
        help="Force a specific backend (default: auto / Google-first)."
    )
    parser.add_argument(
        "--smoke", action="store_true",
        help="Run a non-interactive smoke test and exit with 0 (pass) or 1 (fail)."
    )
    args = parser.parse_args()

    # Import Brain from the same directory (or installed package).
    try:
        from brain import Brain
    except ImportError:
        print("ERROR: could not import Brain from brain.py – "
              "make sure this script is in the same folder.", file=sys.stderr)
        sys.exit(1)

    print("── Initialising Brain …")
    brain = Brain(BASE_CFG)

    # Apply backend overrides
    if args.backend == "google":
        _force_google_only(brain)
    elif args.backend == "local":
        _force_local_only(brain)

    if args.smoke:
        ok = run_smoke(brain)
        brain.close()
        sys.exit(0 if ok else 1)
    else:
        run_repl(brain)
        brain.close()


if __name__ == "__main__":
    main()