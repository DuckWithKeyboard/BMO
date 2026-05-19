const { app, BrowserWindow, ipcMain, protocol, net, session, dialog } = require('electron');
const path = require('path');
const fs   = require('fs');

/* 🔥 CRITICAL: Register custom protocol BEFORE app ready */
protocol.registerSchemesAsPrivileged([
  {
    scheme: 'media',
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      stream: true,
    },
  },
]);

if (require('electron-squirrel-startup')) {
  app.quit();
}

let mainWindow;

const createWindow = () => {
  mainWindow = new BrowserWindow({
    width: 800,
    height: 600,
    frame: false,
    webPreferences: {
      preload: MAIN_WINDOW_PRELOAD_WEBPACK_ENTRY,
    },
  });

  mainWindow.setFullScreen(true);
  mainWindow.loadURL(MAIN_WINDOW_WEBPACK_ENTRY);

  mainWindow.on('maximize', () => {
    mainWindow.webContents.send('window-maximized', true);
  });

  mainWindow.on('unmaximize', () => {
    mainWindow.webContents.send('window-maximized', false);
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow.webContents.send('window-maximized', mainWindow.isMaximized());
  });
};

/* ─── Window Controls ────────────────────────────────────── */
ipcMain.on('win-minimize', () => {
  if (mainWindow) mainWindow.minimize();
});

ipcMain.on('win-maximize', () => {
  if (!mainWindow) return;
  mainWindow.isMaximized()
    ? mainWindow.unmaximize()
    : mainWindow.maximize();
});

ipcMain.on('win-close', () => {
  if (mainWindow) mainWindow.close();
});

/* ─── Load audio files ───────────────────────────────────── */
ipcMain.handle('load-folder', (_, folderPath) => {
  const exts = ['.mp3', '.flac', '.wav', '.ogg', '.m4a', '.aac'];
  return fs.readdirSync(folderPath)
    .filter(f => exts.includes(path.extname(f).toLowerCase()))
    .map(f => path.join(folderPath, f));
});

/* ─── Persisted config (userData/config.json) ────────────── */
function getConfigPath() {
  return path.join(app.getPath('userData'), 'config.json');
}

function readConfig() {
  try { return JSON.parse(fs.readFileSync(getConfigPath(), 'utf8')); }
  catch { return {}; }
}

function writeConfig(data) {
  fs.writeFileSync(getConfigPath(), JSON.stringify(data, null, 2), 'utf8');
}

ipcMain.handle('get-music-folder', () => {
  return readConfig().musicFolder || null;
});

ipcMain.handle('set-music-folder', (_, folderPath) => {
  const config = readConfig();
  config.musicFolder = folderPath;
  writeConfig(config);
  return folderPath;
});

ipcMain.handle('pick-folder', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title:      'Select your music folder',
    properties: ['openDirectory'],
  });
  if (result.canceled || !result.filePaths.length) return null;
  return result.filePaths[0];
});

/* ─── Metadata (music-metadata) ──────────────────────────── */
ipcMain.handle('get-metadata', async (_, filePath) => {
  try {
    const mm = await import('music-metadata');
    const meta = await mm.parseFile(filePath, { skipCovers: false });

    const picture = mm.selectCover
      ? mm.selectCover(meta.common.picture)
      : (meta.common.picture && meta.common.picture[0]) || null;

    return {
      title:  meta.common.title  || null,
      artist: meta.common.artist || null,
      album:  meta.common.album  || null,
      cover: picture ? {
        format: picture.format,
        data:   Buffer.from(picture.data).toString('base64')
      } : null,
    };
  } catch (err) {
    console.error('get-metadata failed for', filePath, err.message);
    return null;
  }
});

/* ─── App bootstrap ──────────────────────────────────────── */
app.whenReady().then(() => {

  /* 🔥 CRITICAL: FORCE CSP (fixes your error) */
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        "Content-Security-Policy": [
          "default-src 'self' data:; " +
          "img-src 'self' data: blob:; " +
          "media-src 'self' media: blob: data:; " +
          "script-src 'self' 'unsafe-inline' 'unsafe-eval'; " +
          "style-src 'self' 'unsafe-inline' blob:;"
        ]
      }
    });
  });

  /* ─── Serve app assets ─────────────────────────────────── */
  protocol.handle('app', (request) => {
    const url      = request.url.replace('app://', '');
    const filePath = path.join('D:/BMO/src', url);
    return net.fetch('file:///' + filePath.replace(/\\/g, '/'));
  });

  /* ─── MEDIA PROTOCOL (audio files) ─────────────────────── */
  /* ─── MEDIA PROTOCOL (audio files) ─────────────────────── */
protocol.handle('media', async (request) => {
  const encoded  = request.url.replace('media://host/', '');
  const filePath = decodeURIComponent(encoded);

  const mimeTypes = {
    '.mp3': 'audio/mpeg', '.flac': 'audio/flac', '.wav': 'audio/wav',
    '.ogg': 'audio/ogg',  '.m4a': 'audio/mp4',   '.aac': 'audio/aac',
  };
  const ext         = path.extname(filePath).toLowerCase();
  const contentType = mimeTypes[ext] || 'audio/mpeg';

  let stat;
  try { stat = fs.statSync(filePath); }
  catch { return new Response('Not found', { status: 404 }); }

  const fileSize    = stat.size;
  const rangeHeader = request.headers.get('Range');

  if (rangeHeader) {
    // Parse "bytes=start-end"
    const [, startStr, endStr] = rangeHeader.match(/bytes=(\d+)-(\d*)/) || [];
    const start     = parseInt(startStr, 10);
    const end       = endStr ? parseInt(endStr, 10) : fileSize - 1;
    const chunkSize = end - start + 1;

    // Read only the requested byte slice
    const buf = Buffer.alloc(chunkSize);
    const fd  = fs.openSync(filePath, 'r');
    fs.readSync(fd, buf, 0, chunkSize, start);
    fs.closeSync(fd);

    return new Response(buf, {
      status: 206,
      headers: {
        'Content-Type':  contentType,
        'Content-Range': `bytes ${start}-${end}/${fileSize}`,
        'Accept-Ranges': 'bytes',
        'Content-Length': String(chunkSize),
      },
    });
  }

  // Non-range: serve the whole file but advertise seekability
  const buf = fs.readFileSync(filePath);
  return new Response(buf, {
    status: 200,
    headers: {
      'Content-Type':   contentType,
      'Accept-Ranges':  'bytes',
      'Content-Length': String(fileSize),
    },
  });
});

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