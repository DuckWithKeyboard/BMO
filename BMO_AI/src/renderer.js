import './index.css';

// ── Image imports ──────────────────────────────────────────
import imgWarmup01          from './assets/images/warmup/warmup 01.png';
import imgGreeting01        from './assets/images/greeting/greeting 01.png';
import imgGreeting02        from './assets/images/greeting/greeting 02.png';
import imgGreeting03        from './assets/images/greeting/greeting 03.png';
import imgThinking04        from './assets/images/thinking/thinking 04.png';
import imgThinking01        from './assets/images/thinking/thinking 01.png';
import imgThinking02        from './assets/images/thinking/thinking 02.png';
import imgThinking03        from './assets/images/thinking/thinking 03.png';
import imgSpeaking03        from './assets/images/speaking/speaking 03.png';
import imgSpeaking01        from './assets/images/speaking/speaking 01.png';
import imgSpeaking02        from './assets/images/speaking/speaking 02.png';
import imgListen01          from './assets/images/listening/listen 01.png';
import imgListen02          from './assets/images/listening/listen 02.png';
import imgListen03          from './assets/images/listening/listen 03.png';
import imgIdle01            from './assets/images/idle/idle 01.png';
import imgError01           from './assets/images/error/error 01.png';
import imgCapturing01       from './assets/images/capturing/capturing 01.png';
import imgFaceAngry         from './assets/images/BMO faces/angry.png';
import imgFaceContemt       from './assets/images/BMO faces/contempt_or_smug_or_happy.png';
import imgFaceDread         from './assets/images/BMO faces/dread.png';
import imgFaceHappy         from './assets/images/BMO faces/happy.png';
import imgFaceJudging       from './assets/images/BMO faces/judging_or_angry.png';
import imgFaceNoticing      from './assets/images/BMO faces/noticing_something.png';
import imgFaceRevulsion     from './assets/images/BMO faces/revulsion.png';
import imgFaceSad           from './assets/images/BMO faces/sad.png';
import imgFaceSlightlySad   from './assets/images/BMO faces/slightly_sad.png';
import imgFaceSmugness      from './assets/images/BMO faces/smugness.png';
import imgFaceStraightFace  from './assets/images/BMO faces/straight_face.png';
import imgFaceStraightAlt   from './assets/images/BMO faces/straight_face (1).png';
import imgFaceAmazed        from './assets/images/BMO faces/amazed_or_surprised.png';
import imgFaceTired         from './assets/images/BMO faces/tired.png';
import imgFaceUnamused      from './assets/images/BMO faces/unamused.png';
import imgFaceUnamusedAlt   from './assets/images/BMO faces/unamused (1).png';

// ── Image-thinking loop (shown while BMO analyses a captured image) ─────────
import imgIThinking01 from './assets/images/image_thinking/ithinking 01.png';
import imgIThinking02 from './assets/images/image_thinking/ithinking 02.png';
import imgIThinking03 from './assets/images/image_thinking/ithinking 03.png';
import imgIThinking04 from './assets/images/image_thinking/ithinking 04.png';
import imgIThinking05 from './assets/images/image_thinking/ithinking 05.png';
import imgIThinking06 from './assets/images/image_thinking/thinking 06.png';

// ── Sound imports ──────────────────────────────────────────
import sndAckGotIt          from './assets/sounds/ack/got_it.wav';
import sndAckOkay           from './assets/sounds/ack/okay.wav';
import sndAckOnIt           from './assets/sounds/ack/on_it.wav';

import sndGreetHelloReady   from './assets/sounds/greeting/hello_ready.wav';
import sndGreetOnline       from './assets/sounds/greeting/online.wav';
import sndGreetSystemsGo    from './assets/sounds/greeting/systems_go.wav';
import sndGreetVideogames   from './assets/sounds/greeting/videogames.wav';

