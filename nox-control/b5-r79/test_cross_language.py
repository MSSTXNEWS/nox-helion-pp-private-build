import contextlib
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from bind_retained_pair import bind_retained_pair
from pair_projection import compare_pair
from canonical_text import recover_text
from link_fields import derive_link_fields
from test_b5_chain_guard import checkpoint, DIALOG, SESSION, raw, sha

class CrossLanguage(unittest.TestCase):
    def test_actual_pair(self):
        h=lambda n: format(n,"064x")
        physical=dict(route="/fixture/model",model_id="fixture",dialog_id="physical-dialog",
            weights_manifest_sha256=h(11),tokenizer_manifest_sha256=h(12),
            bridge_sha256="c44b5aa2ef3d45246276a24bbcfad30bf76533fc2e08089eb91b442002643dc7",
            original_checkpoint_sha256=h(13),owner_admission_receipt_sha256=h(14),
            process=dict(boot_id="boot",pid=42,start_ticks=123),turn_request_ids=["req2","req3"],
            window_start_ms=100,window_end_ms=200)
        wire=dict(wire="named-delta-stable-server-id-v1",route="logical-route",served_sha256=h(21),server_sha256=h(22))
        payloads=[raw(dict(physical,turn=2+i//2,phase=("before","after")[i%2],
            request_id=physical["turn_request_ids"][i//2],observed_ms=110+i*10,
            readback_id=f"receipt-{i}",installed_bridge_sha256=physical["bridge_sha256"],
            served_bridge_sha256=physical["bridge_sha256"])).decode() for i in range(4)]
        fixture=dict(receipts=dict(schema="NOX_B3_R66_READBACK_BYTES_V1",expected=physical,
            receipt_payloads=payloads,receipt_index=[dict(readback_id=f"receipt-{i}",sha256=sha(s.encode())) for i,s in enumerate(payloads)]),turns=[])
        with contextlib.ExitStack() as stack:
            def retained():
                result=[]
                for n in (1,2,3):
                    _,(w,r,ws,rs)=checkpoint(n)
                    fds=[]
                    for data in (w,r):
                        f=stack.enter_context(tempfile.TemporaryFile());f.write(data);f.flush();fds.append(f.fileno())
                    result.append((*fds,ws,rs))
                return tuple(result)
            producer,verifier=retained(),retained()
            scope=dict(dialog_id=DIALOG,session_id=SESSION)
            candidates,turns=[],[]
            for n in (2,3):
                logical=dict(conversation_id="logical-conversation",exchange_id=f"exchange-{n}")
                mapping=dict(physical,schema="NOX_B3_ROUTE_BINDING_V1",wire=wire["wire"],
                    symbolic_route=wire["route"],served_sha256=wire["served_sha256"],server_sha256=wire["server_sha256"],
                    conversation_id=logical["conversation_id"],exchange_bindings=[
                        dict(turn=j,request_id=f"req{j}",exchange_id=f"exchange-{j}") for j in (2,3)])
                terminal=dict(logical,physical_dialog_id=physical["dialog_id"],request_id=f"req{n}",
                    attempt_id=f"attempt-{n}",sequence=n,status="STREAM_ENDED_READBACK_REQUIRED")
                fields=derive_link_fields(**scope,sequence=n,artifacts=producer[:n])
                link=dict(terminal,**fields,schema="NOX_B3_S03_TERMINAL_LINK_V1",served_sha256=wire["served_sha256"])
                data=raw(link)
                evidence=dict(terminal=terminal,served_sha256=wire["served_sha256"],link_bytes=data,link_sha256=sha(data))
                turns.append(evidence)
                candidates.append(recover_text(**scope,sequence=n,artifacts=producer[:n],**evidence))
                rows,(w,r,ws,rs)=checkpoint(n)
                fixture["turns"].append(dict(wire=wire,physical=physical,mapping=mapping,scope=logical,
                    expectedTurn=n,terminal=terminal,link=link,canonical=dict(writer=json.loads(w),readback=json.loads(r),
                    rows=rows,writer_sha256=ws,readback_sha256=rs)))
            args=dict(dialog_id=DIALOG,session_id=SESSION,artifacts=verifier,turns=tuple(turns))
            pair,links=bind_retained_pair(tuple(candidates),physical_input=fixture,**args)
            def node(input,pair,links):
                script="const fs=require('node:fs');const m=require(process.argv[1]);const x=JSON.parse(fs.readFileSync(0,'utf8'));console.log(JSON.stringify(m.checkRetainedPair(...x)));"
                return json.loads(subprocess.check_output(["node","-e",script,str(Path(path).resolve())],
                    input=raw([input,pair,links])))
            z=node(fixture,pair,links)
            self.assertEqual(z["status"],"CONSISTENT_PHYSICAL_RETAINED_PAIR_ONLY",z)
            for k in ("native_accepted","authentication_verified","ack_allowed","next_post_allowed"):
                self.assertIs(z[k],False)
            changed=copy.deepcopy(fixture)
            for t in changed["turns"]:
                t["canonical"]["rows"][0]["content"]="Подмена / cambio"
                t["canonical"]["readback"]["messages"][0]["content"]="Подмена / cambio"
            # Same detached pins and terminal answer: old B3 comparison does not bind earlier row bytes.
            self.assertTrue(node(changed,pair,links)["consistent"])
            with self.assertRaisesRegex(ValueError,"HOLD_B3_CANONICAL_WITNESS"):
                bind_retained_pair(tuple(candidates),physical_input=changed,**args)
            for i in (0,1):
                changed=copy.deepcopy(fixture);changed["turns"][i]["canonical"]["writer"]["durable"]=1
                with self.assertRaises(ValueError):
                    bind_retained_pair(tuple(candidates),physical_input=changed,**args)
            changed=copy.deepcopy(fixture);changed["turns"][1]["terminal"]["attempt_id"]="foreign"
            with self.assertRaisesRegex(ValueError,"HOLD_B3_TERMINAL_LINK"):
                bind_retained_pair(tuple(candidates),physical_input=changed,**args)
            altered=copy.deepcopy(pair);altered["turns"][1]["answer_sha256"]=h(99)
            self.assertFalse(node(fixture,altered,links)["consistent"])
            print("ACTUAL_R78_PYTHON_NODE: positive, earlier-row differential, 2 type negatives, terminal negative, digest negative; native_accepted=false")
if __name__=="__main__":
    # retain Node path for test, hide from unittest CLI
    path=sys.argv[1]
    sys.argv=[sys.argv[0]]
    # use global path in node helper
    unittest.main(verbosity=2)
