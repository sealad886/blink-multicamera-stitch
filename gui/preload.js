const { contextBridge } = require('electron');
// Placeholder for exposing APIs to renderer
contextBridge.exposeInMainWorld('blink', {
  // TODO: wire up backend interactions
});
