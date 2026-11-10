const {app,BrowserWindow,ipcMain,shell,dialog,clipboard} = require('electron');
const fs = require('node:fs/promises');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {StringDecoder} = require('node:string_decoder');
const {parseStage,safeAction} = require('./protocol.cjs');
let window, child, busy=false, history=[], lastOperation=null;
const root = ()=>path.join(process.env.LOCALAPPDATA || app.getPath('userData'),'ChessVisionLab');
const helper = ()=>app.isPackaged ? path.join(process.resourcesPath,'chessvision-helper.exe') : path.join(__dirname,'../resources/chessvision-helper.exe');
const exists = async p=>!!await fs.stat(p).catch(()=>null);
function emit(event){history.push(event); if(history.length>1500)history.shift(); if(window&&!window.isDestroyed())window.webContents.send('manager:event',event);}
async function status(){
 const base=root(); let engine=false;
 async function scan(dir,depth=0){if(depth>5)return; for(const e of await fs.readdir(dir,{withFileTypes:true}).catch(()=>[])){if(e.isDirectory())await scan(path.join(dir,e.name),depth+1); else if(/^stockfish.*\.exe$/i.test(e.name))engine=true;}}
 await scan(path.join(base,'engine'));
 let online=false;
 try{const res=await fetch('http://127.0.0.1:8765/health',{signal:AbortSignal.timeout(900)});const body=await res.text();online=res.ok&&body.includes('ChessVision Lab');}catch{}
 return {root:base,platform:process.platform,busy,online,python:await exists(path.join(base,'.venv','Scripts','python.exe')),engine,extension:await exists(path.join(base,'extension','manifest.json')),lastOperation,history};
}
async function run(action){
 const args=safeAction(action);
 if(process.platform!=='win32')throw new Error('Instalação e execução disponíveis no Windows x64.');
 if(busy)throw new Error('Aguarde a operação em andamento.');
 busy=true; lastOperation={action,state:'running'}; emit({type:'start',action,time:Date.now()});
 try{
 await fs.access(helper());
 child=spawn(helper(),args,{windowsHide:true,stdio:['ignore','pipe','pipe']});
 let pending='';const decoder=new StringDecoder('utf8');
 const line=value=>{emit({type:'log',text:value,time:Date.now()});const stage=parseStage(value);if(stage)emit({type:'stage',action,...stage});};
 const chunk=data=>{pending+=decoder.write(data);const lines=pending.split(/\r?\n/);pending=lines.pop();for(const value of lines)line(value);};
 child.stdout.on('data',chunk);child.stderr.on('data',chunk);
 await new Promise((resolve,reject)=>{child.once('error',reject); child.once('close',code=>code===0?resolve():reject(new Error(`Operação encerrada com código ${code}. Consulte o registro.`)));});
 pending+=decoder.end();if(pending)line(pending);
 lastOperation={action,state:'success'};emit({type:'done',action,time:Date.now()});
 }catch(error){lastOperation={action,state:'error',message:error.message};emit({type:'failure',action,text:error.message,time:Date.now()});}
 finally{busy=false;child=null;}
 return status();
}
if(!app.requestSingleInstanceLock())app.quit();
else {
 app.on('second-instance',()=>{if(window){if(window.isMinimized())window.restore();window.show();window.focus();}});
 app.whenReady().then(()=>{
 window=new BrowserWindow({width:1250,height:850,minWidth:1000,minHeight:720,backgroundColor:'#111723',autoHideMenuBar:true,title:'ChessVision Manager',icon:app.isPackaged?path.join(process.resourcesPath,'icon.ico'):path.join(__dirname,'../resources/icon.ico'),webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true}});
 window.webContents.setWindowOpenHandler(()=>({action:'deny'}));
 window.webContents.on('will-navigate',e=>e.preventDefault());
 window.loadFile(path.join(__dirname,'../dist/index.html'));
 window.on('close',e=>{if(busy){e.preventDefault();dialog.showMessageBox(window,{type:'info',message:'Uma operação está em andamento.',detail:'Aguarde a conclusão antes de fechar a central.',buttons:['Entendi']});}});
 ipcMain.handle('manager:status',()=>status());
 ipcMain.handle('manager:run',(_,action)=>run(action));
 ipcMain.handle('manager:folder',async(_,kind)=>{const locations={installation:root(),extension:path.join(root(),'extension'),logs:root()};if(!Object.hasOwn(locations,kind))throw new Error('Pasta inválida.');if(!await exists(locations[kind]))throw new Error('Instale os componentes primeiro.');const error=await shell.openPath(locations[kind]);if(error)throw new Error(error);});
 ipcMain.handle('manager:copy-extension',()=>clipboard.writeText(path.join(root(),'extension')));
 ipcMain.handle('manager:export',async()=>{const result=await dialog.showSaveDialog(window,{defaultPath:'ChessVision-registro.txt',filters:[{name:'Texto',extensions:['txt']}]});if(!result.canceled){await fs.writeFile(result.filePath,history.filter(e=>e.type==='log'||e.type==='failure').map(e=>e.text).join('\r\n'),'utf8');return true;}return false;});
 });
 app.on('window-all-closed',()=>app.quit());
}
