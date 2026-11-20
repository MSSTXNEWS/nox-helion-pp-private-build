"""Hermetic owner-reclaim gate tests: never touch the host cgroup."""
import unittest
from unittest.mock import patch
from pathlib import Path
import owner_safe_cgroup_reclaim_oneshot as reclaim
import owner_native_operator as operator


class SafeCgroupReclaimTests(unittest.TestCase):
    def sample(self):
        stat = 'file '+str(175*reclaim.GIB)+'\n'
        stat += 'inactive_file '+str(86*reclaim.GIB)+'\n'
        stat += 'shmem '+str(70*reclaim.GIB)+'\n'
        stat += 'anon '+str(4*reclaim.GIB)+'\n'
        content = {
            'memory.current': str(179*reclaim.GIB),
            'memory.max': str(180*reclaim.GIB),
            'memory.stat': stat,
            'memory.events': 'low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\n',
            'memory.pressure': 'some avg10=0.00 avg60=0.00 avg300=0.00 total=0\n'
                               'full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n'
        }
        return content

    def test_exact_current_memory_counter_projection(self):
        data=self.sample()
        with patch.object(reclaim,'read_text',side_effect=lambda p,limit=8192:data[p.name]):
            observed=reclaim.cgroup_memory()
        self.assertEqual(observed['raw'], reclaim.GIB)
        self.assertEqual(observed['cold_lower_bound'], 16*reclaim.GIB)
        self.assertEqual(observed['psi'], {'some':0.0,'full':0.0})
        self.assertEqual(observed['events']['oom'],0)

    def test_oom_psi_raw_and_cold_fences_do_not_bypass(self):
        data=self.sample()
        with patch.object(reclaim,'read_text',side_effect=lambda p,limit=8192:data[p.name]):
            observed=reclaim.cgroup_memory()
        with patch.object(reclaim,'stopped',return_value=False), \
             patch.object(Path,'exists',return_value=True):
            reclaim.check(observed)
            # Emergency admission is limited to cold-cache-dominated cgroups;
            # 64 MiB free is accepted only when STOP/PSI/OOM and cold reserve pass.
            reclaim.check(dict(observed,raw=64*reclaim.MIB))
            for row,reason in [
                (dict(observed,raw=4), 'MEMORY_ADMISSION'),
                (dict(observed,raw=31*reclaim.MIB), 'MEMORY_ADMISSION'),
                (dict(observed,cold_lower_bound=11*reclaim.GIB), 'MEMORY_ADMISSION'),
                (dict(observed,cold_lower_bound=0), 'MEMORY_ADMISSION'),
                (dict(observed,psi={'some':0.12,'full':0.0}), 'PRESSURE'),
                (dict(observed,events={'oom':1,'oom_kill':0}), 'OOM'),
            ]:
                with self.subTest(reason=reason):
                    with self.assertRaisesRegex(RuntimeError,reason):
                        reclaim.check(row)
        with patch.object(reclaim,'stopped',return_value=True), \
             patch.object(Path,'exists',return_value=True):
            with self.assertRaisesRegex(RuntimeError,'STOP'):
                reclaim.check(observed)

    def test_malformed_cgroup_fails_closed(self):
        for name,value in [('memory.current','max'),
                           ('memory.pressure','some avg10=nan\nfull avg10=0.00\n'),
                           ('memory.events','oom oops\n')]:
            data=self.sample()
            data[name]=value
            with self.subTest(name=name):
                with patch.object(reclaim,'read_text',side_effect=lambda p,limit=8192:data[p.name]):
                    with self.assertRaisesRegex(RuntimeError,'HOLD_SAFE_CGROUP_'):
                        reclaim.cgroup_memory()

    def test_unknown_error_reports_only_bounded_reclaim_stage(self):
        previous = reclaim.STAGE
        try:
            reclaim.STAGE = 'RECLAIM_OPEN'
            error = reclaim.internal_hold(PermissionError('NOX2_PRIVATE_SENTINEL'))
            self.assertEqual(error, 'HOLD_SAFE_CGROUP_INTERNAL_RECLAIM_OPEN_PERMISSIONERROR')
            self.assertNotIn('PRIVATE', error)
            reclaim.STAGE = 'INVALID SECRET'
            self.assertEqual(reclaim.internal_hold(OSError('hidden path')),
                             'HOLD_SAFE_CGROUP_INTERNAL_UNKNOWN_OSERROR')
        finally:
            reclaim.STAGE = previous

    def test_repair_transport_is_narrow_and_not_persistent_default(self):
        self.assertEqual(operator.FILES['repair'],
                         'nox-control/owner_cold_file_cache_oneshot.py')
        self.assertEqual(operator.repair_bundle_paths('repair',
                         operator.FILES['repair'],('nox-control/unrelated_file.py',)),())
        self.assertNotEqual(operator.FILES['browser_qa'],operator.FILES['repair'])

    def test_no_destructive_process_or_global_reclaim_api(self):
        source=Path(reclaim.__file__).read_text()
        for forbidden in ('os.kill(', 'os.killpg(', 'memory.drop_caches',
                          '/proc/sys/vm/drop_caches', 'shutil.rmtree(', 'os.remove(',
                          'unlink(', 'terminate('):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden,source)


if __name__=='__main__':
    unittest.main()
