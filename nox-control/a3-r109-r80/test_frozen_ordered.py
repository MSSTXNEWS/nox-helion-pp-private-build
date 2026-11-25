"""R108 fixture setup reused at new R80/R109 joint callsite; no old regression rerun."""
import copy
import json
from finalized_observation import COMMON
from joint_packet import prepare_joint_packet
import os
import subprocess
import unittest
from test_joint_rues import JointBilingual
from review_release import prepare_joint_review
from terminal_canonical import terminal_canonical
from distinct_dialog import review_distinct, pair, digest

def h(n):
    return format(n,"064x")

class FrozenOrderedCallsite(unittest.TestCase):
    def test_frozen_ordered_callsite(self):
        fixture=JointBilingual()
        self.addCleanup(fixture.doCleanups)
        args,_=fixture.build(("30 евро на покупку. 🐾","Quedan exactamente 90 euros. 🐾"))
        packet=prepare_joint_review(**args)
        complete=dict(args, **fixture.submissions(packet,(("correct","incorrect"),("correct","uncertain"))))
        scope=dict(conversation_id="logical-conversation", physical_dialog_id="physical-dialog",
            s03_dialog_id=args["dialog_id"], session_id=args["session_id"],
            served_sha256=h(21),server_sha256=h(22),owner_admission_receipt_sha256=h(14))
        wire=dict(wire="named-delta-stable-server-id-v1",route="logical-route",
                  served_sha256=h(21),server_sha256=h(22))
        physical=dict(route="/fixture/model",model_id="fixture",dialog_id="physical-dialog",
            weights_manifest_sha256=h(11),tokenizer_manifest_sha256=h(12),
            bridge_sha256="c44b5aa2ef3d45246276a24bbcfad30bf76533fc2e08089eb91b442002643dc7",
            original_checkpoint_sha256=h(13),owner_admission_receipt_sha256=h(14),
            process=dict(boot_id="boot",pid=42,start_ticks=123),
            turn_request_ids=["req2","req3"],window_start_ms=100,window_end_ms=200)
        mapping=dict(physical,schema="NOX_B3_ROUTE_BINDING_V1",wire=wire["wire"],
            symbolic_route=wire["route"],served_sha256=h(21),server_sha256=h(22),
            conversation_id=scope["conversation_id"],exchange_bindings=[
                dict(turn=n,request_id=f"req{n}",exchange_id=f"ex{n}") for n in (2,3)])
        bindings, terminals, wires=[],[],[]
        for n in (2,3):
            c=terminal_canonical(dialog_id=args["dialog_id"],session_id=args["session_id"],
                expected_turn=n,artifacts=args["descriptor_sets"][:n])
            user,assistant=c["rows"][-2:]
            terminal=dict(conversation_id=scope["conversation_id"],exchange_id=f"ex{n}",
                physical_dialog_id=physical["dialog_id"],request_id=f"req{n}",
                attempt_id=f"attempt-{n}",sequence=n,status="STREAM_ENDED_READBACK_REQUIRED")
            link=dict(terminal,schema="NOX_B3_S03_TERMINAL_LINK_V1",
                s03_dialog_id=args["dialog_id"],s03_session_id=args["session_id"],
                s03_turn_id=c["writer"]["turn_id"],s03_event_id=c["writer"]["event_id"],
                user_message_id=user["message_id"],assistant_message_id=assistant["message_id"],
                writer_sha256=c["writer_sha256"],readback_sha256=c["readback_sha256"])
            w=pair(dict(wire=wire,physical=physical,mapping=mapping,
                scope=dict(conversation_id=scope["conversation_id"],exchange_id=f"ex{n}"),
                expectedTurn=n,terminal=terminal,link=link))
            wires.append(w)
            b=dict(turn=n,exchange_id=f"ex{n}",request_id=f"req{n}",attempt_id=f"attempt-{n}",
                user_message_id=user["message_id"],assistant_message_id=assistant["message_id"],
                event_id=link["s03_event_id"],turn_id=link["s03_turn_id"],
                writer_sha256=c["writer_sha256"],readback_sha256=c["readback_sha256"],transport_sha256=w[1])
            bindings.append(b)
            terminals.append(pair(dict(scope,**b,schema="nox.transport.terminal-readback.v2",
                state="TERMINAL_SAVED",eof=True,prompt_sha256=digest(user["content"].encode()),
                answer_sha256=digest(assistant["content"].encode()))))
        owner=pair(dict(scope,schema="nox.owner.s03-transport-join.v2",bindings=bindings))
        p=dict(owner_pair=owner,terminal_pairs=tuple(terminals),transport_pairs=tuple(wires),expected_scope=scope)
        payloads=[json.dumps(dict(physical,turn=2+i//2,phase=("before","after")[i%2],
            request_id=physical["turn_request_ids"][i//2],observed_ms=110+10*i,
            readback_id="receipt-"+str(i),installed_bridge_sha256=physical["bridge_sha256"],
            served_bridge_sha256=physical["bridge_sha256"]),separators=(",",":"))
            for i in range(4)]
        receipts=pair(dict(schema="NOX_B3_R66_READBACK_BYTES_V1",expected=physical,
            receipt_payloads=payloads,receipt_index=[dict(readback_id="receipt-"+str(i),
            sha256=digest(s.encode())) for i,s in enumerate(payloads)]))
        browser=h(77)
        fields=("turn","exchange_id","request_id","attempt_id","event_id","turn_id",
                "user_message_id","assistant_message_id")
        docs=[]
        for i,t in enumerate(terminals):
            saved=json.loads(t[0])
            docs.append(dict(scope, **{k:saved[k] for k in fields},
                schema="nox.browser.projection-readback.v1", observation_id=f"obs-{i}",
                browser_sha256=browser, terminal_receipt_sha256=t[1],
                visible_text_sha256=saved["answer_sha256"],visible_row_count=1,
                state="TERMINAL_VISIBLE",ack_state="NOT_SENT"))
        pairs=tuple(pair(d) for d in docs)
        reservations, dispositions = [], []
        for i, obs in enumerate(docs):
            common = {k: obs[k] for k in COMMON - {"observation_sha256"}}
            common["observation_sha256"] = pairs[i][1]
            r = pair(dict(common, schema="nox.browser.ack-reservation-readback.v1",
                reservation_id=f"reserve-{i}", state="RESERVED_NOT_SENT"))
            d = pair(dict(common, schema="nox.browser.projection-disposition.v1",
                disposition_id=f"final-{i}", reservation_id=f"reserve-{i}",
                reservation_sha256=r[1], state="FINALIZED", dom_recheck="MATCHED",
                stop_recheck="CLEAR"))
            reservations.append(r)
            dispositions.append(d)
        reservations, dispositions = tuple(reservations), tuple(dispositions)
        timing=[]
        for i, obs in enumerate(docs):
            n=i+2
            sample=dict(conversation_id=obs["conversation_id"], exchange_id=obs["exchange_id"],
                clock_id="fixture-clock", terminal_event_id=f"fixture-terminal-{n}",
                served_sha256=obs["served_sha256"], begin_ms=100, first_visible_ms=110,
                eof_ms=150,outcome="STREAM_ENDED_READBACK_REQUIRED")
            proof=dict(obs, **{k:v for k,v in sample.items() if k not in obs},
                verified=True,dom_receipt_id=f"fixture-dom-{n}",
                canonical_receipt_id=f"fixture-canonical-{n}",
                dom_sha256=obs["visible_text_sha256"],answer_sha256=obs["visible_text_sha256"],
                dom_commit_ms=170,observation_sha256=pairs[i][1],
                reservation_receipt_id=f"reserve-{i}",reservation_sha256=reservations[i][1],
                disposition_sha256=dispositions[i][1])
            timing.append((sample,proof))
        def run(finals=dispositions):
            return prepare_joint_packet(outcome="completed",review_inputs=complete,
                provenance=p,physical_receipt_pair=receipts,browser_pairs=pairs,
                expected_browser_sha256=browser, disposition_pairs=finals,
                reservation_pairs=reservations,timing=tuple(timing))
        # Independently supplied fixture inputs, not a production host provider.
        def fixture_envelope():
            p=run()
            self.assertEqual(p["status"],"OFFLINE_PACKET_READY")
            raw=p["packet"]
            parsed=json.loads(raw)
            host=[]
            for i,(sample,proof) in enumerate(timing):
                host.append(dict(receipts={k: originals[i][0].decode("utf8")
                    for k,originals in (("observation",pairs),("reservation",reservations),("disposition",dispositions))},
                    trusted=dict(authentication_verified=True,sample=sample,proof=proof,
                        pins={k+"_sha256": originals[i][1] for k,originals in
                        (("observation",pairs),("reservation",reservations),("disposition",dispositions))})))
            return dict(packet=raw,host=dict(packet_sha256=digest(raw.encode()),quality=parsed["review"],turns=copy.deepcopy(host)))
        # Nonoverlapping synthetic clocks only; never normalize production data.
        for key in ("begin_ms","first_visible_ms","eof_ms"):
            timing[1][0][key]+=100
            timing[1][1][key]+=100
        timing[1][1]["dom_commit_ms"]+=100
        positive=fixture_envelope()
        # Retain the exact same canonical witnesses for the separately loaded B5 R80.
        # R80 terminal link includes the served hash, unlike the historical R92 wire.
        frozen_turns=[]
        for n,w in zip((2,3),wires):
            t=json.loads(w[0])
            t["link"]["served_sha256"]=wire["served_sha256"]
            t["canonical"]=terminal_canonical(dialog_id=args["dialog_id"],
                session_id=args["session_id"], expected_turn=n,
                artifacts=args["descriptor_sets"][:n])
            frozen_turns.append(t)
        data=dict(dialog_id=args["dialog_id"],session_id=args["session_id"],
            descriptors=args["descriptor_sets"],physical=dict(receipts=json.loads(receipts[0]),turns=frozen_turns))
        # Separate isolated interpreter: never shadow R109's loaded verifier modules.
        py="""import sys,json,hashlib
sys.path.insert(0,sys.argv[1])
sys.path.insert(0,sys.argv[2])
from freeze_release import freeze_release_payload
from canonical_text import recover_text
x=json.load(sys.stdin)
artifacts=tuple(tuple(d) for d in x['descriptors'])
scope=dict(dialog_id=x['dialog_id'],session_id=x['session_id'])
raw=lambda v:json.dumps(v,ensure_ascii=False,separators=(',',':')).encode()
ev=[]; candidates=[]
for n,t in enumerate(x['physical']['turns'],2):
    link=raw(t['link'])
    item=dict(terminal=t['terminal'],served_sha256=t['wire']['served_sha256'],link_bytes=link,link_sha256=hashlib.sha256(link).hexdigest())
    ev.append(item)
    candidates.append(recover_text(**scope,sequence=n,artifacts=artifacts[:n],**item))
sys.stdout.buffer.write(freeze_release_payload(tuple(candidates),**scope,artifacts=artifacts,turns=tuple(ev),physical_bytes=raw(x['physical'])))
"""
        from pathlib import Path
        import sys
        source=Path(__file__).resolve().parent
        fds=tuple(fd for d in args["descriptor_sets"] for fd in d[:2])
        proc=subprocess.run([sys.executable,"-I","-B","-c",py,str(source/"frozen"),str(source)],
            input=json.dumps(data,ensure_ascii=False).encode(),pass_fds=fds,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.assertEqual(proc.returncode,0,proc.stderr.decode())
        payload=proc.stdout
        # This detached pin is a synthetic fixture witness, NOT authentication.
        positive["frozen"]=payload.decode("utf8")
        positive["detached_fixture_pin"]=digest(payload)
        js="""const fs=require('node:fs'),assert=require('node:assert/strict');
const {makeFrozenOrderedReview:make}=require(process.argv[1]);
const {checkFrozenPayload}=require(process.argv[2]);
const {makeOfflinePairReview:baseline}=require(process.argv[3]);
const data=JSON.parse(fs.readFileSync(0,'utf8'));
const bytes=Buffer.from(data.frozen,'utf8');
for(const t of data.host.turns)for(const k of ['observation','reservation','disposition'])t.receipts[k]=Buffer.from(t.receipts[k],'utf8');
const pin=data.detached_fixture_pin;
assert.equal(checkFrozenPayload(bytes,pin).status,'CONSISTENT_PHYSICAL_RETAINED_PAIR_ONLY');
assert.equal(baseline(()=>data.host)(data.packet).status,'MATCHED_PAIR_OFFLINE');
const evidence={packet_sha256:data.host.packet_sha256,payload_sha256:pin,host:data.host};
const run=make(()=>evidence);
const good=run(bytes,data.packet);
assert.equal(good.status,'MATCHED_FROZEN_ORDERED_OFFLINE',JSON.stringify(good));
assert.equal(good.offline_metrics.length,2);
assert.equal(make()(bytes,data.packet).status,'HOLD_RELEASE_PROVIDER');
assert.equal(make(()=>({...evidence,payload_sha256:'f'.repeat(64)}))(bytes,data.packet).status,'HOLD_RELEASE_FROZEN');
assert.equal(run(Buffer.concat([bytes,Buffer.from(' ')]),data.packet).status,'HOLD_RELEASE_FROZEN');
const changed=JSON.parse(data.packet);changed.turns[1].proof.answer_sha256='f'.repeat(64);
assert.equal(run(bytes,JSON.stringify(changed)).status,'HOLD_RELEASE_DETACHED');
for(const k of ['native_accepted','authentication_verified','training_admitted','ack_allowed','next_post_allowed'])assert.equal(good[k],false);
assert.equal(good.metrics,null);assert.equal(good.quality_sample,null);
console.log('A3 R109/R80 actual frozen -> detached B3 -> R108 pair: 1 offline match; 4 holds; no native authority');
"""
        proc=subprocess.run(["node","-e",js,str(source/"joint_frozen.cjs"),
            str(source/"frozen/b3_r80_frozen_byte_ingress.cjs"),os.environ["B2_R108_MODULE"]],
            input=json.dumps(positive,ensure_ascii=False),text=True,encoding="utf-8",capture_output=True)
        self.assertEqual(proc.returncode,0,proc.stderr)
        print(proc.stdout.strip())