import sndProcCheckingBanks from './assets/sounds/processing/checking_banks.wav';
import sndProcComputing     from './assets/sounds/processing/computing.wav';
import sndProcLetMeThink    from './assets/sounds/processing/let_me_think.wav';
import sndProcOneSecond     from './assets/sounds/processing/one_second.wav';
import sndProcProcessing    from './assets/sounds/processing/processing.wav';

// ── Sound groups ───────────────────────────────────────────
const ACK_SOUNDS        = [sndAckGotIt, sndAckOkay, sndAckOnIt];
const GREETING_SOUNDS   = [sndGreetHelloReady, sndGreetOnline, sndGreetSystemsGo, sndGreetVideogames];
const PROCESSING_SOUNDS = [sndProcCheckingBanks, sndProcComputing, sndProcLetMeThink, sndProcOneSecond, sndProcProcessing];

// How long (ms) between each repeated processing sound while THINKING.
const PROCESSING_INTERVAL_MS = 15000;

// ── Sound engine ───────────────────────────────────────────
//
// One Audio node is kept alive per "slot" so it can be stopped cleanly.
// _processingAudio  – currently-playing processing clip (may be null)
// _processingTimer  – setInterval handle for the processing loop
//
// _lastIndex        – WeakMap<array, number> tracks the last-played index
//                     per sound group so the same clip is never repeated
//                     twice in a row (as long as the group has > 1 file).

let _processingAudio = null;
let _processingTimer = null;

const _lastIndex = new Map();

// Seed each group with a random starting index so the first pick each run
// is already offset — prevents the same clip playing on every cold start.
[ACK_SOUNDS, GREETING_SOUNDS, PROCESSING_SOUNDS].forEach((group) => {
  _lastIndex.set(group, Math.floor(Math.random() * group.length));
});

/**
 * Pick a random entry from `sounds` that is NOT the one played last time.
 * With only 1 clip in the array it will always return that clip.
 */
function _playRandom(sounds) {
  const last = _lastIndex.get(sounds) ?? -1;

  let idx;
  if (sounds.length === 1) {
    idx = 0;
  } else {
    do { idx = Math.floor(Math.random() * sounds.length); } while (idx === last);
  }

  _lastIndex.set(sounds, idx);
  const audio = new Audio(sounds[idx]);
  audio.play().catch((err) => console.warn('[BMO SFX] play() failed:', err));
  return audio;
}

/** Stop and discard a playing Audio node safely. */
function _stopAudio(audio) {
  if (!audio) return;
  audio.pause();
  audio.currentTime = 0;
}

/** Stop the processing sound loop entirely. */
function stopProcessingLoop() {
  if (_processingTimer) { clearInterval(_processingTimer); _processingTimer = null; }
  _stopAudio(_processingAudio);
  _processingAudio = null;
}

/**
 * Start the processing sound loop.
 * Plays a random clip immediately, then repeats every PROCESSING_INTERVAL_MS.
 * Any previous loop is stopped first.
 */
function startProcessingLoop() {
  stopProcessingLoop();
  _processingAudio = _playRandom(PROCESSING_SOUNDS);
  _processingTimer = setInterval(() => {
    _stopAudio(_processingAudio);
    _processingAudio = _playRandom(PROCESSING_SOUNDS);
  }, PROCESSING_INTERVAL_MS);
}

// ── Preload every image into the decode cache ──────────────
[
  imgWarmup01,
  imgGreeting01, imgGreeting02, imgGreeting03,
  imgThinking04, imgThinking01, imgThinking02, imgThinking03,
  imgSpeaking03, imgSpeaking01, imgSpeaking02,
  imgListen01,   imgListen02,   imgListen03,
  imgIdle01,     imgError01,    imgCapturing01,
  imgFaceAngry,  imgFaceContemt,  imgFaceDread,      imgFaceHappy,
  imgFaceJudging, imgFaceNoticing, imgFaceRevulsion,  imgFaceSad,
  imgFaceSlightlySad, imgFaceSmugness,
  imgFaceStraightFace, imgFaceStraightAlt,
  imgFaceAmazed, imgFaceTired,
  imgFaceUnamused, imgFaceUnamusedAlt,
  imgIThinking01, imgIThinking02, imgIThinking03,
  imgIThinking04, imgIThinking05, imgIThinking06,
].forEach((src) => {
  const img = new Image();
  img.src = src;
  img.decode().catch(() => {});
});

