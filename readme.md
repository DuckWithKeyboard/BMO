<div align="center">

```
██████╗ ███╗   ███╗ ██████╗
██╔══██╗████╗ ████║██╔═══██╗
██████╔╝██╔████╔██║██║   ██║
██╔══██╗██║╚██╔╝██║██║   ██║
██████╔╝██║ ╚═╝ ██║╚██████╔╝
╚═════╝ ╚═╝     ╚═╝ ╚═════╝

  O P E R A T I N G   S Y S T E M   ·   M U S I C   ·   A . I
```

**A complete, themed desktop ecosystem — built from four interlocking modules.**  
*One character. One aesthetic. One machine.*

---

[![Electron](https://img.shields.io/badge/Shell-Electron-47848F?style=for-the-badge&logo=electron&logoColor=white)](https://electronjs.org)
[![Python](https://img.shields.io/badge/AI%20Backend-Python%203.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![WebSocket](https://img.shields.io/badge/Bridge-WebSocket%20%3A7878-brightgreen?style=for-the-badge)](https://websockets.spec.whatwg.org/)
[![CUDA](https://img.shields.io/badge/Inference-CUDA%20Accelerated-76B900?style=for-the-badge&logo=nvidia&logoColor=white)](https://developer.nvidia.com/cuda-zone)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

</div>

---
[![Watch the video](https://img.youtube.com/vi/C_x6TbPdiKw/maxresdefault.jpg)](https://www.youtube.com/watch?v=C_x6TbPdiKw)
## ✦ What Is This?

**BMO** is not a single application. It is a fully self-contained, pixel-polished **desktop operating environment** — themed after BMO, the living game console from *Adventure Time* — composed of four purpose-built modules that boot together, communicate over native IPC and WebSocket, and present a unified experience to the user.

You sit down at your computer and you are no longer on Windows. You are in BMO.

The four modules are:

| Module | Role | Stack |
|---|---|---|
| **BMO O.S.** | Desktop shell, wallpaper engine, app launcher | Electron + Webpack |
| **BMO Music** | Full-screen glass-morphism music player | Electron + CSS |
| **BMO A.I. Frontend** | Animated AI companion face, state display | Electron + WebSocket |
| **BMO A.I. Backend** | Local voice AI agent, inference pipeline | Python + CUDA |

Together they form a layered stack: the OS shell is the outer environment, music and AI are launched as child applications from within it, and the AI system is itself a two-process architecture where a Python intelligence engine drives an Electron display layer over a WebSocket bridge.

---

## ✦ The Full Picture

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║                                                                                  ║
║   B M O   O . S .   —   Electron Desktop Shell                                  ║
║   ─────────────────────────────────────────────────────────────────────────      ║
║                                                                                  ║
║   ┌──────────────────────────────────────────────────────────────────────┐       ║
║   │  Cinematic Boot Splash (BMO loading GIF + neon title, 10s)           │       ║
║   │  ↓                                                                   │       ║
║   │  Wallpaper Engine   ──── random pick from /assets/wallpapers/        │       ║
║   │  ↓                                                                   │       ║
║   │  Desktop Icons + Folder Glass Menus                                  │       ║
║   └──────────────────────────────────────────────────────────────────────┘       ║
║           │                                    │                                 ║
║           │ IPC: open-app('music')             │ IPC: open-app('bmoAI')          ║
║           │ spawn() + hide OS shell            │ spawn() + hide OS shell         ║
║           ▼                                    ▼                                 ║
║   ┌─────────────────────┐          ┌─────────────────────────────────────┐       ║
║   │                     │          │                                     │       ║
║   │   B M O  M U S I C  │          │   B M O  A . I .  F R O N T E N D  │       ║
║   │   ─────────────     │          │   ─────────────────────────────     │       ║
║   │                     │          │                                     │       ║
║   │  Glass card UI      │          │  Electron window                    │       ║
║   │  Video background   │          │  Single <img> mount point           │       ║
║   │  Idle mini-pill     │          │  State machine + animation loops    │       ║
║   │  media:// protocol  │          │  WebSocket CLIENT → :7878           │       ║
║   │  Queue panel        │          │                                     │       ║
║   │  Metadata prefetch  │          │  spawn() on launch ─────────────┐  │       ║
║   │                     │          │                                  │  │       ║
║   └─────────────────────┘          └──────────────────────────────┬──┘  │       ║
║           │                                                        │     │       ║
║           │ IPC: app-closed                                        │     ▼       ║
║           └──────────────────────────────────┐    ┌───────────────────────────┐ ║
║                                              │    │                           │ ║
║                                              │    │  B M O  A . I .  B A C K  │ ║
║                                              │    │  ─────────────────────    │ ║
║                                              │    │                           │ ║
║                                              │    │  Python runtime           │ ║
║                                              │    │  OpenWakeWord  (ONNX)     │ ║
║                                              │    │  Faster-Whisper + VAD     │ ║
║                                              │    │  Google Gemma 4 / GGUF    │ ║
║                                              │    │  LuxTTS (zipvoice)        │ ║
║                                              │    │                           │ ║
║                                              │    │  WebSocket SERVER :7878   │ ║
║                                              │    │  ← broadcasts state       │ ║
║                                              │    └───────────────────────────┘ ║
║                                              │                                  ║
║                        IPC: app-closed ──────┘                                  ║
║                        OS shell re-appears with 1.5s splash                     ║
║                                                                                  ║
╚══════════════════════════════════════════════════════════════════════════════════╝
```

---

## ✦ Module Map

### `bmo-os/` — The Shell

Everything starts here. BMO O.S. is an Electron application that **replaces your desktop** — or layers over it — presenting a cinematic boot experience and a wallpaper-driven icon grid. It is the **process parent** for all other modules: when you click the Music icon, the OS shell hides itself and spawns the Music player as an independent child process. When you click the AI icon, it does the same for the AI Frontend.

The OS does not embed or import the other modules. It holds executable paths in a registry (`APP_EXES`) in `main.js` and launches them with Node's `child_process.spawn()`. This keeps every module fully independent — each can be developed, packaged, and updated in isolation.

The lifecycle signal flows back: when a spawned child process exits, `main.js` emits `app-closed` over IPC to the renderer, which replays the 1.5-second splash and fades the desktop back in. The user never sees a raw OS desktop.

**Key files:**

| File | Responsibility |
|---|---|
| `main.js` | Window management, IPC handlers, `APP_EXES` registry, child process lifecycle |
| `preload.js` | Context bridge — exposes `window.bmoOS.openApp()`, `openUrl()`, `onAppClosed()` |
| `renderer.js` | Desktop icon wiring, folder glass menus, wallpaper selection, splash timing |
| `index.css` | Design tokens (`--icon-size`, `--wallpaper-url`, etc.), folder overlay animation |

---

### `bmo-music/` — The Player

BMO Music is a standalone Electron window: full-screen, frameless, frosted-glass. It has no dependency on the OS shell at runtime — it can be launched directly or through the OS, and behaves identically either way.

Its most architecturally interesting decisions are all about **correctness under Electron's security constraints**:

- Audio is served through a custom `media://` protocol registered in `main.js` before `app.whenReady()`. The renderer never touches `file://` directly — Electron's CSP blocks it. The protocol handler implements `Range` / `206 Partial Content` so `<audio>` can seek without re-downloading files.
- Pointer capture for the progress bar is attached at `document` level rather than the element, because Electron's `-webkit-app-region: drag` layer on the frameless window can steal `mousemove` packets mid-gesture.
- Album art is preloaded into a new `Image()` object before the `<img>` src is swapped — zero blank-frame flash between tracks.
- Metadata is fetched sequentially (not in parallel) to avoid disk I/O contention with the audio thread.

The idle mini-player collapses the full glass card to a slim pill docked 20px above the bottom edge after 12 seconds of inactivity, then snaps back instantly on mouse movement — every CSS transition is documented inline.

**IPC surface (via `window.winAPI`):**

| Method | Effect |
|---|---|
| `winAPI.pickFolder()` | Native OS folder picker |
| `winAPI.loadFolder(path)` | Returns `string[]` of audio file paths |
| `winAPI.getMetadata(path)` | Returns `{ title, artist, album, cover }` via `music-metadata` |
| `winAPI.getMusicFolder()` / `setMusicFolder(path)` | Read/write `userData/config.json` |

---

### `bmo-ai/frontend/` — The Face

The AI Frontend is a purpose-built Electron display layer. Its job is singular and uncompromising: **show the right face frame at the right moment, with zero dropped frames and zero flicker**.

It achieves this through two architectural choices. First, all animation frames are pre-decoded via `img.decode()` before the first render — no frame is ever drawn from a partially-loaded buffer. Second, frame swaps happen via direct `.src` assignment on a single `<img>` element — no canvas, no CSS transitions, no compositing overhead.

The state machine drives six display states:

```
idle  ←──────────────────────────────────────────────────────────┐
  │                                                              │
  └─(wake word)─▶  listening  ─(transcript)─▶  thinking  ─(reply)─▶  speaking ──┘
                                                    │
                                              (backend error)
                                                    │
                                                    ▼
                                                  error
                                            (random frame: 01 or 02)
```

State transitions arrive as JSON over WebSocket from the Python backend:

```json
{ "state": "THINKING" }
```

The renderer is the **WebSocket client**. It connects outward to `ws://localhost:7878`, where the Python backend serves as the **WebSocket server**. This inversion is intentional: it means the display layer has no knowledge of the AI pipeline's internal structure, and the backend can be swapped, restarted, or replaced entirely without touching the frontend.

The Frontend also **manages the backend process**. On startup, Electron's `main.js` spawns `python.exe main.py` as a child process, piping its stdout/stderr to the Electron console with `[BMO]` / `[BMO err]` prefixes. On app quit, the Python process is forcefully terminated (`taskkill /f /t` on Windows, `SIGTERM` elsewhere).

**Auto-reconnect** is implemented in the WebSocket client — if the backend restarts (e.g. after a crash or model reload), the frontend reconnects automatically with no user intervention.

---

### `bmo-ai/backend/` — The Brain

The Python backend is the intelligence layer. It runs entirely locally — no data leaves the machine. Four specialized modules are orchestrated by a central state machine in `main.py`:

```
OpenWakeWord  ──("Hey BeMo")──▶
Faster-Whisper + Silero VAD  ──(transcript)──▶
Google Gemma 4 / local GGUF  ──(reply)──▶
LuxTTS (zipvoice)  ──(audio out)──▶  🔊
```

At every state transition, the orchestrator broadcasts a JSON payload over `ws://localhost:7878` to any connected frontend:

```json
{
  "state":  "THINKING",
  "text":   "what the user said",
  "reply":  "what BMO will say"
}
```

**Graceful degradation is built in.** The `Brain` module tries the Google GenAI API first (Gemma 4 26B, cloud-accelerated), and silently falls back to a local GGUF model loaded via `llama-cpp-python` if the API is unavailable, over quota, or unreachable. The fallback loads lazily — no memory is consumed for the local model unless it's actually needed.

**Startup sequence** is sequential and explicit:

```
1. WebSocket server binds to :7878
2. OpenWakeWord ONNX model loads
3. Faster-Whisper + Silero VAD initialize
4. Brain (Google API verified, local GGUF staged)
5. LuxTTS loads, CUDA warmup fires, reference voice cache restored
─────────────────────────────────────────────
  All systems go.  Say 'Hey BeMo' to start.
```

All four models report pass/fail independently — if one module fails to load, the rest still initialize and the error is surfaced clearly rather than silently swallowed.

**Conversation memory** is maintained across an entire session as a rolling message history, passed with each LLM call for coherent multi-turn dialogue.

---

## ✦ Inter-Module Communication

There are **three distinct communication layers** in the BMO stack. Each is appropriate to its context:

### Layer 1 — OS Shell ↔ Child Processes (Node `child_process`)

The OS shell communicates with Music and AI Frontend at the **process level** — not via sockets or IPC messages, but by spawning and killing OS processes. This is the coarsest-grained communication in the system, and deliberately so: it enforces a hard boundary between the shell and its children. Neither Music nor AI Frontend imports or depends on any code from `bmo-os`.

```
bmo-os/main.js
    │
    ├── spawn('...bmo.exe')          ← BMO Music
    │       └── watches 'exit' event
    │
    └── spawn('...bmoAI.exe')        ← BMO AI Frontend
            └── watches 'exit' event
                    │
                    └── emits IPC 'app-closed' → renderer
                            └── re-runs splash → fades desktop in
```

### Layer 2 — Electron Main ↔ Renderer (Electron IPC + Context Bridge)

Within each Electron application (OS shell, Music, AI Frontend), all communication between the privileged main process and the sandboxed renderer goes through a typed context bridge in `preload.js`. Node.js and Electron APIs are never directly exposed to the renderer — they are surfaced only as the specific methods registered on `window.winAPI` (Music) or `window.bmoOS` (OS shell).

This is a security boundary, not just an architectural convention. The renderer runs in a Chromium sandbox. The bridge is the only door.

### Layer 3 — AI Frontend ↔ Python Backend (WebSocket)

The two AI modules communicate over a persistent WebSocket connection at `ws://localhost:7878`. This is the highest-frequency channel in the system — state transitions flow continuously as the user speaks and the AI responds.

The protocol is minimal by design: a single JSON envelope with a `state` field (and optional `text` / `reply` fields for richer consumers). Any frontend that can speak WebSocket JSON can consume it — a browser tab, a React app, a Home Assistant dashboard. The BMO AI Frontend is the primary consumer, but the server does not care what is on the other end.

```
Python backend (ws SERVER :7878)
    │
    │  { "state": "LISTENING" }
    │  { "state": "THINKING",  "text": "what's the weather?" }
    │  { "state": "SPEAKING",  "reply": "I don't have internet access..." }
    │  { "state": "IDLE" }
    │
    ▼
Electron AI Frontend (ws CLIENT)
    └── STATE_MAP lookup → STATES[state] → animate frames
```

---

## ✦ Data & Asset Flow

```
User's Music Folder (local disk)
    │
    └── winAPI.loadFolder(path)
            │
            ├── Scanned for audio files → string[] of paths
            │
            └── Sequential metadata prefetch (music-metadata in main process)
                    ├── title / artist / album / cover → renderer rows update in-place
                    └── served to <audio> via custom media:// protocol (Range-aware)


User's Voice (microphone)
    │
    └── PyAudio capture (chunk: 1280 samples @ 16kHz)
            │
            ├── OpenWakeWord (ONNX)  → wake word score > threshold
            │       └── triggers LISTENING state → WS broadcast
            │
            └── Faster-Whisper + Silero VAD  → transcript string
                    └── triggers THINKING state → WS broadcast
                            │
                            └── Brain.generate(transcript, history)
                                    ├── Google GenAI API (primary)
                                    └── llama-cpp-python GGUF (fallback)
                                            │
                                            └── reply string
                                                    └── LuxTTS synthesis (CUDA)
                                                            ├── triggers SPEAKING state → WS broadcast
                                                            ├── audio playback → speakers
                                                            └── IDLE → WS broadcast
```

---

## ✦ Boot Sequence (Full Stack)

When the user launches the packaged BMO O.S. executable, this is the complete sequence:

```
 0.0s  bmo-os Electron process starts
 0.1s  BrowserWindow created (fullscreen, frameless)
 0.2s  preload.js bridges context
 0.3s  renderer.js loads — html { visibility: hidden } holds
 0.4s  window 'load' fires → .ready class added → UI visible at once (no FOUC)
 0.5s  Splash screen appears: BMO loading GIF + neon titleReveal animation
 0.6s  require.context scans /assets/wallpapers/ — random wallpaper selected
 0.8s  wallpaper preloads into Image() object (no layout flash)
10.0s  HOLD_MS elapses → splash fades → desktop fades in with wallpaper applied

── User clicks AI icon ──────────────────────────────────────────────────────────

10.x s  IPC 'open-app'('bmoAI') fires
         OS shell hides (osWindow.hide())
         spawn('bmoAI.exe') — AI Frontend Electron process starts

10.x+δ  AI Frontend loads:
           main.js spawns python.exe main.py (cwd: BMO project root)
           Python stdout/stderr piped → Electron console [BMO] / [BMO err]

           Python backend sequential init:
             ① WebSocket server binds → :7878
             ② OpenWakeWord ONNX loads
             ③ Faster-Whisper + Silero VAD inits
             ④ Brain: Google API verified / GGUF staged
             ⑤ LuxTTS loads → CUDA warmup → reference voice pkl restored

           AI Frontend renderer connects ws://localhost:7878 (with auto-reconnect)
           State machine enters IDLE → idle 01.png displayed

           "All systems go. Say 'Hey BeMo' to start."

── User says "Hey BeMo" ─────────────────────────────────────────────────────────

           WS broadcast: { "state": "LISTENING" }
           Frontend: listening frames loop at 500ms
           ...
           WS broadcast: { "state": "THINKING", "text": "..." }
           Frontend: thinking frames loop at 600ms
           ...
           WS broadcast: { "state": "SPEAKING", "reply": "..." }
           Frontend: speaking frames loop at 180ms — LuxTTS audio plays
           ...
           WS broadcast: { "state": "IDLE" }
           Frontend: idle 01.png

── User closes AI app ───────────────────────────────────────────────────────────

           AI Frontend quit: Python process killed (taskkill /f /t)
           bmoAI.exe exits
           OS shell detects 'exit' on child process
           IPC 'app-closed' → renderer
           1.5s return splash plays
           Desktop fades back in
```

---

## ✦ Extension Points

Every module in the BMO stack is designed to be extended without breaking the others.

### Adding an app to the OS shell

1. Register the executable in `bmo-os/main.js` under `APP_EXES`.
2. Add an icon button to `index.html` with a `data-app` attribute.
3. Wire the asset in `renderer.js`.

No changes needed to Music, AI Frontend, or Backend.

### Adding a new AI state

1. Drop frame images into `bmo-ai/frontend/assets/images/<state>/`.
2. Add the state definition to `STATES` in `renderer.js`.
3. Add the `STATE_MAP` entry.
4. Emit `{ "state": "YOUR_STATE" }` from any backend module.

No changes needed to the Python backend's core loop.

### Swapping the LLM backend

The `Brain` module in `bmo-ai/backend/modules/brain.py` exposes a single `generate(text, history)` interface. Replace the internals — swap Gemma for Claude, Mistral, or a local Ollama endpoint — and nothing else in the stack changes.

### Adding a new frontend consumer

Any process that can open a WebSocket to `ws://localhost:7878` will receive the full state stream. A browser page, a React dashboard, a mobile app on the local network — none require changes to the Python backend or the Electron frontend.

---

## ✦ Repository Structure (Full Stack)

```
bmo/
│
├── bmo-os/                         ← Desktop shell (Electron + Webpack)
│   ├── src/
│   │   ├── main.js                 ← Window mgmt, IPC, APP_EXES, child process lifecycle
│   │   ├── preload.js              ← Context bridge: window.bmoOS
│   │   ├── renderer.js             ← Desktop UI, folder menus, wallpaper, splash
│   │   ├── index.html
│   │   └── index.css               ← Design tokens, glass folder overlay
│   └── assets/
│       ├── fonts/                  ← CrystalUniverse · MochiBoom · HeartBubble
│       ├── icons/                  ← App + folder icon images
│       ├── images/                 ← Load.gif, sword.png
│       └── wallpapers/             ← Auto-discovered pool (png/jpg/webp)
│
├── bmo-music/                      ← Music player (standalone Electron)
│   ├── src/
│   │   ├── main.js                 ← media:// protocol, IPC, music-metadata
│   │   ├── preload.js              ← Context bridge: window.winAPI
│   │   ├── renderer.js             ← Audio engine, queue, idle collapse, scrub
│   │   ├── index.html
│   │   └── index.css               ← Glass UI, mini-player, @keyframes animations
│   └── src/assets/
│       ├── icons/                  ← Button PNGs, album_default.webp
│       ├── video/                  ← background.mp4 (looping)
│       └── fonts/                  ← CrystalUniverse · HeartBubble
│
├── bmo-ai/
│   │
│   ├── frontend/                   ← AI face display (Electron)
│   │   ├── main.js                 ← Window, Python subprocess spawn, CSP policy
│   │   ├── preload.js              ← Context bridge (extensible)
│   │   ├── renderer.js             ← State machine, animation loops, WS client
│   │   ├── index.html              ← Single <img> mount point
│   │   ├── index.css               ← Full-screen dark fill, object-fit display
│   │   └── assets/images/
│   │       ├── idle/               ← idle 01.png
│   │       ├── warmup/             ← warmup 01.png
│   │       ├── thinking/           ← thinking 01–04.png
│   │       ├── speaking/           ← speaking 01–03.png
│   │       ├── listening/          ← listen 01–03.png
│   │       ├── capturing/          ← capturing 01.png
│   │       └── error/              ← error 01.png, error 02.jpg
│   │
│   └── backend/                    ← Voice AI agent (Python + CUDA)
│       ├── main.py                 ← Orchestrator, state machine, WS server
│       ├── config.yaml             ← All runtime config (models, thresholds, devices)
│       ├── modules/
│       │   ├── wake_word.py        ← OpenWakeWord ONNX always-on detection
│       │   ├── transcriber.py      ← Faster-Whisper + Silero VAD
│       │   ├── brain.py            ← LLM inference: Google API + local GGUF fallback
│       │   └── speaker.py          ← LuxTTS voice synthesis + playback
│       ├── assets/
│       │   ├── hey_bemo.onnx       ← Wake word model
│       │   ├── modelfile.txt       ← System prompt
│       │   ├── *.gguf              ← Local GGUF model (optional fallback)
│       │   └── *.pkl               ← Pre-encoded reference voice cache
│       └── tests/
│           ├── test.py             ← Speaker smoke test
│           └── test_brain.py       ← Brain REPL + CI smoke mode
```

---

## ✦ Technology Reference

| Layer | Technology | Purpose |
|---|---|---|
| Desktop shell | Electron + Webpack (Electron Forge) | Frameless OS window, child process management |
| Music player | Electron + `music-metadata` | Frameless audio player, custom media:// protocol |
| AI display | Electron | Frameless animation display, WebSocket client |
| Wake word | OpenWakeWord (ONNX) | Always-on, offline hotword detection |
| Speech-to-text | Faster-Whisper + Silero VAD | Local, CUDA-accelerated transcription |
| LLM (primary) | Google GenAI API — Gemma 4 26B | Cloud-accelerated reasoning |
| LLM (fallback) | llama-cpp-python — any Gemma 4 GGUF | Fully local inference on CUDA |
| Voice synthesis | LuxTTS (`zipvoice`) + reference pkl | Local voice cloning, CUDA-accelerated |
| State bridge | WebSocket (`ws://localhost:7878`) | Real-time state streaming from Python to Electron |
| IPC (intra-app) | Electron `contextBridge` + `ipcRenderer` | Sandboxed main ↔ renderer communication |
| IPC (inter-app) | Node `child_process.spawn()` | OS shell → child app process lifecycle |
| Asset serving | Custom `media://` Electron protocol | Range-aware audio delivery under CSP |
| Fonts | CrystalUniverse · MochiBoom · HeartBubble | Self-hosted, zero network requests |
| Config | `config.yaml` (backend) / `config.json` (music) | Persisted user settings |

---

## ✦ Getting Started

### Prerequisites

- **Windows** (primary target; macOS/Linux supported for individual modules)
- **Node.js** v18+
- **Python** 3.10+ (Conda environment supported)
- **CUDA-capable GPU** (recommended for AI backend; CPU fallback available)
- **PortAudio** (for PyAudio microphone capture)

### Install & Run (Each Module)

```bash
# BMO O.S. (shell — launch this first)
cd bmo-os && npm install && npm start

# BMO Music (standalone — or launch via OS icon)
cd bmo-music && npm install && npm start

# BMO A.I. Frontend (spawns backend automatically)
cd bmo-ai/frontend && npm install && npm start

# BMO A.I. Backend (can also be run independently for testing)
cd bmo-ai/backend
pip install faster-whisper openwakeword pyaudio sounddevice torch \
            websockets pyyaml zipvoice google-genai
python main.py
```

### Package for Distribution

```bash
# Each module packages independently via Electron Forge
npm run make
# Output: out/make/ — distribute the platform-appropriate installer
```

### Wiring the OS shell to your installed modules

In `bmo-os/main.js`, update the `APP_EXES` registry to point at your packaged executables:

```js
const APP_EXES = {
  music:  'D:\\BMO\\bmo-music\\out\\bmo-win32-x64\\bmo.exe',
  bmoAI:  'D:\\BMO\\bmo-ai\\frontend\\out\\bmoAI-win32-x64\\bmoAI.exe',
  // additional apps...
};
```

In `bmo-ai/frontend/main.js`, update the Python paths:

```js
const python = 'D:\\conda\\envs\\bmo\\python.exe';
const script  = 'D:\\BMO\\bmo-ai\\backend\\main.py';
const cwd     = 'D:\\BMO\\bmo-ai\\backend';
```

---

## ✦ Design Philosophy

**Every module is independently deployable.** BMO Music can run without the OS shell. The AI backend can be queried by any WebSocket client. The frontend display layer doesn't care what is behind the socket. This modularity means each piece can be developed, tested, and shipped on its own timeline — and the OS shell is just the glue that presents them as a unified environment.

**Security is not relaxed for convenience.** Every Electron window runs with context isolation and a strict Content Security Policy. Audio is served over a custom protocol rather than loosening `file://` access. The Python backend never exposes a surface to the public network. None of these constraints were worked around — they were designed around.

**The aesthetic is the architecture.** Every visual decision — the glass morphism, the idle mini-player, the neon splash, the BMO face animations, the frosted folder overlays — is intentional and documented. The code comments explain not just *what* is happening but *why*, which makes BMO as readable as it is usable.

---

<div align="center">

*"I'm a little computer. But I got big dreams."*

**BMO** — *Mathematical.*

</div>
