// See the Electron documentation for details on how to use preload scripts:
// https://www.electronjs.org/docs/latest/tutorial/process-model#preload-scripts
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('bmo', {
  quit:     () => ipcRenderer.send('quit-app'),
  closeApp: () => ipcRenderer.send('quit-app'),
});