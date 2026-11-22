import json, os, subprocess, tempfile, unittest

D = os.path.dirname(os.path.abspath(__file__))
SH = os.path.join(D, "numa_tune.sh")


def tree(nodes=1, cpuset="0-26", cpu_max="2700000 100000", numa_bal="1", gov="powersave", thp_shmem="always [never]"):
    r = tempfile.mkdtemp()
    def w(p, v):
        p = os.path.join(r, p); os.makedirs(os.path.dirname(p), exist_ok=True); 
        with open(p, "w") as fh: fh.write(v)
    for n in range(nodes): os.makedirs(os.path.join(r, f"sys/devices/system/node/node{n}"))
    w("sys/fs/cgroup/cpuset.cpus.effective", cpuset + "\n"); w("sys/fs/cgroup/cpuset.mems.effective", "0\n")
    w("sys/fs/cgroup/cpu.max", cpu_max + "\n"); w("sys/fs/cgroup/memory.max", "818066137088\n")
    w("sys/kernel/mm/transparent_hugepage/enabled", "always [madvise] never\n")
    w("sys/kernel/mm/transparent_hugepage/shmem_enabled", thp_shmem + "\n")
    w("proc/sys/kernel/numa_balancing", numa_bal + "\n")
    w("sys/devices/system/cpu/cpu0/cpufreq/scaling_governor", gov + "\n")
    w("sys/devices/system/cpu/smt/active", "1\n")
    return r


def run(root, *args, uid=None):
    rc = tempfile.mkdtemp(); os.chmod(rc, 0o777)
    kw = {"preexec_fn": (lambda: os.setuid(uid))} if uid is not None else {}
    p = subprocess.run(["bash", SH, "--root", root, "--receipts-dir", rc, *args], capture_output=True, text=True, **kw)
    rec = os.path.join(rc, "OPT-06.json")
    if not os.path.exists(rec):
        return p, None
    with open(rec) as fh:
        return p, json.load(fh)


class T(unittest.TestCase):
    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", SH]).returncode, 0)

    def test_single_node_quota_dry_run_no_writes(self):
        r = tree(); p, j = run(r)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(j["numa_nodes"], 1); self.assertEqual(j["vcpu_effective"], 27); self.assertEqual(j["vcpu_quota"], 27)
        self.assertEqual(j["recommend"]["threads_t"], 25); self.assertEqual(j["recommend"]["prefix"], "")
        self.assertEqual(j["mode"], "dry-run"); self.assertEqual(j["applied"], [])
        self.assertEqual(open(os.path.join(r, "proc/sys/kernel/numa_balancing")).read().strip(), "1")
        self.assertIn("1 узел NUMA", j["notes"]); self.assertIn("THP shmem=never", j["notes"])

    def test_quota_lower_than_cpuset(self):
        _, j = run(tree(cpuset="0-63", cpu_max="1600000 100000"))
        self.assertEqual(j["vcpu_effective"], 16); self.assertEqual(j["recommend"]["threads_t"], 14)

    def test_cpuset_list_parsing_and_quota_max(self):
        _, j = run(tree(cpuset="0-3,8,10-11", cpu_max="max 100000"))
        self.assertEqual(j["vcpu_effective"], 7); self.assertEqual(j["vcpu_quota"], 0)

    def test_two_nodes_recommend_numa_flag(self):
        _, j = run(tree(nodes=2))
        self.assertEqual(j["numa_nodes"], 2); self.assertEqual(j["recommend"]["numa_flag"], "--numa distribute")

    def test_apply_writes_only_writable_and_reports(self):
        r = tree(); p, j = run(r, "--apply")
        self.assertEqual(j["mode"], "apply")
        self.assertEqual(open(os.path.join(r, "proc/sys/kernel/numa_balancing")).read(), "0")
        self.assertEqual(open(os.path.join(r, "sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")).read(), "performance")
        self.assertEqual(sorted(j["applied"]), ["governor_cpu0", "numa_balancing"])

    def test_apply_without_permission_skips(self):
        r = tree()
        subprocess.run(["chmod", "-R", "a+rX", r], check=True)  # файлы 644 у root: чужой uid читает, но не пишет
        subprocess.run(["chmod", "a+rx", os.path.dirname(r)], check=True)
        uid = 65534 if os.geteuid() == 0 else None
        _, j = run(r, "--apply", uid=uid)
        self.assertIsNotNone(j)
        self.assertNotIn("numa_balancing", j["applied"]); self.assertIn("нет прав", j["notes"])
        self.assertEqual(open(os.path.join(r, "proc/sys/kernel/numa_balancing")).read().strip(), "1")

    def test_empty_root_still_writes_valid_receipt(self):
        p, j = run(tempfile.mkdtemp())
        self.assertEqual(p.returncode, 0); self.assertIsNotNone(j); self.assertEqual(j["numa_nodes"], 0)
        self.assertGreaterEqual(j["vcpu_effective"], 1)

    def test_bad_arg(self):
        self.assertEqual(subprocess.run(["bash", SH, "--wat"], capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
