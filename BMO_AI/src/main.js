const { app, BrowserWindow, session } = require('electron');
const { spawn } = require('child_process');
const path = require('path');

if (require('electron-squirrel-startup')) {
  app.quit();
}

// ── Python process ────────────────────────────────────────────────────────

let pyProcess = null;

function startPythonBackend() {
  // Point straight at the env's Python — no activation needed
  const python = 'D:\\Users\\user\\anaconda3\\envs\\B.M.O\\python.exe';
  const script  = 'D:\\Users\\user\\Documents\\B.M.O\\main.py';
  const cwd     = 'D:\\Users\\user\\Documents\\B.M.O';

  console.log(`[BMO] Spawning: ${python} ${script}`);
  console.log(`[BMO] Working dir: ${cwd}`);

  pyProcess = spawn(python, [script], {
    cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
  });

  console.log(`[BMO] PID: ${pyProcess.pid}`);

  pyProcess.on('error', (err) => {
    console.error('[BMO] Failed to start process:', err.message);
  });

  pyProcess.stdout.on('data', (d) => console.log('[BMO]', d.toString().trim()));
  pyProcess.stderr.on('data', (d) => console.error('[BMO err]', d.toString().trim()));
  pyProcess.on('exit', (code, signal) => {
    console.log(`[BMO] exited — code: ${code}, signal: ${signal}`);
    pyProcess = null;
  });
}

function killPythonBackend() {
  if (!pyProcess) return;
  if (process.platform === 'win32') {
    spawn('taskkill', ['/pid', pyProcess.pid, '/f', '/t']);
  } else {
    pyProcess.kill();
  }
  pyProcess = null;
}

// ── Content-Security-Policy ───────────────────────────────────────────────

const SAFE_CSP = [
  "default-src  'self' 'unsafe-inline' data:",
  "script-src   'self' 'unsafe-inline' 'unsafe-eval'",
  "style-src    'self' 'unsafe-inline' https://fonts.googleapis.com",
  "font-src     'self' https://fonts.gstatic.com",
  "connect-src  'self' ws://0.0.0.0:3000 ws://localhost:3000 ws://localhost:7878",
  "img-src      'self' data: blob:",
].join('; ');

function applyCSP() {
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    const headers = { ...details.responseHeaders };

    for (const key of Object.keys(headers)) {
      if (key.toLowerCase() === 'content-security-policy') {
        delete headers[key];
      }
    }

    headers['Content-Security-Policy'] = [SAFE_CSP];
    callback({ responseHeaders: headers });
  });
}

// ── Window ────────────────────────────────────────────────────────────────

const createWindow = () => {
  const mainWindow = new BrowserWindow({
    width: 800,
    height: 600,
    webPreferences: {
      preload: MAIN_WINDOW_PRELOAD_WEBPACK_ENTRY,
    },
  });

  mainWindow.loadURL(MAIN_WINDOW_WEBPACK_ENTRY);
  mainWindow.webContents.openDevTools();
};

// ── App lifecycle ─────────────────────────────────────────────────────────

app.whenReady().then(() => {
  startPythonBackend();
  applyCSP();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('will-quit', killPythonBackend);

app.on('window-all-closed', () => {
  killPythonBackend();
  if (process.platform !== 'darwin') app.quit();
});