const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('chessvision',Object.freeze({
 status:()=>ipcRenderer.invoke('manager:status'),run:action=>ipcRenderer.invoke('manager:run',action),folder:kind=>ipcRenderer.invoke('manager:folder',kind),copyExtension:()=>ipcRenderer.invoke('manager:copy-extension'),exportLog:()=>ipcRenderer.invoke('manager:export'),
 onEvent:callback=>{const listener=(_,event)=>callback(event);ipcRenderer.on('manager:event',listener);return()=>ipcRenderer.removeListener('manager:event',listener);}
}));
