'use strict';
const fs=require('node:fs');
const r70=require(process.env.B3_R70);
const c=JSON.parse(fs.readFileSync(0,'utf8')), n=c.writer.sequence;
const h=n=>n.toString(16).padStart(64,'0');
const wire={wire:'named-delta-stable-server-id-v1',route:'logical-route',served_sha256:h(21),server_sha256:h(22)};
const physical={route:'/fixture/model',model_id:'fixture',dialog_id:'physical-dialog',weights_manifest_sha256:h(11),tokenizer_manifest_sha256:h(12),bridge_sha256:'c44b5aa2ef3d45246276a24bbcfad30bf76533fc2e08089eb91b442002643dc7',original_checkpoint_sha256:h(13),owner_admission_receipt_sha256:h(14),process:{boot_id:'boot',pid:42,start_ticks:123},turn_request_ids:['req2','req3'],window_start_ms:100,window_end_ms:200};
const mapping={...physical,schema:'NOX_B3_ROUTE_BINDING_V1',wire:wire.wire,symbolic_route:wire.route,served_sha256:wire.served_sha256,server_sha256:wire.server_sha256,conversation_id:'logical-conversation',exchange_bindings:[{turn:2,request_id:'req2',exchange_id:'ex2'},{turn:3,request_id:'req3',exchange_id:'ex3'}]};
const scope={conversation_id:'logical-conversation',exchange_id:'ex'+n};
const terminal={...scope,physical_dialog_id:physical.dialog_id,request_id:physical.turn_request_ids[n-2],attempt_id:'attempt-'+n,sequence:n,status:'STREAM_ENDED_READBACK_REQUIRED'};
// Independent synthetic fixture pins and IDs are derived from the fixture contract,
// never from the candidate terminal projection in production.
const link={schema:'NOX_B3_S03_TERMINAL_LINK_V1',...terminal,s03_dialog_id:'a'.repeat(32),s03_session_id:'fixture-owner',s03_event_id:'event-'+n,s03_turn_id:'turn-'+n,user_message_id:'message-'+(2*n-2),assistant_message_id:'message-'+(2*n-1),writer_sha256:c.writer_sha256,readback_sha256:c.readback_sha256};
const args={wire,physical,mapping,scope,expectedTurn:n,terminal,link,canonical:c};
const z=r70.check(args);
if(z.native_accepted!==false||z.authentication_verified!==false||z.next_post_allowed!==false)throw Error('authority');
const bad=r70.check({...args,link:{...link,s03_session_id:'foreign'}});
const wrong=r70.check({...args,link:{...link,writer_sha256:h(99)}});
const replay=r70.check({...args,expectedTurn:1});
console.log(JSON.stringify([z.consistent,bad.consistent,wrong.consistent,replay.consistent]));
