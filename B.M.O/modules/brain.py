"""
brain.py
--------
Inference backend with automatic fallback:

  PRIMARY   → Google GenAI API  (gemma-4-26b-a4b-it)
  FALLBACK  → Local GGUF        (llama-cpp-python)

The Google client is attempted first on every call.  If the API is
unavailable (network error, quota, missing key, etc.) the call is
transparently retried on the local model and a warning is printed.

Config keys (config.yaml → brain:):
    # --- Google API ---
    google_api_key:     ""          # or set env var GOOGLE_API_KEY
    google_model:       "gemma-4-26b-a4b-it"
    thinking_level:     "high"      # "none" | "low" | "medium" | "high"

    # --- Local GGUF fallback ---
    model_path:         "models/gemma4.gguf"
    modelfile_path:     "modelfile.txt"
    n_ctx:              8192
    n_gpu_layers:       -1
    thinking_tokens:    1024
    reply_tokens:       512

Install:
    pip install google-genai llama-cpp-python
    CUDA build: CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python
"""

import os
import re

# ── Thinking-block stripper (used for local-model output) ─────────────────
#   <think>…</think>  |  <thinking>…</thinking>
#   <|channel>thought … <channel|>   ← what some Gemma 4 GGUFs emit
_THINK_RE = re.compile(
    r"(?:"
    r"<think(?:ing)?>.*?</think(?:ing)?>"
    r"|"
    r"<\|channel>thought.*?<channel\|>"
    r")",
    re.DOTALL | re.IGNORECASE,
)

# ── Lazy imports so a missing package only fails the relevant backend ──────

def _try_import_google():
    try:
        from google import genai
        from google.genai import types
        return genai, types
    except ImportError:
        return None, None

def _try_import_llama():
    try:
        from llama_cpp import Llama
        return Llama
    except ImportError:
        return None


