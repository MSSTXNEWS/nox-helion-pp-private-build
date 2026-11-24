"""One joint RU/ES source integration, with actual retained descriptors and R70."""
import copy
import unittest
from test_joint_rues import JointBilingual
from review_release import prepare_joint_review
from terminal_canonical import terminal_canonical
from distinct_dialog import review_distinct, pair, digest

def h(n):
    return format(n,"064x")

class DistinctDialog(unittest.TestCase):
    def test_distinct_physical_canonical_review_provenance(self):
        fixture=JointBilingual()
        self.addCleanup(fixture.doCleanups)
        args,_=fixture.build(("30 евро на покупку.","Quedan exactamente 90 euros."))
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
        def run(q=p, outcome="completed"):
            return review_distinct(outcome=outcome,review_inputs=complete,provenance=q)
        result=run()
        self.assertEqual(result["route"],"REVIEW_DATA_ONLY")
        self.assertEqual(len(result["quality_sample"]["correction_evidence"]["entries"]),4)
        evidence=result["dialog_provenance"]
        self.assertNotEqual(evidence["physical_dialog_id"],evidence["s03_dialog_id"])
        self.assertEqual(evidence["owner_sha256"],owner[1])
        self.assertEqual(evidence["terminal_sha256"],[x[1] for x in terminals])
        self.assertEqual(evidence["transport_sha256"],[x[1] for x in wires])
        self.assertFalse(evidence["authentication_verified"])
        for bad in (dict(p,expected_scope=dict(scope,physical_dialog_id="foreign")),
                    dict(p,terminal_pairs=()),dict(p,terminal_pairs=(terminals[0],terminals[0])),
                    dict(p,terminal_pairs=((terminals[0][0],"0"*64),terminals[1])),
                    dict(p,transport_pairs=(wires[1],wires[0]))):
            held=run(bad)
            self.assertEqual(held["route"],"HOLD")
            self.assertIsNone(held["quality_sample"])
        for outcome in ("failed","uncertain"):
            held=run(outcome=outcome)
            self.assertEqual(held["route"],"HOLD")
            self.assertIsNone(held["quality_sample"])
            self.assertFalse(held["next_post_allowed"])
