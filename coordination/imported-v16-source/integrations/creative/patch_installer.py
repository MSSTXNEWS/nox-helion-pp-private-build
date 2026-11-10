"""Stage the compiled Creative child and canonical helpers in a disposable builder.

Only the CI copy is changed; original R13/OneHost sources and D02 assets stay
unchanged. A relocated builder must use the owning checkout, not copy siblings.
"""
from pathlib import Path
import sys


_REPOSITORY_ANCHOR = "$e06RepoRoot=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path"
_REPOSITORY_STAGE = """# Creative runs a disposable copy below work/e06; keep the original owner.
# Resolve from the script, never the caller CWD, and guard the ENTIRE checkout.
Assert-E06PlainPathAncestors -Candidate $PSScriptRoot -Scope 'BUILDER'
$e06RepoRoot=((& git -C $PSScriptRoot rev-parse --show-toplevel) | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($e06RepoRoot)) {
  throw 'E06_SOURCE_ROOT_UNAVAILABLE'
}
Assert-E06PlainPathAncestors -Candidate $e06RepoRoot -Scope 'REPOSITORY'
$e06RepoRoot=(Resolve-Path -LiteralPath $e06RepoRoot).Path
$e06OwnerRoot=Join-Path $e06RepoRoot 'coordination/e06'
Assert-E06PlainPathAncestors -Candidate $e06OwnerRoot -Scope 'OWNER_SCRIPTS'"""
_MANIFEST_ANCHOR = '# Include the existing program files in the conservative NSIS manifest.'


def stage_builder(text: str, source: Path) -> str:
    """Validate all inherited anchors before returning a single complete change."""
    replacements = [(_REPOSITORY_ANCHOR, _REPOSITORY_STAGE)]
    for name in ('verify_native_receipt_json.py', 'l01_manifest_bridge.py'):
        replacements.append((f"Join-Path $PSScriptRoot '{name}'",
                             f"Join-Path $e06OwnerRoot '{name}'"))
    for old, _ in replacements:
        if text.count(old) != 1:
            raise ValueError('HOLD: R13 builder owner path anchor drift')
    if text.count(_MANIFEST_ANCHOR) != 1 or 'CREATIVE_PAYLOAD_MISSING_HOLD' in text:
        raise ValueError('HOLD: R13 builder manifest anchor drift or already staged')
    # Canonical helper byte pins, strict JSON admission and both dirty-checkout
    # guards are deliberately untouched. Never fall back to a copy-side helper.
    for old, new in replacements:
        text = text.replace(old, new, 1)
    quoted_source = "'" + str(source).replace("'", "''") + "'"
    insert = """# Stage trusted sidecar worker as an on-demand child of the ONE visible WPF host.
$creativeWorkerDir=""" + quoted_source + """
$creativeTarget=Join-Path $payload 'Backend/Creative'
if (Test-Path -LiteralPath $creativeTarget) {throw 'CREATIVE_PAYLOAD_OVERWRITE_HOLD'}
Copy-Item -LiteralPath $creativeWorkerDir -Destination $creativeTarget -Recurse
if (!(Test-Path -LiteralPath (Join-Path $creativeTarget 'NOX_CreativeWorker.exe') -PathType Leaf)) {throw 'CREATIVE_PAYLOAD_MISSING_HOLD'}
"""
    return text.replace(_MANIFEST_ANCHOR, insert + _MANIFEST_ANCHOR, 1)


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        raise SystemExit('USAGE patch_installer.py R13_BUILDER WORKER_DIR')
    target = Path(args[0])
    source = Path(args[1]).resolve()
    if not source.is_dir() or not (source / 'NOX_CreativeWorker.exe').is_file():
        raise SystemExit('CREATIVE_WORKER_EXE_NOT_BUILT')
    try:
        updated = stage_builder(target.read_text(encoding='utf-8-sig'), source)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    target.write_text(updated, encoding='utf-8')
    print('CREATIVE_NSIS_PAYLOAD_PATCH_STAGED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
