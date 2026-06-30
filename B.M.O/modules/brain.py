"""
brain.py
--------
Inference backend with automatic fallback:

  PRIMARY  → Google GenAI API  (gemma-4-26b-a4b-it)
  FALLBACK → Local GGUF        (llama-cpp-python)

The Google client is attempted first on every call. If the API is
unavailable (network error, quota, missing key, etc.) the call is
transparently retried on the local model and a warning is printed.

Vision calls require the Google API — there is no local vision fallback.

Config keys (config.yaml → brain:):
    # --- Google API ---
    google_api_key:     ""          # or set env var GOOGLE_API_KEY
    google_model:       "gemma-4-26b-a4b-it"

    # --- Local GGUF fallback ---
    model_path:         "models/gemma4.gguf"
    modelfile_path:     "modelfile.txt"   # used for SYSTEM + MESSAGE few-shot
    n_ctx:              8192
    n_gpu_layers:       -1
    thinking_tokens:    512
    reply_tokens:       300

    # --- Sampling (applies to both backends unless noted) ---
    sampling:
        temperature:    1.3
        top_p:          0.95
        top_k:          64
        max_output_tokens: 400   # Google API / num_predict equivalent
        min_p:          0.05     # local GGUF only
        repeat_penalty: 1.0     # local GGUF only (1.0 = disabled)

Install:
    pip install google-genai llama-cpp-python
    CUDA build: CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python

Return value of respond():
    (reply: str, face: str | None)
    reply — clean text with BMO/B.M.O/bmo/bemo replaced by "beemo", <FACE> tag stripped
    face  — face name extracted from <FACE>…</FACE>, or None if tag absent
"""

import os
import re
import random


# ── Regex constants ───────────────────────────────────────────────────────────

# Strips <think>…</think> / <thinking>…</thinking> and Gemma 4 GGUF thought blocks
_THINK_RE = re.compile(
    r"(?:<think(?:ing)?>.*?</think(?:ing)?>|<\|channel>thought.*?<channel\|>)",
    re.DOTALL | re.IGNORECASE,
)

# Extracts <FACE>facename</FACE> (case-insensitive); tag + surrounding whitespace stripped
_FACE_RE = re.compile(r"\s*<FACE>\s*([^<]+?)\s*</FACE>\s*", re.IGNORECASE)

# Extracts [VISION:screenshot] or [VISION:camera]; tag + surrounding whitespace stripped
_VISION_RE = re.compile(r"\s*\[VISION:(screenshot|camera)\]\s*", re.IGNORECASE)

# Extracts <OPEN>appname</OPEN>; tag + surrounding whitespace stripped
_APP_RE = re.compile(r"\s*<OPEN>\s*([^<]+?)\s*</OPEN>\s*", re.IGNORECASE)

# Strips bracket-wrapped stage directions: [beemo stares …], [looks worried], etc.
# Applied after _VISION_RE so [VISION:…] is already consumed.
_ACTION_RE = re.compile(r"\[[^\]]*\]")

# Replaces BMO / B.M.O / bmo / bemo (all cases) with "beemo" for correct TTS pronunciation.
# Pattern is idempotent: running it twice still gives "beemo".
_BMO_RE = re.compile(r"\b(?:B\.?M\.?O\.?|bemo)\b", re.IGNORECASE)


# ── Lazy imports ──────────────────────────────────────────────────────────────

def _try_import_google():
    try:
        from google import genai
        from google.genai import types
        return genai, types
    except ImportError:
        return None, None


