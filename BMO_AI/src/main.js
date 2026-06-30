const { app, BrowserWindow, session, ipcMain, protocol } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs   = require('fs');

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
  "img-src      'self' data: blob: bmo:",
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
    fullscreen: true,
    frame: false,
    webPreferences: {
      preload: MAIN_WINDOW_PRELOAD_WEBPACK_ENTRY,
    },
  });

  mainWindow.loadURL(MAIN_WINDOW_WEBPACK_ENTRY);
};

// ── App lifecycle ─────────────────────────────────────────────────────────

app.whenReady().then(() => {
  startPythonBackend();
  applyCSP();

  // ── bmo:// — serves local files captured by the Python backend ───────────
  // Usage in renderer: 'bmo:///' + filePath.replace(/\\/g, '/')
  //   Triple-slash keeps host empty so the full Windows/POSIX path is in pathname.
  // Handles both Windows (D:/…) and POSIX (/tmp/…) paths.
  protocol.registerBufferProtocol('bmo', (request, callback) => {
    // Use URL parsing so "bmo:///C:/foo/bar.png" → pathname "/C:/foo/bar.png"
    // then strip the leading slash to get the real Windows/POSIX path.
    // Slicing the raw string dropped the drive-letter colon because the URL
    // engine parsed "bmo://C:/path" as host="C", path="/path".
    const rawPath = decodeURIComponent(new URL(request.url).pathname.replace(/^\//, ''));
    try {
      const data     = fs.readFileSync(rawPath);
      const ext      = path.extname(rawPath).toLowerCase();
      const mimeType = ext === '.png' ? 'image/png' : 'image/jpeg';
      callback({ mimeType, data });
    } catch (err) {
      console.error('[BMO Protocol] Cannot read capture file:', rawPath, err.message);
      callback({ error: -6 }); // NET::ERR_FILE_NOT_FOUND
    }
  });

  createWindow();

  // Renderer sends this when SHUTTING_DOWN is received over WebSocket.
  ipcMain.on('quit-app', () => {
    killPythonBackend();
    app.quit();
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('will-quit', killPythonBackend);

app.on('window-all-closed', () => {
  killPythonBackend();
  if (process.platform !== 'darwin') app.quit();
});