"""NOX T06 manual one-shot Windows compilation: exact source ONLY, no installed release."""
import hashlib, io, json, os, pathlib, re, stat, subprocess, sys, zipfile
ROOT=pathlib.Path(__file__).resolve().parents[2]
STAGE=ROOT/"work/t06-wpf-p02-compile"
R11=STAGE/"R11"
SRC=ROOT  # EXACT canonical GitHub owner sources; never the stale imported GitLab overlay.
# Exact audited 32/64-bit WebView2 registry gate; unrelated builder lines can evolve.
WEBVIEW2_E06_REGISTRY_BLOCK_SHA256="e9d91ac3ed0bf5437ff38f07d2179a9e7a130835c4d0d1be49fa2c563f0e8bd1"
P01_PREFLIGHT_ANCESTOR_GIT_BLOB="e683e30b4e6fc32c31652061c569d6ce77c2cb2e"
EXPECTED={
"coordination/e06/MainWindow.NativeP02.cs":"9be154ae8b87566db8d694add9b2e694329f16f9",
"coordination/e06/OneHostP02WebView2Bridge.cs":"dee767ec4cb4a8210b6a6feb28f13730760521a7",
"coordination/e06/stage_native_p02.py":"76ce136353f1382288c3d6daee7cb6a5d0df4786",
"Packages/P02/worker-chat/NativePythonPipe.cs":"e8e4f95106f4d40c29c68d81378c7938e6a7c0f5"
}
# The existing E06 owner has ONE reviewed list of the 18 additive WPF/P02/
# P03 source components. Reuse that manifest, never fork a second overlay list.
# Its pins are re-verified against the exact authenticated GitHub checkout.
REQUIRED_NATIVE_DESTINATIONS=frozenset((
    "Integration/NativePythonPipe.cs",
    "Integration/OneHostP02WebView2Bridge.cs",
    "Integration/SpaceBrowserBoundary.cs",
    "Integration/NoXAutostart.cs",
    "Integration/P03/ModelArtifactReviewRegistry.cs",
    "Integration/P03/ModelCatalog.cs",
    "Integration/P03/ModelCenterNativeRoutes.cs",
    "Integration/P03/ModelDownloadQueueStore.cs",
    "Integration/P03/ModelDownloadQueueWorker.cs",
    "Integration/P03/ModelLifecycleEvents.cs",
    "Integration/P03/ModelLocalAttestation.cs",
    "Integration/P03/ModelQuickActions.cs",
    "Integration/P03/ModelSafetensorsImport.cs",
    "Integration/P03/ModelTagReviewLeads.cs",
    "Integration/P03/ModelWowBridgeContract.cs",
    "Integration/P03/OllamaLoopbackHttpClientFactory.cs",
    "Integration/P03/OllamaModelAdapter.cs",
    "Integration/P03/WindowsHardwareFacts.cs",
))

def canonical_owner_manifest():
    """Read only the existing original E06 source pins; reject manifest drift."""
    script=ROOT/"coordination/e06/build_onehost_installer.ps1"
    require(script.is_file() and not script.is_symlink(),
            "T06_CANONICAL_ORIGINAL_BUILDER_MISSING")
    policy=script.read_text("utf-8-sig").replace("\r\n","\n")
    start="$p02StageSources=@(\n"
    end="\n)\n# Validate every donor BEFORE copying any source into the staged project."
    require(policy.count(start)==1 and policy.count(end)==1,
            "T06_CANONICAL_OWNER_MANIFEST_ANCHOR_HOLD")
    section=policy.split(start,1)[1].split(end,1)[0]
    row=re.compile(r"\A@\{relative='([^']+)';dest='([^']+)';blob='([0-9a-f]{40})'\},?\Z")
    entries=[]
    for line in section.splitlines():
        stripped=line.strip()
        if not stripped:
            continue
        match=row.fullmatch(stripped)
        require(match is not None,"T06_CANONICAL_OWNER_MANIFEST_UNRECOGNIZED_ROW_HOLD")
        entries.append(match.groups())
    destinations=[destination for _,destination,_ in entries]
    require(len(entries)==len(REQUIRED_NATIVE_DESTINATIONS)==18 and
            set(destinations)==REQUIRED_NATIVE_DESTINATIONS and
            len(set(destinations))==len(entries) and
            len(set(source for source,_,_ in entries))==len(entries),
            "T06_CANONICAL_OWNER_18_COMPONENTS_NOLOSS_HOLD")
    pins={source:blob for source,_,blob in entries}
    require(
        pins.get("Packages/P02/worker-chat/NativePythonPipe.cs")==
            EXPECTED["Packages/P02/worker-chat/NativePythonPipe.cs"] and
        pins.get("coordination/e06/OneHostP02WebView2Bridge.cs")==
            EXPECTED["coordination/e06/OneHostP02WebView2Bridge.cs"] and
        "sha='"+EXPECTED["coordination/e06/stage_native_p02.py"]+"'" in policy and
        "sha='"+EXPECTED["coordination/e06/MainWindow.NativeP02.cs"]+"'" in policy,
        "T06_CANONICAL_OWNER_STAGING_PINS_DIVERGED")
    return tuple(entries)

