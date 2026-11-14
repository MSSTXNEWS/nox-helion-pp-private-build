"""Preflight and locally stage Hugging Face weights into a <=70GB owned block.

Install: pip install huggingface_hub. Never removes existing weights or caches.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
from soul_gpu import root_path, GB, TOTAL_GB, BLOCK_GB, RESERVE_GB

ALLOW = {"Qwen/Qwen3-4B-Instruct-2507", "Qwen/Qwen3-4B", "Qwen/Qwen3-8B"}
PATTERNS = ["*.safetensors", "*.json", "*.txt", "*.model", "*.tiktoken", "*.py", "LICENSE", "*.md"]

def used_bytes(path: Path) -> int:
    if not path.exists(): return 0
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file() and not p.is_symlink())

def stage(block: int, repo_id: str, root: Path) -> dict:
    if block not in (1,2,3): raise ValueError("Block must be 1..3")
    if repo_id not in ALLOW: raise ValueError("Only reviewed base model IDs allowed")
    try:
        from huggingface_hub import HfApi, snapshot_download
    except ImportError as exc:
        raise RuntimeError("pip install huggingface_hub") from exc
    root.mkdir(parents=True,exist_ok=True)
    dest = root / "blocks" / f"block-{block}"
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError("Block already exists; no overwrite or duplicate download")
    repo = HfApi().model_info(repo_id,files_metadata=True)
    files = [s for s in repo.siblings if s.rfilename.endswith((".safetensors",".json",".txt",".model",".tiktoken",".py",".md")) or s.rfilename == "LICENSE"]
    if not files or any(s.size is None for s in files):
        raise ValueError("Cannot prove complete download size before fetching")
    required = sum(s.size for s in files)
    if required > BLOCK_GB * GB:
        raise ValueError("Selected weights exceed 70 GB block")
    current = used_bytes(root)
    if current + required + GB > TOTAL_GB * GB:
        raise ValueError("270 GB total budget would be exceeded")
    free = shutil.disk_usage(root).free
    if free < required + RESERVE_GB*GB:
        raise ValueError("Insufficient free disk capacity for model + 60GB reserve")
    dest.mkdir(parents=True,exist_ok=True)
    try:
        snapshot_download(repo_id=repo_id,revision=repo.sha,local_dir=str(dest),allow_patterns=PATTERNS,max_workers=2)
        actual = used_bytes(dest)
        if actual > BLOCK_GB*GB or used_bytes(root)>TOTAL_GB*GB:
            raise ValueError("Budget exceeded after download; leave files for manual investigation")
        manifest = {"block":block,"repo_id":repo_id,"revision":repo.sha,"estimated_bytes":required,
                    "actual_bytes":actual,"status":"downloaded-not-trained","licensed_use_requires_review":True}
        (dest / "NOX_BLOCK_MANIFEST.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
        return manifest
    except Exception:
        # Never delete or silently retry partially downloaded bytes.
        raise

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--block",type=int,required=True)
    a.add_argument("--repo",default="Qwen/Qwen3-4B-Instruct-2507",choices=sorted(ALLOW))
    a.add_argument("--root",type=Path,default=root_path())
    args=a.parse_args()
    print(json.dumps(stage(args.block,args.repo,args.root),indent=2))
