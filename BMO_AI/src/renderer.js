import './index.css';

// ── Image imports ──────────────────────────────────────────
// Warmup
import imgWarmup01      from './assets/images/warmup/warmup 01.png';

// Thinking (loop order: 04 → 01 → 02 → 03)
import imgThinking04    from './assets/images/thinking/thinking 04.png';
import imgThinking01    from './assets/images/thinking/thinking 01.png';
import imgThinking02    from './assets/images/thinking/thinking 02.png';
import imgThinking03    from './assets/images/thinking/thinking 03.png';

// Speaking (loop order: 03 → 01 → 02)
import imgSpeaking03    from './assets/images/speaking/speaking 03.png';
import imgSpeaking01    from './assets/images/speaking/speaking 01.png';
import imgSpeaking02    from './assets/images/speaking/speaking 02.png';

// Listening (loop: 01 → 02 → 03)
import imgListen01      from './assets/images/listening/listen 01.png';
import imgListen02      from './assets/images/listening/listen 02.png';
import imgListen03      from './assets/images/listening/listen 03.png';

// Idle
import imgIdle01        from './assets/images/idle/idle 01.png';

// Error
import imgError01       from './assets/images/error/error 01.png';
import imgError02       from './assets/images/error/error 02.jpg';

// Capturing
import imgCapturing01   from './assets/images/capturing/capturing 01.png';

// ── Preload all images into the browser cache ──────────────
// This ensures every image is decoded before it's ever displayed,
// completely eliminating the flicker caused by late decoding.
const ALL_IMAGES = [
  imgWarmup01,
  imgThinking04, imgThinking01, imgThinking02, imgThinking03,
  imgSpeaking03, imgSpeaking01, imgSpeaking02,
  imgListen01, imgListen02, imgListen03,
  imgIdle01,
  imgError01, imgError02,
  imgCapturing01,
];

// Fire-and-forget: create Image objects so the browser fetches & decodes
// each asset now. decode() returns a Promise we don't need to await —
// the images will be ready long before the first animation frame.
ALL_IMAGES.forEach((src) => {
  const img = new Image();
  img.src = src;
  img.decode().catch(() => {}); // silence errors for already-cached assets
});

// ── State definitions ──────────────────────────────────────
// loopInterval (ms): how long each frame is shown during a loop.
// Single / random states ignore this field.
const STATES = {
  idle: {
    type: 'single',
    images: [imgIdle01],
  },
  warmup: {
    type: 'single',
    images: [imgWarmup01],
  },
  thinking: {
    type: 'loop',
    loopInterval: 600,   // slightly snappy — conveys active processing
    images: [imgThinking04, imgThinking01, imgThinking02, imgThinking03],
  },
  speaking: {
    type: 'loop',
    loopInterval: 180,   // fast mouth movement while talking
    images: [imgSpeaking03, imgSpeaking01, imgSpeaking02],
  },
  listening: {
    type: 'loop',
    loopInterval: 500,   // gentle, attentive pulse
    images: [imgListen01, imgListen02, imgListen03],
  },
  capturing: {
    type: 'single',
    images: [imgCapturing01],
  },
  error: {
    type: 'random',
    images: [imgError01, imgError02],
  },
};

// ── Single-layer hard-cut display ─────────────────────────
// One <img> element. Setting .src on an already-decoded image
// (via img.decode() in the preloader above) paints immediately
// with no blank frame — the decode cache is shared.

const displayImg = document.getElementById('display');

/**
 * @param {string} url - Webpack-resolved image URL.
 */
function showImage(url) {
  displayImg.src = url;
}

// ── Animation loop state ───────────────────────────────────
let loopTimer = null;
let loopIndex = 0;

function clearLoop() {
  if (loopTimer) {
    clearInterval(loopTimer);
    loopTimer = null;
  }
}

function activateState(stateName) {
  const state = STATES[stateName];
  if (!state) return;

  clearLoop();

  if (state.type === 'single') {
    showImage(state.images[0]);

  } else if (state.type === 'loop') {
    showImage(state.images[0]);
    loopIndex = 0;

    loopTimer = setInterval(() => {
      loopIndex = (loopIndex + 1) % state.images.length;
      showImage(state.images[loopIndex]);
    }, state.loopInterval);

  } else if (state.type === 'random') {
    const pick = state.images[Math.floor(Math.random() * state.images.length)];
    showImage(pick);
  }
}

// ── Boot ───────────────────────────────────────────────────
activateState('idle');

// ── WebSocket bridge ───────────────────────────────────────
// Receives: { "state": "IDLE"|"LISTENING"|"THINKING"|"SPEAKING" }
// Auto-reconnects every 3 s.
const WS_URL = 'ws://localhost:7878';

const STATE_MAP = {
  IDLE:      'idle',
  LISTENING: 'listening',
  THINKING:  'thinking',
  SPEAKING:  'speaking',
};

let _ws = null;
let _reconnectTimer = null;

function connectWs() {
  if (_ws && (_ws.readyState === WebSocket.OPEN || _ws.readyState === WebSocket.CONNECTING)) return;

  _ws = new WebSocket(WS_URL);

  _ws.addEventListener('open', () => {
    console.log(`[BMO WS] Connected to ${WS_URL}`);
    if (_reconnectTimer) { clearTimeout(_reconnectTimer); _reconnectTimer = null; }
  });

  _ws.addEventListener('message', (event) => {
    let payload;
    try {
      payload = JSON.parse(event.data);
    } catch {
      console.warn('[BMO WS] Bad JSON:', event.data);
      return;
    }

    const rendererState = STATE_MAP[payload.state];
    if (!rendererState) {
      console.warn('[BMO WS] Unknown state:', payload.state);
      return;
    }

    activateState(rendererState);
  });

  _ws.addEventListener('close', () => {
    console.log('[BMO WS] Disconnected — retrying in 3 s …');
    scheduleReconnect();
  });

  _ws.addEventListener('error', () => {
    _ws.close();
  });
}

function scheduleReconnect() {
  if (_reconnectTimer) return;
  _reconnectTimer = setTimeout(() => {
    _reconnectTimer = null;
    connectWs();
  }, 3000);
}

connectWs();