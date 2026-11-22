"""Export explicitly reviewed synthetic/de-identified skills and preflight a local GLM PEFT adapter.

Offline stdlib CLI. No conversations or project stores are read implicitly.
"""
import argparse
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import struct
import sys
from tempfile import TemporaryDirectory
import unicodedata


DENY = re.compile(
    r"[\w.+-]+@[\w.-]+\.[\w-]+|(?:https?://|www\.)\S+|"
    r"(?:\+\d[\d ()-]{7,}\d)|\b(?:\d[ -]?){10,19}\b|"
    r"\b[A-ZXYZ]\d{7,8}[A-Z]\b|\b\d{8}[A-Z]\b|"
    r"\b(?:gh[pousr]_|github_pat_|sk-|AKIA|eyJ[A-Za-z0-9_-]{10,}\.)\S+|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY|"
    r"\b(?:пароль|токен|password|contraseña|token|secret)\s*[:=]\s*\S+|"
    r"(?:\bменя зовут|\bмой адрес|\bмой диагноз|\bmi direcci[oó]n|\bme llamo|\bmi diagn[oó]stico)\b",
    re.IGNORECASE,
)
REFERENCE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}\Z")
COMMIT = re.compile(r"(?:[a-f0-9]{40}|[a-f0-9]{64})\Z")
HEX256 = re.compile(r"[a-f0-9]{64}\Z")


def normalized(text):
    return " ".join(unicodedata.normalize("NFKC",text).casefold().split())


def digest(data):
    return sha256(data).hexdigest()


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(",",":"))


def file_digest(path):
    h=sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1<<20),b""): h.update(block)
    return h.hexdigest()


def reviewed(row):
    if not isinstance(row,dict): raise ValueError("row_type")
    if row.get("approved") is not True or row.get("training_opt_in") is not True:
        raise ValueError("approval_or_opt_in")
    if row.get("training_scope")!="skill" or row.get("personal_facts") is not False or row.get("manually_deidentified") is not True:
        raise ValueError("scope_or_privacy_review")
    language=row.get("language")
    provenance=row.get("provenance")
    if language not in ("ru","es"): raise ValueError("language")
    if not isinstance(provenance,dict) or provenance.get("kind") not in ("synthetic","reviewed_skill"):
        raise ValueError("provenance")
    ref=provenance.get("id")
    if not isinstance(ref,str) or not REFERENCE.fullmatch(ref): raise ValueError("source_reference")
    texts=[]
    for key in ("prompt","chosen","rejected"):
        value=row.get(key)
        if not isinstance(value,str) or not value.strip() or len(value)>32768:
            raise ValueError("missing_or_oversize_text")
        if DENY.search(unicodedata.normalize("NFKC",value)): raise ValueError("sensitive_pattern")
        texts.append(value.strip())
    if normalized(texts[1])==normalized(texts[2]): raise ValueError("same_alternatives")
    return language,ref,texts


def dump_lines(path,rows):
    with path.open("x",encoding="utf8") as f:
        for r in rows: f.write(canonical(r)+"\n")


def export_pairs(source, dest):
    """Reject invalid data atomically; never copy rejected text into error messages."""
    dest=Path(dest)
    if dest.exists(): raise ValueError("destination_exists")
    pairs={}
    counts=Counter()
    sft=[]; dpo=[]; slp=[]; refs=[]
    with Path(source).open(encoding="utf8") as f:
        for i,line in enumerate(f,1):
            if not line.strip(): continue
            try:
                lang,ref,(prompt,chosen,rejected)=reviewed(json.loads(line))
            except (TypeError,ValueError) as e:
                reason="invalid_json" if isinstance(e,json.JSONDecodeError) else str(e)
                raise ValueError(f"line {i}: {reason}") from None
            # Prevent counting a repeated example twice or training contradictory preferences.
            identity=normalized(prompt)
            target=(normalized(chosen), normalized(rejected))
            if identity in pairs:
                if pairs[identity]!=target: raise ValueError(f"line {i}: conflicting_prompt")
                continue
            pairs[identity]=target
            user=[{"role":"user","content":prompt}]
            good=[{"role":"assistant","content":chosen}]
            bad=[{"role":"assistant","content":rejected}]
            sft.append({"messages":user+good})
            dpo.append({"prompt":user,"chosen":good,"rejected":bad})
            slp.extend([{"prompt":user,"completion":good,"label":True},{"prompt":user,"completion":bad,"label":False}])
            refs.append({"row":len(dpo),"source_id":ref,"language":lang,"pair_sha256":digest(canonical(dpo[-1]).encode())})
            counts[lang]+=1
    if not pairs: raise ValueError("empty_dataset")
    dest.parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(dir=dest.parent,prefix=".nox-skill-") as staging:
        directory=Path(staging)/"dataset"
        directory.mkdir(mode=0o700)
        for name,rows in (("sft.jsonl",sft),("dpo.jsonl",dpo),("kto_train.jsonl",slp),("provenance.jsonl",refs)):
            dump_lines(directory/name,rows)
        stats={"mode":"sft","pairs":len(dpo),"languages":dict(counts),"scope":"skill","target":"main_glm",
               "sha256":{f.name:file_digest(f) for f in sorted(directory.iterdir())}}
        (directory/"stats.json").write_text(canonical(stats)+"\n",encoding="utf8")
        directory.rename(dest)
    return stats


def parse_object(path):
    with Path(path).open(encoding="utf8") as f: d=json.load(f)
    if not isinstance(d,dict): raise ValueError("expected_json_object")
    return d


