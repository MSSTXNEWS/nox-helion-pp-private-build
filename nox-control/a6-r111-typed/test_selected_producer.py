"""One real selected producer call and typed rejection; synthetic only."""
import contextlib, json, sys, tempfile
from pathlib import Path
from hashlib import sha256
root=Path(sys.argv[1]).resolve()
here=Path(__file__).resolve().parent
frozen=root/"nox-control/a3-r109-r80/frozen"
sys.path[:0]=[str(frozen),str(here)]
import freeze_typed_release, typed_prefix, frozen_consumer
from canonical_text import recover_text
from link_fields import derive_link_fields
from fixture_checkpoint import checkpoint,DIALOG,SESSION,raw,sha
assert all(Path(m.__file__).resolve().parent==frozen for m in (freeze_typed_release,typed_prefix,frozen_consumer))
assert freeze_typed_release.freeze_typed_payload is typed_prefix.freeze_typed_payload
assert typed_prefix.freeze_consumer_payload is frozen_consumer.freeze_consumer_payload
h=lambda n:format(n,"064x")
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
    def retained(values=None):
        result=[]
        for n in (1,2,3):
            rows,(w,r,ws,rs)=checkpoint(n)
            if values is not None:
                rows[0]["metadata"]={"retained_flag":values[n-1]}
                doc=json.loads(r); doc["messages"]=rows; r=raw(doc); rs=sha(r)
            fds=[]
            for data in (w,r):
                f=stack.enter_context(tempfile.TemporaryFile()); f.write(data); f.flush(); fds.append(f.fileno())
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
        data=raw(link); evidence=dict(terminal=terminal,served_sha256=wire["served_sha256"],link_bytes=data,link_sha256=sha(data))
        turns.append(evidence); candidates.append(recover_text(**scope,sequence=n,artifacts=producer[:n],**evidence))
        rows,(w,r,ws,rs)=checkpoint(n)
        fixture["turns"].append(dict(wire=wire,physical=physical,mapping=mapping,scope=logical,expectedTurn=n,terminal=terminal,link=link,
            canonical=dict(writer=json.loads(w),readback=json.loads(r),rows=rows,writer_sha256=ws,readback_sha256=rs)))
    args=dict(**scope,artifacts=verifier,turns=tuple(turns),physical_bytes=raw(fixture))
    payload=freeze_typed_release.freeze_release_payload(tuple(candidates),**args)
    assert type(payload) is bytes and json.loads(payload)[0]==fixture
    for values in ((True,1,1),(1,1,1.0),(0.0,-0.0,-0.0)):
        try: freeze_typed_release.freeze_release_payload(tuple(candidates),**dict(args,artifacts=retained(values)))
        except ValueError as e: assert str(e)=="HOLD_S03_TYPED_PREFIX_CHANGED",str(e)
        else: raise AssertionError("typed prefix accepted")
    print(json.dumps(dict(selected_typed_frozen_producer="PASS",offline_payload_bytes=len(payload),typed_holds=3,host_provider_bound=False,native_accepted=False,full_joint_ci=False)))
