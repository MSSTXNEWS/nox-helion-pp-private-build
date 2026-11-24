import contextlib
import copy
import json
import os
import subprocess
import tempfile
import unittest
from retained_pair import compose_pair
from terminal_canonical import terminal_canonical
from test_b5_chain_guard import checkpoint, DIALOG, SESSION, sha

def fixture():
    h=lambda n: format(n,"064x")
    p=dict(route="/fixture/model",model_id="fixture",dialog_id="physical-dialog",
        weights_manifest_sha256=h(11),tokenizer_manifest_sha256=h(12),
        bridge_sha256="c44b5aa2ef3d45246276a24bbcfad30bf76533fc2e08089eb91b442002643dc7",
        original_checkpoint_sha256=h(13),owner_admission_receipt_sha256=h(14),
        process=dict(boot_id="boot",pid=42,start_ticks=123),
        turn_request_ids=["req2","req3"],window_start_ms=100,window_end_ms=200)
    wire=dict(wire="named-delta-stable-server-id-v1",route="logical-route",
        served_sha256=h(21),server_sha256=h(22))
    mapping=dict(p,schema="NOX_B3_ROUTE_BINDING_V1",wire=wire["wire"],
        symbolic_route=wire["route"],served_sha256=wire["served_sha256"],
        server_sha256=wire["server_sha256"],conversation_id="logical-conversation",
        exchange_bindings=[dict(turn=n,request_id="req"+str(n),exchange_id="ex"+str(n)) for n in (2,3)])
    turns=[]
    for n in (2,3):
        scope=dict(conversation_id="logical-conversation",exchange_id="ex"+str(n))
        terminal=dict(scope,physical_dialog_id=p["dialog_id"],request_id="req"+str(n),
            attempt_id="attempt-"+str(n),sequence=n,status="STREAM_ENDED_READBACK_REQUIRED")
        _,(_,_,ws,rs)=checkpoint(n)
        link=dict(terminal,schema="NOX_B3_S03_TERMINAL_LINK_V1",s03_dialog_id=DIALOG,
            s03_session_id=SESSION,s03_event_id="event-"+str(n),s03_turn_id="turn-"+str(n),
            user_message_id="message-"+str(2*n-2),assistant_message_id="message-"+str(2*n-1),
            writer_sha256=ws,readback_sha256=rs)
        turns.append(dict(wire=wire,physical=p,mapping=mapping,scope=scope,expectedTurn=n,terminal=terminal,link=link))
    payloads=[json.dumps(dict(p,turn=2+i//2,phase=("before","after")[i%2],
        request_id=p["turn_request_ids"][i//2],observed_ms=110+10*i,readback_id="receipt-"+str(i),
        installed_bridge_sha256=p["bridge_sha256"],served_bridge_sha256=p["bridge_sha256"]),
        separators=(",",":")) for i in range(4)]
    return dict(schema="NOX_B3_R66_READBACK_BYTES_V1",expected=p,receipt_payloads=payloads,
        receipt_index=[dict(readback_id="receipt-"+str(i),sha256=sha(s.encode())) for i,s in enumerate(payloads)]),tuple(turns)

def descriptors(stack,rewrite=False):
    out=[]
    for n in (1,2,3):
        _,(w,r,ws,rs)=checkpoint(n,rewrite=rewrite)
        pair=[]
        for raw in (w,r):
            f=stack.enter_context(tempfile.TemporaryFile());f.write(raw);f.flush();pair.append(f.fileno())
        out.append((*pair,ws,rs))
    return tuple(out)

def check(payload):
    z=subprocess.run(["node",os.environ["B5_R72_NODE"]],
        input=json.dumps(payload,ensure_ascii=False),text=True,capture_output=True,check=True)
    return json.loads(z.stdout)["consistent"]

class Pair(unittest.TestCase):
    def test_actual_single_chain(self):
        with contextlib.ExitStack() as stack:
            a=descriptors(stack);b=descriptors(stack,rewrite=True)
            receipts,turns=fixture()
            args=dict(dialog_id=DIALOG,session_id=SESSION,artifacts=a,receipts=receipts,turns=turns)
            good=compose_pair(**args)
            self.assertTrue(check(good))
            self.assertEqual(good["turns"][0]["canonical"]["rows"],good["turns"][1]["canonical"]["rows"][:4])
            alternate=terminal_canonical(dialog_id=DIALOG,session_id=SESSION,expected_turn=3,artifacts=b)
            wrong=copy.deepcopy(good)
            wrong["turns"][1]["canonical"]=alternate
            link=wrong["turns"][1]["link"]
            link.update(writer_sha256=b[2][2],readback_sha256=b[2][3])
            # R71 alone accepts separately coherent but divergent histories.
            self.assertTrue(check(wrong))
            bad_turns=copy.deepcopy(turns);bad_turns[1]["link"]=link
            self.assertFalse(check(compose_pair(**dict(args,turns=bad_turns))))
            with self.assertRaises(ValueError):
                compose_pair(**dict(args,artifacts=a[:2]+b[2:]))
            with self.assertRaises(ValueError):
                compose_pair(**dict(args,turns=tuple(wrong["turns"])))
            with self.assertRaises(ValueError):
                compose_pair(**dict(args,turns=turns[::-1]))
            bad=copy.deepcopy(receipts);bad["receipt_payloads"][0]+=" "
            self.assertFalse(check(compose_pair(**dict(args,receipts=bad))))
            with self.assertRaises(ValueError):
                compose_pair(**dict(args,session_id="foreign"))
