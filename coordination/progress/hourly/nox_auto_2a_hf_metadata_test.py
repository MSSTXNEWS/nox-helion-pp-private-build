#!/usr/bin/env python3
"""Synthetic tests for read-only owner HF index/header probe; NOT native attestation."""
from pathlib import Path
import hashlib, importlib.util, json, re, tempfile

src=Path(__file__).resolve().parents[3]/'nox-control'/'owner_native_inspect.py'
spec=importlib.util.spec_from_file_location('original_owner_native_inspect',src)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def shard(base,tensor='a',name='model-00001-of-00001.safetensors'):
    header=json.dumps({tensor:{'dtype':'F16','shape':[1],'data_offsets':[0,2]}}).encode()
    (base/name).write_bytes(len(header).to_bytes(8,'little')+header+b'\0\0')

def fixture(base):
    (base/'tokenizer.json').write_text('{}')
    (base/'tokenizer_config.json').write_text('{}')
    shard(base)
    (base/'model.safetensors.index.json').write_text(
        json.dumps({'weight_map':{'a':'model-00001-of-00001.safetensors'}}))

with tempfile.TemporaryDirectory() as d:
    root=Path(d);fixture(root)
    good=m.hf_metadata_probe(root)
    assert good['status']=='HEADER_INDEX_MATCH_ONLY_CONTENT_SHA_PENDING'
    assert good['tensor_count']==1 and good['weight_payload_sha256_verified'] is False
    print('PASS 1-2: header/index matches; no false weight-content SHA claim')
    (root/'model.safetensors.index.json').write_text(
        json.dumps({'weight_map':{'b':'model-00001-of-00001.safetensors'}}))
    assert m.hf_metadata_probe(root)['status']=='HOLD_TENSOR_INDEX_HEADER_MISMATCH'
    print('PASS 3: misrouted index tensor')
    (root/'model.safetensors.index.json').write_text(
        '{"weight_map":{"a":"model-00001-of-00001.safetensors","a":"model-00001-of-00001.safetensors"}}')
    assert m.hf_metadata_probe(root)['status'].startswith('HOLD_METADATA_')
    print('PASS 4: duplicated index key')
    fixture(root);(root/'tokenizer.json').unlink()
    assert m.hf_metadata_probe(root)['status']=='HOLD_TOKENIZER_REQUIRED_FILES'
    print('PASS 5: missing tokenizer')
    fixture(root);(root/'model-00001-of-00001.safetensors').unlink()
    (root/'model-00001-of-00001.safetensors').symlink_to('/etc/hosts')
    assert m.hf_metadata_probe(root)['status']=='HOLD_SHARD_UNSAFE'
    print('PASS 6: symlinked shard')
    (root/'model-00001-of-00001.safetensors').unlink()
    fixture(root);(root/'extra.safetensors').write_bytes(b'0')
    assert m.hf_metadata_probe(root)['status']=='HOLD_SHARD_INDEX_FILESET_MISMATCH'
    print('PASS 7: extra unindexed shard')
print('NOX_AUTO_2A_HF_METADATA_SYNTHETIC_7_7_PASS; NATIVE_HOLD')
