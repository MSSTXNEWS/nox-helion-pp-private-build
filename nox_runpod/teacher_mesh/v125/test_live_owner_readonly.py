"""V125 local source-only regression. Fixtures never touch Vast or real S03."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from nox_runpod.teacher_mesh.v125 import live_owner_readonly as live


class SensorParsers(unittest.TestCase):
    def test_procstat_cpu_and_meminfo(self):
        self.assertEqual((190,40),live._stat('cpu  40 30 30 35 5 20 20 10 0 0\n'))
        self.assertAlmostEqual(live._mem('MemTotal: 8388608 kB\nMemAvailable: 2097152 kB\n')['percent'],75)
        with self.assertRaisesRegex(RuntimeError,'HOLD_PROCFS_MEM_SOURCE'):
            live._mem('MemTotal: 10000 kB\nMemAvailable: 20000 kB\n')
        with self.assertRaisesRegex(RuntimeError,'HOLD_PROCFS_CPU_SOURCE'):
            live._stat('notcpu 1 2 3')
    def test_two_actual_gpu_rows(self):
        rows=live._gpu_rows('0, 34, 32768, 1024, 52\n1, 66, 32768, 2048, 64\n')
        self.assertEqual([0,1],[x['index'] for x in rows])
        self.assertEqual(64,rows[1]['gpu_core_temp_c'])
        with self.assertRaisesRegex(RuntimeError,'HOLD_GPU_SAMPLE_RANGE'):
            live._gpu_rows('0, 110, 32768, 1024, 52\n')
        with self.assertRaisesRegex(RuntimeError,'HOLD_GPU_SAMPLE_COUNT'):
            live._gpu_rows('0, 34, 32768, 1024, 52\n0, 34, 32768, 1024, 52\n')
    def test_status_only_real_sources_and_no_fake_hotspot(self):
        def stat(_):
            stat.calls+=1
            return (1000,300) if stat.calls==1 else (1200,350)
        stat.calls=0
        with patch.object(live,'_stat',side_effect=stat),\
             patch.object(live,'_mem',return_value={'total_gib':16,'used_gib':7,'percent':43.75}),\
             patch.object(live,'_gpu_rows',return_value=[
                 {'index':0,'gpu_percent':30,'vram_total_gib':32,'vram_used_gib':2,'gpu_core_temp_c':55}]),\
             patch.object(live.Path,'read_text',return_value='ignore'),\
             patch.object(live.time,'sleep',return_value=None),\
             patch.object(live.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='0,30,32768,2048,55')):
            result=live._status()
        self.assertEqual(result['gpu_percent'],30)
        self.assertEqual(result['system']['cpu_usage_pct'],75)
        self.assertIsNone(result['gpu_hotspot_c'])
        self.assertIs(result['physical_windows_pc_verified'],False)
        self.assertEqual(result['scope'],'VAST_ONEHOST_SERVER_NOT_OWNER_WINDOWS_PC')


class AuthenticatedRoutes(unittest.TestCase):
    def setUp(self):
        self.app=FastAPI()
        live.register_nox_v125_live_readonly(
            self.app,{'_session_ok':lambda req:req.cookies.get('owner')=='valid',
                      '_unauthorized':lambda:JSONResponse({'error':'NO_OWNER_COOKIE'},status_code=401)})
        self.client=TestClient(self.app)
    def test_all_five_routes_deny_anonymous(self):
        for path in live._ROUTES:
            self.assertEqual(self.client.get(path).status_code,401,path)
    def test_metrics_and_source_scope_for_authenticated_owner(self):
        payload={'status':'READY','system':{'cpu_usage_pct':20},
                 'scope':'VAST_ONEHOST_SERVER_NOT_OWNER_WINDOWS_PC'}
        with patch.object(live,'_status',return_value=payload):
            resp=self.client.get('/api/status',cookies={'owner':'valid'})
        self.assertEqual(resp.status_code,200)
        self.assertEqual(resp.json()['scope'],payload['scope'])
        self.assertEqual(resp.headers.get('Cache-Control'),'no-store')
    def test_fail_closed_on_missing_gpu_sensor(self):
        with patch.object(live,'_status',side_effect=RuntimeError('HOLD_NATIVE_NVIDIA_SMI')):
            resp=self.client.get('/api/status',cookies={'owner':'valid'})
        self.assertEqual(resp.status_code,503)
        self.assertEqual(resp.json()['reason'],'HOLD_NATIVE_NVIDIA_SMI')
    def test_existing_route_collision_refused(self):
        with self.assertRaisesRegex(RuntimeError,'HOLD_V125_CONFLICT_EXISTING_ENDPOINT'):
            live.register_nox_v125_live_readonly(self.app,{'_session_ok':lambda _:True,
                                                            '_unauthorized':lambda:None})
    def test_real_capability_contract_cannot_claim_training(self):
        result=live._capabilities(self.app)
        self.assertFalse(result['all_web_features_verified'])
        self.assertFalse(result['features']['training']['full_weight_optimizer_verified'])
        self.assertEqual(result['schema'],'NOX_NATIVE_CONTROLLER_V2')
    def test_training_is_actual_read_only_supervisor_adapter(self):
        import sys
        stub=SimpleNamespace(_training_state=lambda:{'status':'HOLD_CHECKPOINT_NOT_VERIFIED','supervisor_state':'EXITED'})
        with patch.dict(sys.modules,{'nox_v118_real_read_surfaces':stub}):
            result=live._trainer()
        self.assertEqual(result['supervisor_state'],'EXITED')
        self.assertFalse(result['verified_live'])


if __name__=='__main__':
    unittest.main()
