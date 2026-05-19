// See the Electron documentation for details on how to use preload scripts:
// https://www.electronjs.org/docs/latest/tutorial/process-model#preload-scripts

// See the Electron documentation for details on how to use preload scripts:
// https://www.electronjs.org/docs/latest/tutorial/process-model#preload-scripts
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('winAPI', {
  minimize: () => ipcRenderer.send('win-minimize'),
  maximize: () => ipcRenderer.send('win-maximize'),
  close:    () => ipcRenderer.send('win-close'),

  onMaximizeChange: (callback) =>
    ipcRenderer.on('window-maximized', (_, val) => callback(val)),

  loadFolder: (folderPath) => ipcRenderer.invoke('load-folder', folderPath),

  // Returns { title, artist, album, cover: { format, data } } | null
  getMetadata: (filePath) => ipcRenderer.invoke('get-metadata', filePath),

  // Persisted music-folder config
  getMusicFolder: ()           => ipcRenderer.invoke('get-music-folder'),
  setMusicFolder: (folderPath) => ipcRenderer.invoke('set-music-folder', folderPath),
  pickFolder:     ()           => ipcRenderer.invoke('pick-folder'),
});