def _try_import_llama():
    """
    Import Llama and return a subclass patched to apply samplers in
    Gemma 4's recommended order: temperature → top_p → top_k → min_p
    instead of llama-cpp-python's default: top_k → top_p → min_p → temperature.

    Temperature-first flattens the full distribution before the probability
    filters run, giving top_p/top_k a wider, more diverse candidate pool.

    Falls back to the unpatched Llama class if the internal API has changed.
    """
    try:
        from llama_cpp import Llama
    except ImportError:
        return None

    try:
        from llama_cpp import _internals as _int
        import inspect

        sig = inspect.signature(Llama._init_sampler)
        expected_params = {"top_k", "top_p", "min_p", "temp",
                           "repeat_penalty", "logits_processor", "grammar"}
        if not expected_params.issubset(sig.parameters):
            raise AttributeError(f"unexpected _init_sampler params: {set(sig.parameters)}")

        class _GemmaOrderedLlama(Llama):
            def _init_sampler(
                self,
                top_k             = 40,
                top_p             = 0.95,
                min_p             = 0.05,
                typical_p         = 1.0,
                temp              = 0.80,
                repeat_penalty    = 1.0,
                frequency_penalty = 0.0,
                presence_penalty  = 0.0,
                tfs_z             = 1.0,
                mirostat_mode     = 0,
                mirostat_eta      = 0.1,
                mirostat_tau      = 5.0,
                penalize_nl       = True,
                logits_processor  = None,
                grammar           = None,
            ):
                sampler = _int.LlamaSampler()

                if (repeat_penalty != 1.0 or frequency_penalty != 0.0 or presence_penalty != 0.0):
                    try:
                        sampler.add_penalties(
                            n_vocab         = self._model.n_vocab(),
                            special_eos_id  = self._token_eos,
                            linefeed_id     = self._token_nl,
                            penalty_last_n  = self.last_n_tokens_size,
                            penalty_repeat  = repeat_penalty,
                            penalty_freq    = frequency_penalty,
                            penalty_present = presence_penalty,
                            penalize_nl     = penalize_nl,
                            ignore_eos      = False,
                        )
                    except Exception as exc:
                        print(f"[Brain] ⚠ Sampler: add_penalties failed ({exc}); skipping.", flush=True)

                if grammar is not None:
                    try:
                        sampler.add_grammar(self._model, grammar)
                    except Exception as exc:
                        print(f"[Brain] ⚠ Sampler: add_grammar failed ({exc}); skipping.", flush=True)

                if temp == 0:
                    sampler.add_greedy()
                    return sampler

                sampler.add_temp(temp)

                if top_p is not None and top_p < 1.0:
                    sampler.add_top_p(top_p, min_keep=1)
                if top_k is not None and top_k > 0:
                    sampler.add_top_k(top_k)
                if min_p is not None and min_p > 0.0:
                    sampler.add_min_p(min_p, min_keep=1)

                sampler.add_dist(seed=random.randint(0, 2**31 - 1))
                return sampler

        _GemmaOrderedLlama.__name__ = "Llama"
        return _GemmaOrderedLlama

    except Exception as exc:
        print(f"[Brain] ⚠ Sampler patch skipped ({exc}); using llama-cpp-python's default chain.", flush=True)
        return Llama


# ── Module-level helpers ──────────────────────────────────────────────────────

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


