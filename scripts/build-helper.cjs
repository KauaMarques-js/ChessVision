const {spawnSync}=require('node:child_process');
const path=require('node:path');
const result=spawnSync(process.env.CHESSVISION_GO||'go',['build','-buildvcs=false','-trimpath','-ldflags=-s -w','-o',path.join(__dirname,'../resources/chessvision-helper.exe'),'.'],{cwd:path.join(__dirname,'../backend'),env:{...process.env,GOOS:'windows',GOARCH:'amd64',CGO_ENABLED:'0'},stdio:'inherit'});
if(result.error){console.error(result.error.message);process.exit(1)}process.exit(result.status??1);
