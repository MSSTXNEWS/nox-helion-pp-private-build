'use strict';
const fs=require('node:fs');
const r70=require('./b3_r70_s03_terminal_identity.cjs');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
process.stdout.write(JSON.stringify(r70.check(input)));
