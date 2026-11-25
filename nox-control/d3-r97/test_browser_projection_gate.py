"""One joint RU/ES source integration, with actual retained descriptors and R70."""
import copy
import json
from browser_projection_gate import review_browser_projection
import unittest
from test_joint_rues import JointBilingual
from review_release import prepare_joint_review
from terminal_canonical import terminal_canonical
from distinct_dialog import review_distinct, pair, digest

def h(n):
    return format(n,"064x")

class BrowserProjectionGate(unittest.TestCase):
    def test_browser_projection_quality_gate(self):
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
        def run(projections=pairs):
            return review_browser_projection(outcome="completed",review_inputs=complete,
                provenance=p,physical_receipt_pair=receipts,browser_pairs=projections,
                expected_browser_sha256=browser)
        for bad in (None, (pair(dict(docs[0],visible_text_sha256=digest("30 евро".encode()))),pairs[1]),
                    (pair(dict(docs[0],exchange_id="foreign")),pairs[1]),
                    (pair(dict(docs[0],ack_state="UNCERTAIN")),pairs[1]),
                    (pairs[0],pair(dict(docs[1],observation_id="obs-0"))),
                    (pair(dict(docs[0],visible_row_count=2)),pairs[1])):
            result=run(bad)
            self.assertEqual(result["reason"],"HOLD_B2_BROWSER_TEXT_UNVERIFIED")
            self.assertIsNone(result["quality_sample"])
            for k in ("native_accepted","training_admitted","next_post_allowed","ack_allowed"):
                self.assertFalse(result[k])
        result=run()
        self.assertEqual(result["route"],"REVIEW_DATA_ONLY")
        self.assertEqual(result["dialog_provenance"]["browser_projection_sha256"],[x[1] for x in pairs])
        self.assertEqual(len(result["quality_sample"]["correction_evidence"]["entries"]),4)
        for k in ("native_accepted","training_admitted","next_post_allowed","ack_allowed"):
            self.assertFalse(result[k])
        self.assertFalse(result["dialog_provenance"]["authentication_verified"])
        print("R97_BROWSER_PROJECTION: 6 HOLD; 1 MATCHED_OFFLINE; NATIVE_ACCEPTED=false")
