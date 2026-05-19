/**
 * renderer.js — Music Player
 */
import './index.css';

import maxIcon     from './assets/icons/one.png';
import restoreIcon from './assets/icons/both.png';

import albumDefault from './assets/icons/album_default.webp';
import bgVideo      from './assets/video/background.mp4';

import iconPrev     from './assets/icons/btn-prev.png';
import iconPlay     from './assets/icons/btn-play.png';
import iconPause    from './assets/icons/btn-pause.png';
import iconNext     from './assets/icons/btn-next.png';
import iconPlaylist from './assets/icons/playlist.png';
import markerGif    from './assets/icons/Marker.gif';

/* ─── Window Controls ────────────────────────────────────── */
// Lift the FOUC visibility guard — styles and fonts are now applied
window.addEventListener('load', () => document.documentElement.classList.add('ready'));

document.getElementById('min-btn').onclick   = () => window.winAPI.minimize();
document.getElementById('max-btn').onclick   = () => window.winAPI.maximize();
document.getElementById('close-btn').onclick = () => window.winAPI.close();

const maxBtn = document.getElementById('max-btn');
window.winAPI.onMaximizeChange((isMaximized) => {
  if (isMaximized) {
    // two.png is 480×480 (1:1) → display as 38×38
    maxBtn.style.backgroundImage = `url(${restoreIcon})`;
    maxBtn.style.width  = '38px';
    maxBtn.style.height = '38px';
  } else {
    // one.png is 430×315 (1.37:1) → display as 52×38
    maxBtn.style.backgroundImage = `url(${maxIcon})`;
    maxBtn.style.width  = '52px';
    maxBtn.style.height = '38px';
  }
});

/* ─── Set button icon sources ────────────────────────────── */
document.querySelector('#prev-btn img').src    = iconPrev;
document.querySelector('#play-btn img').src    = iconPlay;
document.querySelector('#next-btn img').src    = iconNext;
document.getElementById('bg-video').src        = bgVideo;
document.getElementById('playlist-icon').src   = iconPlaylist;
document.getElementById('progress-marker').src = markerGif;

// Hide the album <video>, show the <img> with the webp default
const albumVideo = document.getElementById('album-video');
const albumCover = document.getElementById('album-cover');
albumVideo.style.display = 'none';
albumCover.src           = albumDefault;
albumCover.style.display = 'block';

