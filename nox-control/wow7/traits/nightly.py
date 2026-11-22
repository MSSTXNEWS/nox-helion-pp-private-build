"""nightly: ночной цикл ползунков (вызывать из «сна», тихие часы). Порядок: traits.consolidate -> per.consolidate -> apply_to.
Состояние: NOX_TRAITS / NOX_PERSONALITY / NOX_DEVELOPMENT (по умолчанию /root/nox/state/*.json).
--dry-run: работает на копиях состояния во временной папке, ничего не меняет."""
import argparse
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import traits as T  # noqa: E402  (подтягивает PER в sys.path)
import development as D  # noqa: E402
import persona_rollback  # noqa: E402
import personality as P  # noqa: E402

ENV = (("NOX_TRAITS", "/root/nox/state/traits.json"), ("NOX_PERSONALITY", "/root/nox/state/personality.json"),
       ("NOX_DEVELOPMENT", "/root/nox/state/development.json"))


def _judge_step(paths, dry):
    """TRAITS-08: судья эпизодов (быстрая модель) -> observe/propose до консолидации. Нет эпизодов/модели - пропуск без ошибки. NOX_TRAITS_JUDGE=0 выключает."""
    if os.environ.get("NOX_TRAITS_JUDGE", "1") == "0":
        return {"status": "off"}
    try:
        import judge as J
        sp = os.path.join(os.path.dirname(paths["NOX_TRAITS"]), "traits_judge.json")
        return J.run(traits_path=paths["NOX_TRAITS"], state_path=sp, force=True)       # nightly сам вызывается из «сна» в тихие часы
    except Exception as ex:
        return {"status": "error", "error": str(ex)[:200]}


def run(dry=False):
    paths = {k: os.environ.get(k, d) for k, d in ENV}
    if dry:
        tmp = tempfile.mkdtemp(prefix="traits-dry-")
        for k, p in paths.items():
            q = os.path.join(tmp, os.path.basename(p))
            if os.path.exists(p):
                shutil.copy(p, q)
            paths[k] = q
    jrep = _judge_step(paths, dry)
    dev, per = D.Development(paths["NOX_DEVELOPMENT"]), P.Personality(paths["NOX_PERSONALITY"])
    tr = T.Traits(paths["NOX_TRAITS"])
    dev.apply_to(per)
    label = persona_rollback.snapshot_all(tr, per, "night-%d" % int(tr.clock()))      # общий снапшот TRAITS+PER: одна команда отката
    before = tr.signature()[1]
    rep = tr.consolidate(dev=dev, per=per)
    per_changes = per.consolidate()
    return {"dry_run": dry, "phase": dev.phase, "opened": rep["opened"], "trait_changes": len(rep["changes"]),
            "proposed_changes": rep["proposed"], "axes_synced": rep["synced"], "axis_changes": [c[0] for c in per_changes],
            "snapshot": label, "signature_changed": before != tr.signature()[1], "judge": jrep, "pending_cards": len([p for p in tr.proposals if p["status"] == "PENDING"])}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    print(json.dumps(run(ap.parse_args().dry_run), ensure_ascii=False))
