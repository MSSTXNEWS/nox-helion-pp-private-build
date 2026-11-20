'use strict';

const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const path = require('node:path');
const vm = require('node:vm');

if (process.argv.length !== 3) {
  throw new Error('Usage: node test_owner_resonance_reconnect_continuity.cjs <exact released owner_resonance_gateway.py>');
}

const extractCandidateScript = `
import ast
import hashlib
import runpy
import sys
from pathlib import Path

attach = runpy.run_path(sys.argv[1])['attach_reconnect_continuity']
released = Path(sys.argv[2]).read_bytes()
try:
    attach(released + b'\\n')
except ValueError as error:
    assert str(error) == 'HOLD_RESONANCE_RECONNECT_PREIMAGE'
else:
    raise AssertionError('altered release was accepted')
candidate = attach(released)
assert hashlib.sha256(candidate).hexdigest() == '4868b2bbf81a4344a84762228cce56f3e65b2fc7d1c7d37a87ea59ba8b06c58a'
page = next(
    node.value.func.value.value
    for node in ast.parse(candidate).body
    if isinstance(node, ast.Assign)
    and any(isinstance(target, ast.Name) and target.id == 'PAGE' for target in node.targets)
)
print(page.split('<script>', 1)[1].split('</script>', 1)[0])
`;

const patchModule = path.join(__dirname, 'owner_resonance_reconnect_continuity.py');
const script = execFileSync('python3', ['-B', '-c', extractCandidateScript, patchModule, process.argv[2]], {
  encoding: 'utf8',
});
// Skip startup authentication; exercise the released browser handlers against a synthetic NDJSON transport.
const startup = script.lastIndexOf("call('/chat/session').then(open)");
assert.ok(startup > 0);
const binding = {dialog_id:'a'.repeat(32), request_id:'b'.repeat(32)};
const requests = [];
let transcript = [];
const newElement = () => ({
  textContent:'', value:'', hidden:true,
  append(...nodes) { for (const node of nodes) if (typeof node === 'string') this.textContent += node; },
});
const elements = new Map();
const context = {
  assert, binding, TextDecoder, URLSearchParams,
  setTranscript(frames) { transcript = frames; },
  document:{
    getElementById(id) {
      if (!elements.has(id)) elements.set(id,newElement());
      return elements.get(id);
    },
    createTextNode:text=>text,
  },
  setTimeout: resolve => resolve(),
  async fetch(path, options) {
    requests.push([path,options.method]);
    const bytes = new TextEncoder().encode(transcript.map((value,i)=>JSON.stringify({...binding,seq:i+1,...value})+'\n').join(''));
    let offset = 0;
    return {ok:true,headers:{get:()=> 'application/x-ndjson'},body:{getReader(){return {
      async read(){return offset<bytes.length ? {done:false,value:bytes.slice(offset,++offset)} : {done:true}},
      async cancel(){},
      releaseLock(){},
    };}}};
  },
};
const test = `
(async () => {
  function start() {
    const turn = {binding,cursor:0,stopping:false,answer:by('answer')};
    turn.answer.textContent = '';
    pending = turn;
    frame(turn,{...binding,seq:1,type:'phase',phase:'accepted',scoped_stop:false});
    frame(turn,{...binding,seq:2,type:'delta',text:'Я🧠'});
    return turn;
  }
  let turn = start();
  turn.answer.textContent = 'locally damaged display';
  setTranscript([
    {type:'phase',phase:'accepted',scoped_stop:false},
    {type:'delta',text:'Я🧠'},
    {type:'delta',text:' вижу el sueño'},
  ]);
  await assert.rejects(readTurn(turn,true),/disconnect/);
  assert.equal(turn.answer.textContent,'Я🧠 вижу el sueño');
  assert.equal(turn.cursor,3);

  turn = start();
  setTranscript([
    {type:'phase',phase:'accepted',scoped_stop:false},
    {type:'delta',text:'Другой ответ'},
    {type:'delta',text:' недопустимое продолжение'},
  ]);
  await follow(turn);
  assert.equal(turn.answer.textContent,'Я🧠','divergent replay must preserve visible answer');
  assert.equal(turn.cursor,2);
  assert.equal(pending,turn);
  assert.equal(retry.hidden,false);
  assert.match(banner.textContent,/другой префикс ответа/);
})()`;
vm.runInNewContext(script.slice(0,startup)+test,context).then(()=>{
  assert.equal(requests.length,2);
  assert.ok(requests.every(([path,method])=>path.endsWith('&after=0') && method===undefined));
  console.log('PASS: split UTF-8, matching and divergent full replay, unchanged cursor, same GET, no POST');
}).catch(err=>{console.error(err);process.exitCode=1;});