def _load_few_shot_messages(path: str) -> list[dict]:
    """
    Parse MESSAGE user/assistant pairs from an Ollama-style modelfile.
    Returns a list of {"role": ..., "content": ...} dicts, ready to be
    prepended to every chat completion call.
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    messages = []
    for m in re.finditer(
        r'^MESSAGE\s+(user|assistant)\s+"(.*?)"',
        raw, re.DOTALL | re.MULTILINE | re.IGNORECASE,
    ):
        messages.append({"role": m.group(1).lower(), "content": m.group(2)})
    return messages


def _history_to_text(system_prompt: str, history: list[dict],
                     few_shot: list[dict] | None = None) -> str:
    """
    Flatten system prompt + few-shot examples + chat history into a single
    string for the stateless Google API call, using Gemma's turn-tagged format.
    Few-shot messages are injected after the system turn and before real history.
    """
    parts = [f"<start_of_turn>system\n{system_prompt}<end_of_turn>"]
    for msg in (few_shot or []):
        role = "user" if msg["role"] == "user" else "model"
        parts.append(f"<start_of_turn>{role}\n{msg['content']}<end_of_turn>")
    for msg in history:
        role = "user" if msg["role"] == "user" else "model"
        parts.append(f"<start_of_turn>{role}\n{msg['content']}<end_of_turn>")
    parts.append("<start_of_turn>model\n")
    return "\n".join(parts)


def _postprocess(text: str) -> tuple[str, str | None, str | None, str | None]:
    """
    1. Extract <FACE>…</FACE> tag → face name (or None).
    2. Extract [VISION:type] tag → vision_type (or None).
    3. Extract <OPEN>appname</OPEN> tag → app_name (or None).
    4. Strip remaining [bracket action text] (stage directions).
    5. Replace BMO / B.M.O / bmo (all cases) with "beemo".
    Returns (clean_text, face, vision_type, app_name).
    """
    face: str | None = None
    vision_type: str | None = None
    app_name: str | None = None

    face_match = _FACE_RE.search(text)
    if face_match:
        face = face_match.group(1).strip()
        text = _FACE_RE.sub("", text).strip()

    vision_match = _VISION_RE.search(text)
    if vision_match:
        vision_type = vision_match.group(1).lower()
        text = _VISION_RE.sub("", text).strip()

    app_match = _APP_RE.search(text)
    if app_match:
        app_name = app_match.group(1).strip().lower()
        text = _APP_RE.sub("", text).strip()

    text = _ACTION_RE.sub("", text).strip()
    text = _BMO_RE.sub("beemo", text)

    return text, face, vision_type, app_name


# ── Brain class ───────────────────────────────────────────────────────────────

class Brain:
    def __init__(self, cfg: dict):
        br_cfg = cfg["brain"]

        self._system_prompt   = _load_system_prompt(br_cfg["modelfile_path"])
        self._few_shot        = _load_few_shot_messages(br_cfg["modelfile_path"])
        self._history: list[dict] = []

        self._thinking_budget = br_cfg.get("thinking_tokens", 512)
        self._reply_tokens    = br_cfg.get("reply_tokens", 300)

        s = br_cfg.get("sampling", {})
        self._temperature       = s.get("temperature",       1.3)
        self._top_p             = s.get("top_p",             0.95)
        self._top_k             = s.get("top_k",             64)
        self._max_output_tokens = s.get("max_output_tokens", 400)
        self._min_p             = s.get("min_p",             0.05)
        self._repeat_penalty    = s.get("repeat_penalty",    1.0)

        self._google_model  = br_cfg.get("google_model", "gemma-4-26b-a4b-it")
        self._google_client = None
        self._google_types  = None

        # thinking_level is noted here but intentionally NOT sent to the API —
        # gemma-4-26b-a4b-it rejects ThinkingConfig with INVALID_ARGUMENT.
        # Kept in config for documentation / future model support.

        genai, types = _try_import_google()
        if genai is not None:
            api_key = br_cfg.get("google_api_key") or os.environ.get("GOOGLE_API_KEY", "")
            try:
                self._google_client = genai.Client(api_key=api_key if api_key else None)
                self._google_types  = types
                print(f"[Brain] Google GenAI client initialised (model: {self._google_model}).", flush=True)
            except Exception as exc:
                print(f"[Brain] ⚠ Google GenAI init failed ({exc}); will use local model only.", flush=True)
        else:
            print("[Brain] google-genai not installed; will use local model only.", flush=True)

        self._llm    = None
        self._br_cfg = br_cfg

    # ── Public API ────────────────────────────────────────────────────────────

    def respond(self, user_text: str) -> tuple[str, str | None, str | None, str | None]:
        """
        Append user text, run inference, return (clean_reply, face, vision_type, app_name).

        clean_reply  — BMO/B.M.O/bmo/bemo replaced with "beemo", <FACE>,
                       [VISION:*], and <OPEN:*> tags stripped.
        face         — face name from <FACE>…</FACE>, or None if tag absent.
        vision_type  — "screenshot" | "camera" if model requested an image, else None.
        app_name     — executable name from <OPEN>…</OPEN>, or None if tag absent.
        """
        self._history.append({"role": "user", "content": user_text})

        raw_reply = None

        if self._google_client is not None:
            raw_reply = self._respond_google(user_text)

        if raw_reply is None:
            print("[Brain] Falling back to local GGUF model …", flush=True)
            raw_reply = self._respond_local()

        clean_reply, face, vision_type, app_name = _postprocess(raw_reply)
        self._history.append({"role": "assistant", "content": clean_reply})
        return clean_reply, face, vision_type, app_name

    def respond_with_vision(
        self,
        user_text: str,
        image_data: bytes,
        mime_type: str = "image/jpeg",
    ) -> tuple[str, str | None]:
        """
        Send the captured image to the Google API and get a response.

        History at this point already contains:
            user  : original user_text
            model : BMO's "about to look" message (vision tag stripped)

        Returns (clean_reply, face). The new exchange is appended to history.
        Vision requires the Google API — there is no local fallback.
        """
        raw_reply = None

        if self._google_client is not None:
            raw_reply = self._respond_google_vision(user_text, image_data, mime_type)

        if raw_reply is None:
            raw_reply = (
                "I can't see right now — my vision requires the Google API, "
                "which isn't available."
            )

        clean_reply, face, _, _ = _postprocess(raw_reply)  # vision_type, app_name unused here
        self._history.append({"role": "user",      "content": "[Image provided.]"})
        self._history.append({"role": "assistant",  "content": clean_reply})
        return clean_reply, face

    def reset_history(self):
        self._history = []

    def warmup(self) -> str:
        """
        Called once during boot. Probes the Google API if configured; on failure
        disables it and pre-loads the local GGUF to avoid first-call latency.
        Returns a one-line status string for the boot log.
        """
        if self._google_client is not None:
            print("      [Brain] Probing Google API …", flush=True)
            if self._probe_google():
                return f"✓ Backend: Google API ({self._google_model})"
            print("      [Brain] ⚠ Google API unreachable — loading local GGUF now …", flush=True)
            self._google_client = None
            ok = self._ensure_local_model()
            if ok:
                return "✓ Backend: local GGUF (Google API unavailable)"
            return "✗ Backend: NONE — both Google API and local GGUF failed"
        else:
            print("      [Brain] No Google client — loading local GGUF now …", flush=True)
            ok = self._ensure_local_model()
            if ok:
                return "✓ Backend: local GGUF"
            return "✗ Backend: NONE — local GGUF failed to load"

    def close(self):
        pass   # llama-cpp frees memory when the Llama object is GC'd

    # ── Google backend ────────────────────────────────────────────────────────

    def _probe_google(self) -> bool:
        """Minimal single-token probe. Returns True if the API responds."""
        try:
            response = self._google_client.models.generate_content(
                model    = self._google_model,
                contents = "ping",
                config   = self._google_types.GenerateContentConfig(max_output_tokens=1),
            )
            _ = response.text
            return True
        except Exception as exc:
            print(f"      [Brain] Probe failed: {exc}", flush=True)
            return False

    def _respond_google(self, user_text: str) -> str | None:
        """
        Call the Google GenAI API.
        Returns the raw reply string, or None on any error so the caller
        can fall back to the local model.

        Note: ThinkingConfig is intentionally omitted — gemma-4-26b-a4b-it
        returns INVALID_ARGUMENT if it is present. The model's default
        thinking behaviour is controlled server-side.
        To avoid empty responses caused by thinking tokens exhausting
        max_output_tokens, we enforce a minimum of 800 output tokens.
        """
        try:
            contents = _history_to_text(self._system_prompt, self._history, self._few_shot)
            # Thinking tokens are consumed before any reply text is written.
            # Use at least 800 so the model has room to actually respond.
            output_tokens = max(self._max_output_tokens, 800)
            response = self._google_client.models.generate_content(
                model    = self._google_model,
                contents = contents,
                config   = self._google_types.GenerateContentConfig(
                    temperature       = self._temperature,
                    top_p             = self._top_p,
                    top_k             = self._top_k,
                    max_output_tokens = output_tokens,
                ),
            )
            reply = (response.text or "").strip()
            if not reply:
                finish = None
                try:
                    finish = response.candidates[0].finish_reason
                except Exception:
                    pass
                print(f"[Brain] ⚠ Google API returned empty response "
                      f"(finish_reason={finish}); falling back.", flush=True)
                return None
            return reply
        except Exception as exc:
            print(f"[Brain] ⚠ Google API error: {exc}", flush=True)
            return None

    def _respond_google_vision(
        self,
        user_text: str,
        image_data: bytes,
        mime_type: str,
    ) -> str | None:
        """
        Multimodal call to the Google GenAI API.
        Sends full conversation history as structured Content objects,
        then appends a vision turn containing the image.
        Returns the raw reply string, or None on any error.
        """
        try:
            types = self._google_types

            contents: list = [
                types.Content(
                    role="user",
                    parts=[types.Part(text=f"<start_of_turn>system\n{self._system_prompt}<end_of_turn>")],
                ),
                types.Content(
                    role="model",
                    parts=[types.Part(text="Understood.")],
                ),
            ]

            for msg in self._few_shot:
                role = "user" if msg["role"] == "user" else "model"
                contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

            for msg in self._history:
                role = "user" if msg["role"] == "user" else "model"
                contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

            contents.append(types.Content(
                role="user",
                parts=[
                    types.Part(inline_data=types.Blob(data=image_data, mime_type=mime_type)),
                    types.Part(text="[Image provided as requested.]"),
                ],
            ))

            response = self._google_client.models.generate_content(
                model    = self._google_model,
                contents = contents,
                config   = types.GenerateContentConfig(
                    temperature       = self._temperature,
                    top_p             = self._top_p,
                    top_k             = self._top_k,
                    max_output_tokens = self._max_output_tokens,
                ),
            )
            reply = (response.text or "").strip()
            if not reply:
                print("[Brain] ⚠ Google API Vision returned empty response.", flush=True)
                return None
            return reply
        except Exception as exc:
            print(f"[Brain] ⚠ Google API Vision error: {exc}", flush=True)
            return None

    # ── Local GGUF backend ────────────────────────────────────────────────────

    def _ensure_local_model(self) -> bool:
        """Load the local GGUF on first use. Returns True if ready."""
        if self._llm is not None:
            return True

        Llama = _try_import_llama()
        if Llama is None:
            print("[Brain] ✗ llama-cpp-python not installed — cannot fall back to local model.", flush=True)
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
                seed         = random.randint(0, 2**31 - 1),
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
            + self._few_shot
            + self._history
        )

        # ── Safe token budget ─────────────────────────────────────────────────
        # We must not request more output tokens than the context window has
        # room for after the prompt. We measure prompt size by tokenising the
        # flattened text (llm.tokenize is available in every llama-cpp fork).
        # If that fails for any reason we fall back conservatively.
        n_ctx  = self._br_cfg.get("n_ctx", 8192)
        wanted = self._thinking_budget + self._reply_tokens

        def _trim_history_once() -> list[dict]:
            """Drop the oldest user+assistant pair from history."""
            if len(self._history) >= 2:
                print("[Brain] ⚠ Context full — trimming oldest history turn.", flush=True)
                self._history = self._history[2:]
            return (
                [{"role": "system", "content": self._system_prompt}]
                + self._few_shot
                + self._history
            )

        # Chat-template overhead per message (role tags, turn markers, BOS, etc.).
        # Gemma 4's template adds ~10 tokens per message on top of content tokens.
        _TEMPLATE_OVERHEAD_PER_MSG = 10

        def _count_tokens(msgs: list[dict]) -> int:
            flat = " ".join(m["content"] for m in msgs)
            # tokenize() returns a list of token ids; add_bos=False avoids
            # double-counting the BOS that the chat formatter will add.
            content_tokens = len(self._llm.tokenize(flat.encode("utf-8"), add_bos=False))
            # Add per-message overhead so our budget matches what create_chat_completion
            # actually uses.  The flat-string tokenise misses role tags and turn markers,
            # which is exactly what caused "Requested tokens (4102) exceed context window
            # of 4096" even when the raw content appeared to fit.
            return content_tokens + len(msgs) * _TEMPLATE_OVERHEAD_PER_MSG

        try:
            prompt_tokens = _count_tokens(messages)
            # Trim until we have at least (wanted + 32) tokens free, or we
            # run out of history to trim (leave system prompt intact).
            while prompt_tokens + wanted + 32 > n_ctx and len(self._history) >= 2:
                messages      = _trim_history_once()
                prompt_tokens = _count_tokens(messages)

            available  = n_ctx - prompt_tokens - 8   # 8-token safety margin
            max_tokens = max(64, min(wanted, available))

            # Hard safety: if even the system prompt alone fills the window
            # (n_ctx too small for this model's system prompt), cap output tokens
            # and warn rather than crashing.
            if available <= 0:
                print(
                    f"[Brain] ✗ System prompt + few-shot (~{prompt_tokens} tokens) "
                    f"exceeds n_ctx ({n_ctx}).  Raise n_ctx in config.yaml.  "
                    "Clamping output to 64 tokens as emergency fallback.",
                    flush=True,
                )
                max_tokens = 64
        except Exception as exc:
            print(f"[Brain] ⚠ Token count failed ({exc}); using conservative budget.", flush=True)
            # Hard conservative fallback: never request more than 1/5 of ctx.
            max_tokens = min(wanted, n_ctx // 5)

        # ── Inference ─────────────────────────────────────────────────────────
        try:
            result = self._llm.create_chat_completion(
                messages       = messages,
                max_tokens     = max_tokens,
                temperature    = self._temperature,
                top_p          = self._top_p,
                top_k          = self._top_k,
                min_p          = self._min_p,
                repeat_penalty = self._repeat_penalty,
                stop           = ["<end_of_turn>", "<eos>"],
            )
        except ValueError as exc:
            # Last-resort catch: if the formatter still overflows (e.g. because
            # the system prompt alone is larger than n_ctx), return a graceful
            # error instead of crashing the whole process.
            print(
                f"[Brain] ✗ Context overflow caught at inference ({exc}).  "
                "Please raise n_ctx in config.yaml.",
                flush=True,
            )
            return "(BMO is thinking very hard right now and needs more space. Try raising n_ctx in config.yaml.)"

        raw_reply   = result["choices"][0]["message"]["content"].strip()
        clean_reply = _THINK_RE.sub("", raw_reply).strip()

        if result["choices"][0].get("finish_reason") == "length":
            print("[Brain] ⚠ Response hit max_tokens — consider raising "
                  "thinking_tokens / reply_tokens in config.yaml.", flush=True)

        return clean_reply