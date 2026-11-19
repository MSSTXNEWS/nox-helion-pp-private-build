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

# Layout checks are synthetic, never native tensor SHA evidence.
with tempfile.TemporaryDirectory() as d:
    root=Path(d); fixture(root)
    name='model-00001-of-00001.safetensors'
    (root/'model.safetensors.index.json').write_text(json.dumps({'weight_map':{'a':name,'b':name}}))
    def pair(a_shape=(1,),b_offsets=(2,4),payload=bytes(4),b_dtype='F16'):
        hdr={'a':{'dtype':'F16','shape':list(a_shape),'data_offsets':[0,2]},
             'b':{'dtype':b_dtype,'shape':[1],'data_offsets':list(b_offsets)}}
        raw=json.dumps(hdr).encode()
        (root/name).write_bytes(len(raw).to_bytes(8,'little')+raw+payload)
        return m.hf_metadata_probe(root)['status']
    assert pair()=='HEADER_INDEX_MATCH_ONLY_CONTENT_SHA_PENDING'
    print('PASS 8: contiguous two-tensor payload')
    assert pair(a_shape=(2,))=='HOLD_TENSOR_BYTE_SIZE'
    print('PASS 9: incorrect tensor shape bytes')
    assert pair(b_offsets=(1,3),payload=bytes(3))=='HOLD_TENSOR_LAYOUT'
    print('PASS 10: overlapping offsets')
    assert pair(b_offsets=(3,5),payload=bytes(5))=='HOLD_TENSOR_LAYOUT'
    print('PASS 11: hole between tensors')
    assert pair(payload=bytes(5))=='HOLD_TENSOR_LAYOUT'
    print('PASS 12: unindexed trailing data')
    assert pair(b_dtype='F9')=='HOLD_TENSOR_DTYPE_UNSUPPORTED'
    print('PASS 13: unknown dtype')

# A synthetic signature-parser regression: no installed native TRL is inferred.
good={'schema':'NOX_SFTCONFIG_NATIVE_SIGNATURE_V1','trl_version':'1.18.0',
      'missing_required_kwargs':[],'save_safetensors_parameter':False}
wire=lambda value:'NOX_SFTCONFIG_SIGNATURE='+json.dumps(value)
actual=m.parse_sftconfig_signature_probe(0,wire(good))
assert actual['status']=='LEGACY_TRUE_REQUIRES_SAFE_OMISSION'
assert actual['constructor_executed'] is False and actual['optimizer_updates']==0
print('PASS 14: safe omitted legacy argument, without claiming a constructor call')
good['save_safetensors_parameter']=True
assert m.parse_sftconfig_signature_probe(0,wire(good))['status']=='SIGNATURE_ACCEPTS_LEGACY_SAVE_SAFETENSORS'
print('PASS 15: real-signature marker supporting legacy flag')
good['missing_required_kwargs']=['max_steps']
assert m.parse_sftconfig_signature_probe(0,wire(good))['status']=='HOLD_REQUIRED_SFTCONFIG_KWARGS_UNSUPPORTED'
print('PASS 16: required API incompatibility blocks admission')
assert m.parse_sftconfig_signature_probe(3,'')['status']=='HOLD_NATIVE_TRL_SIGNATURE_IMPORT'
assert m.parse_sftconfig_signature_probe(0,'unexpected')['status']=='HOLD_NATIVE_TRL_SIGNATURE_OUTPUT'
good['missing_required_kwargs']=['unknown_kwarg']
assert m.parse_sftconfig_signature_probe(0,wire(good))['status']=='HOLD_NATIVE_TRL_SIGNATURE_SCHEMA'
print('PASS 17-19: import failure, missing marker and unexpected fields block')
print('NOX_AUTO_2A_SFTCONFIG_SIGNATURE_SYNTHETIC_6_6_PASS; NATIVE_HOLD')

print('NOX_AUTO_2A_HF_METADATA_SYNTHETIC_13_13_PASS; NATIVE_HOLD')