// ── Face name → image URL map ──────────────────────────────
// Arrays are picked at random each time.
const FACE_MAP = {
  angry:                     imgFaceAngry,
  contempt_or_smug_or_happy: imgFaceContemt,
  dread:                     imgFaceDread,
  happy:                     imgFaceHappy,
  judging_or_angry:          imgFaceJudging,
  noticing_something:        imgFaceNoticing,
  revulsion:                 imgFaceRevulsion,
  sad:                       imgFaceSad,
  slightly_sad:              imgFaceSlightlySad,
  smugness:                  imgFaceSmugness,
  straight_face:             [imgFaceStraightFace, imgFaceStraightAlt],
  amazed:                    imgFaceAmazed,
  tired:                     imgFaceTired,
  unamused:                  [imgFaceUnamused, imgFaceUnamusedAlt],
};

function resolveFaceUrl(faceName) {
  if (!faceName) return null;
  const entry = FACE_MAP[faceName];
  if (!entry) return null;
  return Array.isArray(entry) ? entry[Math.floor(Math.random() * entry.length)] : entry;
}

// How long (ms) to hold the face expression before moving to the next state.
const FACE_HOLD_MS = 1000;

// ── State definitions ──────────────────────────────────────
const STATES = {
  idle:       { type: 'single', images: [imgIdle01] },
  warmup:     { type: 'single', images: [imgWarmup01] },
  thinking:   { type: 'loop',   loopInterval: 600, images: [imgThinking04, imgThinking01, imgThinking02, imgThinking03] },
  ithinking:  { type: 'loop',   loopInterval: 600, images: [imgIThinking01, imgIThinking02, imgIThinking03, imgIThinking05, imgIThinking06] },
  speaking:   { type: 'random-loop', loopInterval: 50,  images: [imgSpeaking03, imgSpeaking01, imgSpeaking02] },
  listening:  { type: 'loop',   loopInterval: 500, images: [imgListen01,   imgListen02,   imgListen03] },
  capturing:  { type: 'single', images: [imgCapturing01] },
  error:      { type: 'random', images: [imgError01] },
};

// ── Display ────────────────────────────────────────────────
const displayImg = document.getElementById('display');

function showImage(url) { displayImg.src = url; }

// ── Capture overlay ────────────────────────────────────────
// The #capture-overlay <img> sits at top-left above the background.
// It shows the screenshot / camera frame that BMO is currently analysing.

const captureOverlay = document.getElementById('capture-overlay');

/**
 * Show the capture overlay with a local file served via the bmo:// protocol.
 * @param {string} filePath  Absolute Windows or POSIX path emitted by main.py.
 */
function showCaptureOverlay(filePath) {
  if (!filePath) return;
  // Convert backslashes so the URL is valid, and use triple-slash so the URL
  // engine sees an empty host: "bmo:///D:/foo/bar.png" → pathname "/D:/foo/bar.png".
  // Double-slash ("bmo://D:/…") was parsed as host="D", path="/…", silently
  // dropping the drive letter colon and breaking Electron's protocol handler.
  const url = 'bmo:///' + filePath.replace(/\\/g, '/');
  captureOverlay.src = url;
  captureOverlay.style.display = 'block';
  console.log('[BMO] Capture overlay →', url);
}

/** Hide and reset the capture overlay. */
function hideCaptureOverlay() {
  captureOverlay.style.display = 'none';
  captureOverlay.src = '';
}

// ── Animation loop ─────────────────────────────────────────
let _loopTimer = null;
let _loopIndex = 0;

function clearLoop() {
  if (_loopTimer) { clearInterval(_loopTimer); _loopTimer = null; }
}

