/* R47 regression for existing PACK02 CSV parser NIP02-21. Run: node proposals/NOX-PACK02-50/test_csv_bom_r47.mjs */
import assert from 'node:assert/strict';
import {execute, IDS} from './ops.mjs';
const bom = '\uFEFFname,age\r\nAda,37\r\n';
assert.deepEqual(execute('data.csv.parse', bom).result, [{name:'Ada', age:'37'}]);
assert.deepEqual(execute('data.csv.filter', bom, {field:'name', term:'ada'}).result, [{name:'Ada', age:'37'}]);
assert.deepEqual(execute('data.csv.parse', 'name,age\n"\uFEFFAda",37').result, [{name:'\uFEFFAda', age:'37'}]);
assert.equal(IDS.length, 50);
console.log('PACK02 CSV BOM 3/3 PASS; IDS 50/50');
