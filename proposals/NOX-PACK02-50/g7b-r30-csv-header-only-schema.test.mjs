import test from 'node:test';
import assert from 'node:assert/strict';
import { execute, IDS } from './ops.mjs';

const op=(name,body,options={})=>execute(name,body,options).result;
test('G7-B R30: CSV header-only validation',()=>{
  const header='name,amount\n';
  assert.equal(IDS.length,50);
  assert.deepEqual(op('data.csv.parse',header),[]);
  assert.deepEqual(op('data.csv.stats',header),{rows:0,columns:['name','amount'],emptyCells:0});
  assert.deepEqual(op('data.csv.select',header,{fields:'name'}),[]);
  assert.deepEqual(op('data.csv.filter',header,{field:'name',term:'x'}),[]);
  assert.deepEqual(op('data.csv.sort',header,{field:'amount'}),[]);
  for(const id of ['data.csv.select','data.csv.filter','data.csv.sort']){
    const options=id==='data.csv.select'?{fields:'missing'}:{field:'missing',term:'x'};
    assert.throws(()=>op(id,header,options),/CSV_UNKNOWN_FIELD/);
  }
  assert.deepEqual(op('data.csv.stats','').columns,[]);
  assert.deepEqual(op('data.csv.parse','name,amount\nAda,2'),[{name:'Ada',amount:'2'}]);
});
