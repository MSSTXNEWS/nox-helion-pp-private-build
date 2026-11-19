import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('adapter_audit', HERE / 'owner_adapter_lineage_audit.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def safetensors(path, tensors, metadata=None):
    header, offset, body = {}, 0, bytearray()
    for name, (shape, dtype) in tensors.items():
        length = m.math.prod(shape) * m.DTYPE_BYTES[dtype]
        header[name] = {'shape': shape, 'dtype': dtype, 'data_offsets': [offset, offset + length]}
        body.extend(b'\0' * length)
        offset += length
    if metadata is not None:
        header['__metadata__'] = metadata
    encoded = json.dumps(header, separators=(',', ':')).encode()
    raw = struct.pack('<Q', len(encoded)) + encoded + body
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def linear():
    prefix = 'base_model.model.model.layers.0.self_attn.q_proj'
    adapter = {prefix + '.lora_A.weight': {'shape': [2, 3], 'dtype': 'F32'},
               prefix + '.lora_B.weight': {'shape': [4, 2], 'dtype': 'F32'}}
    base = {'model.layers.0.self_attn.q_proj.weight': {'shape': [4, 3], 'dtype': 'BF16'}}
    return adapter, base, {'peft_type': 'LORA', 'r': 2, 'lora_alpha': 4, 'fan_in_fan_out': False}


class LineageAuditTests(unittest.TestCase):
    def test_base_header_read_does_not_read_tensor_payload_or_export_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'model.safetensors'
            safetensors(path, {'layer.weight': ([4, 3], 'F32')}, {'private': 'PRIVATE_EXPERIENCE'})
            calls = []
            original = os.pread
            def read(fd, length, offset):
                calls.append((length, offset))
                return original(fd, length, offset)
            with patch.object(m.os, 'pread', side_effect=read):
                values, result = m.read_safetensors(path, m.Budget(), full_hash=False)
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0], (8, 0))
            self.assertEqual(calls[1][1], 8)
            self.assertEqual(sum(length for length, _ in calls), result['header_bytes'])
            self.assertFalse(result['full_file_sha256_verified'])
            self.assertNotIn('PRIVATE_EXPERIENCE', json.dumps(result))

    def test_duplicate_header_keys_holes_and_wrong_byte_products_rejected(self):
        examples = [
            b'{"x":{"dtype":"F32","shape":[1],"data_offsets":[0,4]},"x":{"dtype":"F32","shape":[1],"data_offsets":[0,4]}}',
            b'{"x":{"dtype":"F32","shape":[1],"data_offsets":[1,5]}}',
            b'{"x":{"dtype":"F32","shape":[2],"data_offsets":[0,4]}}',
        ]
        with tempfile.TemporaryDirectory() as folder:
            for index, header in enumerate(examples):
                path = Path(folder) / str(index)
                body = b'\0' * (5 if index == 1 else 4)
                path.write_bytes(struct.pack('<Q', len(header)) + header + body)
                with self.subTest(index=index), self.assertRaises(m.AuditHold):
                    m.read_safetensors(path, m.Budget(), full_hash=False)

    def test_zero_and_scalar_tensors_are_valid_format_but_not_linear_lora(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'weights'
            safetensors(path, {'empty': ([0, 4], 'F32'), 'scalar': ([], 'F32')})
            values, result = m.read_safetensors(path, m.Budget(), full_hash=False)
            self.assertEqual(result['zero_element_tensors'], 1)
            assessed = m.structure(values, {}, {'peft_type': 'LORA'})
            self.assertEqual(assessed['unsupported_tensor_count'], 2)
            self.assertFalse(assessed['automatic_merge_allowed'])

    def test_full_sha_still_available_for_unverified_header(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bad.safetensors'
            header = b'{"x":1,"x":2}'
            raw = struct.pack('<Q', len(header)) + header
            path.write_bytes(raw)
            tensors, result = m.read_safetensors(path, m.Budget(), full_hash=True)
            self.assertEqual(tensors, {})
            self.assertEqual(result['state'], 'HEADER_UNVERIFIED')
            self.assertEqual(result['full_file_sha256'], hashlib.sha256(raw).hexdigest())

    def test_linear_shape_match_never_proves_origin_or_merge_safety(self):
        adapter, base, config = linear()
        result = m.structure(adapter, base, config)
        self.assertEqual(result['state'], 'SUPPORTED_LINEAR_DIMENSIONS_MATCH')
        self.assertEqual(result['exact_name_and_dimension_pairs'], 1)
        self.assertFalse(result['original_base_identity_proved'])
        self.assertFalse(result['previous_merge_excluded'])
        self.assertFalse(result['automatic_merge_allowed'])
        origin = m.origin_assessment({'config': {'base_model_name_or_path': 'model', 'revision': 'a' * 40}},
                                     {'config': {'_name_or_path': 'model', '_commit_hash': 'a' * 40}})
        self.assertTrue(origin['recorded_base_reference_equal'])
        self.assertTrue(origin['recorded_immutable_revision_equal'])
        self.assertEqual(origin['reapply_gate'], 'HOLD_ORIGIN_AND_PREVIOUS_MERGE_UNVERIFIED')

    def test_collision_fused_target_and_extra_tensors_do_not_silently_match(self):
        adapter, base, config = linear()
        first = next(iter(adapter))
        adapter[first.replace('.lora_A.weight', '.lora_A.other.weight')] = adapter[first]
        result = m.structure(adapter, base, config)
        self.assertEqual(result['normalization_collision_count'], 1)
        self.assertIn('UNKNOWN', result['state'])
        adapter, base, config = linear()
        base = {next(iter(base)).replace('q_proj', 'qkv_proj'): next(iter(base.values()))}
        self.assertEqual(m.structure(adapter, base, config)['missing_target_count'], 1)
        adapter['base_model.model.extra.lora_magnitude_vector'] = {'shape': [4], 'dtype': 'F32'}
        self.assertEqual(m.structure(adapter, base, config)['unsupported_tensor_count'], 1)

    def test_mismatch_and_transpose_require_distinct_evidence(self):
        adapter, base, config = linear()
        base[next(iter(base))]['shape'] = [4, 7]
        self.assertEqual(m.structure(adapter, base, config)['state'], 'INCOMPATIBLE_OBSERVED_LINEAR_DIMENSIONS')
        adapter, base, config = linear()
        config['fan_in_fan_out'] = True
        base[next(iter(base))]['shape'] = [3, 4]
        result = m.structure(adapter, base, config)
        self.assertEqual(result['state'], 'TRANSPOSED_DIMENSIONS_MATCH_ORIENTATION_UNVERIFIED')
        self.assertFalse(result['automatic_merge_allowed'])

    def test_full_adapter_hash_does_not_depend_on_readable_config(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'adapter_model.safetensors'
            expected = safetensors(path, {'x': ([2], 'F32')})
            config = root / 'adapter_config.json'
            config.write_text('{"r":2,"r":3}')
            target = {'id': 'toy', 'kind': 'existing_adapter', 'path': str(path), 'config_path': str(config),
                      'expected_bytes': path.stat().st_size}
            with patch.object(m, 'ROOT', root):
                result = m.inspect_adapter(target, m.Budget())
            self.assertEqual(result['public']['config']['state'], 'CONFIG_UNVERIFIED')
            self.assertEqual(result['public']['file']['full_file_sha256'], expected)

    def test_base_index_mapping_checked_against_every_shard_header(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / 'config.json').write_text('{"model_type":"toy"}')
            safetensors(base / 'model-1.safetensors', {'x.weight': ([2, 3], 'F32')})
            safetensors(base / 'model-2.safetensors', {'y.weight': ([3, 4], 'F32')})
            mapping = {'x.weight': 'model-1.safetensors', 'y.weight': 'model-2.safetensors'}
            (base / 'model.safetensors.index.json').write_text(json.dumps({'weight_map': mapping}))
            expected = {name: (base / name).stat().st_size for name in mapping.values()}
            with patch.object(m, 'BASE', base), patch.object(m, 'EXPECTED_SHARDS', expected):
                result = m.inspect_base(m.Budget())
                self.assertEqual(result['public']['shard_count'], 2)
                self.assertFalse(result['public']['base_full_weight_digest_verified'])
                mapping['x.weight'] = 'model-2.safetensors'
                mapping['y.weight'] = 'model-1.safetensors'
                (base / 'model.safetensors.index.json').write_text(json.dumps({'weight_map': mapping}))
                with self.assertRaisesRegex(m.AuditHold, 'INDEX_HEADER_MISMATCH'):
                    m.inspect_base(m.Budget())

    def test_provenance_mention_is_not_proof_and_private_text_not_emitted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'merge_PRIVATE_EXPERIENCE.json'
            value = {'merged_adapters': [{'sha256': 'a' * 64}], 'private_chat': 'PRIVATE_EXPERIENCE'}
            path.write_text(json.dumps(value))
            with patch.object(m, 'provenance_candidates', return_value=([path], False)):
                result = m.inspect_provenance([], {'a' * 64}, m.Budget())
            self.assertFalse(result['prior_merge_exclusion_proved'])
            self.assertEqual(result['records'][0]['declared_applied_adapter_digests'], ['a' * 64])
            self.assertNotIn('PRIVATE_EXPERIENCE', json.dumps(result))

    def test_duplicate_proposal_requires_drive_and_retains_standalone_ssd(self):
        def row(path, inode, links=1):
            return {'public': {'path': path, 'kind': 'existing_adapter', 'storage_class': 'ROOT_VOLUME',
                               'file': {'full_file_sha256_verified': True, 'full_file_sha256': 'a' * 64,
                                        'bytes': 100, 'stat_identity': [1, inode, 100, 0, 0], 'hardlinks': links}}}
        adapters = [row('/root/nox/a/adapter.safetensors', 1), row('/root/nox/b/adapter.safetensors', 2),
                    row('/root/nox/checkpoint-5/adapter.safetensors', 3)]
        unknown = m.duplicate_groups(adapters, {'verified_adapter_sha256s': []})[0]
        self.assertFalse(unknown['ssd_dedup_review_candidate'])
        proved = m.duplicate_groups(adapters, {'verified_adapter_sha256s': ['a' * 64]})[0]
        self.assertTrue(proved['ssd_dedup_review_candidate'])
        self.assertEqual(proved['maximum_reviewable_duplicate_bytes'], 100)
        self.assertFalse(proved['deletion_authorized_by_this_audit'])
        only_one_standalone = m.duplicate_groups([adapters[0], adapters[2]], {'verified_adapter_sha256s': ['a' * 64]})[0]
        self.assertFalse(only_one_standalone['ssd_dedup_review_candidate'])

    def test_drive_proof_requires_fresh_pinned_receipt_and_all_three_ram_hashes(self):
        targets = [value for value in m.TARGETS if value['kind'] == 'restored_drive']
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            scripts = root / 'scripts'
            scripts.mkdir()
            (scripts / 'owner_drive_ram_bridge.py').write_bytes((HERE / 'owner_drive_ram_bridge.py').read_bytes())
            path = root / 'receipt.json'
            receipt = {'schema': 'NOX_DRIVE_RAM_RECEIPT_V1', 'state': 'RAM_FILES_SHA_VERIFIED_NOT_MERGED',
                       'manifest_sha256': m.DRIVE_MANIFEST_SHA, 'private_urls_exported': False,
                       'weights_merged': False, 'request': '12345', 'source_sha': 'b' * 40,
                       'envelope_sha256': 'c' * 64, 'finished_at': time.time(),
                       'assets': [{'role': target['role'], 'filename': Path(target['path']).name,
                                   'bytes': target['expected_bytes'], 'sha256': target['expected_sha256'],
                                   'verified': True} for target in targets]}
            path.write_text(json.dumps(receipt))
            path.chmod(0o600)
            adapters = [{'public': {'id': target['id'], 'kind': 'restored_drive',
                                    'matches_approved_drive_sha256': True}} for target in targets]
            with patch.object(m, 'ROOT', root), patch.object(m, 'DRIVE_STATE', path):
                self.assertEqual(len(m.drive_proof(adapters)['verified_adapter_sha256s']), 3)
                adapters[0]['public']['matches_approved_drive_sha256'] = False
                self.assertEqual(m.drive_proof(adapters)['verified_adapter_sha256s'], [])
                adapters[0]['public']['matches_approved_drive_sha256'] = True
                receipt['finished_at'] = time.time() - 4000
                path.write_text(json.dumps(receipt))
                self.assertEqual(m.drive_proof(adapters)['verified_adapter_sha256s'], [])

    def test_fifo_and_deadline_are_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fifo'
            os.mkfifo(path)
            started = time.monotonic()
            with self.assertRaisesRegex(m.AuditHold, 'FILE_SCOPE'):
                with m.opened(path, 1024):
                    pass
            self.assertLess(time.monotonic() - started, .1)
        with self.assertRaisesRegex(m.AuditHold, 'DEADLINE'):
            m.Budget(seconds=-1).check()

    def test_read_only_source_has_no_native_mutation_or_tensor_loader(self):
        tree = ast.parse((HERE / 'owner_adapter_lineage_audit.py').read_text())
        forbidden = {'write_bytes', 'write_text', 'mkdir', 'unlink', 'remove', 'replace', 'rename',
                     'torch', 'torch_load', 'merge_and_unload', 'get_tensor'}
        methods = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertFalse(methods & forbidden)
        self.assertLess(m.MAX_SECONDS, 120)
        self.assertEqual(len(m.EXPECTED_SHARDS), 26)
        self.assertEqual(sum(m.EXPECTED_SHARDS.values()), 71903776776)


if __name__ == '__main__':
    unittest.main()
