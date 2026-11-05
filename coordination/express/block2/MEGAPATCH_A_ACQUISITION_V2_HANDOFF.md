# NOX HELION EXPRESS INTEGRATOR · MEGAPATCH A · Acquisition V2 native bridge
TaskID: BLOCK2-A-V2-INVENTORY
Owner: current PR162 integrator. Base HEAD: c9afd2107433b91cfbac4bd07346e20ce1ff959f.
Status: SOURCE_INTEGRATED_NOT_WINDOWS_E07; independent CI must run on post-commit HEAD.

Scope: one read-only acquisition-library probe, integrated into the EXISTING
FirstBootCoordinator. OneHost/P03/P01 workers, queue, STOP, consent and install
state remain authoritative. No second downloader, SQLite write DB, app, installer
or GPU service was added.

Inputs from signed native owner policy only:
  acquisition_library: {
    schema: NOX-ACQUISITION-NATIVE-CONFIG-v1,
    db_path: <absolute file under approved_scan_roots>,
    db_sha256: <independently pinned 64 lowercase hex>,
    manifest_path: <optional absolute path>,
    manifest_sha256: <optional independent 64-hex SHA>,
    assets_root: <optional approved directory>
  }
The optional manifest is NOT the original acquisition library schema: it is a
supplementary native-owner-issued physical proof index:
  {"schema":"NOX-ACQUISITION-FILES-v1",
   "files":[{"path":"relative/name","sha256":"<64hex>","bytes":123}]}
Unsupported or missing manifest means ZERO physical files verified, never an
assumed count of 98; SQLite FTS5 counts are reported only after on-disk SHA
verification, not asserted as 143. No missing weights/downloads auto-promoted.

Native operations require signed owner policy/consent; candidates remain
DISCOVERED, unverified weights remain REVIEW_REQUIRED, no automatic execution.
A malformed native acquisition policy, corrupt/mismatched database or changed
physical files causes fail-closed FirstBoot HOLD before queue dispatch.

Prebuilt V2 SQLite, actual Qwen model bytes and Windows tool binaries were NOT
available for this run. Never call them installed. The operating system binary
build, UI activation, signed dependency install and E07 remain independent gates.
Source tests: 10/10 local positive/negative Python tests PASS.
