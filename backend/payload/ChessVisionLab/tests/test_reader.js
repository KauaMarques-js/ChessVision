/* Offline unit tests for board-reader DOM adapter, no dependencies. */
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const script = fs.readFileSync(__dirname+'/../extension/board_reader.js','utf8');
let pieces=[], flipped=false, currentTime=1000, dataFen=null;
const messages=[];
function add(piece,file,rank) {pieces.push({classList:['piece',piece,`square-${file}${rank}`]});}
function starting() {
  pieces=[];
  for(let f=1;f<=8;f++) {add('wp',f,2); add('bp',f,7);}
  ['r','n','b','q','k','b','n','r'].forEach((p,i)=>{add('w'+p,i+1,1);add('b'+p,i+1,8)});
}
starting();
const expectedStart='rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR';
const board={classList:{contains:x=>flipped&&x==='flipped'},
  querySelectorAll:()=>pieces,getAttribute:x=>x==='data-fen'?dataFen:null};
let timeoutCb=()=>{}, intervalCb=()=>{};
const doc={documentElement:{},querySelectorAll:x=>x==='wc-chess-board'?[board]:[],querySelector:()=>null};
const ctx={document:doc,Date:{now:()=>currentTime},location:{pathname:'/play/computer'},
  MutationObserver:class {observe(){}},
  setTimeout:fn=>{timeoutCb=fn;return 1},clearTimeout:()=>{},setInterval:fn=>{intervalCb=fn},
  chrome:{runtime:{sendMessage:(msg,cb)=>{messages.push(msg);cb({ok:true});},lastError:null}}};
vm.runInNewContext(script,ctx);
let count=0;
function test(name,fn) {fn();count++;}

test('Initial standard chessboard',()=>{
  timeoutCb();
  assert.strictEqual(messages.length,1);
  assert.strictEqual(messages[0].payload.placement,expectedStart);
  assert.strictEqual(messages[0].payload.turn,null);
});
test('Unchanged board does not flood local bridge',()=>{
  currentTime+=1000; intervalCb();
  assert.strictEqual(messages.length,1);
});
test('Heartbeat keeps connection alive',()=>{
  currentTime+=5000;intervalCb();
  assert.strictEqual(messages.length,2);
});
test('White pawn moved from e2 to e4',()=>{
  pieces=pieces.filter(p=>!p.classList.includes('square-52'));
  add('wp',5,4); currentTime+=1000; timeoutCb();
  assert.strictEqual(messages.length,3);
  assert.strictEqual(messages.at(-1).payload.placement,'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR');
});
test('Flipped board does not flip chess coordinates',()=>{
  flipped=true;currentTime+=1000;timeoutCb();
  assert.strictEqual(messages.at(-1).payload.orientation,'black');
  assert.strictEqual(messages.at(-1).payload.placement,'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR');
});
test('FEN attribute provides reliable side-to-move',()=>{
  dataFen='rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1';
  currentTime+=1000;timeoutCb();
  assert.strictEqual(messages.at(-1).payload.turn,'b');
});
test('No publish during duplicate animation',()=>{
  const before=messages.length;
  add('wp',5,4);currentTime+=1000;timeoutCb();
  assert.strictEqual(messages.length,before);
  pieces.pop();
});
test('No publish if king missing',()=>{
  const before=messages.length;
  const kingIndex=pieces.findIndex(p=>p.classList.includes('wk'));
  const [king] = pieces.splice(kingIndex,1);
  currentTime+=1000;timeoutCb();
  assert.strictEqual(messages.length,before);
  pieces.push(king);
});
console.log('DOM board reader: '+count+' tests passed');
