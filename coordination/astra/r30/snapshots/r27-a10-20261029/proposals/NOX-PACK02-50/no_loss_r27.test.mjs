import test from 'node:test';
import assert from 'node:assert/strict';
import {execute} from './ops.mjs';
const run=(id,input)=>execute(id,input).result;

test('CSV stringify retains fields first appearing in later rows',()=>{
  const input=[{name:'Ada'},{name:'Bob',score:9}];
  assert.equal(run('data.csv.stringify',JSON.stringify(input)),'name,score\nAda,\nBob,9');
});
test('CSV rejects non-object records instead of silently omitting them',()=>{
  for(const input of [[{},[]],[{},3],[{},null]])
    assert.throws(()=>run('data.csv.stringify',JSON.stringify(input)),/CSV_RECORD_OBJECT_REQUIRED/);
});
test('CSV stringify rejects ambiguous headers before emitting unusable text',()=>{
  for(const input of [[{Name:1,name:2}],[{'':1}]])
    assert.throws(()=>run('data.csv.stringify',JSON.stringify(input)),/INVALID_CSV_HEADER/);
});
test('CSV nested data uses lossless JSON cell encoding',()=>{
  const raw=run('data.csv.stringify',JSON.stringify([{x:{a:1},y:[2,3]}]));
  assert.deepEqual(run('data.csv.parse',raw),[{x:'{"a":1}',y:'[2,3]'}]);
});
test('CSV explicitly quoted empty records are preserved, blank lines skipped',()=>{
  assert.deepEqual(run('data.csv.parse','value\n""\n\n""'),[{value:''},{value:''}]);
});
test('CSV quoted CRLF and CR cell payload survives a round trip',()=>{
  for(const value of ['a\r\nb','a\rb']) {
    const raw=run('data.csv.stringify',JSON.stringify([{note:value}]));
    assert.deepEqual(run('data.csv.parse',raw),[{note:value}]);
  }
});
test('CSV accepts CR-only record boundaries outside quotes',()=>{
  assert.deepEqual(run('data.csv.parse','a,b\r1,2\r'),[{a:'1',b:'2'}]);
});
test('JSON flatten distinguishes empty path segments and literal escape',()=>{
  const out=run('data.json.flatten',JSON.stringify({'':{b:1},b:2,'\\e':3}));
  assert.deepEqual(out,{'\\e.b':1,b:2,'\\\\e':3});
});
