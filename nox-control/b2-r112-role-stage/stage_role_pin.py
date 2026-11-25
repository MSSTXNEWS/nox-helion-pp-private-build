"""Add the tested B2 role-pin wrapper after the existing R112 verdict stage."""
import hashlib
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / 'b2-r112/candidate.cjs'
CANDIDATE = '8af0944cb5dcc33b9f1433c2dd9b80fcddb50ebf'
VERDICT = '727600ede64523c899680dec84f2edc1ec4d2d2e'
REL = Path('nox-control/b2-r112')


def blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def exact(path, pin):
    if path.resolve() != path or not path.is_file():
        raise ValueError('HOLD_ROLE_PIN_PATH:' + str(path))
    raw = path.read_bytes()
    if blob(raw) != pin:
        raise ValueError('HOLD_ROLE_PIN_DIGEST:' + str(path))
    return raw


def stage_role_pin(root):
    # Offline single-writer extraction only; stage_verdict must already have run.
    root = Path(root).absolute()
    if root.resolve(strict=True) != root or not root.is_dir():
        raise ValueError('HOLD_ROLE_PIN_ROOT')
    exact(root / REL / 'verdict_consistency.cjs', VERDICT)
    raw = exact(SOURCE, CANDIDATE)
    dst = root / REL / 'candidate.cjs'
    if dst.resolve() != dst or dst.exists():
        raise ValueError('HOLD_ROLE_PIN_OVERWRITE')
    with dst.open('xb') as stream:
        stream.write(raw)
    return dst
