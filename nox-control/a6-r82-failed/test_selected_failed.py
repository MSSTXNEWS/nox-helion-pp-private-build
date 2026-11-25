"""Actual selected diagnostic from extracted layout; no repeat successful producer."""
import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1]).resolve()
here=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(here))
from stage_failed import stage_failed
def snapshot():
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}
before=snapshot()
dest=stage_failed(root)
after=snapshot()
assert all(after[k]==v for k,v in before.items())
assert len(after)-len(before)==8
try: stage_failed(root)
except ValueError as e: assert str(e)=="HOLD_FAILED_DIAGNOSTIC_OVERWRITE"
else: raise AssertionError("overwrite")
sys.path[:0]=[str(dest),str(here.parent/"a6-r111-typed")]
import diagnostic,typed_failed_poststate,b5_r55_pinned,b5_chain_guard
from fixture_checkpoint import checkpoint,DIALOG,SESSION,TEXT,raw,sha
assert all(pathlib.Path(m.__file__).resolve().parent==dest for m in
           (diagnostic,typed_failed_poststate,b5_r55_pinned,b5_chain_guard))
assert diagnostic.classify_typed_failed_turn is typed_failed_poststate.classify_typed_failed_turn
def evidence(n, observed):
    chain=[]
    for i in range(1,n+1):
        rows,(w,r,ws,rs)=checkpoint(i)
        rows[0]["metadata"]={"flag":True}
        doc=json.loads(r); doc["messages"]=rows; r=raw(doc)
        chain.append((rows,(w,r,ws,sha(r))))
    rows=checkpoint(n+1)[0][:-1]
    rows[0]["metadata"]={"flag":observed}
    b=raw(dict(source="canonical_s03",independent=True,dialog_id=DIALOG,
               session_id=SESSION,attempt_id="attempt-next",messages=rows))
    receipt=raw(dict(schema="nox.s03.failed-attempt-binding.v1",dialog_id=DIALOG,
                session_id=SESSION,attempt_id="attempt-next",snapshot_sha256=sha(b),
                user_message_id=rows[-1]["message_id"]))
    return dict(dialog_id=DIALOG,session_id=SESSION,attempt_id="attempt-next",
                prompt=TEXT[2*n],prior_chain=tuple(chain),snapshot_raw=b,snapshot_sha256=sha(b),
                admission_raw=receipt,admission_sha256=sha(receipt))
for n in (1,2):
    for observed,expected in ((True,"HOLD_S03_FAILURE_PENDING_USER"),
                              (1,"HOLD_S03_FAILURE_TYPED_PREFIX_CHANGED")):
        result=diagnostic.review_failed(evidence=evidence(n,observed))
        assert result["state"]==expected,result
        assert all(v is False for k,v in result.items() if k!="state")
assert diagnostic.review_failed(evidence={})["state"].startswith("HOLD_")
print(json.dumps(dict(selected_diagnostic="PASS",new_files=8,unchanged_files=len(before),
    cases=5,overwrite_hold=True,all_authority_false=True,native_accepted=False)))