function activateState(stateName) {
  if (!STATES[stateName]) { console.warn(`[BMO] Unknown state: "${stateName}"`); return; }

  // While the post-capture hold is active, queue the request; last one wins.
  if (_captureHoldTimer !== null) {
    console.log(`[BMO] "${stateName}" queued (capture hold active)`);
    _captureQueuedState = stateName;
    return;
  }

  _activateStateRaw(stateName);
}

// ── One-shot sequence ──────────────────────────────────────
//
// playOnce() uses its OWN timer so clearLoop() (called by activateState)
// cannot accidentally cancel a greeting mid-sequence.
// _greetingActive is checked in the IDLE handler to drop the backend's
// redundant IDLE that always follows READY — the greeting's onDone
// callback already transitions to idle when the last frame is shown.

let _onceTimer      = null;
let _greetingActive = false;

function cancelOnce() {
  if (_onceTimer) { clearInterval(_onceTimer); _onceTimer = null; }
  _greetingActive = false;
}

/**
 * Plays through `images` once at `intervalMs` per frame, then calls `onDone`.
 * Immune to clearLoop(); interrupted only by cancelOnce() or a real user event.
 */
function playOnce(images, intervalMs, onDone) {
  cancelOnce();
  _greetingActive = true;
  let idx = 0;
  showImage(images[idx]);
  _onceTimer = setInterval(() => {
    idx += 1;
    if (idx < images.length) {
      showImage(images[idx]);
    } else {
      cancelOnce();   // clears _greetingActive before onDone fires
      onDone();
    }
  }, intervalMs);
}

// ── Face-hold machinery ────────────────────────────────────
//
// Sequence after a SPEAKING turn:
//   SPEAKING  → store face in _pendingFace, start speaking loop
//   SPEAKER_STOP → show face (if any), start FACE_HOLD_MS timer, clear _pendingFace
//   IDLE / LISTENING → if hold still running: queue the state (activates when timer fires)
//                      if hold already done:  activate immediately
//
// This means the face appears the moment audio stops, held for exactly
// FACE_HOLD_MS regardless of when the backend's next state message arrives.

let _pendingFace  = null;   // face received with SPEAKING, consumed on SPEAKER_STOP
let _faceHoldTimer = null;  // non-null while the face expression is on screen
let _queuedState  = null;   // next state to enter once the face hold finishes
let _inSpeaking   = false;  // guard: true between SPEAKING and SPEAKER_STOP
let _pendingQuit  = false;  // true when SHUTTING_DOWN arrived; quit after speaker settles
let _quitting     = false;  // latched true on SHUTTING_DOWN; prevents WS reconnect

// ── Capture-hold machinery ─────────────────────────────────
// After CAPTURING_END the capturing frame is locked on screen for
// CAPTURE_HOLD_MS.  Any activateState() call during that window is
// stored in _captureQueuedState; the last one wins and fires when
// the hold expires.  SHUTTING_DOWN bypasses the hold entirely.

const CAPTURE_HOLD_MS = 1000;
let _captureHoldTimer  = null;   // non-null while capture hold is active
let _captureQueuedState = null;  // state requested while hold was running

function _activateStateRaw(stateName) {
  // Direct path — skips capture-hold gate.  Used internally by the hold itself.
  const state = STATES[stateName];
  if (!state) { console.warn(`[BMO] Unknown state: "${stateName}"`); return; }
  clearLoop();

  if (state.type === 'single') {
    showImage(state.images[0]);
  } else if (state.type === 'loop') {
    _loopIndex = 0;
    showImage(state.images[0]);
    _loopTimer = setInterval(() => {
      _loopIndex = (_loopIndex + 1) % state.images.length;
      showImage(state.images[_loopIndex]);
    }, state.loopInterval);
  } else if (state.type === 'random-loop') {
    showImage(state.images[0]);
    _loopTimer = setInterval(() => {
      const max = state.images.length;
      let idx;
      do { idx = Math.floor(Math.random() * max); } while (max > 1 && idx === 0);
      showImage(state.images[idx]);
    }, state.loopInterval);
  } else if (state.type === 'random') {
    showImage(state.images[Math.floor(Math.random() * state.images.length)]);
  }
}

