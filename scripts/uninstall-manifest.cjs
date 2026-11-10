const fs=require('node:fs');const path=require('node:path');
const root=path.join(__dirname,'../release/win-unpacked');let files=[],dirs=[];
function walk(dir){for(const e of fs.readdirSync(dir,{withFileTypes:true})){const p=path.join(dir,e.name);if(e.isDirectory()){dirs.push(path.relative(root,p));walk(p)}else files.push(path.relative(root,p));}}
walk(root);
const esc=s=>s.replaceAll('\\','/').replaceAll('$','$$').replaceAll('"','$\\"');
fs.writeFileSync(path.join(__dirname,'../resources/uninstall-files.nsh'),files.map(f=>`Delete "$INSTDIR/${esc(f)}"`).join('\n')+'\n'+dirs.reverse().map(d=>`RMDir "$INSTDIR/${esc(d)}"`).join('\n')+'\n');
