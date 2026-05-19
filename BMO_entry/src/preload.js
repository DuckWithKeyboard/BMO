// See the Electron documentation for details on how to use preload scripts:
// https://www.electronjs.org/docs/latest/tutorial/process-model#preload-scripts
const { contextBridge, ipcRenderer } = require('electron');

// Expose a safe bridge to the renderer.
// window.bmoOS.openApp('music')      → main.js → launches the exe via spawn.
// window.bmoOS.openUrl(url)          → main.js → opens URL in a fullscreen window.
//                                       F11 = toggle fullscreen, Escape = close.
// window.bmoOS.onAppClosed(callback) → fires when the launched app/window exits.
contextBridge.exposeInMainWorld('bmoOS', {
  openApp:     (appId) => ipcRenderer.send('open-app', appId),
  openUrl:     (url)   => ipcRenderer.send('open-url-fullscreen', url),
  onAppClosed: (cb)    => ipcRenderer.on('app-closed', cb),
});