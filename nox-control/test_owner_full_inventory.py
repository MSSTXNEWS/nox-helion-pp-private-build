import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import owner_full_inventory as inventory


def string(value):
    raw=value.encode();return struct.pack('<Q',len(raw))+raw


def gguf(fields,version=3):
    result=b'GGUF'+struct.pack('<IQQ',version,42,len(fields))
    for key,kind,value in fields:result+=string(key)+struct.pack('<I',kind)+value
    return result


class InventoryTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.root=Path(folder.name)
        patcher=patch.object(inventory,'ROOT',self.root);patcher.start();self.addCleanup(patcher.stop)

    def test_gguf_architecture_is_observed_without_tokenizer_or_prompt_text(self):
        private='PRIVATE_TOKENIZER_OR_TEMPLATE_TEXT'
        path=self.root/'model.gguf'
        path.write_bytes(gguf([
            ('general.architecture',8,string('qwen2moe')),
            ('general.name',8,string('NOX observed weights')),
            ('general.file_type',4,struct.pack('<I',15)),
            ('qwen2moe.context_length',4,struct.pack('<I',65536)),
            ('tokenizer.ggml.tokens',9,struct.pack('<IQ',8,2)+string(private)+string('word')),
            ('tokenizer.chat_template',8,string(private)),
            ('general.description',8,string(private))]))
        observed=inventory.gguf_metadata(path)
        self.assertEqual(observed['state'],'HEADER_OBSERVED')
        self.assertEqual(observed['metadata']['general.architecture'],'qwen2moe')
        self.assertEqual(observed['metadata']['qwen2moe.context_length'],65536)
        self.assertNotIn(private,json.dumps(observed))
        self.assertFalse(observed['full_tensor_hash_verified'])

    def test_gguf_rejects_oversized_arrays_unknown_types_and_versions(self):
        samples=[gguf([('tokenizer.ggml.tokens',9,struct.pack('<IQ',8,200001))]),
                 gguf([('general.file_type',999,b'')]),gguf([],version=999),b'GGUF']
        for index,value in enumerate(samples):
            path=self.root/f'bad{index}.gguf';path.write_bytes(value)
            self.assertEqual(inventory.gguf_metadata(path)['state'],'UNKNOWN')

    def test_special_files_do_not_block_bounded_readers(self):
        path=self.root/'model.gguf';os.mkfifo(path)
        with self.assertRaises(ValueError):inventory.bounded(path)
        self.assertEqual(inventory.gguf_metadata(path)['state'],'UNKNOWN')
        self.assertEqual(inventory.tensor_header(path)['state'],'UNKNOWN')

    def test_safetensor_metadata_never_loads_pickle_or_tensor_values(self):
        path=self.root/'adapter_model.safetensors'
        document={'layer.lora_A.weight':{'dtype':'F32','shape':[2,2],'data_offsets':[0,16]},
                  '__metadata__':{'note':'PRIVATE_ADAPTER_NOTE'}}
        header=json.dumps(document).encode();path.write_bytes(struct.pack('<Q',len(header))+header+b'\x00'*16)
        result=inventory.tensor_header(path)
        self.assertEqual(result['state'],'HEADER_OBSERVED')
        self.assertEqual(result['elements'],4)
        self.assertNotIn('PRIVATE_ADAPTER_NOTE',json.dumps(result))
        self.assertFalse(result['tensor_values_read'])

    def test_zero_step_with_fresh_files_and_receipt_is_not_training_proof(self):
        output=self.root/'runs';path=output/'checkpoint-0';path.mkdir(parents=True)
        for name in inventory.CHECKPOINT_FILES:(path/name).write_bytes(b'fixture')
        (path/'trainer_state.json').write_text(json.dumps({'global_step':0,'log_history':[]}))
        (path/'adapter_config.json').write_text('{}')
        lineage={'schema':'NOX_T866U_FP32_ADAPTER_CONTINUATION_V1','base':{'path':str(self.root/'base')}}
        (output/'owner_lineage.json').write_text(json.dumps(lineage))
        digest=hashlib.sha256(json.dumps(lineage,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        receipt={'schema':'NOX_T866U_FP32_ADAPTER_CONTINUATION_V1','global_step':0,'successful_optimizer_steps':5,
                 'loss':1.0,'adapter_delta_verified':True,'before_tensor_sha256':'a'*64,'after_tensor_sha256':'b'*64,
                 'lineage_sha256':digest,'checkpoint':{'path':str(path),'global_step':0,
                 'files_sha256':{name:hashlib.sha256((path/name).read_bytes()).hexdigest() for name in inventory.CHECKPOINT_FILES}}}
        (output/'owner_receipt_step_0.json').write_text(json.dumps(receipt))
        result=inventory.checkpoint(path)
        self.assertTrue(result['seven_recovery_artifacts_present'])
        self.assertFalse(result['positive_step_recorded'])
        self.assertEqual(result['training_provenance'],'RECEIPT_PRESENT_NOT_VALIDATED')
        self.assertFalse(result['large_file_hashes_recomputed'])

    def test_s03_exports_schema_counts_only(self):
        path=self.root/'s03.sqlite'
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE s03_items(id TEXT, text TEXT)')
            db.execute('INSERT INTO s03_items VALUES(?,?)',('private-id','PRIVATE_OWNER_CHAT_TEXT'))
        result=inventory.memory_database(path)
        self.assertEqual(result['state'],'S03_SCHEMA_OBSERVED')
        self.assertEqual(result['counts']['s03_items'],1)
        self.assertTrue(result['quick_check_ok'])
        wire=json.dumps(result)
        self.assertNotIn('PRIVATE_OWNER_CHAT_TEXT',wire)
        self.assertNotIn('private-id',wire)

    def test_targeted_source_redacts_quoted_credentials_and_opaque_assignments(self):
        path=self.root/'pool.py'
        source="""API_TOKEN='OPAQUE_GLOBAL_SECRET'
PROMPT='Answer without a forced title'
def prepare_payload(value):
    headers={'api_key': 'OPAQUE_DICT_SECRET', 'X-API-Key': 'OPAQUE_HEADER_SECRET'}
    NOX_API_KEY = 'OPAQUE_ASSIGNMENT_SECRET'
    raw='sk-abcdefghijk123456789012345'
    return value, API_TOKEN, PROMPT
"""
        path.write_text(source)
        result=inventory.diagnostic_source(path,('prepare_payload',))
        wire=json.dumps(result)
        for secret in ('OPAQUE_GLOBAL_SECRET','OPAQUE_DICT_SECRET','OPAQUE_HEADER_SECRET','OPAQUE_ASSIGNMENT_SECRET','sk-abcdefghijk123456789012345'):
            self.assertNotIn(secret,wire)
        self.assertIn('Answer without a forced title',wire)
        self.assertEqual(result['sha256'],hashlib.sha256(source.encode()).hexdigest())

    def test_live_mapping_records_inode_and_ignores_other_paths(self):
        proc=self.root/'proc';folder=proc/'123';folder.mkdir(parents=True)
        (folder/'maps').write_text('1000-2000 r--p 00000000 08:01 456 /root/nox/models/current.gguf\n'
                                  '2000-3000 r--p 00000000 08:01 789 /root/private/secret.gguf\n')
        with patch.object(inventory,'PROC',proc):rows=inventory.mapped_models(123)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['inode'],456)
        self.assertEqual(rows[0]['device'],os.makedev(8,1))
        self.assertEqual(rows[0]['evidence'],'LIVE_PROCESS_MAPPING')

    def test_receipt_private_and_never_overwrites_existing(self):
        path=self.root/'receipt.json'
        inventory.write_receipt(path,{'schema':inventory.SCHEMA})
        self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
        original=path.read_bytes()
        with self.assertRaises(RuntimeError):inventory.write_receipt(path,{'changed':True})
        self.assertEqual(path.read_bytes(),original)

    def test_provider_configuration_returns_booleans_without_secret_values(self):
        folder=self.root/'config';folder.mkdir()
        (folder/'api_credentials.json').write_text(json.dumps({
            'openai':{'api_key':'OPAQUE_OPENAI_PRIVATE_VALUE'},
            'anthropic':{'api_key_env':'ANTHROPIC_API_KEY'}}))
        (self.root/'.env').write_text('GEMINI_API_KEY="OPAQUE_GEMINI_PRIVATE_VALUE"\n')
        with patch.object(inventory,'supervisor',return_value={'services':[]}),patch.object(inventory,'process_rows',return_value=[]):
            result=inventory.credential_presence()
        self.assertFalse(result['values_exported'])
        wire=json.dumps(result)
        self.assertNotIn('OPAQUE_OPENAI_PRIVATE_VALUE',wire)
        self.assertNotIn('OPAQUE_GEMINI_PRIVATE_VALUE',wire)
        self.assertTrue(any(row['nonempty']['OPENAI_API_KEY'] for row in result['configuration_files']))
        self.assertTrue(any(row['nonempty']['GEMINI_API_KEY'] for row in result['configuration_files']))
        self.assertTrue(any(row['env_reference']['ANTHROPIC_API_KEY'] for row in result['configuration_files']))


if __name__=='__main__':unittest.main()