def targets(obj):
    fields=obj.get("target_modules")
    if not isinstance(fields,list) or not fields or not all(isinstance(f,str) and re.fullmatch(r"\w+(?:\.\w+)*",f) for f in fields):
        raise ValueError("expected_explicit_target_modules")
    if len(fields)!=len(set(fields)): raise ValueError("duplicate_target_module")
    return set(fields)


def tensor_pairs(path, allowed, rank):
    with Path(path).open("rb") as f:
        raw=f.read(8)
        if len(raw)!=8: raise ValueError("invalid_safetensors_header")
        length=struct.unpack("<Q",raw)[0]
        if not 2<=length<=16*1024*1024: raise ValueError("invalid_safetensors_header")
        header=json.loads(f.read(length))
        size=os.fstat(f.fileno()).st_size-length-8
    if not isinstance(header,dict): raise ValueError("invalid_safetensors_index")
    pairs={}; found=set(); ranges=[]
    for name,desc in header.items():
        if name=="__metadata__": continue
        m=re.fullmatch(r"(.+)\.lora_([AB])(?:\.default)?\.weight",name)
        if m is None or not isinstance(desc,dict): raise ValueError("unsupported_adapter_tensor")
        path,side=m.groups()
        target=next((x for x in sorted(allowed,key=len,reverse=True) if path==x or path.endswith("."+x)),None)
        if target is None: raise ValueError("tensor_outside_target_modules")
        found.add(target)
        shape=desc.get("shape"); span=desc.get("data_offsets")
        if not isinstance(shape,list) or len(shape)!=2 or not all(type(x) is int and x>0 for x in shape):
            raise ValueError("invalid_tensor_shape")
        width={"F32":4,"F16":2,"BF16":2}.get(desc.get("dtype"))
        if not width or not isinstance(span,list) or len(span)!=2 or not all(type(x) is int for x in span):
            raise ValueError("unsupported_tensor_format")
        start,end=span
        if not 0<=start<end<=size or end-start!=shape[0]*shape[1]*width: raise ValueError("invalid_tensor_extent")
        if shape[0 if side=="A" else 1]!=rank: raise ValueError("tensor_rank_mismatch")
        if side in pairs.setdefault(path,set()): raise ValueError("duplicate_tensor_side")
        pairs[path].add(side)
        ranges.append((start,end))
    if not pairs or found!=allowed or any(v!={"A","B"} for v in pairs.values()): raise ValueError("incomplete_lora_pairs")
    cursor=0
    for start,end in sorted(ranges):
        if start!=cursor: raise ValueError("invalid_tensor_layout")
        cursor=end
    if cursor!=size: raise ValueError("trailing_tensor_data")
    return len(pairs)


def validate_manifest(runtime, manifest, config, adapter_path):
    """Compare trusted runtime inventory, trainer manifest, PEFT config and actual local bytes."""
    for obj in (runtime,manifest):
        if obj.get("role")!="main_glm": raise ValueError("requires_main_glm_role")
        model=obj.get("base_model")
        arch=obj.get("architecture")
        rev=obj.get("revision")
        if not isinstance(model,str) or not model.strip() or model.lower().endswith(".gguf"):
            raise ValueError("requires_original_base_model")
        if not isinstance(arch,str) or "glm" not in arch.lower(): raise ValueError("requires_glm_architecture")
        if not isinstance(rev,str) or not COMMIT.fullmatch(rev): raise ValueError("requires_immutable_revision")
    for field in ("architecture","base_model","revision"):
        if runtime[field]!=manifest[field]: raise ValueError("runtime_mismatch:"+field)
    allow=targets(runtime)
    if targets(manifest)!=allow or targets(config)!=allow: raise ValueError("target_modules_mismatch")
    if config.get("peft_type")!="LORA" or config.get("task_type")!="CAUSAL_LM": raise ValueError("requires_lora_causal_lm")
    if config.get("base_model_name_or_path")!=runtime["base_model"]: raise ValueError("peft_base_mismatch")
    if config.get("revision") not in (None,runtime["revision"]): raise ValueError("peft_revision_mismatch")
    if config.get("rank_pattern") or config.get("modules_to_save") or config.get("use_dora") or config.get("bias","none")!="none":
        raise ValueError("unsupported_nonstandard_lora")
    rank=config.get("r")
    if type(rank) is not int or rank<1: raise ValueError("invalid_adapter_rank")
    path=Path(adapter_path)
    if path.suffix!=".safetensors": raise ValueError("expected_peft_safetensors")
    expected=manifest.get("adapter_sha256")
    if not isinstance(expected,str) or not HEX256.fullmatch(expected) or file_digest(path)!=expected: raise ValueError("adapter_sha256_mismatch")
    pairs=tensor_pairs(path,allow,rank)
    return {"compatible_metadata":True,"role":"main_glm","layer_pairs":pairs,"adapter_sha256":expected,"loaded":False}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    actions=parser.add_subparsers(dest="cmd",required=True)
    exp=actions.add_parser("export")
    exp.add_argument("pairs"); exp.add_argument("new_directory")
    check=actions.add_parser("validate")
    for name in ("runtime","manifest","peft_config","adapter"):
        check.add_argument(name)
    args=parser.parse_args(argv)
    try:
        if args.cmd=="export": result=export_pairs(args.pairs,args.new_directory)
        else: result=validate_manifest(parse_object(args.runtime),parse_object(args.manifest),parse_object(args.peft_config),args.adapter)
    except (OSError,ValueError,TypeError) as e:
        print(canonical({"ok":False,"error":str(e)}),file=sys.stderr)
        return 2
    print(canonical({"ok":True,**result}))
    return 0


if __name__=="__main__": sys.exit(main())