# ─────────────────────────────────────────────────────────────────────────
class Brain:
    def __init__(self, cfg: dict):
        br_cfg = cfg["brain"]

        self._system_prompt   = _load_system_prompt(br_cfg["modelfile_path"])
        self._history: list[dict] = []

        # ── Local-model token budgets ─────────────────────────────────────
        self._thinking_budget = br_cfg.get("thinking_tokens", 1024)
        self._reply_tokens    = br_cfg.get("reply_tokens", 512)

        # ── Google API setup ──────────────────────────────────────────────
        self._google_model    = br_cfg.get("google_model", "gemma-4-26b-a4b-it")
        self._thinking_level  = br_cfg.get("thinking_level", "high")
        self._google_client   = None
        self._google_types    = None

        genai, types = _try_import_google()
        if genai is not None:
            api_key = br_cfg.get("google_api_key") or os.environ.get("GOOGLE_API_KEY", "")
            try:
                self._google_client = genai.Client(
                    api_key=api_key if api_key else None
                )
                self._google_types = types
                print("[Brain] Google GenAI client initialised "
                      f"(model: {self._google_model}).", flush=True)
            except Exception as exc:
                print(f"[Brain] ⚠ Google GenAI init failed ({exc}); "
                      "will use local model only.", flush=True)
        else:
            print("[Brain] google-genai not installed; "
                  "will use local model only.", flush=True)

        # ── Local GGUF setup (lazy — only loaded if needed) ───────────────
        self._llm     = None
        self._br_cfg  = br_cfg   # keep for deferred loading

    # ── Public API ────────────────────────────────────────────────────────

    def respond(self, user_text: str) -> str:
        """Append user text, run inference, return clean reply."""
        self._history.append({"role": "user", "content": user_text})

        reply = None

        # 1. Try Google API
        if self._google_client is not None:
            reply = self._respond_google(user_text)

        # 2. Fallback to local GGUF
        if reply is None:
            print("[Brain] Falling back to local GGUF model …", flush=True)
            reply = self._respond_local()

        self._history.append({"role": "assistant", "content": reply})
        return reply

    def reset_history(self):
        self._history = []

    def close(self):
        pass   # llama-cpp frees memory when the Llama object is GC'd

    # ── Google backend ────────────────────────────────────────────────────

    def _respond_google(self, user_text: str) -> str | None:
        """
        Call the Google GenAI API.
        Returns the clean reply string, or None on any error so the caller
        can fall back to the local model.
        """
        try:
            # Build a single-turn contents string that includes history so
            # Gemma has conversational context (the API is stateless).
            contents = _history_to_text(
                self._system_prompt, self._history
            )

            response = self._google_client.models.generate_content(
                model    = self._google_model,
                contents = contents,
                config   = self._google_types.GenerateContentConfig(
                    thinking_config = self._google_types.ThinkingConfig(
                        thinking_level=self._thinking_level
                    )
                ),
            )

            reply = (response.text or "").strip()
            if not reply:
                print("[Brain] ⚠ Google API returned empty response; "
                      "falling back.", flush=True)
                return None

            print(f"[Brain] Source: Google API ({self._google_model})",
                  flush=True)
            return reply

        except Exception as exc:
            print(f"[Brain] ⚠ Google API error: {exc}", flush=True)
            return None

    # ── Local GGUF backend ────────────────────────────────────────────────

    def _ensure_local_model(self) -> bool:
        """Load the local GGUF on first use.  Returns True if ready."""
        if self._llm is not None:
            return True

        Llama = _try_import_llama()
        if Llama is None:
            print("[Brain] ✗ llama-cpp-python not installed – "
                  "cannot fall back to local model.", flush=True)
            return False

        br = self._br_cfg
        try:
            print("[Brain] Loading local GGUF model …", flush=True)
            self._llm = Llama(
                model_path   = br["model_path"],
                n_ctx        = br.get("n_ctx", 8192),
                n_gpu_layers = br.get("n_gpu_layers", -1),
                flash_attn   = True,
                verbose      = False,
            )
            print("[Brain] Local model ready.", flush=True)
            return True
        except Exception as exc:
            print(f"[Brain] ✗ Failed to load local GGUF: {exc}", flush=True)
            return False

    def _respond_local(self) -> str:
        """Run inference on the local GGUF model."""
        if not self._ensure_local_model():
            return "(Error: no inference backend available.)"

        messages = (
            [{"role": "system", "content": self._system_prompt}]
            + self._history
        )

        result = self._llm.create_chat_completion(
            messages    = messages,
            max_tokens  = self._thinking_budget + self._reply_tokens,
            temperature = 0.7,
            top_p       = 0.9,
            stop        = ["<end_of_turn>", "<eos>"],
        )

        raw_reply = result["choices"][0]["message"]["content"].strip()

        think_match = _THINK_RE.search(raw_reply)
        if think_match:
            print(f"[Brain] <think> block "
                  f"({len(think_match.group())} chars) stripped.", flush=True)

        clean_reply = _THINK_RE.sub("", raw_reply).strip()

        if result["choices"][0].get("finish_reason") == "length":
            print("[Brain] ⚠ Response hit max_tokens – consider raising "
                  "thinking_tokens / reply_tokens in config.yaml.", flush=True)

        print("[Brain] Source: local GGUF", flush=True)
        return clean_reply


# ── Helpers ───────────────────────────────────────────────────────────────

def _history_to_text(system_prompt: str, history: list[dict]) -> str:
    """
    Flatten system prompt + chat history into a single string for the
    stateless Google API call.  Uses a simple turn-tagged format that
    Gemma instruction-tuned models understand well.
    """
    parts = [f"<start_of_turn>system\n{system_prompt}<end_of_turn>"]
    for msg in history:
        role    = "user" if msg["role"] == "user" else "model"
        content = msg["content"]
        parts.append(f"<start_of_turn>{role}\n{content}<end_of_turn>")
    parts.append("<start_of_turn>model\n")   # prompt the model to continue
    return "\n".join(parts)


def _load_system_prompt(path: str) -> str:
    """Supports Ollama-style SYSTEM blocks or plain text files."""
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    block = re.search(
        r'(?i)^SYSTEM\s+(?:"""(.*?)"""|\'\'\'(.*?)\'\'\'|(.*?)(?=\n[A-Z]|\Z))',
        raw, re.DOTALL | re.MULTILINE,
    )
    if block:
        return (block.group(1) or block.group(2) or block.group(3)).strip()
    return raw.strip()