function startCaptureHold() {
  if (_captureHoldTimer) { clearTimeout(_captureHoldTimer); }
  _captureQueuedState = null;
  _captureHoldTimer = setTimeout(() => {
    _captureHoldTimer   = null;
    const next          = _captureQueuedState ?? 'idle';
    _captureQueuedState = null;
    console.log(`[BMO] Capture hold done → "${next}"`);
    _activateStateRaw(next);
  }, CAPTURE_HOLD_MS);
}

function clearFaceHold() {
  if (_faceHoldTimer) { clearTimeout(_faceHoldTimer); _faceHoldTimer = null; }
  _queuedState = null;
}

/**
 * Signal Python that the renderer is done, then wait for Python's WebSocket
 * to close before quitting Electron.
 *
 * WHY: Electron spawns Python as a child process.  Calling window.bmo.quit()
 * immediately after sending READY_TO_QUIT races against Python's final work
 * (os.startfile app launches, module teardown).  Electron wins that race and
 * kills Python before it finishes — so launched apps are never seen.
 *
 * FIX: send READY_TO_QUIT, then let the 'close' WebSocket event drive the
 * actual Electron quit.  Python closes its WS server naturally when its
 * process ends, so 'close' fires only after Python is truly done.
 * A 5-second hard timeout guards against Python hanging or crashing.
 */
let _forceQuitTimer = null;

function doQuit() {
  if (_ws && _ws.readyState === WebSocket.OPEN) {
    _ws.send(JSON.stringify({ event: 'READY_TO_QUIT' }));
    // Wait for Python to close the WS (its process exiting) before we quit.
    // The 'close' handler below calls _doElectronQuit() when that happens.
    // Hard timeout: if Python doesn't exit within 5 s, force-quit anyway.
    if (_forceQuitTimer) clearTimeout(_forceQuitTimer);
    _forceQuitTimer = setTimeout(() => {
      console.warn('[BMO WS] Python did not close WS in time — force quitting.');
      _doElectronQuit();
    }, 5000);
  } else {
    // WS already closed (or was never open) — quit straight away.
    _doElectronQuit();
  }
}

/** Actually close the Electron window — called only after Python has exited. */
function _doElectronQuit() {
  if (_forceQuitTimer) { clearTimeout(_forceQuitTimer); _forceQuitTimer = null; }
  window.bmo.quit();
}

// How long (ms) to show the idle face before actually quitting.
const IDLE_BEFORE_QUIT_MS = 2000;

/**
 * Shows the idle image for IDLE_BEFORE_QUIT_MS, then calls doQuit().
 * Used so the shutdown sequence is: face hold → idle → quit.
 */
function doQuitAfterIdle() {
  activateState('idle');
  setTimeout(() => doQuit(), IDLE_BEFORE_QUIT_MS);
}

/**
 * Called on SPEAKER_DONE.
 * Shows the face for FACE_HOLD_MS then activates whatever state arrives next.
 * If _pendingQuit is set, quits after the hold instead of transitioning.
 * If no face, transitions (or quits) immediately.
 */
function onSpeakerStop(faceName) {
  clearLoop();
  clearFaceHold();

  const faceUrl = resolveFaceUrl(faceName);

  if (!faceUrl) {
    if (faceName) console.warn(`[BMO] Unknown face: "${faceName}"`);
    // No face to show — if a shutdown is pending, show idle then quit.
    if (_pendingQuit) { _pendingQuit = false; doQuitAfterIdle(); }
    return;
  }

  console.log(`[BMO] SPEAKER_DONE: showing face "${faceName}" for ${FACE_HOLD_MS} ms`);
  showImage(faceUrl);

  _faceHoldTimer = setTimeout(() => {
    _faceHoldTimer = null;
    if (_pendingQuit) {
      // Shutdown was pending — show idle, then quit.
      _pendingQuit = false;
      doQuitAfterIdle();
    } else if (_queuedState) {
      console.log(`[BMO] Face hold done → "${_queuedState}"`);
      activateState(_queuedState);
      _queuedState = null;
    }
  }, FACE_HOLD_MS);
}

