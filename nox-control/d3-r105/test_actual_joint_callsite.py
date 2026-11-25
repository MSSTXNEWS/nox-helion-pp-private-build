"""One joint RU/ES source integration, with actual retained descriptors and R70."""
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

class ActualJointCallsite(unittest.TestCase):
    def test_actual_joint_callsite(self):
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
        collision=pair(dict(json.loads(dispositions[0][0]), disposition_id=docs[0]["observation_id"]))
        bad=run((collision,dispositions[1]))
        self.assertEqual(bad["status"],"HOLD_B2_CROSS_KIND_RECEIPT_ID")
        self.assertIsNone(bad["packet"])
        good=run()
        self.assertEqual(good["status"],"OFFLINE_PACKET_READY")
        self.assertIsNone(good["quality_sample"])
        packet=good["packet"]
        parsed=json.loads(packet)
        self.assertEqual(len(parsed["review"]["quality_sample"]["correction_evidence"]["entries"]),4)
        for i,row in enumerate(parsed["turns"]):
            self.assertNotIn("verified",row["proof"])
            for kind,originals in (("observation",pairs),("reservation",reservations),("disposition",dispositions)):
                self.assertEqual(row[kind],[originals[i][0].decode("utf-8"),originals[i][1]])
        js="""const fs=require('node:fs'),assert=require('node:assert/strict');
const {makeJointReview}=require(process.argv[1]);
const raw=fs.readFileSync(0,'utf8');
const denied=makeJointReview()(raw);
assert.equal(denied.status,'HOLD_HOST_AUTHENTICATION');
assert.equal(denied.metrics,null);
const gate=makeJointReview(x=>x===raw); // fixture only
const good=gate(raw);
assert.equal(good.status,'MATCHED_JOINT_OFFLINE');
assert.equal(good.metrics,null);assert.equal(good.quality_sample,null);
assert.equal(good.native_accepted,false);assert.equal(good.ack_allowed,false);
assert.equal(good.fixture_metrics.length,2);
for(const m of good.fixture_metrics){assert.equal(m.completion_ms,70);assert.equal(m.ttft_ms,10);}
const changed=JSON.parse(raw);changed.turns[0].proof.reservation_sha256=changed.turns[1].reservation[1];
assert.equal(gate(JSON.stringify(changed)).metrics,null);
console.log('R105_ACTUAL_CHAIN: R104_R101_R103=true; COLLISION=HOLD; NO_HOST=HOLD; FIXTURE_ONLY=true; NATIVE_ACCEPTED=false');
"""
        proc=subprocess.run(["node","-e",js,os.environ["D3_R103_MODULE"]],
            input=packet,text=True,encoding="utf-8",capture_output=True,check=True)
        print(proc.stdout.strip())