def stage_current_owner_components(r11):
    """Preflight ALL original blobs before adding any file to disposable R11."""
    entries=canonical_owner_manifest()
    verified=[]
    repo=ROOT.resolve(strict=True)
    for relative,destination,pin in entries:
        parts=pathlib.PurePosixPath(relative)
        output=pathlib.PurePosixPath(destination)
        require(not parts.is_absolute() and not output.is_absolute() and
                all(x not in (".","..","") for x in parts.parts+output.parts) and
                "\\" not in relative and "\\" not in destination and
                relative.endswith(".cs") and destination.endswith(".cs") and
                destination in REQUIRED_NATIVE_DESTINATIONS and
                relative.startswith(("Packages/P02/","Packages/P03/","coordination/e06/")),
                "T06_CANONICAL_OWNER_STAGE_UNTRUSTED_PATH")
        origin=ROOT.joinpath(*parts.parts)
        require(origin.is_file() and not origin.is_symlink() and
                origin.resolve(strict=True).is_relative_to(repo),
                "T06_CANONICAL_OWNER_COMPONENT_MISSING_OR_REDIRECTED:"+relative)
        original=origin.read_bytes()
        staged=original
        if git_blob(staged)!=pin:
            require(b"\r\n" in original and
                    b"\r" not in original.replace(b"\r\n",b""),
                    "T06_CANONICAL_OWNER_COMPONENT_NON_CRLF_DRIFT:"+relative)
            staged=original.replace(b"\r\n",b"\n")
        require(git_blob(staged)==pin,
                "T06_CANONICAL_OWNER_COMPONENT_SHA_HOLD:"+relative)
        target=r11.joinpath(*output.parts)
        require(not target.exists() and not target.is_symlink(),
                "T06_CANONICAL_OWNER_COMPONENT_STAGE_COLLISION:"+destination)
        verified.append((target,staged,pin))
    # Only now write the reviewed complete P02/P03 source set; zero ZIP changes.
    for target,content,pin in verified:
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open("xb") as destination:
            destination.write(content)
        require(git_blob(target.read_bytes())==pin,
                "T06_CANONICAL_OWNER_COMPONENT_READBACK_HOLD:"+target.name)
    print("T06_ORIGINAL_E06_CANONICAL_NATIVE_P02_P03_STAGED",
          len(verified),"NO_ZIP_OR_OWNER_CHECKOUT_WRITE",flush=True)
    return len(verified)

def git_blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
def require(good,why):
    if not good: raise RuntimeError(why)