/**
 * Called when IDLE or LISTENING arrives after a SPEAKING turn.
 * Queues behind the face hold if it's still running; otherwise activates now.
 */
function transitionToState(stateName) {
  if (_faceHoldTimer !== null) {
    console.log(`[BMO] "${stateName}" queued (face hold active)`);
    _queuedState = stateName;
  } else {
    activateState(stateName);
  }
}

// ── Boot ───────────────────────────────────────────────────
// Hold the warmup image until the backend emits READY (all modules loaded).
activateState('warmup');

// ── WebSocket bridge ───────────────────────────────────────
// ws://localhost:7878  —  auto-reconnects every 3 s.
const WS_URL = 'ws://localhost:7878';
let _ws = null;
let _reconnectTimer = null;

function connectWs() {
  if (_ws && (_ws.readyState === WebSocket.OPEN || _ws.readyState === WebSocket.CONNECTING)) return;
  _ws = new WebSocket(WS_URL);

  _ws.addEventListener('open', () => {
    console.log(`[BMO WS] Connected to ${WS_URL}`);
    if (_reconnectTimer) { clearTimeout(_reconnectTimer); _reconnectTimer = null; }
  });

  _ws.addEventListener('message', ({ data }) => {
    let payload;
    try { payload = JSON.parse(data); }
    catch { console.warn('[BMO WS] Bad JSON:', data); return; }

    // main.py now uses "event" as the key (was "state")
    const { event: wsEvent, face = null } = payload;
    console.log(`[BMO WS] ▶ ${wsEvent}  face=${JSON.stringify(face)}`);

    switch (wsEvent) {

      // ── All modules ready — play greeting animation then idle ──
      case 'READY':
        _playRandom(GREETING_SOUNDS);
        playOnce(
          [imgGreeting01, imgGreeting02, imgGreeting03],
          600,
          () => activateState('idle'),
        );
        break;

      // ── Playback starts ──────────────────────────────────
      case 'SPEAKING':
        stopProcessingLoop();          // kill any processing loop still running
        cancelOnce();                  // abort greeting if still running
        hideCaptureOverlay();          // done analysing — clear the captured frame
        _pendingFace = face;           // face is now delivered with SPEAKING (not separately)
        _inSpeaking  = true;
        activateState('speaking');
        break;

      // ── Playback ends — show face now ────────────────────
      // Renamed from SPEAKER_STOP → SPEAKER_DONE in new main.py
      case 'SPEAKER_DONE': {
        const f   = _pendingFace;
        _pendingFace = null;
        _inSpeaking  = false;
        onSpeakerStop(f);
        break;
      }

      // ── Audio captured; Whisper is processing ────────────
      // New event in new main.py. Visually identical to THINKING from the
      // renderer's perspective — keeps the thinking animation running.
      case 'TRANSCRIBING':
        _pendingFace = null;
        _inSpeaking  = false;
        clearFaceHold();
        cancelOnce();                  // abort greeting if still running
        hideCaptureOverlay();          // capture phase is over
        _playRandom(ACK_SOUNDS);       // "got it / okay / on it"
        activateState('thinking');
        break;

      // ── Next state after speaking ────────────────────────
      // These queue behind the face hold (or activate immediately if no face).
      // Safety net: if SPEAKER_DONE was never received (e.g. empty TTS reply),
      // _inSpeaking guards so we still consume and show any pending face.
      case 'IDLE':
        // Ignore the IDLE that the backend fires right after READY —
        // the greeting sequence's onDone callback already transitions to idle.
        if (_greetingActive) break;
        hideCaptureOverlay();
        if (_inSpeaking) {
          const f   = _pendingFace;
          _pendingFace = null;
          _inSpeaking  = false;
          onSpeakerStop(f);
        }
        transitionToState('idle');
        break;

      case 'LISTENING':
        hideCaptureOverlay();
        if (_inSpeaking) {
          const f   = _pendingFace;
          _pendingFace = null;
          _inSpeaking  = false;
          onSpeakerStop(f);
        }
        transitionToState('listening');
        break;

      // ── Thinking — cancel any face hold (user spoke mid-hold) ──
      case 'THINKING':
        _pendingFace = null;
        _inSpeaking  = false;
        clearFaceHold();
        cancelOnce();                  // abort greeting if still running
        hideCaptureOverlay();          // plain thinking — no capture overlay
        startProcessingLoop();         // play processing sounds at intervals
        activateState('thinking');
        break;

      // ── Thinking while analysing a captured image ────────
      // main.py saves the capture to a temp file and sends its path here.
      // The ithinking animation plays on the main display; the captured
      // frame appears in the top-left overlay so the user can see what
      // BMO is looking at.
      case 'THINKING_WITH_IMAGE': {
        const { image_path } = payload;
        _pendingFace = null;
        _inSpeaking  = false;
        clearFaceHold();
        cancelOnce();
        startProcessingLoop();
        if (image_path) showCaptureOverlay(image_path);
        activateState('ithinking');
        break;
      }

      // ── Process is about to exit ─────────────────────────
      // Set _pendingQuit so onSpeakerStop() quits after the face hold
      // (or immediately if face is null). SPEAKER_DONE always arrives
      // before SHUTTING_DOWN in the Python flow, but _inSpeaking guards
      // the edge case where it hasn't landed yet.
      case 'SHUTTING_DOWN': {
        stopProcessingLoop();
        // Cancel any capture hold so shutdown is never blocked by it.
        if (_captureHoldTimer) { clearTimeout(_captureHoldTimer); _captureHoldTimer = null; _captureQueuedState = null; }
        _quitting    = true;   // prevent the WS close handler from scheduling a reconnect
        _pendingQuit = true;

        if (_inSpeaking) {
          // SPEAKER_DONE hasn't arrived yet — onSpeakerStop will handle quit.
          break;
        }

        // SPEAKER_DONE already processed — if a face hold is still running,
        // replace it so it calls doQuit() on completion.
        // If no hold at all, quit straight away.
        if (_faceHoldTimer !== null) {
          clearTimeout(_faceHoldTimer);
          _faceHoldTimer = setTimeout(() => {
            _faceHoldTimer = null;
            _pendingQuit = false;
            doQuitAfterIdle();
          }, FACE_HOLD_MS);
        } else {
          _pendingQuit = false;
          doQuitAfterIdle();
        }
        break;
      }

      // ── Camera snapshot in progress ──────────────────────
      case 'CAPTURING_START':
        activateState('capturing');
        break;

      // ── Snapshot done — hold the frame for CAPTURE_HOLD_MS ──
      case 'CAPTURING_END':
        startCaptureHold();
        break;

      default:
        console.warn('[BMO WS] Unknown event:', wsEvent);
    }
  });

  _ws.addEventListener('close', () => {
    if (_quitting) {
      // Python's process exited — its WS server closed the connection.
      // NOW it's safe to close Electron (apps are already running).
      console.log('[BMO WS] Python exited cleanly — closing Electron.');
      _doElectronQuit();
      return;
    }
    console.log('[BMO WS] Disconnected — retrying in 3 s …');
    scheduleReconnect();
  });

  _ws.addEventListener('error', () => { _ws.close(); });
}

function scheduleReconnect() {
  if (_reconnectTimer) return;
  _reconnectTimer = setTimeout(() => { _reconnectTimer = null; connectWs(); }, 3000);
}

connectWs();

// ── ESC to quit ────────────────────────────────────────────
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    console.log('[BMO] ESC pressed — quitting');
    window.bmo.closeApp();
  }
});