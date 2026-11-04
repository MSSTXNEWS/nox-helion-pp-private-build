"""T06: stage exact original helion_voice from the immutable 729-file ZIP.
No new backend, native consent bypass, user data mutation, build or model install.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, stat, tempfile, zipfile
from pathlib import Path
ARCHIVE_SHA256 = "ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a"
FILES = {
  "helion_voice/__init__.py": "c53ab711e2ed5e8e8abdf501ae6cd30db8c9bd6e917213083693861825496354",
  "helion_voice/_worker.py": "433953a4793238d439fa60c29bf51a2e179ae2fed7b9ddd1cb8ca39ee321b5db",
  "helion_voice/adapters.py": "dd78b8cb380d46d959754ba641ece60dd4e15a8a305cbefdf0b612c9c9d72c12",
  "helion_voice/audio.py": "e3f5f63f6f42b7ac1bc55a3dc4461ca5f393af336070ef998f52e2d194c18fae",
  "helion_voice/benchmark.py": "86e86fe1b400a74572ed21974b5e51c55f9fb80e28be2e86bf79419afb95c500",
  "helion_voice/control.py": "30e51e9163683a6b8a84c306feba3bb6958f58e35d18a664e6bb08cc73137395",
  "helion_voice/devices.py": "978848a1240c5688599062bfc950eb7bec25cba9e8bb26f03c137b1a7f01568d",
  "helion_voice/integration.py": "303100b5260b93f9339051094439d744df3465aa1b59118a6d660991406cd01c",
  "helion_voice/intent.py": "6d2b4699986f0accccb82a62ebaf345b9751bccce1a72dd03f127890cf0bc400",
  "helion_voice/phrasebook.json": "0502c6f0ffe59b2532cdd1e7bd44144b59203918e07ad40c199223023929af74",
  "helion_voice/phrasebook.py": "4a7ad49ec5007d8108bdc3d7ba25e8789f08755d7e740b480b899c16f881da17",
  "helion_voice/safety.py": "d00adbd30877d69d5e7987226c5ef8231a6093ffdf51eba3d207f778ec697390",
  "helion_voice/service.py": "91edfc757a9052a52bf8468baae035add538b923a688eddbf98d643c36442b99"
}

class SourceHold(RuntimeError): pass

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def stage(archive: Path, target_root: Path, receipt: Path, run_id: str):
    if not re.fullmatch(r"[A-Za-z0-9._-]{8,96}",run_id):
        raise SourceHold("INVALID_RUN_ID")
    if not archive.is_file() or archive.is_symlink() or digest(archive.read_bytes()) != ARCHIVE_SHA256:
        raise SourceHold("ORIGINAL_ARCHIVE_SHA_HOLD")
    if target_root.is_symlink() or receipt.is_symlink():
        raise SourceHold("OUTPUT_SYMLINK_HOLD")
    target_root.mkdir(parents=True,exist_ok=True)
    if target_root.resolve()==archive.parent.resolve():
        raise SourceHold("ORIGINAL_SOURCE_DIRECTORY_IS_OUTPUT")
    records=[]
    with zipfile.ZipFile(archive) as z:
        members=[i for i in z.infolist() if not i.is_dir()]
        by_name={i.filename:i for i in members}
        if len(by_name)!=len(members) or {n for n in by_name if n.startswith("helion_voice/")} != set(FILES):
            raise SourceHold("VOICE_MEMBER_LIST_MISMATCH")
        for name,sha in FILES.items():
            info=by_name[name]
            if info.file_size>2000000 or ((info.external_attr >> 16)&0o170000)==stat.S_IFLNK:
                raise SourceHold("UNSAFE_VOICE_MEMBER:"+name)
            raw=z.read(info)
            if digest(raw)!=sha:
                raise SourceHold("VOICE_MEMBER_SHA_HOLD:"+name)
            out=target_root/name
            if any(p.is_symlink() for p in (target_root,target_root/"helion_voice",out.parent,out)):
                raise SourceHold("VOICE_OUTPUT_SYMLINK_HOLD:"+name)
            out.parent.mkdir(parents=True,exist_ok=True)
            if out.exists():
                if not out.is_file() or digest(out.read_bytes())!=sha:
                    raise SourceHold("EXISTING_OWNER_SOURCE_CONFLICT:"+name)
                disposition="ALREADY_IDENTICAL"
            else:
                fd,tmp=tempfile.mkstemp(dir=str(out.parent),prefix=".original-")
                try:
                    with os.fdopen(fd,"wb") as fp:
                        fp.write(raw);fp.flush();os.fsync(fp.fileno())
                    os.replace(tmp,out)
                finally:
                    if os.path.exists(tmp): os.unlink(tmp)
                disposition="ADDED"
            if digest(out.read_bytes())!=sha:
                raise SourceHold("VOICE_READBACK_HOLD:"+name)
            records.append({"path":name,"bytes":len(raw),"sha256":sha,"state":disposition})
    result={"schema":"NOX_V16_T06_ORIGINAL_VOICE_STAGE_V1","run_id":run_id,
            "original_archive_sha256":ARCHIVE_SHA256,"original_voice_files":records,
            "status":"SOURCE_STAGED_NOT_NATIVE_ACCEPTED","native_consent":"REQUIRED",
            "existing_host_binding":"HOLD_UNTIL_VERIFIED","new_backend":False,
            "EXE_NSIS_GITLAB_E07":"NOT_RUN"}
    receipt.parent.mkdir(parents=True,exist_ok=True)
    if receipt.exists(): raise SourceHold("RECEIPT_EXISTS")
    receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--archive",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--receipt",type=Path,required=True)
    parser.add_argument("--run-id",required=True)
    args=parser.parse_args()
    print("ORIGINAL_VOICE_STAGE_PASS",len(stage(args.archive,args.output,args.receipt,args.run_id)["original_voice_files"]))
