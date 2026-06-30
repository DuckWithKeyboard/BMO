/**
 * Renderer context – loaded by webpack.
 * https://electronjs.org/docs/tutorial/process-model
 */

import './index.css';

// ─── Asset imports ────────────────────────────────────────────
import loadingGif   from './assets/images/Load.gif';
import swordPng     from './assets/images/sword.png';

// Desktop icons
import musicImg    from './assets/icons/music.jpg';
import bmoImg      from './assets/icons/bmo.jpg';
import gamesImg    from './assets/icons/games.jpg';
import internetImg from './assets/icons/internet.jpg';

// Exit icon
import exitImg   from 'D:/BMO_entry/src/assets/icons/exit.jpg';
import overlayImg from 'D:/BMO_entry/src/assets/icons/overlay.jpg';

// Folder icons
import messengerImg from 'D:/BMO_entry/src/assets/icons/messenger.jpeg';
import silksongImg  from 'D:/BMO_entry/src/assets/icons/silksong.ico';
import forzaImg     from 'D:/BMO_entry/src/assets/icons/forza.ico';

// ─── Wallpapers ───────────────────────────────────────────────
const wallpaperCtx = require.context(
  './assets/wallpapers',
  false,
  /\.(png|jpe?g|webp)$/i,
);
const WALLPAPERS = wallpaperCtx.keys().map(wallpaperCtx);

function pickRandom(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

// ─── Folder definitions ───────────────────────────────────────
//
// Each icon entry supports:
//   img   — static imported image
//   label — display name
//   url   — opens a fullscreen Electron window at this URL (Escape to close, F11 for fullscreen)
//   appId — launches the registered exe via open-app
//
const FOLDERS = {
  games: {
    label: 'Games',
    icons: [
      {
        img:   messengerImg,
        label: 'Messenger',
        url:   'https://messenger.abeto.co/',
      },
      {
        img:   silksongImg,
        label: 'Silksong',
        appId: 'silksong',
      },
      {
        img:   forzaImg,
        label: 'Forza Horizon 5',
        appId: 'forza',
      },
    ],
  },
};

// ─── Splash helpers ───────────────────────────────────────────
const splash = document.getElementById('splash-screen');

function showSplash() {
  if (!splash) return;
  splash.classList.remove('hidden');
}

function hideSplash() {
  if (!splash) return;
  splash.classList.add('hidden');
}

// ─── Splash asset injection ───────────────────────────────────
const splashGif   = document.getElementById('splash-gif');
const splashSword = document.getElementById('splash-sword');
if (splashGif)   splashGif.src   = loadingGif;
if (splashSword) splashSword.src = swordPng;

// ─── Desktop icon image injection ────────────────────────────
document.getElementById('icon-music').src    = musicImg;
document.getElementById('icon-bmo').src      = bmoImg;
document.getElementById('icon-games').src    = gamesImg;
document.getElementById('icon-internet').src = internetImg;
document.getElementById('icon-overlay').src  = overlayImg;
document.getElementById('icon-exit').src     = exitImg;

// ─── Desktop app icon click handlers ─────────────────────────
document.querySelectorAll('.desktop-icon[data-app]').forEach(btn => {
  btn.addEventListener('click', () => {
    showSplash();
    window.bmoOS.openApp(btn.dataset.app);
  });
});

// ─── Exit icon click handler ──────────────────────────────────
document.querySelector('.desktop-icon[data-action="exit"]')
  ?.addEventListener('click', () => {
    window.bmoOS.quitApp();
  });

// ─── App close handler ────────────────────────────────────────
window.bmoOS.onAppClosed(() => {
  setTimeout(hideSplash, 1500);
});

// ─── Folder menu logic ────────────────────────────────────────
const folderMenu      = document.getElementById('folder-menu');
const folderMenuTitle = folderMenu.querySelector('.folder-menu-title');
const folderMenuIcons = folderMenu.querySelector('.folder-menu-icons');
const folderMenuClose = folderMenu.querySelector('.folder-menu-close');

function openFolder(key) {
  const folder = FOLDERS[key];
  if (!folder) return;

  folderMenuTitle.textContent = folder.label;
  folderMenuIcons.innerHTML   = '';

  if (folder.icons.length === 0) {
    const empty = document.createElement('p');
    empty.style.cssText = 'color:rgba(255,255,255,0.5);font-size:0.8rem;padding:0.5rem 0;';
    empty.textContent   = 'No items yet.';
    folderMenuIcons.appendChild(empty);
  } else {
    folder.icons.forEach(({ img, label, url, appId }) => {
      const item = document.createElement('div');
      item.className = 'desktop-item';

      const btn = document.createElement('button');
      btn.className = 'desktop-icon';
      btn.setAttribute('aria-label', label);

      const imgEl = document.createElement('img');
      imgEl.alt = '';
      imgEl.src = img;
      btn.appendChild(imgEl);

      btn.addEventListener('click', () => {
        closeFolder();
        showSplash();
        if (url) {
          window.bmoOS.openUrl(url);
        } else if (appId) {
          window.bmoOS.openApp(appId);
        }
      });

      const lbl = document.createElement('span');
      lbl.className   = 'desktop-label';
      lbl.textContent = label;

      item.appendChild(btn);
      item.appendChild(lbl);
      folderMenuIcons.appendChild(item);
    });
  }

  folderMenu.classList.add('open');
  folderMenu.setAttribute('aria-hidden', 'false');
  document
    .querySelector(`.desktop-folder[data-folder="${key}"]`)
    ?.setAttribute('aria-expanded', 'true');
}

function closeFolder() {
  folderMenu.classList.remove('open');
  folderMenu.setAttribute('aria-hidden', 'true');
  document
    .querySelectorAll('.desktop-folder')
    .forEach(btn => btn.setAttribute('aria-expanded', 'false'));
}

document.querySelectorAll('.desktop-folder').forEach(btn => {
  btn.addEventListener('click', () => openFolder(btn.dataset.folder));
});

folderMenuClose.addEventListener('click', closeFolder);
folderMenu.addEventListener('click', e => {
  if (e.target === folderMenu) closeFolder();
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeFolder();
});

// ─── Initial splash dismissal + wallpaper reveal ─────────────
const HOLD_MS = 8000;

window.addEventListener('load', () => {
  if (WALLPAPERS.length > 0) {
    const wallpaperUrl = pickRandom(WALLPAPERS);
    const preload      = new Image();
    preload.src        = wallpaperUrl;
    preload.onload = () => {
      document.body.style.setProperty('--wallpaper-url', `url("${wallpaperUrl}")`);
    };
  }

  setTimeout(() => {
    document.getElementById('desktop')?.classList.add('visible');
    hideSplash();
  }, HOLD_MS);
});