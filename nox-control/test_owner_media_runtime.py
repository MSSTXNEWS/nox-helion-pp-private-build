"""Media request, queue, GPU lease, output scope, and existing-auth tests."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('owner_media_runtime', Path(__file__).with_name('owner_media_runtime.py'))
media = importlib.util.module_from_spec(spec)
spec.loader.exec_module(media)


def fixture_job(kind='image'):
    return {'id': 'a' * 32, 'request': media.validate_request({'kind': kind, 'prompt': 'A public test scene'}),
            'owner': 'native-owner', 'state': 'QUEUED', 'outputs': [], 'generation_verified': False}


def fixture_assets():
    return {name: {'filename': name + '.safetensors'} for name in ('checkpoint', 'unet', 'clip', 'vae')}


class MediaTests(unittest.TestCase):
    def test_requests_reject_arbitrary_graphs_and_unbounded_work(self):
        for data in ({'kind': 'image', 'prompt': 'x', 'workflow': {}},
                     {'kind': 'video', 'prompt': 'x', 'frames': 1000},
                     {'kind': 'video', 'prompt': 'x', 'width': 1024, 'height': 1024},
                     {'kind': 'image', 'prompt': 'x', 'frames': 2},
                     {'kind': 'image', 'prompt': 'x', 'seed': True}):
            with self.assertRaises(media.MediaHold):
                media.validate_request(data)

    def test_fixed_workflows_match_checkpoint_schedules_and_real_video_output(self):
        image = media.workflow(fixture_job(), fixture_assets())
        self.assertEqual((image['3']['inputs']['steps'], image['3']['inputs']['cfg'], image['3']['inputs']['scheduler']), (4, 1.0, 'sgm_uniform'))
        self.assertEqual(image['9']['class_type'], 'SaveImage')
        video = media.workflow(fixture_job('video'), fixture_assets())
        self.assertEqual(video['47']['class_type'], 'SaveWEBM')
        self.assertEqual(video['47']['inputs']['codec'], 'vp9')
        self.assertEqual(video['40']['inputs']['length'], 17)
        self.assertEqual(video['48']['inputs']['shift'], 8.0)
        self.assertEqual(media.validate_request({'kind': 'video', 'prompt': 'x', 'width': 832, 'height': 480})['height'], 480)

    def test_live_node_inventory_must_offer_the_exact_model(self):
        graph = {'1': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': 'expected.safetensors'}}}
        objects = {'CheckpointLoaderSimple': {'input': {'required': {'ckpt_name': [['other.safetensors']]}}}}
        with self.assertRaisesRegex(media.MediaHold, 'MODEL_MISSING'):
            media.validate_graph(graph, objects)
        objects['CheckpointLoaderSimple']['input']['required']['ckpt_name'][0].append('expected.safetensors')
        media.validate_graph(graph, objects)

    def test_existing_training_gpu_lease_prevents_submission(self):
        with tempfile.TemporaryDirectory() as root, patch.object(media, 'ROOT', Path(root)):
            job = fixture_job(); media.atomic(media.job_path(job['id']), job)
            config = {'output_root': str(Path(root) / 'media/outputs')}
            with media.exclusive(Path(root) / 'state/forge_training.lock'), patch.object(media, 'configuration', return_value=config), patch.object(media, 'engine_identity'), patch.object(media, 'assets_for', return_value=fixture_assets()), patch.object(media, 'validate_graph'), patch.object(media, 'media_stop', return_value=False), patch.object(media, 'prepare_training', return_value={'active': False}), patch.object(media, 'wait_training'), patch.object(media, 'engine', return_value={}) as engine:
                outcome, details = media.run_media_task({'params': {'job_id': job['id']}})
            self.assertEqual(outcome, 'wait')
            self.assertEqual(details['state'], 'WAIT_RESOURCE_LEASE')
            self.assertFalse(any(call.args[0] == '/prompt' for call in engine.call_args_list))

    def test_stale_worker_update_cannot_erase_owner_cancel(self):
        with tempfile.TemporaryDirectory() as root, patch.object(media, 'ROOT', Path(root)):
            job = fixture_job(); media.atomic(media.job_path(job['id']), job)
            stale = copy.deepcopy(job)
            media.update_job(job, cancel_requested=True)
            media.update_job(stale, state='RUNNING')
            self.assertTrue(media.load_job(job['id'])['cancel_requested'])

    def test_pending_cancellation_deletes_only_owned_prompt_never_global_interrupt(self):
        with tempfile.TemporaryDirectory() as root, patch.object(media, 'ROOT', Path(root)):
            job = fixture_job(); job.update(prompt_id='owned-prompt-123456', cancel_requested=True)
            media.atomic(media.job_path(job['id']), job)
            with patch.object(media, 'media_stop', return_value=False), patch.object(media, 'queue_ids', return_value={'queue_pending': [job['prompt_id'], 'another-prompt'], 'queue_running': []}), patch.object(media, 'engine', return_value={}) as engine:
                state, outputs = media.poll_generation({}, job)
            self.assertEqual(state, 'CANCELLED')
            self.assertEqual(outputs, [])
            engine.assert_called_once_with('/queue', {'delete': [job['prompt_id']]})

    def test_output_cannot_escape_job_directory(self):
        with tempfile.TemporaryDirectory() as root:
            out = Path(root)
            job_id = 'a' * 32
            own = out / 'nox' / job_id; own.mkdir(parents=True)
            (own / 'image.png').write_bytes(b'image')
            config = {'output_root': str(out)}
            self.assertEqual(media.output_path(config, job_id, {'type': 'output', 'subfolder': 'nox/' + job_id, 'filename': 'image.png'}), own / 'image.png')
            for item in ({'type': 'output', 'subfolder': '../', 'filename': 'secret'},
                         {'type': 'output', 'subfolder': 'nox/' + job_id, 'filename': '../../secret'},
                         {'type': 'temp', 'subfolder': 'nox/' + job_id, 'filename': 'image.png'}):
                with self.assertRaises(media.MediaHold):
                    media.output_path(config, job_id, item)

    def test_queue_ingestion_is_idempotent_and_boost_only_admits_exact_media_jobs(self):
        with tempfile.TemporaryDirectory() as root, patch.object(media, 'ROOT', Path(root)), patch.object(media, 'media_stop', return_value=False):
            job = fixture_job(); media.atomic(media.job_path(job['id']), job)
            media.atomic(Path(root) / 'state/media/inbox' / (job['id'] + '.json'), {'job_id': job['id']})
            state = {'tasks': {}}
            self.assertEqual(media.ingest_media_tasks(state), 1)
            self.assertEqual(media.ingest_media_tasks(state), 0)
            task = next(iter(state['tasks'].values()))
            self.assertTrue(media.media_task_admitted(task))
            task['locks'] = ['gpu0']
            self.assertFalse(media.media_task_admitted(task))

    def test_owner_training_hold_is_never_removed(self):
        with tempfile.TemporaryDirectory() as root, patch.object(media, 'ROOT', Path(root)), patch.object(media, 'service_state', return_value={'state': 'STOPPED'}):
            hold = Path(root) / 'state/TRAIN_HOLD.flag'; hold.parent.mkdir(parents=True); hold.write_text('OWNER_MANUAL_HOLD')
            yielded = media.prepare_training(fixture_job())
            self.assertFalse(yielded['resume'])
            media.resume_training(fixture_job(), {}, yielded)
            self.assertEqual(hold.read_text(), 'OWNER_MANUAL_HOLD')

    def test_dispatcher_transform_checks_pin_and_composes_admission(self):
        source = 'def main():\n    pass\nif __name__ == "__main__":\n    main()\n'
        with self.assertRaises(media.MediaHold):
            media.patch_dispatcher_media(source, '0' * 64)
        transformed = media.patch_dispatcher_media(source, hashlib.sha256(source.encode()).hexdigest())
        self.assertIn(media.PATCH_MARKER, transformed)
        self.assertEqual(media.patch_dispatcher_media(transformed, '0' * 64), transformed)


class MediaAuthTests(unittest.TestCase):
    def application(self, authorized):
        from fastapi import FastAPI
        from starlette.responses import JSONResponse
        app = FastAPI()
        media.register_media(app, {'_session_ok': lambda request: authorized,
                                  '_unauthorized': lambda: JSONResponse({'error': 'AUTH_REQUIRED'}, status_code=401)})
        return app

    def test_existing_owner_auth_protects_every_media_surface(self):
        from fastapi.testclient import TestClient
        with TestClient(self.application(False)) as client, patch.object(media, 'capabilities') as engine:
            self.assertEqual(client.get('/api/ui/media').status_code, 401)
            self.assertEqual(client.post('/api/ui/media/jobs', json={'kind': 'image', 'prompt': 'x'}).status_code, 401)
            self.assertEqual(client.get('/api/ui/media/jobs/' + 'a' * 32).status_code, 401)
            self.assertEqual(client.get('/api/ui/media/jobs/' + 'a' * 32 + '/outputs/0').status_code, 401)
            self.assertEqual(client.post('/api/ui/media/jobs/' + 'a' * 32 + '/cancel').status_code, 401)
            engine.assert_not_called()

    def test_authenticated_cross_origin_generation_is_rejected(self):
        from fastapi.testclient import TestClient
        with TestClient(self.application(True)) as client, patch.object(media, 'create_job') as create:
            response = client.post('/api/ui/media/jobs', headers={'origin': 'https://unrelated.example'}, json={'kind': 'image', 'prompt': 'x'})
            self.assertEqual(response.status_code, 403)
            create.assert_not_called()

    def test_export_rejects_same_size_replacement_of_verified_asset(self):
        from fastapi.testclient import TestClient
        with tempfile.TemporaryDirectory() as root, patch.object(media, 'ROOT', Path(root)):
            job = fixture_job(); job.update(state='COMPLETED', generation_verified=True)
            out = Path(root) / 'outputs'; own = out / 'nox' / job['id']; own.mkdir(parents=True)
            original = b'\x89PNG\r\n\x1a\nverified-image-payload'
            target = own / 'image.png'; target.write_bytes(original)
            job['outputs'] = [{'filename': target.name, 'subfolder': 'nox/' + job['id'],
                               'type': 'output', 'bytes': len(original),
                               'sha256': hashlib.sha256(original).hexdigest(), 'media_type': 'image/png'}]
            media.atomic(media.job_path(job['id']), job)
            route = '/api/ui/media/jobs/' + job['id'] + '/outputs/0'
            with patch.object(media, 'configuration', return_value={'output_root': str(out)}), TestClient(self.application(True)) as client:
                before = client.get(route)
                self.assertEqual(before.status_code, 200)
                self.assertEqual(before.content, original)
                self.assertEqual(before.headers['content-type'], 'image/png')
                target.write_bytes(b'x' * len(original))
                after = client.get(route)
            self.assertEqual(after.status_code, 503)
            self.assertEqual(after.json()['reason'], 'HOLD_OUTPUT_CHANGED')

    def test_export_requires_verified_hash_and_kind_bound_mime(self):
        from fastapi.testclient import TestClient
        with tempfile.TemporaryDirectory() as root, patch.object(media, 'ROOT', Path(root)):
            job = fixture_job(); job.update(state='COMPLETED', generation_verified=True)
            out = Path(root) / 'outputs'; own = out / 'nox' / job['id']; own.mkdir(parents=True)
            raw = b'original'; target = own / 'image.png'; target.write_bytes(raw)
            item = {'filename': target.name, 'subfolder': 'nox/' + job['id'], 'type': 'output',
                    'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'media_type': 'image/png'}
            with patch.object(media, 'configuration', return_value={'output_root': str(out)}), TestClient(self.application(True)) as client:
                for change in ({'media_type': 'text/html'}, {'sha256': None}, {'sha256': 'invalid'}):
                    with self.subTest(change=change):
                        job['outputs'] = [{**item, **change}]
                        media.atomic(media.job_path(job['id']), job)
                        response = client.get('/api/ui/media/jobs/' + job['id'] + '/outputs/0')
                        self.assertEqual(response.status_code, 503)
                        self.assertEqual(response.json()['reason'], 'HOLD_OUTPUT_VERIFICATION_MISSING')


if __name__ == '__main__':
    unittest.main()
