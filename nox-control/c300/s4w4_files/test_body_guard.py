import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import body_guard as B
T = 49152.0
F = {n: "/x/%s" % n for n in B.ORDER}
def G(others_gb, body_gb=21.6): return {"total_mib": T, "used_mib": (others_gb + body_gb) * 1024, "body_pid": 1, "body_mib": body_gb * 1024}
def ch(others, **kw): return B.decide(G(others), files=F, peaks={}, **kw)["choice"]
def test_all_free_picks_first(): assert ch(9.2) == "p5_best"
def test_p5_best_does_not_fit_falls_to_ncmoe0(): assert ch(21.0) == "gpu_ncmoe0"   # 21+21.6+1=43.6<=45.2; p5_best 22.8+22=45.8>45.2
def test_training_holds_vram_falls_to_ncmoe22(): assert ch(30.0) == "liska_ncmoe22"   # 30+11.6+1=42.6
def test_heavy_training_ncmoe36(): assert ch(37.0) == "dpo_ncmoe36"
def test_nothing_fits(): assert ch(40.0) is None
def test_body_memory_not_counted_as_others(): assert B.decide(G(9.2, 21.6), files=F, peaks={})["others_gb"] == 9.2
def test_missing_files_skipped(): assert B.decide(G(9.2), files={"gpu_ncmoe0": "/x"}, peaks={})["choice"] == "gpu_ncmoe0"
def test_start_skips_earlier(): assert ch(9.2, start="liska_ncmoe22") == "liska_ncmoe22"
def test_measured_peak_overrides_seed(): assert B.decide(G(9.2), files=F, peaks={"p5_best": 40.0})["choice"] == "gpu_ncmoe0"
def test_unknown_cmd_estimate_monotonic():
    a = B.peak_gb("zz", "--n-cpu-moe 0 -c 1", {}); b = B.peak_gb("zz", "--n-cpu-moe 36 -c 1", {}); assert a > b > 5
def test_incident_scenario():   # чат лежал: рестарт ncmoe0 при 30+ ГБ чужих не должен выбираться
    assert ch(31.0) != "gpu_ncmoe0" and ch(31.0) != "p5_best"
def test_lock_exclusive(tmp_path, monkeypatch):
    import fcntl
    monkeypatch.setattr(B, "ST", str(tmp_path)); monkeypatch.setattr(B, "LOCKF", str(tmp_path / "l")); monkeypatch.setattr(B, "LOG", str(tmp_path / "log")); monkeypatch.setattr(B, "ALERTS", str(tmp_path / "al"))
    h = open(tmp_path / "l", "w"); fcntl.flock(h.fileno(), fcntl.LOCK_EX)
    assert B.main(["--reason", "t"]) == 4 and "busy" in open(tmp_path / "al").read()

def test_fits_file(tmp_path):
    f = tmp_path / "donor_hybrid.cmd.gpu_ncmoe0"; f.write_text("-ngl 99\n--n-cpu-moe 0\n-c 32768\n")
    assert B.fits_file(str(f), G(9.2), {})[0] is True and B.fits_file(str(f), G(31.0), {})[0] is False
    g2 = tmp_path / "donor_gpu.cmd"; g2.write_text("-ngl 99\n-c 49152\n--parallel 10\n"); assert B.fits_file(str(g2), G(9.2), {})[0] is True and B.fits_file(str(g2), G(21.5), {})[0] is False
