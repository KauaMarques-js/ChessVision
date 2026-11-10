const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const script = fs.readFileSync(__dirname + '/../extension/background.js', 'utf8');
let listener;
let requests=[];
const ctx = {
  chrome: {runtime: {onMessage: {addListener: fn => {listener=fn;}}}},
  fetch: (url, opts) => {
    requests.push({url,opts});
    return Promise.resolve({ok:true});
  }
};
vm.runInNewContext(script, ctx);
const sender = {url:'https://www.chess.com/play/computer'};
const data = {placement:'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR', moves:[]};
let invalid=false;
listener({type:'chessvision-position',payload:data},{url:'https://example.com/'},()=>{invalid=true;});
assert.strictEqual(invalid,false);
assert.strictEqual(requests.length,0);
let callbackResult;
const keepAlive = listener({type:'chessvision-position',payload:data},sender,reply=>callbackResult=reply);
assert.strictEqual(keepAlive,true);
assert.strictEqual(requests.length,1);
assert.strictEqual(requests[0].url,'http://127.0.0.1:8765/position');
assert.strictEqual(JSON.parse(requests[0].opts.body).placement,data.placement);
setImmediate(() => {
  assert(callbackResult.ok);
  console.log('Service worker bridge: 3 tests passed');
});