def verified_source_head():
    """GitLab builds ONLY the authenticated, frozen canonical GitHub tree."""
    try:
        probe=subprocess.run(["git", "rev-parse", "--verify", "HEAD^{commit}"],
            cwd=ROOT, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("T06_SOURCE_COMMIT_UNVERIFIED") from exc
    head=probe.stdout.strip().lower()
    require(probe.returncode==0 and re.fullmatch(r"[0-9a-f]{40}", head) is not None,
            "T06_SOURCE_COMMIT_UNVERIFIED")
    declared=os.environ.get("CI_COMMIT_SHA", "").strip().lower()
    ci_host=os.environ.get("CI_SERVER_HOST", "").strip().lower()
    if declared or ci_host:
        # Even if GitLab's own HEAD equals CI_COMMIT_SHA, it is NOT proof
        # that this tree is the owner's frozen canonical GitHub PR source.
        frozen=os.environ.get("NOX_T06_GITHUB_FROZEN_SHA", "").strip().lower()
        bootstrap=os.environ.get("NOX_T06_GITLAB_ORIGIN_SHA", "").strip().lower()
        frozen_ref=os.environ.get("NOX_T06_GITHUB_FROZEN_REF", "")
        require(
            ci_host=="gitlab.com" and
            os.environ.get("CI_PROJECT_PATH")=="s-grouptwet/nox-helion-pp-private-build" and
            os.environ.get("NOX_T06_AUTHENTICATED_GITHUB_FETCH")=="PASS" and
            re.fullmatch(r"[0-9a-f]{40}", declared) is not None and
            re.fullmatch(r"[0-9a-f]{40}", frozen) is not None and
            re.fullmatch(r"buildpin/nox-express-20261102-[0-9a-f]{12}", frozen_ref) is not None and
            frozen_ref.endswith(head[:12]) and
            frozen==head and bootstrap==declared,
            "T06_GITLAB_AUTHENTICATED_FROZEN_SOURCE_REQUIRED")
    return head

def stage_exact_owner_webview2_registry_views(r11, canonical_script):
    """Reuse the existing E06 signed-runtime 32/64-bit gate in disposable R11.

    The same-VM GitLab NSIS path does NOT call build_onehost_installer.ps1.
    Without this staging step it tests the old provider-redirected preflight.
    The original immutable ZIP, owner NSIS and non-WebView2 code stay intact.
    """
    preflight = r11 / "Installer" / "Preflight-InstallPath.ps1"
    if (not preflight.is_file() or preflight.is_symlink() or
            not canonical_script.is_file() or canonical_script.is_symlink()):
        raise RuntimeError("T06_WEBVIEW2_OWNER_PREFLIGHT_SOURCE_MISSING")
    raw = preflight.read_bytes()
    if not raw or len(raw) > 262144:
        raise RuntimeError("T06_WEBVIEW2_OWNER_PREFLIGHT_BYTES_HOLD")
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        original = raw.decode("utf-8-sig")
        donor = canonical_script.read_text(encoding="utf-8-sig")
    except UnicodeError as exc:
        raise RuntimeError("T06_WEBVIEW2_PREFLIGHT_ENCODING_HOLD") from exc
    begin_anchor = "# Official Microsoft WebView2 runtime detection uses registry pv, not Edge browser presence."
    end_anchor = "if (-not $installed) { throw 'P01_WEBVIEW2_RUNTIME_MISSING: Install official Microsoft Evergreen WebView2 Runtime first; no silent download.' }"
    if original.count(begin_anchor) != 1 or original.count(end_anchor) != 1:
        raise RuntimeError("T06_WEBVIEW2_ORIGINAL_PREFLIGHT_ANCHOR_HOLD")
    begin = original.index(begin_anchor)
    end = original.index(end_anchor)
    if begin >= end:
        raise RuntimeError("T06_WEBVIEW2_PREFLIGHT_ANCHOR_ORDER_HOLD")
    legacy = original[begin:end]
    if any(token not in legacy for token in (
            "Registry::HKEY_CURRENT_USER", "Registry::HKEY_LOCAL_MACHINE",
            "Get-ItemProperty", "[version]", "pv")):
        raise RuntimeError("T06_WEBVIEW2_ORIGINAL_PREFLIGHT_PREIMAGE_HOLD")
    start_marker = "$webviewReplacement=@'"
    stop_marker = "\n'@"
    if donor.count(start_marker) != 1:
        raise RuntimeError("T06_WEBVIEW2_CANONICAL_DONOR_AMBIGUOUS")
    start = donor.index(start_marker) + len(start_marker)
    if donor[start:start + 1] != "\n":
        raise RuntimeError("T06_WEBVIEW2_CANONICAL_DONOR_FORMAT_HOLD")
    start += 1
    stop = donor.find(stop_marker, start)
    if stop < start:
        raise RuntimeError("T06_WEBVIEW2_CANONICAL_DONOR_CLOSURE_HOLD")
    replacement = donor[start:stop]
    if hashlib.sha256((replacement+"\n").encode("utf-8")).hexdigest() != WEBVIEW2_E06_REGISTRY_BLOCK_SHA256:
        raise RuntimeError("T06_WEBVIEW2_CANONICAL_DONOR_BLOCK_SHA_HOLD")
    if (not replacement.startswith("# Official Microsoft WebView2 Evergreen Runtime:") or
            replacement.count("{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}") != 1 or
            "[Microsoft.Win32.RegistryView]::Registry32" not in replacement or
            "[Microsoft.Win32.RegistryView]::Registry64" not in replacement or
            "[Microsoft.Win32.RegistryHive]::CurrentUser" not in replacement or
            "[Microsoft.Win32.RegistryHive]::LocalMachine" not in replacement or
            r"\A[0-9]+(?:\.[0-9]+){3}\z" not in replacement or
            "$runtimeVersion.Major -gt 0" not in replacement):
        raise RuntimeError("T06_WEBVIEW2_CANONICAL_REGISTRY_GATE_HOLD")
    eol = "\r\n" if "\r\n" in original else "\n"
    after = original[:begin] + replacement.replace("\n", eol) + eol + original[end:]
    # SourceLock the actual Windows NSIS staging guard, not just the GitHub
    # donor. The archived original 729-file ZIP stays byte-identical.
    approved_path = ROOT / "stage/proposals/P01/C09/Installer/Preflight-InstallPath.ps1"
    if not approved_path.is_file() or approved_path.is_symlink():
        raise RuntimeError("T06_P01_PREFLIGHT_ANCESTOR_SOURCE_MISSING")
    approved_raw = approved_path.read_bytes()
    if not 512 <= len(approved_raw) <= 262144 or git_blob(approved_raw) != P01_PREFLIGHT_ANCESTOR_GIT_BLOB:
        raise RuntimeError("T06_P01_PREFLIGHT_ANCESTOR_SOURCE_BLOB_HOLD")
    approved = approved_raw.decode("utf-8-sig")
    new_marker = "# Never stage through a junction in the install path OR an upstream"
    old_marker = "# Never stage through a junction in the user-controlled install path or its parents."
    end_marker = "# Verify the existing installer-owned marker before allowing an update; a filename alone is not proof."
    if approved.count(new_marker) != 1 or approved.count(end_marker) != 1:
        raise RuntimeError("T06_P01_PREFLIGHT_ANCESTOR_APPROVED_ANCHOR_HOLD")
    guard_begin, guard_end = approved.index(new_marker), approved.index(end_marker)
    approved_guard = approved[guard_begin:guard_end]
    if (guard_begin >= guard_end or
            "while ($cursor)" not in approved_guard or
            "[IO.Path]::GetDirectoryName($cursor)" not in approved_guard or
            "-not $node.PSIsContainer" not in approved_guard or
            "[IO.FileAttributes]::ReparsePoint" not in approved_guard or
            "$localRoot" in approved_guard):
        raise RuntimeError("T06_P01_PREFLIGHT_ANCESTOR_APPROVED_GUARD_HOLD")
    if after.count(old_marker) == 1 and after.count(end_marker) == 1:
        legacy_begin, legacy_end = after.index(old_marker), after.index(end_marker)
        legacy_guard = after[legacy_begin:legacy_end]
        if (legacy_begin >= legacy_end or
                "$localRoot" not in legacy_guard or
                "P01_INSTALL_REPARSE_ANCESTOR" not in legacy_guard or
                "[IO.Path]::GetDirectoryName($cursor)" not in legacy_guard):
            raise RuntimeError("T06_P01_PREFLIGHT_ANCESTOR_LEGACY_DRIFT_HOLD")
        after = after[:legacy_begin] + approved_guard.replace("\n", eol) + after[legacy_end:]
    elif after.count(new_marker) != 1 or after.count(end_marker) != 1:
        raise RuntimeError("T06_P01_PREFLIGHT_ANCESTOR_UNKNOWN_PREIMAGE_HOLD")
    staged_guard_begin = after.index(new_marker)
    staged_guard_end = after.index(end_marker)
    if (staged_guard_begin >= staged_guard_end or
            after[staged_guard_begin:staged_guard_end].replace("\r\n", "\n") != approved_guard or
            after.count("P01_INSTALL_REPARSE_ANCESTOR") != 1):
        raise RuntimeError("T06_P01_PREFLIGHT_ANCESTOR_GRAFT_HOLD")
    if (after == original or after.count(end_anchor) != 1 or
            after.count("P01_WEBVIEW2_RUNTIME_MISSING") != 1):
        raise RuntimeError("T06_WEBVIEW2_OWNER_PREFLIGHT_NOLOSS_HOLD")
    new_bytes = (b"\xef\xbb\xbf" if has_bom else b"") + after.encode("utf-8")
    preflight.write_bytes(new_bytes)  # disposable CI R11 ONLY, original ZIP untouched
    if preflight.read_bytes() != new_bytes:
        raise RuntimeError("T06_WEBVIEW2_STAGED_READBACK_HOLD")
    print("T06_WEBVIEW2_ORIGINAL_PREFLIGHT_REGISTRY32_64_STAGED_NOT_E07", flush=True)

def main():
    source_git_sha=verified_source_head()
    manifest=json.loads((ROOT/"donors/P01_C07/P01_C07_RECEIPT.json").read_text("utf-8"))
    chunks=io.BytesIO();digest=hashlib.sha256()
    for row in manifest["parts"]:
        path=ROOT/row["path"]
        require(path.is_file() and not path.is_symlink(),"DONOR_PART_MISSING")
        data=path.read_bytes()
        require(len(data)==row["size_bytes"] and git_blob(data)==row["git_blob_sha1"],"DONOR_PART_PIN_HOLD")
        chunks.write(data);digest.update(data)
    require(chunks.tell()==manifest["original_zip_bytes"] and
            digest.hexdigest()==manifest["original_zip_sha256"],"DONOR_ZIP_SHA_HOLD")
    for name,sha in EXPECTED.items():
        owner_file=SRC/name
        data=owner_file.read_bytes()
        if git_blob(data)!=sha:
            # Windows Git checkout may convert GitHub LF source to CRLF.
            # The ONLY permitted canonicalization restores exact GitHub bytes;
            # non-line-ending differences remain a hard SourceLock failure.
            require(b"\r\n" in data and b"\r" not in data.replace(b"\r\n",b""),
                    "GITHUB_OWNER_OVERLAY_NON_CRLF_DRIFT:"+name)
            canonical=data.replace(b"\r\n",b"\n")
            require(git_blob(canonical)==sha,
                    "GITHUB_OWNER_OVERLAY_SHA_HOLD:"+name+
                    " raw="+git_blob(data)+" normalized="+git_blob(canonical))
            # Preserve the exact authenticated Git checkout: never edit the
            # source preimages to compensate for runner CRLF normalization.
            data=canonical
        require(git_blob(data)==sha,"GITHUB_OWNER_OVERLAY_FINAL_SHA_HOLD:"+name)
    R11.mkdir(parents=True,exist_ok=False)
    seen=set();nfiles=0;total=0
    with zipfile.ZipFile(chunks) as archive:
        for info in archive.infolist():
            name=info.filename
            if not name.startswith("R11/") or info.is_dir(): continue
            rel=pathlib.PurePosixPath(name).parts[1:]
            require(rel and all(x not in ("",".","..") for x in rel) and
                    "\\" not in name and "\0" not in name,"ZIP_MEMBER_PATH_HOLD")
            low="/".join(rel).casefold()
            require(low not in seen,"ZIP_CASE_COLLISION_HOLD")
            seen.add(low)
            require(stat.S_IFMT(info.external_attr>>16)!=stat.S_IFLNK,"ZIP_SYMLINK_HOLD")
            total+=info.file_size
            require(info.file_size<64*1024*1024 and total<200*1024*1024,"ZIP_SIZE_HOLD")
            target=R11.joinpath(*rel)
            target.parent.mkdir(parents=True,exist_ok=True)
            require(not target.exists(),"ZIP_OVERWRITE_HOLD")
            with archive.open(info) as f, target.open("xb") as o:
                while True:
                    part=f.read(1024*1024)
                    if not part:break
                    o.write(part)
            nfiles+=1
    require(nfiles>=75,"ORIGINAL_R11_INCOMPLETE")
    import os
    if os.environ.get("NOX_T06_INSPECT_ONLY")=="YES":
        targets=(
            "Packages/P03/module/ModelCenterEvent.cs",
            "Packages/P03/worker-window/ModelDownloaderWindow.xaml.cs",
            "Packages/P03/module/ComponentInstaller.cs",
            "Packages/P02/OpenAI/OpenAiResponsesProvider.cs",
            "MainWindow.xaml.cs",
            "NOX.P01.Shell.csproj",
        )
        result=STAGE/"source-inspect"
        result.mkdir(parents=True,exist_ok=False)
        for target in targets:
            source=R11/target
            require(source.is_file() and not source.is_symlink(),
                    "T06_ORIGINAL_COMPILE_SOURCE_MISSING:"+target)
            data=source.read_bytes()
            require(0<len(data)<=450000,"T06_ORIGINAL_COMPILE_SOURCE_OVERSIZE")
            out=result/target
            out.parent.mkdir(parents=True,exist_ok=True)
            out.write_bytes(data)
            print("T06_ORIGINAL_COMPILE_SOURCE",target,len(data),
                  hashlib.sha256(data).hexdigest(),flush=True)
        print("T06_ORIGINAL_CONFLICT_SOURCE_EXTRACT_PASS",len(targets),flush=True)
        return
    # Same-VM NSIS source MUST receive existing E06 explicit 32/64-bit runtime gate.
    # Other owner files, signed installers and original ZIP remain untouched.
    stage_exact_owner_webview2_registry_views(
        R11, ROOT / 'coordination/e06/build_onehost_installer.ps1')
    # Preserve the original MainWindow, zero HOME/MENU/WORK modification outside R11.
    # The older imported GitLab 4-file overlay silently stripped current
    # A1 signed consent, native STOP epoch, P03 model queue and Browser ACL.
    # Reuse the exact same 18 Git-blob-pinned sources as the original E06.
    require(stage_current_owner_components(R11)==18,
            "T06_CANONICAL_OWNER_SOURCE_STAGE_INCOMPLETE")
    stage_path=SRC/"coordination/e06/stage_native_p02.py"
    addon_path=SRC/"coordination/e06/MainWindow.NativeP02.cs"
    run=subprocess.run([sys.executable,str(stage_path),str(R11),str(addon_path)],
                      capture_output=True,text=True,timeout=60)
    print(run.stdout,flush=True)
    require(run.returncode==0,"MAINWINDOW_ORIGINAL_STAGE_HOLD:"+run.stderr[-900:])
    print("T06_ORIGINAL_WPF_SOURCE_STAGED",nfiles,flush=True)
    # Diagnose only the exact first compiler failure, preserving the donor.
    owner_p05=R11/"Packages/P05/InstallerRunReport.cs"
    if owner_p05.is_file():
        content=owner_p05.read_text(encoding="utf-8-sig",errors="replace").splitlines()
        excerpt="\n".join(f"{n+1}: {content[n]}" for n in range(458,min(len(content),526)))
        (STAGE/"P05_ORIGINAL_SOURCE_EXCERPT.txt").write_text(excerpt,encoding="utf-8")
        # Original P05 C# source uses invalid multiline inline raw literals.
        # Repair ONLY disposable-stage string literals, retaining every HTML
        # codepoint and every dynamic expression without altering the archive.
        import re
        source=owner_p05.read_bytes()
        bom=source.startswith(b"\xef\xbb\xbf")
        original=source.decode("utf-8-sig")
        first='        return """<!doctype html>'
        last='</main></body></html>""";'
        require(original.count(first)==1 and original.count(last)==1,
                "T06_P05_EXACT_ORIGINAL_HTML_ANCHOR_DRIFT")
        start=original.index(first)
        end=original.index(last,start)+len(last)
        before=original[start:end]
        strings=re.findall(r'"""(.*?)"""',before,flags=re.S)
        require(len(strings)>=10 and before.count('"""')==2*len(strings),
                "T06_P05_STRING_INTERVAL_COUNT_HOLD")
        def verbatim(match):
            # C# @"..." preserves physical newlines, unlike malformed """...""".
            return '@"'+match.group(1).replace('"','""')+'"'
        fixed=re.sub(r'"""(.*?)"""',verbatim,before,flags=re.S)
        require('"""' not in fixed and fixed!=before and
                fixed.count('@"')==len(strings),"T06_P05_VERBATIM_PATCH_HOLD")
        post=original[:start]+fixed+original[end:]
        owner_p05.write_bytes((b"\xef\xbb\xbf" if bom else b"")+post.encode("utf-8"))
        (STAGE/"P05_STAGE_REPAIR.json").write_text(json.dumps({
            "original_sha256":hashlib.sha256(source).hexdigest(),
            "staged_sha256":hashlib.sha256(owner_p05.read_bytes()).hexdigest(),
            "source_archive_unchanged":True,
            "html_string_segments_preserved":len(strings),
            "scope":"one P05 HTML return expression in disposable R11 only",
            "release_accepted":False},indent=2),encoding="utf-8")
        print("T06_P05_EXACT_HTML_VERBATIM_SOURCE_REPAIRED",len(strings),flush=True)
    # Apply exact owner-preserving P03 duplicate + P02 OpenAI namespace fix
    # before the single real Windows compiler pass. Original ZIP is immutable.
    compat=ROOT/"coordination/e06/stage_wpf_compat_no_loss.py"
    compat_raw=compat.read_bytes()
    require(git_blob(compat_raw)== "fc206205ec46e52d8d65eab33490193a27d1529a" or
            (b"\r\n" in compat_raw and
             git_blob(compat_raw.replace(b"\r\n",b"\n"))=="fc206205ec46e52d8d65eab33490193a27d1529a"),
            "T06_OWNER_COMPAT_SOURCE_BLOB_HOLD")
    compatibility=subprocess.run([sys.executable,str(compat),str(R11)],
                                 capture_output=True,text=True,timeout=60)
    print(compatibility.stdout,flush=True)
    require(compatibility.returncode==0,
            "T06_WPF_OWNER_COMPAT_STAGE_HOLD:"+compatibility.stderr[-1000:])
    # The eight remaining compiler errors are in the ORIGINAL verified WPF
    # owner sources, after P05/P03 duplicate staging. Repair only disposable
    # R11, retain all download/consent/STOP operations and original ZIP bytes.
    # One preflight for the whole patch: zero writes if any anchor drifts.
    repair_targets = {
        "Contracts/EventV3Bridge.cs": R11/"Contracts/EventV3Bridge.cs",
        "Packages/P03/worker-window/ModelDownloaderWindow.xaml.cs":
            R11/"Packages/P03/worker-window/ModelDownloaderWindow.xaml.cs",
        "Packages/P03/worker-queue/ModelDownloadQueueStore.cs":
            R11/"Packages/P03/worker-queue/ModelDownloadQueueStore.cs",
    }
    draft={}; prior_hashes={}; changed={}
    for rel,file in repair_targets.items():
        require(file.is_file() and not file.is_symlink(),
                "T06_E06_FINAL_OWNER_FILE_HOLD:"+rel)
        data=file.read_bytes()
        prior_hashes[rel]=hashlib.sha256(data).hexdigest()
        text=data.decode("utf-8-sig")
        draft[rel]=(text,data.startswith(b"\xef\xbb\xbf"),"\r\n" in text)
    event="Contracts/EventV3Bridge.cs"
    original,bom,crlf=draft[event]
    rows=original.replace("\r\n","\n").splitlines(keepends=True)
    require(len(rows)>88, "T06_EVENT_V3_LONG_NULL_SOURCE_DRIFT")
    # The C# conditional often spans lines. Anchor by the original compiler
    # error around line 88 and find its one NULL arm in the same statement.
    # An arbitrary unrelated NULL or multiple candidates fail closed.
    # Match the complete conditional statement that contains compiler error
    # EventV3Bridge.cs(88,25), not a nearby earlier NULL token.
    original_source="".join(rows)
    position=sum(len(line) for line in rows[:87])+min(24,len(rows[87])-1)
    begin=max(original_source.rfind(";",0,position),
              original_source.rfind("{",0,position),
              original_source.rfind("}",0,position))+1
    stop=original_source.find(";",position)
    require(stop>position,"T06_EVENT_V3_STATEMENT_BOUNDARY_HOLD")
    clause=original_source[begin:stop]
    arms=list(re.finditer(r"(?:\?|:)\s*(null)\b",clause))
    if len(arms)!=1 or "?" not in clause or ":" not in clause:
        print("T06_EVENT_V3_EXACT_STATEMENT",
              repr(clause[:1000]),flush=True)
        raise RuntimeError("T06_EVENT_V3_LONG_NULL_EXACT_BRANCH_HOLD")
    offset=begin+arms[0].start(1)
    changed[event]=original_source[:offset]+"(long?)null"+original_source[offset+4:]
    win="Packages/P03/worker-window/ModelDownloaderWindow.xaml.cs"
    original,bom,crlf=draft[win]
    normalized=original.replace("\r\n","\n")
    expected={
      "_queueStore.Items.CollectionChanged += _queueItemsChanged;":
      "((System.Collections.Specialized.INotifyCollectionChanged)_queueStore.Items).CollectionChanged += _queueItemsChanged;",
      "_queueStore.Items.CollectionChanged -= _queueItemsChanged;":
      "((System.Collections.Specialized.INotifyCollectionChanged)_queueStore.Items).CollectionChanged -= _queueItemsChanged;",
      "var hasCompleted = item.HasBytesCompletedMeasurement;":
      "var hasCompleted = item.BytesCompleted > 0;",
      "var hasTotal = item.HasBytesTotalMeasurement;":
      "var hasTotal = item.BytesTotal > 0;",
      "var percent = bytesTotal is > 0 && bytesCompleted is not null":
      "double? percent = bytesTotal is > 0 && bytesCompleted is not null",
    }
    for before,after in expected.items():
        require(normalized.count(before)==1,"T06_MODEL_CENTER_8_SOURCE_DRIFT:"+before)
        normalized=normalized.replace(before,after,1)
    changed[win]=normalized
    queue="Packages/P03/worker-queue/ModelDownloadQueueStore.cs"
    original,bom,crlf=draft[queue]
    normalized=original.replace("\r\n","\n")
    require("PersistedQueueItem" in normalized and
            re.search(r"\bPersistedItem\b",normalized) is not None,
            "T06_QUEUE_PERSISTED_ITEM_TYPE_DRIFT")
    normalized,nref=re.subn(r"\bPersistedItem\b","PersistedQueueItem",normalized)
    require(nref>0 and nref<8,"T06_QUEUE_PERSISTED_ITEM_COUNT_DRIFT")
    changed[queue]=normalized
    for rel,body in changed.items():
        file=repair_targets[rel]
        original,bom,crlf=draft[rel]
        actual=body.replace("\n","\r\n") if crlf else body
        raw=(b"\xef\xbb\xbf" if bom else b"")+actual.encode("utf-8")
        require(hashlib.sha256(raw).hexdigest()!=prior_hashes[rel],
                "T06_MEGA_PATCH_NO_EFFECT:"+rel)
        file.write_bytes(raw)
        require(file.read_bytes()==raw,"T06_MEGA_PATCH_READBACK_FAIL:"+rel)
    print("T06_R50_WPF_FINAL_8_COMPAT_STAGED",len(changed),
          "ORIGINAL_MEDIA_AND_ARCHIVES_UNCHANGED",flush=True)
    import os, shutil
    # Read ONLY precise unresolved P01/P03/P05 owner lines from the verified
    # disposable R11 source. No source files rewritten for inspection.
    if os.environ.get("NOX_T06_INSPECT_ONLY")=="YES":
        wanted={
          "Contracts/EventV3Bridge.cs": (88,),
          "Packages/P03/worker-window/ModelDownloaderWindow.xaml.cs":
              (186,741,742,1528,1551),
          "Packages/P03/worker-queue/ModelDownloadQueueStore.cs":
              (890,905,908,915),
        }
        for rel, indexes in wanted.items():
            file=R11/rel
            require(file.is_file(),"T06_OWNER_SOURCE_FILE_MISSING:"+rel)
            rows=file.read_text("utf-8-sig",errors="replace").splitlines()
            print("T06_EXACT_OWNER_SOURCE",rel,flush=True)
            included=set()
            for index in indexes:
                for j in range(max(0,index-13),min(len(rows),index+11)):
                    if j not in included:
                        included.add(j)
                        esc=rows[j].encode("ascii","backslashreplace").decode("ascii")
                        print(f"T06_SOURCE_LINE {j+1}: {esc}",flush=True)
        for file in R11.rglob("*.cs"):
            rows=file.read_text("utf-8-sig",errors="replace").splitlines()
            ids=[j for j,x in enumerate(rows) if (
                "class DownloadQueueItem" in x or
                "record DownloadQueueItem" in x or
                "HasBytesCompletedMeasurement" in x or
                "HasBytesTotalMeasurement" in x)]
            if not ids:continue
            print("T06_MEASUREMENT_DECLARATION",file.relative_to(R11),flush=True)
            out=set()
            for index in ids[:12]:
                for j in range(max(0,index-4),min(len(rows),index+30)):
                    if j not in out:
                        out.add(j)
                        esc=rows[j].encode("ascii","backslashreplace").decode("ascii")
                        print(f"T06_MEASUREMENT_LINE {j+1}: {esc}",flush=True)
        print("T06_EXACT_OWNER_INSPECTION_PASS_NO_SOURCE_MUTATION",flush=True)
        return
    dotnet=shutil.which("dotnet")
    sdk=(subprocess.run([dotnet,"--list-sdks"],capture_output=True,text=True,timeout=30)
         if dotnet else None)
    print("T06_DOTNET_SDK_PREINSTALLED",
          (sdk.stdout if sdk else "MISSING_DOTNET_COMMAND")[:400],flush=True)
    # R50 ONE-SHOT: the GitLab Windows image already has SDK 9. SDK 9 can
    # cross-target net8.0-windows for diagnostic source compilation, with
    # MSBuild restoring official targeting packs when required. No Choco V2
    # metadata lookup: its 504 was an infrastructure failure, not a code bug.
    # The final release E06 builder retains the separate exact-.NET8 gate.
    require(sdk is not None and sdk.returncode==0, "T06_WINDOWS_DOTNET_COMMAND_REQUIRED")
    supported=tuple(line.split(".",1)[0] for line in sdk.stdout.splitlines()
                    if line and line[0].isdigit())
    require(any(v in ("8","9") for v in supported),
            "T06_WINDOWS_COMPILER_SDK8_OR_SDK9_REQUIRED")
    print("T06_EPHEMERAL_DOTNET_SDK_REUSED_NO_CHOCOLATEY",sdk.stdout[:400],flush=True)
    print("T06_DOTNET8_READY",sdk.stdout[:400],flush=True)
    # One build attempt, one disposable source. Reuse .NET's built-in global
    # using support to repair missing framework imports across the original
    # 94-file project without rewriting any approved owner .cs files.
    # This adds only namespaces, not synthetic handlers, stubs or replacement UX.
    compat=R11/"Integration/NOX.BuildGlobalUsings.cs"
    require(not compat.exists() and not compat.is_symlink(),
            "T06_BUILD_COMPAT_STAGE_COLLISION")
    compat.write_text(
        "global using System.IO;\n"
        "global using System.Net.Http;\n"
        "global using System.Net.Http.Headers;\n"
        "global using System.Threading;\n"
        "global using System.Threading.Tasks;\n",
        encoding="utf-8")
    # Preserve evidence of the ORIGINAL unresolved owner symbols and duplicate
    # methods. Never silently strip UI, ModelCenter code or consent handlers.
    import re
    inspected={
      "MainWindow.xaml.cs":(r"(?m)^using [^;]+;",r"WindowsCredentialSecretProvider",
                            r"OpenAiResponsesProvider"),
      "Packages/P03/module/ModelCenterEvent.cs":(r"OperationId",),
      "Packages/P03/worker-window/ModelDownloaderWindow.xaml.cs":
          (r"RefreshComponentActions",r"ReadComponentOperation"),
    }
    for relative,patterns in inspected.items():
        target=R11/relative
        if not target.is_file(): continue
        rows=target.read_text("utf-8-sig",errors="replace").splitlines()
        indices=[i for i,line in enumerate(rows)
                 if any(re.search(pattern,line) for pattern in patterns)]
        print("T06_OWNER_SOURCE_TRACE",relative,"matches",len(indices),flush=True)
        for i in indices[:18]:
            excerpt=" | ".join(f"{j+1}:{rows[j][:160]}"
                             for j in range(max(0,i-1),min(len(rows),i+3)))
            print("T06_ORIGINAL_LINE",excerpt.encode("ascii","backslashreplace").decode("ascii"),flush=True)
    output=STAGE/"publish";output.mkdir(parents=True,exist_ok=False)
    # R77: Creative and WOW200 MUST precede the existing MENU R76 stage.
    # Reuse the approved stages rather than rebuild or replace D02 originals.
    if os.environ.get("NOX_MEGA_8_14")=="YES" or os.environ.get("NOX_MEGA_8_14_SOURCE_ONLY")=="YES":
        import importlib.util
        for label,relative,blob in (
            ("CREATIVE","integrations/creative/stage_creative.py",
             "d89911ccf3260e0ad7fe82f954a1d4adf560372c"),
            ("WOW200","integrations/wow200/stage_wow200.py",
             "393b47edf1c9b6f92716b6dea44a02f7797fb5b4")):
            candidate=ROOT/relative
            require(candidate.is_file() and not candidate.is_symlink(),
                    "T06_D02_"+label+"_SOURCE_MISSING")
            contents=candidate.read_bytes()
            actual=git_blob(contents)
            if actual!=blob and b"\r\n" in contents and b"\r" not in contents.replace(b"\r\n",b""):
                actual=git_blob(contents.replace(b"\r\n",b"\n"))
            require(actual==blob,"T06_D02_"+label+"_SOURCE_BLOB_HOLD")
            module_spec=importlib.util.spec_from_file_location("nox_r77_"+label.lower(),candidate)
            require(module_spec is not None and module_spec.loader is not None,
                    "T06_D02_"+label+"_IMPORT_HOLD")
            module=importlib.util.module_from_spec(module_spec)
            module_spec.loader.exec_module(module)
            owner_root=ROOT/("integrations/creative" if label=="CREATIVE" else "integrations/wow200")
            evidence=module.stage(R11,owner_root)
            require(evidence.get("release_accepted") is False,
                    "T06_D02_"+label+"_SOURCE_RECEIPT_HOLD")
            if label=="WOW200":
                require(evidence.get("count")==65 and
                        evidence.get("active_d02_engine")=="OWNER1_PR144_PINNED" and
                        evidence.get("pack01_catalog_routes")==50 and
                        evidence.get("legacy_d02_runtime_imported") is False,
                        "T06_D02_WOW200_OWNER_RECEIPT_HOLD")
            print("T06_R77_APPROVED_D02_"+label+"_STAGED_NOT_E07",flush=True)
    # Owner-approved secondary megablock 8–14. Never edits source archives.
    if os.environ.get("NOX_MEGA_8_14")=="YES" or os.environ.get("NOX_MEGA_8_14_SOURCE_ONLY")=="YES":
        import importlib.util
        stage_file=ROOT/"coordination/mega814/stage_original_r11.py"
        spec=importlib.util.spec_from_file_location("mega814_stage",stage_file)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.run(R11,os.environ.get("NOX_MENU10_APPROVED_PNG") or None,
                   os.environ.get("NOX_PERSONA_APPROVED_FOLDER") or None)
        result=subprocess.run([sys.executable,str(ROOT/"coordination/mega814/qa_source_gate.py")],cwd=ROOT,capture_output=True,text=True,timeout=45)
        print("NOX_MEGA814_OWNER_GATE",result.stdout[:500],flush=True)
        require(result.returncode==0,"NOX_MEGA814_SOURCE_GATE_HOLD:"+result.stderr[-350:])
    cmd=["dotnet","build",str(R11/"NOX.P01.Shell.csproj"),"-c","Release",
         "-r","win-x64","--nologo","--verbosity","minimal",
         "-p:PublishSingleFile=false","-p:PublishTrimmed=false"]
    proc=subprocess.run(cmd,capture_output=True,text=True,timeout=900)
    transcript=proc.stdout+"\nSTDERR:\n"+proc.stderr
    (STAGE/"BUILD_LOG.txt").write_text(transcript,encoding="utf-8",errors="replace")
    print("T06_DOTNET_BUILD_EXIT",proc.returncode,flush=True)
    print(transcript[-12000:],flush=True)
    require(verified_source_head()==source_git_sha,"T06_SOURCE_HEAD_MOVED_DURING_BUILD")
    result={"source_git_sha":source_git_sha,"original_zip_sha256":digest.hexdigest(),
            "original_files_staged":nfiles,"dotnet_build_exit":proc.returncode,
            "native_ingress_e2e":"NOT_RUN","original_python_cli":"NOT_ATTESTED",
            "release_accepted":False}
    (STAGE/"T06_COMPILE_EVIDENCE.json").write_text(json.dumps(result,indent=2),"utf-8")
    require(proc.returncode==0,"T06_WPF_NATIVE_P02_COMPILE_FAIL")
    print("T06_ORIGINAL_WPF_P02_NATIVE_COMPILE_PASS_SOURCE_ONLY",flush=True)
    if os.environ.get("NOX_T06_PACKAGE_CANDIDATE")=="YES":
        import importlib.util
        stage=ROOT/"coordination/e06/t06_package_original_onehost.py"
        spec=importlib.util.spec_from_file_location("nox_t06_pack",stage)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.build(R11,STAGE)
if __name__=="__main__":main()
