"""T06 Windows diagnostic OneHost candidate, reuse exact P01 owner NSIS.

Needs the already SHA+framed-IPC verified Python EXE job and original R11
staged sources. No second frontend, backend, RAG, or changed originals.
This is NOT E07 acceptance; user installation data must remain untouched.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import re
import stat

EXPECTED_ZIP_SHA="90076eba83a213ba2b410632ced3288d41a6691ab63f81ad0520aa3cbbbfcb52"
VALIDATED_OLD_PYTHON_SHA="4e488372cf3f6410d268a7ef72b3e4b359a7a3e6642c7a16ac2e6f7eb06fc5f3"
def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as stream:
        while chunk:=stream.read(1024*1024):h.update(chunk)
    return h.hexdigest()
def need(ok,msg):
    if not ok:raise RuntimeError(msg)

def verify_source_tree_entry(path, root):
    """Reject unmanifested directory junctions before a directory can be skipped.

    Every component inside the disposable owner root must be a real directory;
    the leaf must be a regular file or directory, never a reparse point.
    """
    path, root = Path(path), Path(root)
    try:
        components = path.relative_to(root).parts
    except ValueError as exc:
        raise RuntimeError("T06_PAYLOAD_PATH_OUTSIDE_TRUSTED_ROOT") from exc
    nodes = [root]
    for component in components:
        nodes.append(nodes[-1] / component)
    for index, node in enumerate(nodes):
        try:
            info = node.lstat()
        except OSError as exc:
            raise RuntimeError("T06_PAYLOAD_PATH_MISSING_OR_UNREADABLE") from exc
        need(not node.is_symlink() and
             not getattr(node, "is_junction", lambda: False)() and
             not (getattr(info, "st_file_attributes", 0) &
                  getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)),
             "T06_PAYLOAD_PATH_REPARSE_HOLD")
        need(stat.S_ISDIR(info.st_mode) if index < len(nodes) - 1 else
             (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)),
             "T06_PAYLOAD_NONREGULAR_COMPONENT_HOLD")

def attest_nsis_compiler_unchanged(compiler, expected_sha):
    """Reject replaced/reparsed compiler before and after NSIS execution.

    This detects local substitutions, NOT vendor signature/license approval.
    """
    binary=Path(compiler)
    need(type(expected_sha) is str and
         re.fullmatch(r"[0-9a-f]{64}",expected_sha) is not None,
         'T06_NSIS313_COMPILER_SHA_PIN_INVALID')
    need(binary.is_file() and not binary.is_symlink() and
         not getattr(binary,'is_junction',lambda:False)(),
         'T06_NSIS313_COMPILER_REPARSE_HOLD')
    for ancestor in binary.parents:
        need(not ancestor.is_symlink() and
             not getattr(ancestor,'is_junction',lambda:False)(),
             'T06_NSIS313_COMPILER_REPARSE_HOLD')
    need(sha(binary)==expected_sha,
         'T06_NSIS313_COMPILER_CHANGED_SINCE_PREFLIGHT')


def preflight_nsis_compiler(lookup=None, runner=None, candidates=None):
    """Only reuse an existing NSIS 3.13 compiler; never install tooling in a build."""
    lookup=lookup or shutil.which
    runner=runner or subprocess.run
    on_path=lookup('makensis.exe')
    locations=([Path(on_path)] if on_path else [])
    locations.extend(candidates if candidates is not None else (
        Path('C:/Program Files (x86)/NSIS/makensis.exe'),
        Path('C:/Program Files/NSIS/makensis.exe')))
    compiler=next((p for p in locations if p.exists() or p.is_symlink()),None)
    need(compiler is not None and compiler.is_file() and not compiler.is_symlink() and
         not getattr(compiler,'is_junction',lambda:False)(),
         'T06_NSIS313_PREINSTALLED_COMPILER_REQUIRED_NO_NETWORK')
    for ancestor in compiler.parents:
        need(not ancestor.is_symlink() and
             not getattr(ancestor,'is_junction',lambda:False)(),
             'T06_NSIS313_COMPILER_REPARSE_HOLD')
    try:
        probe=runner([str(compiler),'/VERSION'],capture_output=True,
                     text=True,timeout=20)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise RuntimeError('T06_NSIS313_VERSION_PROBE_FAILED') from exc
    need(probe.returncode==0,'T06_NSIS313_VERSION_PROBE_FAILED')
    need(re.fullmatch(r'v?3\.13',probe.stdout.strip(),flags=re.I) is not None,
         'T06_NSIS313_EXACT_VERSION_REQUIRED')
    binary_sha=sha(compiler)
    attest_nsis_compiler_unchanged(compiler,binary_sha)
    print('T06_PREINSTALLED_NSIS313_OFFLINE_SHA256',binary_sha,flush=True)
    return str(compiler),binary_sha

def verify_nsis_setup(setup: Path) -> dict:
    """Reject redirected or stale PE output; hash the SAME admitted file handle."""
    need(setup.is_file() and not setup.is_symlink(),
         "T06_NSIS_SETUP_MISSING_OR_REDIRECTED")
    need(not getattr(setup, "is_junction", lambda: False)(),
         "T06_NSIS_SETUP_REPARSE_ANCESTOR_HOLD")
    for ancestor in setup.parents:
        need(not ancestor.is_symlink() and
             not getattr(ancestor, "is_junction", lambda: False)(),
             "T06_NSIS_SETUP_REPARSE_ANCESTOR_HOLD")
    initial=setup.stat()
    need(initial.st_size>=1024*1024,"T06_NSIS_SETUP_TOO_SMALL_OR_TRUNCATED")
    with setup.open("rb") as stream:
        opened=os.fstat(stream.fileno())
        need((opened.st_dev,opened.st_ino,opened.st_size)==
             (initial.st_dev,initial.st_ino,initial.st_size),
             "T06_NSIS_SETUP_REPLACED_BEFORE_OPEN")
        size=opened.st_size
        dos=stream.read(64)
        need(len(dos)==64 and dos[:2]==b"MZ","T06_NSIS_SETUP_NOT_WINDOWS_PE")
        pe_offset=int.from_bytes(dos[60:64],"little")
        need(64<=pe_offset<=min(size-4,1024*1024),
             "T06_NSIS_SETUP_PE_OFFSET_INVALID")
        stream.seek(pe_offset)
        need(stream.read(4)==b"PE\x00\x00","T06_NSIS_SETUP_PE_SIGNATURE_INVALID")
        stream.seek(0)
        digest=hashlib.sha256()
        total=0
        while chunk:=stream.read(1024*1024):
            digest.update(chunk)
            total+=len(chunk)
        after_fd=os.fstat(stream.fileno())
    final=setup.stat()
    # On CPython 3.12 Windows, stat(path).st_ctime_ns can denote creation
    # while fstat(descriptor).st_ctime_ns can reflect metadata-change time.
    # Bind the SAME physical file by device/inode, size, mtime and birthtime
    # across both APIs, and enforce unchanged ctime within each API pair.
    # POSIX retains the original strict four-way ctime comparison.
    identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
    same_identity=(identity(initial)==identity(opened)==
                   identity(after_fd)==identity(final))
    if os.name=="nt":
        births=[getattr(s,"st_birthtime_ns",None)
                for s in (initial,opened,after_fd,final)]
        time_ok=(all(type(value) is int for value in births) and
                 len(set(births))==1 and
                 initial.st_ctime_ns==final.st_ctime_ns and
                 opened.st_ctime_ns==after_fd.st_ctime_ns)
    else:
        time_ok=(initial.st_ctime_ns==opened.st_ctime_ns==
                 after_fd.st_ctime_ns==final.st_ctime_ns)
    need(not setup.is_symlink() and total==size and same_identity and time_ok,
         "T06_NSIS_SETUP_CHANGED_DURING_VERIFY")
    return {"bytes":total,"sha256":digest.hexdigest()}

def download_artifact(relative,target):
    """Transfer same-job candidate bytes locally, never via GitLab artifact HTTP.

    Both source paths are fixed owner outputs. The receipt and binary hash are
    validated again below, prior to modifying any WPF or NSIS source.
    """
    expected={
        "work/t06-manual-source-inspect/python-exe-candidate/NATIVE_PYTHON_EXE_CANDIDATE_RECEIPT.json",
        "work/t06-manual-source-inspect/python-exe-candidate/NOX_HELION_PRIVATE_CANDIDATE.exe",
    }
    need(relative in expected,"T06_LOCAL_ARTIFACT_UNEXPECTED_PATH")
    origin=Path(__file__).resolve().parents[2]/relative
    need(origin.is_file() and not origin.is_symlink() and
         origin.resolve(strict=True).is_relative_to(Path(__file__).resolve().parents[2]),
         "T06_LOCAL_ARTIFACT_NOT_VERIFIED_OR_REDIRECTED")
    need(not target.exists() and not target.is_symlink(),
         "T06_LOCAL_DESTINATION_COLLISION")
    with origin.open("rb") as stream,target.open("xb") as dest:
        while chunk:=stream.read(1024*1024):
            dest.write(chunk)
    need(sha(origin)==sha(target),"T06_LOCAL_ARTIFACT_COPY_SHA_HOLD")


# Exact reviewed original P01 installed-file verifier, not a new backend/installer.
# Original ZIP729 remains immutable. Only the disposable R11 Installer copy changes.
P01_INSTALLED_VERIFIER_GIT_BLOB = "2fe86cad7e96eaf1a67354dfce3cf3f96dd33dfa"
# The immutable original R11/C07 installer verifier, evidenced by E06 physical staging.
# GitLab and GitHub E06 must admit the SAME exact archived preimage before C09.
P01_ARCHIVED_VERIFIER_SHA256 = "e741c131ddc1af45391ed64b4cdce686895aa78bd67e6bd4795fa97f548d455b"

def _git_blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode("ascii")+b"\0"+raw).hexdigest()

def stage_reviewed_installed_payload_verifier(owner_script, reviewed_script):
    """Bind the approved C09 verifier to both existing NSIS and installed smoke.

    The verified ZIP may contain an older Verify-Payload without the explicit
    -AllowInstalledMetadata contract. Never edit that ZIP or a live installation.
    Reject unknown legacy preimages, changed C09 source, and redirected paths.
    """
    for item in (owner_script, *owner_script.parents,
                 reviewed_script, *reviewed_script.parents):
        need(not item.is_symlink() and
             not getattr(item, "is_junction", lambda: False)(),
             "T06_P01_VERIFY_PATH_REPARSE_HOLD")
    need(owner_script.is_file() and reviewed_script.is_file() and
         owner_script.parent.name == "Installer" and
         512 <= owner_script.stat().st_size <= 262144 and
         512 <= reviewed_script.stat().st_size <= 262144,
         "T06_P01_VERIFY_ORIGINAL_OR_REVIEWED_SOURCE_HOLD")
    original = owner_script.read_bytes()
    approved_raw = reviewed_script.read_bytes()
    need(b"\r" not in approved_raw.replace(b"\r\n", b""),
         "T06_P01_VERIFY_REVIEWED_LINE_ENDINGS_HOLD")
    canonical = approved_raw.replace(b"\r\n", b"\n")
    need(_git_blob(canonical) == P01_INSTALLED_VERIFIER_GIT_BLOB,
         "T06_P01_VERIFY_APPROVED_GIT_BLOB_HOLD")
    try:
        old_text = original.decode("utf-8-sig")
        approved_text = canonical.decode("utf-8-sig")
    except UnicodeError as exc:
        raise RuntimeError("T06_P01_VERIFY_ENCODING_HOLD") from exc
    need(all(mark in old_text for mark in (
         "P01_PAYLOAD_VERIFY_FAILED", "payload.sha256.json", "SHA256")),
         "T06_P01_VERIFY_ARCHIVED_SOURCE_UNRECOGNIZED_HOLD")
    need(all(mark in approved_text for mark in (
         "[switch]$AllowInstalledMetadata", "Assert-P01UniqueManifestMembers",
         "P01_PAYLOAD_VERIFY_FAILED", "Get-FileHash", "nox-p01-owned.txt",
         "Uninstall.exe", "P01_PAYLOAD_SHA256_PASS")),
         "T06_P01_VERIFY_APPROVED_POLICY_INCOMPLETE_HOLD")
    changed = original != canonical
    if changed:
        # Unknown R11 bytes cannot be overwritten just because marker text matches.
        # The approved C09 verifier is permitted without an archived preimage only
        # when it is already the exact canonical Git-blob-pinned content.
        need(hashlib.sha256(original).hexdigest() == P01_ARCHIVED_VERIFIER_SHA256,
             "T06_P01_VERIFY_ARCHIVE_PREIMAGE_SHA_HOLD")
        owner_script.write_bytes(canonical)
    need(_git_blob(owner_script.read_bytes()) == P01_INSTALLED_VERIFIER_GIT_BLOB,
         "T06_P01_VERIFY_STAGED_READBACK_HOLD")
    return {"reviewed_git_blob": P01_INSTALLED_VERIFIER_GIT_BLOB,
            "changed_disposable_R11": changed,
            "installed_metadata_switch_pinned": True,
            "release_accepted": False}


def stage_reviewed_ps51_sha_compat(owner_script: Path) -> dict:
    """Keep C09 verification identical under the original NSIS PowerShell 5.1.

    The immutable approved C09 source remains in Git. The active NSIS /S invokes
    powershell.exe (not pwsh.exe); the separate original OneHost build route
    already uses this same .NET SHA-256 helper for that host. Only a disposable
    C07 staged copy can be transformed, after its exact approved Git blob is
    independently verified. Unknown bytes fail without being overwritten.
    """
    need(owner_script.name == "Verify-Payload.ps1" and
         owner_script.parent.name == "Installer" and
         all(not part.is_symlink() and
             not getattr(part, "is_junction", lambda: False)()
             for part in (owner_script, *owner_script.parents)),
         "T06_PS51_VERIFIER_UNSAFE_PATH_HOLD")
    before = owner_script.read_bytes()
    need(_git_blob(before) == P01_INSTALLED_VERIFIER_GIT_BLOB,
         "T06_PS51_VERIFIER_UNAPPROVED_PREIMAGE_HOLD")
    text = before.decode("utf-8-sig")
    old_header = "$ErrorActionPreference = 'Stop'"
    old_hash = "  $actual = (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant()"
    need(text.count(old_header) == 1 and text.count(old_hash) == 1 and
         "Get-P01VerifiedSha256" not in text and
         all(marker in text for marker in (
             "Assert-P01UniqueManifestMembers", "Assert-NoReparseAncestors",
             "P01_PAYLOAD_VERIFY_FAILED", "sha mismatch", "Uninstall.exe")),
         "T06_PS51_VERIFIER_CONTRACT_PREIMAGE_HOLD")
    helper = """function Get-P01VerifiedSha256([string]$Path) {
  $inputStream=$null
  $digest=$null
  try {
    $inputStream=[IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    $digest=[Security.Cryptography.SHA256]::Create()
    return ([BitConverter]::ToString($digest.ComputeHash($inputStream))).Replace('-','').ToLowerInvariant()
  } finally {
    if ($null -ne $digest) { $digest.Dispose() }
    if ($null -ne $inputStream) { $inputStream.Dispose() }
  }
}
"""
    eol = "\r\n" if "\r\n" in text else "\n"
    helper = helper.replace("\n", eol)
    updated = text.replace(old_header, old_header + eol + helper + eol).replace(
        old_hash, "  $actual = Get-P01VerifiedSha256 $full")
    changed = updated.encode("utf-8")
    need(changed != before and updated.count("Get-P01VerifiedSha256") == 2 and
         old_hash not in updated and "Get-FileHash" not in updated,
         "T06_PS51_VERIFIER_TRANSFORM_HOLD")
    owner_script.write_bytes(changed)
    need(owner_script.read_bytes() == changed,
         "T06_PS51_VERIFIER_STAGED_READBACK_HOLD")
    return {"approved_preimage_git_blob": P01_INSTALLED_VERIFIER_GIT_BLOB,
            "staged_sha256": hashlib.sha256(changed).hexdigest(),
            "staged_bytes": len(changed),
            "compatibility_scope": "POWERSHELL51_DOTNET_SHA256_ONLY",
            "release_accepted": False}


# Reuse approved C09 original NSIS registry line only in disposable C07 stage.
C09_NSIS_REVIEW_BLOB = "87d901c3846359a91be3e8288f24302cc7060257"
C07_NSIS_REGISTRY_LINE_SHA256 = "6ab87005e57b21c50252b13173784aafc348aeff3953aef60e1226f6154651d4"
C09_UNINSTALL_LINE = "  WriteRegStr HKCU \"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APP_ID}\" \"UninstallString\" '\"$INSTDIR\\Uninstall.exe\"'"
C07_UNINSTALL_LINE = "  WriteRegStr HKCU \"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APP_ID}\" \"UninstallString\" '$\"$INSTDIR\\Uninstall.exe$\"'"

def stage_c07_uninstall_quote(path: Path, review: Path):
    for node in (path,review,*path.parents,*review.parents):
        need(not node.is_symlink() and
             not getattr(node,"is_junction",lambda:False)(),
             "T06_NSIS_UNINSTALL_QUOTE_REPARSE_HOLD")
    need(path.is_file() and review.is_file() and
         path.parent.name=="Installer" and review.parent.name=="Installer",
         "T06_NSIS_UNINSTALL_QUOTE_OWNER_PATH_HOLD")
    approved_raw=review.read_bytes()
    need(_git_blob(approved_raw.replace(b"\r\n",b"\n"))==C09_NSIS_REVIEW_BLOB,
         "T06_NSIS_UNINSTALL_QUOTE_REVIEW_BLOB_HOLD")
    need(approved_raw.decode("utf-8-sig").splitlines().count(C09_UNINSTALL_LINE)==1,
         "T06_NSIS_UNINSTALL_QUOTE_REVIEW_LINE_HOLD")
    before=path.read_bytes()
    lines=before.decode("utf-8-sig").splitlines(keepends=True)
    candidates=[(index,item) for index,item in enumerate(lines)
                if '"UninstallString"' in item and "WriteRegStr" in item]
    need(len(candidates)==1,"T06_NSIS_UNINSTALL_QUOTE_DUPLICATE_HOLD")
    index,original=candidates[0]
    content_line=original.rstrip("\r\n")
    need(content_line in (C07_UNINSTALL_LINE,C09_UNINSTALL_LINE),
         "T06_NSIS_UNINSTALL_QUOTE_UNREVIEWED_HOLD")
    if content_line==C09_UNINSTALL_LINE:
        return {"changed":False,"sha256":sha(path),"release_accepted":False}
    need(hashlib.sha256(content_line.encode("utf-8")).hexdigest()==C07_NSIS_REGISTRY_LINE_SHA256,
         "T06_NSIS_UNINSTALL_QUOTE_PREIMAGE_SHA_HOLD")
    lines[index]=C09_UNINSTALL_LINE+original[len(content_line):]
    updated=("".join(lines)).encode("utf-8")
    if before.startswith(b"\xef\xbb\xbf"): updated=b"\xef\xbb\xbf"+updated
    need(updated!=before,"T06_NSIS_UNINSTALL_QUOTE_NOLOSS_HOLD")
    path.write_bytes(updated)
    need(path.read_bytes()==updated,
         "T06_NSIS_UNINSTALL_QUOTE_READBACK_HOLD")
    return {"changed":True,"pre_sha256":hashlib.sha256(before).hexdigest(),
            "sha256":sha(path),"release_accepted":False}

# Exact reviewed P01 32/64-bit WebView2 Evergreen registry-source fix.
# Stage only into disposable ORIGINAL R11, never into ZIP729 or installed NOX.
P01_REVIEWED_PREFLIGHT_GIT_BLOB = "e683e30b4e6fc32c31652061c569d6ce77c2cb2e"
# Canonical source pin for the original E06 32/64-bit Evergreen registry here-string.
WEBVIEW2_E06_REGISTRY_BLOCK_SHA256 = "e9d91ac3ed0bf5437ff38f07d2179a9e7a130835c4d0d1be49fa2c563f0e8bd1"
P01_WEBVIEW2_START = "# Official Microsoft WebView2 runtime detection uses registry pv, not Edge browser presence."
P01_WEBVIEW2_END = "if (-not $installed) { throw 'P01_WEBVIEW2_RUNTIME_MISSING: Install official Microsoft Evergreen WebView2 Runtime first; no silent download.' }"


def stage_reviewed_webview2_preflight(owner_script: Path, reviewed_script: Path) -> dict:
    need(owner_script.is_file() and not owner_script.is_symlink() and
         reviewed_script.is_file() and not reviewed_script.is_symlink(),
         "T06_WEBVIEW2_PREFLIGHT_REGULAR_SOURCE_REQUIRED")
    approved_raw=reviewed_script.read_bytes()
    need(b"\r" not in approved_raw.replace(b"\r\n", b""),
         "T06_WEBVIEW2_REVIEWED_SOURCE_LINE_ENDINGS_HOLD")
    approved_bytes=approved_raw.replace(b"\r\n", b"\n")
    approved_blob=hashlib.sha1(
        b"blob "+str(len(approved_bytes)).encode("ascii")+b"\x00"+approved_bytes
    ).hexdigest()
    need(approved_blob==P01_REVIEWED_PREFLIGHT_GIT_BLOB,
         "T06_WEBVIEW2_REVIEWED_SOURCE_GIT_BLOB_DRIFT")
    approved_text=approved_bytes.decode("utf-8-sig")
    old_bytes=owner_script.read_bytes()
    original=old_bytes.decode("utf-8-sig")
    # The compiled NSIS preflight must contain the EXACT approved P01
    # volume-root ancestor guard, not merely the reviewed registry gate.
    guard_start="# Never stage through a junction in the install path OR an upstream"
    guard_end="# Verify the existing installer-owned marker before allowing an update; a filename alone is not proof."
    need(approved_text.count(guard_start)==1 and
         approved_text.count(guard_end)==1 and
         original.count(guard_start)==1 and
         original.count(guard_end)==1,
         "T06_P01_PREFLIGHT_ANCESTOR_SOURCELOCK_HOLD")
    approved_guard=approved_text[approved_text.index(guard_start):approved_text.index(guard_end)]
    staged_guard=original[original.index(guard_start):original.index(guard_end)]
    need(staged_guard.replace("\r\n","\n")==approved_guard and
         "while ($cursor)" in staged_guard and
         "[IO.Path]::GetDirectoryName($cursor)" in staged_guard and
         "-not $node.PSIsContainer" in staged_guard and
         "$localRoot" not in staged_guard,
         "T06_P01_PREFLIGHT_ANCESTOR_SOURCELOCK_HOLD")
    need(b"\r" not in old_bytes.replace(b"\r\n", b""),
         "T06_WEBVIEW2_ORIGINAL_SOURCE_LINE_ENDINGS_HOLD")
    # The current T06 compiler already inserts the independently reviewed
    # E06 Registry32/Registry64 replacement BEFORE this packaging function.
    # Verify that exact immutable E06 donor instead of overwriting it with a
    # second logically equivalent preflight (which would break SourceLock).
    e06_start="# Official Microsoft WebView2 Evergreen Runtime: inspect the explicit 32/64-bit"
    if P01_WEBVIEW2_START not in original and e06_start in original:
        e06_path=Path(__file__).resolve().parent/"build_onehost_installer.ps1"
        need(e06_path.is_file() and not e06_path.is_symlink(),
             "T06_WEBVIEW2_E06_PINNED_DONOR_MISSING")
        donor_raw=e06_path.read_bytes()
        need(b"\r" not in donor_raw.replace(b"\r\n",b""),
             "T06_WEBVIEW2_E06_DONOR_ENCODING_HOLD")
        donor=donor_raw.replace(b"\r\n",b"\n")
        donor_git=hashlib.sha1(
            b"blob "+str(len(donor)).encode("ascii")+b"\x00"+donor
        ).hexdigest()
        # Full builder SHA is provenance only; exact audited registry gate stays pinned.
        block_start="$webviewReplacement=@'\n"
        block_end="\n'@"
        donor_text=donor.decode("utf-8-sig")
        need(donor_text.count(block_start)==1,
             "T06_WEBVIEW2_E06_DONOR_BLOCK_AMBIGUOUS")
        a=donor_text.index(block_start)+len(block_start)
        b=donor_text.find(block_end,a)
        need(b>a, "T06_WEBVIEW2_E06_DONOR_BLOCK_UNCLOSED")
        approved_e06=donor_text[a:b]+"\n"
        need(hashlib.sha256(approved_e06.encode("utf-8")).hexdigest()==
             WEBVIEW2_E06_REGISTRY_BLOCK_SHA256,
             "T06_WEBVIEW2_E06_DONOR_BLOCK_SHA_DRIFT")
        need(original.count(e06_start)==1 and
             original.count(P01_WEBVIEW2_END)==1,
             "T06_WEBVIEW2_E06_STAGED_ANCHOR_HOLD")
        owner_a=original.index(e06_start)
        owner_b=original.index(P01_WEBVIEW2_END)
        need(owner_a<owner_b and
             original[owner_a:owner_b].replace("\r\n","\n")==approved_e06 and
             "[Microsoft.Win32.RegistryView]::Registry32" in approved_e06 and
             "[Microsoft.Win32.RegistryView]::Registry64" in approved_e06 and
             "Microsoft Edge Stable alone is NOT an accepted runtime" in approved_e06,
             "T06_WEBVIEW2_E06_STAGED_BYTES_DRIFT")
        return {"sha256":hashlib.sha256(old_bytes).hexdigest(),
                "source_git_blob":approved_blob,
                "e06_donor_git_blob":donor_git,
                "e06_donor_block_sha256":WEBVIEW2_E06_REGISTRY_BLOCK_SHA256,
                "changed":False,
                "runtime_installed_verified":False,
                "e07_accepted":False}

    def region(text):
        need(text.count(P01_WEBVIEW2_START)==1 and
             text.count(P01_WEBVIEW2_END)==1,
             "T06_WEBVIEW2_ORIGINAL_ANCHOR_DRIFT")
        first=text.index(P01_WEBVIEW2_START)
        last=text.index(P01_WEBVIEW2_END)+len(P01_WEBVIEW2_END)
        need(first<last, "T06_WEBVIEW2_PREFLIGHT_ANCHOR_ORDER_HOLD")
        return first,last,text[first:last]
    _,_,approved_block=region(approved_text)
    begin,finish,old_block=region(original)
    need(all(fragment in approved_block for fragment in
             ("[Microsoft.Win32.RegistryView]::Registry32",
              "[Microsoft.Win32.RegistryView]::Registry64",
              "GetValueKind('pv')",
              "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}")),
         "T06_WEBVIEW2_REVIEWED_REGISTRY32_CONTRACT_HOLD")
    if old_block.replace("\r\n", "\n")!=approved_block:
        # Unknown competing preflight policy must fail closed, never overwrite.
        need(all(x in old_block for x in
                 ("Registry::HKEY_CURRENT_USER",
                  "Registry::HKEY_LOCAL_MACHINE",
                  "Get-ItemProperty", "pv")) and
             "[Microsoft.Win32.RegistryView]" not in old_block,
             "T06_WEBVIEW2_UNKNOWN_OR_PARTIALLY_PATCHED_OWNER_HOLD")
        eol="\r\n" if b"\r\n" in old_bytes else "\n"
        candidate=original[:begin]+approved_block.replace("\n",eol)+original[finish:]
        encoded=(b"\xef\xbb\xbf" if old_bytes.startswith(b"\xef\xbb\xbf") else b"")+candidate.encode("utf-8")
        need(not owner_script.is_symlink(), "T06_WEBVIEW2_OWNER_REPARSE_HOLD")
        owner_script.write_bytes(encoded)
        need(owner_script.read_bytes()==encoded,
             "T06_WEBVIEW2_OWNER_STAGE_READBACK_HOLD")
    staged=owner_script.read_bytes()
    staged_text=staged.decode("utf-8-sig")
    need(all(x in staged_text for x in
             ("[Microsoft.Win32.RegistryView]::Registry32",
              "[Microsoft.Win32.RegistryView]::Registry64", P01_WEBVIEW2_END)),
         "T06_WEBVIEW2_ORIGINAL_STAGED_RUNTIME_GATE_HOLD")
    return {"sha256":hashlib.sha256(staged).hexdigest(),
            "source_git_blob":approved_blob,
            "changed":staged!=old_bytes,
            "runtime_installed_verified":False,
            "e07_accepted":False}


def stage_ci_nsis_first_failure_trace(path: Path):
    """CI-only original installer /S phase markers. Never a release or E07 proof."""
    need(path.name == "NOX-HELION-Setup.nsi" and path.parent.name == "Installer" and
         path.is_file() and not path.is_symlink(), "T06_NSIS_TRACE_PATH_HOLD")
    original = path.read_bytes()
    text = original.decode("utf-8-sig")
    eol = "\r\n" if "\r\n" in text else "\n"
    normalized = text.replace("\r\n", "\n")
    marker = 'Section "NOX HELION application" SEC_MAIN'
    need(normalized.count(marker) == 1 and
         "NOX_EXPRESS_CI_NSIS_TRACE.txt" not in normalized,
         "T06_NSIS_TRACE_PREIMAGE_HOLD")
    start = normalized.index(marker)
    end = normalized.find("\nSectionEnd", start)
    need(end > start, "T06_NSIS_TRACE_SECTION_HOLD")
    section = normalized[start:end]
    gate = '  Pop $CheckResult\n  ${If} $ExitCode != "0"'
    need(section.count(gate) == 2, "T06_NSIS_TRACE_GATE_HOLD")
    for label in ("PREFLIGHT_EXIT", "VERIFY_EXIT"):
        probe = ('  FileOpen $9 "$TEMP\\NOX_EXPRESS_CI_NSIS_TRACE.txt" a\n'
                 '  FileWrite $9 "' + label + '=$ExitCode$\\r$\\n"\n'
                 '  FileClose $9\n')
        section = section.replace(
            gate, '  Pop $CheckResult\n' + probe +
            '  ${If} $ExitCode != "0"', 1)
    changed = normalized[:start] + section + normalized[end:]
    need(changed.count("NOX_EXPRESS_CI_NSIS_TRACE.txt") == 2 and
         changed.count("PREFLIGHT_EXIT=$ExitCode") == 1 and
         changed.count("VERIFY_EXIT=$ExitCode") == 1,
         "T06_NSIS_TRACE_INCOMPLETE_HOLD")
    result = (b"\xef\xbb\xbf" if original.startswith(b"\xef\xbb\xbf") else b"") + changed.replace("\n", eol).encode("utf-8")
    path.write_bytes(result)
    need(path.read_bytes() == result, "T06_NSIS_TRACE_READBACK_HOLD")
    return {"trace_probes": 2, "release_accepted": False, "e07": "NOT_RUN"}

def build(root,staged):
    staged=Path(staged).resolve(strict=True)
    root=Path(root).resolve(strict=True)
    # Verify this disposable ORIGINAL WPF/NSIS package uses the same real source
    # as the compiler. A borrowed compile receipt is not a new BuildID.
    from t06_compile_original_wpf_p02 import verified_source_head
    source_sha=verified_source_head()
    compile_path=staged/"T06_COMPILE_EVIDENCE.json"
    need(compile_path.is_file() and not compile_path.is_symlink(),
         "T06_PACKAGE_COMPILE_RECEIPT_MISSING")
    proof=json.loads(compile_path.read_text("utf-8"))
    need(type(proof) is dict and
         proof.get("source_git_sha")==source_sha and
         proof.get("original_zip_sha256")==EXPECTED_ZIP_SHA and
         type(proof.get("original_files_staged")) is int and
         proof["original_files_staged"]==94 and
         type(proof.get("dotnet_build_exit")) is int and
         proof["dotnet_build_exit"]==0,
         "T06_PACKAGE_COMPILE_SOURCE_HEAD_OR_R11_94_HOLD")
    receipt_path=staged/"NATIVE_PYTHON_EXE_CANDIDATE_RECEIPT.json"
    exe_path=staged/"NOX_HELION_PRIVATE_CANDIDATE.exe"
    for relative,target in (
      ("work/t06-manual-source-inspect/python-exe-candidate/NATIVE_PYTHON_EXE_CANDIDATE_RECEIPT.json",receipt_path),
      ("work/t06-manual-source-inspect/python-exe-candidate/NOX_HELION_PRIVATE_CANDIDATE.exe",exe_path)):
        download_artifact(relative,target)
    receipt=json.loads(receipt_path.read_text("utf-8"))
    candidate_sha=receipt.get("exe_sha256")
    need(receipt.get("phase")=="BUILT_AND_NATIVE_STDIO_SMOKE_PASS" and
         receipt.get("native_windows_exe_request_reply")=="PASS" and
         receipt.get("run_id_matched") is True and
         receipt.get("request_id_matched") is True and
         receipt.get("source_original_archive_sha256")=="ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a" and
         type(candidate_sha) is str and re.fullmatch(r"[0-9a-f]{64}",candidate_sha) and
         type(receipt.get("exe_size")) is int and receipt["exe_size"]==exe_path.stat().st_size and
         receipt.get("original_729_unchanged") is True and
         receipt.get("release_accepted") is False,
         "T06_NATIVE_BACKEND_RECEIPT_INVALID")
    need(sha(exe_path)==candidate_sha,"T06_NATIVE_BACKEND_BINARY_SHA_HOLD")
    # WPF pins original backend SHA in a checked partial file. Only the
    # disposable staging tree receives the attested compiled Python SHA.
    partial=root/"Integration/MainWindow.NativeP02.cs"
    need(partial.is_file() and not partial.is_symlink(),"T06_ORIGINAL_NATIVE_PARTIAL_MISSING")
    body=partial.read_text("utf-8")
    current='private const string NativePythonSha = "'+VALIDATED_OLD_PYTHON_SHA+'";'
    need(body.count(current)==1,"T06_WPF_ORIGINAL_BACKEND_PIN_ANCHOR_HOLD")
    partial.write_text(body.replace(current,
        'private const string NativePythonSha = "'+candidate_sha+'";'),encoding="utf-8")
    payload=staged/"payload"
    cmd=["dotnet","publish",str(root/"NOX.P01.Shell.csproj"),
         "-c","Release","-r","win-x64","--self-contained","true",
         "-p:PublishSingleFile=false","-p:PublishTrimmed=false",
         "-o",str(payload),"--nologo","--verbosity","minimal"]
    published=subprocess.run(cmd,capture_output=True,text=True,timeout=900)
    (staged/"WPF_SELFCONTAINED_PUBLISH_LOG.txt").write_text(
        published.stdout+"\n"+published.stderr,encoding="utf-8")
    need(published.returncode==0,"T06_WPF_SELFCONTAINED_PUBLISH_HOLD")
    entry=payload/"NOX.P01.Shell.exe"
    need(entry.is_file(),"T06_WPF_NATIVE_ENTRYPOINT_MISSING")
    # Reuse the original owner assets, never synthesize faces/backgrounds.
    original_assets=root/"Assets"
    need(original_assets.is_dir() and not original_assets.is_symlink(),
         "T06_APPROVED_ORIGINAL_ASSETS_MISSING")
    verify_source_tree_entry(original_assets,root)
    for file in original_assets.rglob("*"):
        verify_source_tree_entry(file,root)
        if file.is_dir():continue
        need(file.is_file() and not file.is_symlink(),"T06_REPARSE_ORIGINAL_ASSET_DENIED")
        out=payload/file.relative_to(root)
        out.parent.mkdir(parents=True,exist_ok=True)
        verify_source_tree_entry(out.parent,payload)
        if out.exists() or out.is_symlink():
            verify_source_tree_entry(out,payload)
            need(out.is_file() and sha(out)==sha(file),
                 "T06_PUBLISHED_ASSET_SOURCE_MISMATCH")
        else:shutil.copy2(file,out)
        verify_source_tree_entry(out,payload)
    # The EXISTING R76 owner MENU10 integration is verified in the same
    # disposable WPF tree and the SAME published NSIS payload. Do not copy
    # another UI, overwrite approved art, or claim Windows E07 from source QA.
    megab_attestation=None
    if os.environ.get("NOX_MEGA_8_14")=="YES":
        import importlib.util
        gate_path=Path(__file__).resolve().parents[2]/"coordination/mega814/publish_onehost_payload.py"
        need(gate_path.is_file() and not gate_path.is_symlink(),
             "T06_MEGAB_R76_PUBLISHER_MISSING")
        gate_spec=importlib.util.spec_from_file_location("nox_r76_onehost_pub",gate_path)
        need(gate_spec is not None and gate_spec.loader is not None,
             "T06_MEGAB_R76_PUBLISHER_IMPORT_HOLD")
        gate=importlib.util.module_from_spec(gate_spec)
        gate_spec.loader.exec_module(gate)
        verified=gate.publish(root,payload)
        stage_proof_path=root/"Assets/mega814/MEGA814_RECEIPT.json"
        need(stage_proof_path.is_file(),
             "T06_MEGAB_R76_STAGE_RECEIPT_MISSING")
        stage_proof=json.loads(stage_proof_path.read_text("utf-8"))
        need(verified.get("files")==14 and
             verified.get("release_accepted") is False and
             verified.get("menu10_sha256")==gate.MENU_SHA and
             stage_proof.get("index_preimage_mode")=="D02_CREATIVE_WOW200_VERIFIED" and
             stage_proof.get("menu10_asset_verified") is True and
             stage_proof.get("release_accepted") is False,
             "T06_MEGAB_R76_SOURCE_AND_ASSET_ADMISSION_HOLD")
        megab_attestation={
            "status":"VERIFIED_IN_SAME_NSIS_PAYLOAD_NOT_E07",
            "asset_count":14,
            "menu10_sha256":gate.MENU_SHA,
            "index_sha256":sha(payload/"Assets/index.html"),
            "asset_receipt_sha256":sha(payload/"Assets/mega814/MEGA814_RECEIPT.json"),
            "release_accepted":False
        }
        print("T06_MEGAB_R76_SAME_ONEHOST_ASSETS_14_PASS_NOT_E07",flush=True)
    backend=payload/"Backend"
    backend.mkdir(exist_ok=True)
    shutil.copy2(exe_path,backend/exe_path.name)
    need(sha(backend/exe_path.name)==candidate_sha,
         "T06_BUNDLED_NATIVE_EXE_SHA_MISMATCH")
    inventory=[]
    for file in sorted(payload.rglob("*")):
        verify_source_tree_entry(file,payload)
        if file.is_dir():continue
        need(file.is_file() and not file.is_symlink(),"T06_PAYLOAD_REPARSE_HOLD")
        inventory.append({"path":file.relative_to(payload).as_posix(),
                          "bytes":file.stat().st_size,"sha256":sha(file)})
    manifest={"schema":"NOX_P01_PAYLOAD_SHA256_V1","entrypoint":"NOX.P01.Shell.exe",
        "taskId":"NOX-V16-E06-CANDIDATE","runId":"NOX-V16-T06-WINDOWS-CANDIDATE",
        "version":"16.0.0","files":inventory}
    manifest_file=payload/"payload.sha256.json"
    manifest_file.write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    installer_dir=root/"Installer"
    # Stage approved native registry32 detection into the ORIGINAL R11 script
    # actually passed to NSIS; do not modify archive or install anything.
    webview_proof=stage_reviewed_webview2_preflight(
        installer_dir/"Preflight-InstallPath.ps1",
        Path(__file__).resolve().parents[2]/"stage/proposals/P01/C09/Installer/Preflight-InstallPath.ps1")
    print("T06_ORIGINAL_R11_WEBVIEW2_NATIVE_PREFLIGHT_STAGE "+
          json.dumps(webview_proof,sort_keys=True),flush=True)
    # Both NSIS fresh-stage and installed/rollback checks use this SAME
    # original C09 source-locked verifier; never modify immutable ZIP729.
    verifier_proof=stage_reviewed_installed_payload_verifier(
        installer_dir/"Verify-Payload.ps1",
        Path(__file__).resolve().parents[2]/
        "stage/proposals/P01/C09/Installer/Verify-Payload.ps1")
    print("T06_P01_INSTALLED_VERIFIER_PINNED_SOURCE_ONLY "+
          json.dumps(verifier_proof,sort_keys=True),flush=True)
    # NSIS /S and original same-VM installed rollback both invoke powershell.exe.
    # Reuse the already-reviewed PS5.1 .NET SHA helper in this disposable C07
    # copy only, after the exact C09 Git-blob admission above; no policy relaxed.
    verifier_ps51_proof=stage_reviewed_ps51_sha_compat(
        installer_dir/"Verify-Payload.ps1")
    print("T06_P01_VERIFIER_PS51_STAGED_SHA "+
          json.dumps(verifier_ps51_proof,sort_keys=True),flush=True)
    # Verify the EXACT copy that NSIS compiles against before emitting Setup.
    proof=subprocess.run(["pwsh.exe","-NoProfile","-NonInteractive",
        "-ExecutionPolicy","Bypass","-File",
        str(installer_dir/"Verify-Payload.ps1"),"-Root",str(payload),
        "-Manifest",str(manifest_file)],capture_output=True,text=True,timeout=180)
    need(proof.returncode==0,"T06_ORIGINAL_OWNER_MANIFEST_VERIFY_HOLD:"+proof.stdout[-900:]+proof.stderr[-900:])
    quote_proof=stage_c07_uninstall_quote(
        installer_dir/"NOX-HELION-Setup.nsi",
        Path(__file__).resolve().parents[2]/
        "stage/proposals/P01/C09/Installer/NOX-HELION-Setup.nsi")
    print("T06_C09_REVIEWED_NSIS_UNINSTALL_QUOTE_STAGE "+
          json.dumps(quote_proof,sort_keys=True),flush=True)
    if os.environ.get("NOX_CI_NSIS_TRACE") == "YES":
        need(os.environ.get("GITHUB_ACTIONS") == "true" and
             os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted" and
             os.environ.get("RUNNER_OS") == "Windows" and
             os.environ.get("GITHUB_REPOSITORY") ==
                 "MSSTXNEWS/nox-helion-pp-private-build" and
             os.environ.get("GITHUB_REF") ==
                 "refs/heads/integration/nox-v16-unified-candidate-20261028-r01",
             "T06_NSIS_CI_TRACE_AUTH_HOLD")
        trace_file = Path(os.environ["TEMP"]) / "NOX_EXPRESS_CI_NSIS_TRACE.txt"
        need(not trace_file.exists() and not trace_file.is_symlink(),
             "T06_NSIS_CI_TRACE_COLLISION_HOLD")
        stage_ci_nsis_first_failure_trace(installer_dir/"NOX-HELION-Setup.nsi")
        print("T06_CI_NSIS_TRACE_DIAGNOSTIC_ONLY_NOT_RELEASE", flush=True)
    nsis,nsis_compiler_sha=preflight_nsis_compiler()
    setup=staged/"NOX-HELION-V16-ONEHOST-CANDIDATE-SETUP.exe"
    need(not setup.exists() and not setup.is_symlink(),
         "T06_NSIS_OUTPUT_COLLISION")
    args=[nsis,"/V2",
       "/DPAYLOAD_DIR="+str(payload),
       "/DVERIFY_SCRIPT="+str(installer_dir/"Verify-Payload.ps1"),
       "/DPREFLIGHT_SCRIPT="+str(installer_dir/"Preflight-InstallPath.ps1"),
       "/DREMOVE_SCRIPT="+str(installer_dir/"Remove-InstalledPayload.ps1"),
       "/DOUTPUT_SETUP="+str(setup),
       "/DAPP_VERSION=16.0.0",str(installer_dir/"NOX-HELION-Setup.nsi")]
    attest_nsis_compiler_unchanged(nsis,nsis_compiler_sha)
    compiled=subprocess.run(args,capture_output=True,text=True,timeout=600)
    (staged/"NSIS_CANDIDATE_BUILD_LOG.txt").write_text(
         compiled.stdout+"\n"+compiled.stderr,encoding="utf-8")
    attest_nsis_compiler_unchanged(nsis,nsis_compiler_sha)
    need(compiled.returncode==0,"T06_ORIGINAL_NSIS_CANDIDATE_BUILD_HOLD")
    setup_proof=verify_nsis_setup(setup)
    need(verified_source_head()==source_sha,
         "T06_PACKAGE_SOURCE_HEAD_MOVED_DURING_BUILD")
    candidate={"schema":"NOX-E06-ONEHOST-CANDIDATE-v1",
         "source_git_sha":source_sha,
         "source_zip_sha256":EXPECTED_ZIP_SHA,
         "wpf_sha256":sha(entry),"backend_sha256":candidate_sha,
         "manifest_sha256":sha(manifest_file),
         "nsis_compiler_version":"3.13",
         "nsis_compiler_sha256":nsis_compiler_sha,
         "nsis_compiler_provenance":"HASHED_BINARY_ONLY_NOT_LICENSE_ATTESTED",
         "setup_sha256":setup_proof["sha256"],"setup_bytes":setup_proof["bytes"],
         "backend_native_stdio_windows_exe_smoke":"PASS",
         "wpf_source_compilation":"PASS","wpf_installed_interactive_qa":"NOT_RUN",
         "e07":"NOT_ACCEPTED","release_accepted":False,
         "webview2_p01_preflight_sha256":webview_proof["sha256"],
         "installed_owner_verifier":verifier_proof,
         "webview2_p01_source_git_blob":webview_proof["source_git_blob"],
         "webview2_e06_donor_git_blob":webview_proof.get("e06_donor_git_blob")}
    if megab_attestation is not None:
        candidate["mega814"]=megab_attestation
    (staged/"ONEHOST_CANDIDATE_RECEIPT.json").write_text(
         json.dumps(candidate,indent=2),encoding="utf-8")
    print("T06_ORIGINAL_NSIS_ONEHOST_CANDIDATE_BUILT",candidate["setup_sha256"],flush=True)
    return candidate
