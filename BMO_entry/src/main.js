const { app, BrowserWindow, ipcMain } = require('electron');
const { spawn } = require('child_process');
const path = require('node:path');

// Handle creating/removing shortcuts on Windows when installing/uninstalling.
if (require('electron-squirrel-startup')) {
  app.quit();
}

// ─── App exe paths ────────────────────────────────────────────
const APP_EXES = {
  music:    'D:\\BMO\\out\\bmo-win32-x64\\music_player.exe',
  internet: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  bmo:      'D:\\BMO_AI\\out\\B.M.O-win32-x64\\BMO.exe',
  overlay:  'D:\\bmo_overlay\\out\\bmo_overlay-win32-x64\\bmo_overlay.exe',
  silksong: 'D:\\Users\\user\\Downloads\\Hollow-Knight-Silksong-SteamRIP.com\\Hollow Knight Silksong\\Hollow Knight Silksong.exe',
  forza:    'D:\\Forza.Horizon.5.v1.614.70.0.Incl.ALL.DLC\\Forza.Horizon.5.v1.614.70.0.Incl.ALL.DLC\\56789OIUYTUIOP[][POIUYTYUIOPBBNVBNJKL M,..exe',
};

// ─── Keep a reference to the OS window ───────────────────────
let osWindow = null;

const createWindow = () => {
  osWindow = new BrowserWindow({
    fullscreen: true,
    frame:      false,
    webPreferences: {
      preload: MAIN_WINDOW_PRELOAD_WEBPACK_ENTRY,
    },
  });

  osWindow.loadURL(MAIN_WINDOW_WEBPACK_ENTRY);
  osWindow.webContents.openDevTools();

  osWindow.on('closed', () => {
    osWindow = null;
  });
};

// ─── Helper: restore OS window after a child closes ──────────
function onChildClosed() {
  if (osWindow && !osWindow.isDestroyed()) {
    osWindow.show();
    osWindow.focus();
    osWindow.webContents.send('app-closed');
  }
}

// ─── IPC: quit the app ────────────────────────────────────────
ipcMain.on('quit-app', () => {
  app.quit();
});

// ─── IPC: launch exe ─────────────────────────────────────────
// Uses spawn with the exe's own directory as cwd so games that
// rely on relative paths (assets, saves, etc.) find their files.
ipcMain.on('open-app', (_event, appId) => {
  const exePath = APP_EXES[appId];
  if (!exePath) {
    console.warn(`No exe registered for app: "${appId}"`);
    return;
  }

  if (osWindow && !osWindow.isDestroyed()) {
    osWindow.hide();
  }

  const child = spawn(exePath, [], {
    cwd:      path.dirname(exePath),
    detached: false,
    stdio:    'ignore',
  });

  child.on('error', (err) => {
    console.error(`Failed to launch ${appId}:`, err);
    onChildClosed(); // show OS again even on error
  });

  child.on('close', onChildClosed);
});

// ─── IPC: open URL in a fullscreen Electron window ───────────
// F11  → toggle fullscreen
// Escape → close the window entirely and return to OS
ipcMain.on('open-url-fullscreen', (_event, url) => {
  if (osWindow && !osWindow.isDestroyed()) {
    osWindow.hide();
  }

  const urlWindow = new BrowserWindow({
    fullscreen: true,
    frame:      false,
    webPreferences: {
      nodeIntegration:  false,
      contextIsolation: true,
    },
  });

  urlWindow.loadURL(url);

  urlWindow.webContents.on('before-input-event', (_e, input) => {
    if (input.type !== 'keyDown') return;

    if (input.key === 'F11') {
      urlWindow.setFullScreen(!urlWindow.isFullScreen());
    }

    if (input.key === 'Escape') {
      urlWindow.close();
    }
  });

  urlWindow.on('closed', onChildClosed);
});

// ─── Electron lifecycle ───────────────────────────────────────
app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});