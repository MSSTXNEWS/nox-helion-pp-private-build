'use strict';
const r71=require(process.env.B3_R71);
const z=r71.check(JSON.parse(require('node:fs').readFileSync(0,'utf8')));
if(z.native_accepted!==false||z.authentication_verified!==false||z.next_post_allowed!==false)throw Error('authority');
console.log(JSON.stringify(z));