/* ─── Helpers ─────────────────────────────────────────────── */
function formatTime(secs) {
  if (!secs || isNaN(secs)) return '0:00';
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

// Convert a Windows/POSIX file path to a media:// URL served by the main process.
// Direct file:// access is blocked by Electron's security model in the renderer.
function toFileUrl(filePath) {
  const normalized = filePath.replace(/\\/g, '/');
  return 'media://host/' + encodeURIComponent(normalized);
}

/* ─── Progress ────────────────────────────────────────────── */
function updateProgress(fraction) {
  const pct = Math.max(0, Math.min(1, fraction)) * 100;
  document.getElementById('progress-fill').style.width  = pct + '%';
  document.getElementById('progress-marker').style.left = pct + '%';
}
window._updateProgress = updateProgress;

/* ─── Marquee ─────────────────────────────────────────────── */
function refreshMarquee(text) {
  const el   = document.getElementById('track-title');
  const wrap = el.parentElement;
  el.textContent = text;
  el.classList.remove('scrolling');
  // Kick off animation only when text overflows
  requestAnimationFrame(() => {
    if (el.scrollWidth > wrap.clientWidth) {
      el.classList.add('scrolling');
    }
  });
}

/* ─── Audio Engine ────────────────────────────────────────── */
const audio = document.getElementById('audio-player');
let playlist     = [];
let currentIndex = 0;

/** Load a track by index, fetch its metadata, update the UI */
async function loadTrack(index) {
  if (!playlist.length) return;
  currentIndex = Math.max(0, Math.min(index, playlist.length - 1));
  const track   = playlist[currentIndex];

  // Point the audio element at the file
  audio.src = toFileUrl(track.path);

  // Optimistic UI update with filename-derived title
  refreshMarquee(track.title);
  document.getElementById('track-artist').textContent = track.artist || '—';
  document.getElementById('current-time').textContent = '0:00';
  document.getElementById('total-time').textContent   = '0:00';
  updateProgress(0);

  // Show cover immediately if already cached from prefetch.
  // If prefetch ran and found nothing, reset to default right away.
  // If prefetch hasn't run yet, keep the previous cover — we'll swap once metadata arrives.
  if (track.cover) {
    albumCover.src = track.cover;
  } else if (track.metaLoaded) {
    albumCover.src = albumDefault;
  }

  // Fetch real metadata (title, artist, embedded cover art)
  try {
    const meta = await window.winAPI.getMetadata(track.path);
    if (meta) {
      if (meta.title)  { track.title  = meta.title;  refreshMarquee(meta.title); }
      if (meta.artist) { track.artist = meta.artist; document.getElementById('track-artist').textContent = meta.artist; }
      if (meta.cover) {
        const coverSrc = `data:${meta.cover.format};base64,${meta.cover.data}`;
        track.cover = coverSrc;
        // Preload before swap so the image never blinks through a blank frame
        const img = new Image();
        img.onload = () => { albumCover.src = coverSrc; };
        img.src = coverSrc;
      } else if (!track.cover) {
        // No cover anywhere — only now fall back to the placeholder
        albumCover.src = albumDefault;
      }
    } else if (!track.cover) {
      albumCover.src = albumDefault;
    }
  } catch (e) {
    if (!track.cover) albumCover.src = albumDefault;
  }
  track.metaLoaded = true;

  // Just move the active highlight — no full re-render (preserves scroll position)
  updateActiveItem(currentIndex);
}

function playAudio() {
  audio.play().catch(console.error);
  document.querySelector('#play-btn img').src = iconPause;
}

function pauseAudio() {
  audio.pause();
  document.querySelector('#play-btn img').src = iconPlay;
}

/* ─── Control Buttons ─────────────────────────────────────── */
document.getElementById('play-btn').addEventListener('click', () => {
  if (!playlist.length) return; // no folder set yet — nothing to play
  if (audio.paused) {
    if (!audio.src || audio.src === window.location.href) {
      loadTrack(0).then(playAudio);
    } else {
      playAudio();
    }
  } else {
    pauseAudio();
  }
});

document.getElementById('prev-btn').addEventListener('click', () => {
  if (!playlist.length) return;
  // If more than 3 s in, restart the current track; otherwise go back
  if (audio.currentTime > 3) {
    audio.currentTime = 0;
  } else {
    loadTrack((currentIndex - 1 + playlist.length) % playlist.length).then(playAudio);
  }
});

document.getElementById('next-btn').addEventListener('click', () => {
  if (!playlist.length) return;
  loadTrack((currentIndex + 1) % playlist.length).then(playAudio);
});

// Auto-advance when a track ends
audio.addEventListener('ended', () => {
  loadTrack((currentIndex + 1) % playlist.length).then(playAudio);
});

/* ─── Progress Bar ─────────────────────────────────────────── */
audio.addEventListener('timeupdate', () => {
  if (isScrubbing) return;           // visuals are driven by the scrub, not playback
  if (!audio.duration) return;
  updateProgress(audio.currentTime / audio.duration);
  document.getElementById('current-time').textContent = formatTime(audio.currentTime);
  document.getElementById('total-time').textContent   = formatTime(audio.duration);
});

audio.addEventListener('loadedmetadata', () => {
  document.getElementById('total-time').textContent = formatTime(audio.duration);
});

/* ─── Progress Bar — scrub by click or drag ─────────────────────
   We use document-level pointermove/pointerup instead of setPointerCapture
   on the element because Electron's frameless-window OS drag layer can
   intercept mousemove packets mid-gesture even when the source element has
   -webkit-app-region:no-drag, causing the drag to silently drop after the
   first pixel of movement. Document-level listeners sit above that layer. */
const progressTrack = document.getElementById('progress-track');
let isScrubbing  = false;
let scrubFraction = 0;

function fractionFromEvent(e) {
  const rect = progressTrack.getBoundingClientRect();
  return Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
}

function onScrubMove(e) {
  if (!isScrubbing || !audio.duration) return;
  scrubFraction = fractionFromEvent(e);
  updateProgress(scrubFraction);
  document.getElementById('current-time').textContent = formatTime(scrubFraction * audio.duration);
}

function onScrubEnd(e) {
  if (!isScrubbing) return;
  isScrubbing = false;
  document.removeEventListener('pointermove',   onScrubMove);
  document.removeEventListener('pointerup',     onScrubEnd);
  document.removeEventListener('pointercancel', onScrubEnd);
  // pointercancel carries no valid coordinates — skip the seek commit
  if (e.type === 'pointercancel' || !audio.duration) return;
  scrubFraction = fractionFromEvent(e);
  audio.currentTime = scrubFraction * audio.duration;
  updateProgress(scrubFraction);
  document.getElementById('current-time').textContent = formatTime(audio.currentTime);
}

progressTrack.addEventListener('pointerdown', (e) => {
  if (!audio.duration) return;
  e.preventDefault();
  isScrubbing   = true;
  scrubFraction = fractionFromEvent(e);
  updateProgress(scrubFraction);
  document.getElementById('current-time').textContent = formatTime(scrubFraction * audio.duration);
  // Attach move/end to document so they survive the pointer leaving the element
  document.addEventListener('pointermove',   onScrubMove);
  document.addEventListener('pointerup',     onScrubEnd);
  document.addEventListener('pointercancel', onScrubEnd);
});

/* ─── Playlist Panel Toggle ───────────────────────────────── */
const playlistPanel     = document.getElementById('playlist-panel');
const playlistToggleBtn = document.getElementById('playlist-toggle-btn');
const playlistCloseBtn  = document.getElementById('playlist-close-btn');

const glassBox    = document.querySelector('.glass-box');
const winControls = document.querySelector('.window-controls');

function openPlaylist() {
  playlistPanel.classList.remove('closing');
  playlistPanel.classList.add('open');
  glassBox.classList.add('pl-open');
  winControls.classList.add('pl-open');
}

function closePlaylist() {
  playlistPanel.classList.remove('open');
  playlistPanel.classList.add('closing');
  glassBox.classList.remove('pl-open');
  winControls.classList.remove('pl-open');
  playlistPanel.addEventListener('animationend', () => {
    playlistPanel.classList.remove('closing');
  }, { once: true });
}

playlistToggleBtn.addEventListener('click', async () => {
  // Close if already open
  if (playlistPanel.classList.contains('open')) {
    closePlaylist();
    return;
  }

  // First-time use: no folder saved yet — ask the user to pick one
  const savedFolder = await window.winAPI.getMusicFolder();
  if (!savedFolder) {
    const picked = await window.winAPI.pickFolder();
    if (!picked) return; // user cancelled — do nothing
    await window.winAPI.setMusicFolder(picked);
    await loadMusicFolder(picked);
  }

  openPlaylist();
});
playlistCloseBtn.addEventListener('click', closePlaylist);

/* ─── Playlist Rendering ──────────────────────────────────── */
function renderPlaylist(tracks, activeIndex, onSelect) {
  const listEl = document.getElementById('playlist-list');
  listEl.innerHTML = '';

  if (!tracks || tracks.length === 0) {
    listEl.innerHTML = '<div class="playlist-empty">No tracks loaded — click the album art to add music.</div>';
    return;
  }

  tracks.forEach((track, i) => {
    const item = document.createElement('div');
    item.className = 'playlist-item' + (i === activeIndex ? ' active' : '');
    item.innerHTML = `
      <img class="playlist-item-thumb" src="${track.cover || albumDefault}" alt="" draggable="false" />
      <div class="playlist-item-info">
        <div class="playlist-item-title">${track.title || 'Unknown Title'}</div>
        <div class="playlist-item-artist">${track.artist || 'Unknown Artist'}</div>
      </div>
    `;
    item.addEventListener('click', () => {
      if (typeof onSelect === 'function') onSelect(i);
      closePlaylist();
    });
    listEl.appendChild(item);
  });
}
window._renderPlaylist = renderPlaylist;

/** Move the active highlight without re-rendering the whole list */
function updateActiveItem(index) {
  document.querySelectorAll('#playlist-list .playlist-item').forEach((el, i) => {
    el.classList.toggle('active', i === index);
  });
}

/** Patch a single playlist row's thumb/title/artist in-place */
function updatePlaylistItem(index) {
  const items = document.querySelectorAll('#playlist-list .playlist-item');
  const item  = items[index];
  if (!item) return;
  const track    = playlist[index];
  const thumb    = item.querySelector('.playlist-item-thumb');
  const titleEl  = item.querySelector('.playlist-item-title');
  const artistEl = item.querySelector('.playlist-item-artist');
  if (thumb)    thumb.src             = track.cover  || albumDefault;
  if (titleEl)  titleEl.textContent  = track.title  || 'Unknown Title';
  if (artistEl) artistEl.textContent = track.artist || 'Unknown Artist';
}

/* ─── Background Metadata Prefetch ───────────────────────── */
/** Fetches metadata for every track in the playlist sequentially.
 *  Updates each playlist row as soon as its data arrives. */
async function prefetchAllMetadata() {
  for (let i = 0; i < playlist.length; i++) {
    if (playlist[i].metaLoaded) continue; // already done (e.g. the playing track)
    try {
      const meta = await window.winAPI.getMetadata(playlist[i].path);
      if (meta) {
        if (meta.title)  playlist[i].title  = meta.title;
        if (meta.artist) playlist[i].artist = meta.artist;
        if (meta.cover)  playlist[i].cover  = `data:${meta.cover.format};base64,${meta.cover.data}`;
      }
    } catch (_) { /* silently skip bad files */ }
    playlist[i].metaLoaded = true;
    updatePlaylistItem(i);
  }
}

/* ─── Idle Collapse — Mini Player ────────────────────────── */
/**
 * After IDLE_MS of no mouse/keyboard activity the player collapses
 * into a slim pill at the bottom of the window. Any mouse movement
 * brings it back to centre and restarts the countdown.
 */
const IDLE_MS = 12_000; // 12 s — feels natural for a music player
let   idleTimer = null;
let   isMini    = false;

function enterMini() {
  if (isMini) return;
  isMini = true;
  // Close the queue panel so it doesn't dangle off a tiny pill
  if (playlistPanel.classList.contains('open')) closePlaylist();

  // Strip .scrolling before adding .mini so the CSS :not(.scrolling) rule
  // snaps the element back to translateX(0) as the transition begins.
  const titleEl = document.getElementById('track-title');
  titleEl.classList.remove('scrolling');

  glassBox.classList.add('mini');
  document.body.classList.add('mini');

  // After the layout settles at the narrower pill width, re-check whether the
  // title still overflows and restart the animation cleanly from position 0.
  requestAnimationFrame(() => {
    void titleEl.offsetWidth; // force reflow so the transform reset lands
    if (titleEl.scrollWidth > titleEl.parentElement.clientWidth) {
      titleEl.classList.add('scrolling');
    }
  });
}

function exitMini() {
  if (!isMini) return;
  isMini = false;
  glassBox.classList.remove('mini');
  document.body.classList.remove('mini');
}

function resetIdle() {
  if (isMini) exitMini();
  clearTimeout(idleTimer);
  idleTimer = setTimeout(enterMini, IDLE_MS);
}

// Wake up on any intentional input
document.addEventListener('mousemove',  resetIdle, { passive: true });
document.addEventListener('mousedown',  resetIdle, { passive: true });
document.addEventListener('keydown',    resetIdle, { passive: true });
document.addEventListener('wheel',      resetIdle, { passive: true });
document.addEventListener('touchstart', resetIdle, { passive: true });

// Kick off the first countdown immediately
resetIdle();

/* ─── Music Folder Loading ────────────────────────────────── */
/** Load all audio from a folder path, render playlist, prefetch metadata. */
async function loadMusicFolder(folderPath) {
  let filePaths;
  try {
    filePaths = await window.winAPI.loadFolder(folderPath);
  } catch (err) {
    console.error('loadFolder failed for', folderPath, err);
    return;
  }

  if (!filePaths || filePaths.length === 0) {
    console.warn('No audio files found in', folderPath);
    return;
  }

  playlist = filePaths.map((fp) => {
    const fileName = fp.split('\\').pop().split('/').pop();
    const title    = fileName.replace(/\.[^/.]+$/, '');
    return { title, artist: 'Unknown Artist', path: fp };
  });
  currentIndex = 0;

  renderPlaylist(playlist, 0, (i) => { loadTrack(i).then(playAudio); });
  loadTrack(0); // loads art + metadata, does NOT auto-play
  prefetchAllMetadata();
  console.log(`Loaded ${playlist.length} track(s) from ${folderPath}`);
}

/* ─── Auto-load Saved Folder on Start ────────────────────── */
window.winAPI.getMusicFolder()
  .then((savedFolder) => {
    if (!savedFolder) return; // No folder configured yet — wait for first playlist click
    return loadMusicFolder(savedFolder);
  })
  .catch((err) => console.error('Startup auto-load failed:', err));