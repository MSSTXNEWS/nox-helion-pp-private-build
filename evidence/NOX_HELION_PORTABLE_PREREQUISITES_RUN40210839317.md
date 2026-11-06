# NOX HELION · Portable prerequisites

**Candidate:** PRE-PRE fast candidate, Run `40210839317`  
**GitHub workflow artifact:** `PP-001-C1-R3-Windows-candidate-40210839317` · artifact ID `12605282328` · 103,014,095 bytes · SHA-256 `f7b57520904cb60e17ce91737bb9f2f8af583a4ab769734a851551fa9f4eb625`  
**Source tree:** `d61632a7dd4ca889f16eba2d330e2ed5fd6b3842` · source archive SHA-256 `ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a`

## Files to extract together

| Candidate file | Size | SHA-256 | Purpose |
|---|---:|---|---|
| `work/candidate/dist/NOX_HELION_PRIVATE_CANDIDATE.exe` | 79,088,677 B | `93a329ba1ece9cfd66951b377e04e9c1166ec6ba3ce13a5911ba8e36de99dfb8` | Main desktop candidate |
| `work/candidate/dist/NOX_HELION_BACKGROUND_CANDIDATE.exe` | 9,431,904 B | `a92594e1f0d349c2e7b8903655a69dace5f8e096557ebda82616d7e6d0ad40b7` | Optional background worker candidate |
| `work/candidate/launch_background_user.ps1` | 1,000 B | `f77f522b40762b85a4b52119e12d3ac190832034c8408d043efe5dc2b96f29b4` | Owner-invoked background launcher |
| `work/candidate/register_windows_background.ps1` | 2,678 B | `ee0e9e7daae9e284a487712775797f6fd15fbe019f7c1015fb4b1dbc2fc8ddfb` | Optional per-user task registration |
| `work/candidate/unregister_windows_background.ps1` | 839 B | `a99ff8136dd88e8bd1bb9898c29f36acbaad6ddad7ab50a4b22b6b96d8e63a13` | Remove optional per-user task |
| `work/candidate/CANDIDATE_README.txt`, `BUILD_STATUS.txt`, `C_RELEASE_SPRINT_BUILD_RECEIPT.json` | included | See artifact | Candidate status and evidence; retain with the EXEs |
| `work/candidate/DEPENDENCY_NOTICES.txt`, `QA_DEPENDENCY_NOTICES.txt` | included | See artifact | Third-party notices; retain with the EXEs |

Use the files directly from the workflow ZIP; do not rename the EXEs. The ZIP also contains CI evidence and QA wheelhouse files, which are build evidence rather than files required to launch the candidate.

## Pinned build environment

- Windows x64 hosted runner: Windows Server 2025; Python `3.12.10` x64; PyInstaller `6.16.0`.
- The build venv used pinned versions: `altgraph 0.17.4`, `cffi 2.0.0`, `colorama 0.4.6`, `cryptography 50.0.2`, `iniconfig 2.3.1`, `numpy 2.2.6`, `packaging 25.0`, `pefile 2023.2.7`, `pluggy 1.7.0`, `pycparser 2.23`, `Pygments 2.21.0`, `PyInstaller 6.16.0`, `pyinstaller-hooks-contrib 2025.8`, `PyJWT 2.15.1`, `pytest 8.4.2`, `pywin32-ctypes 0.2.3`, `setuptools 80.9.0`, and `trimesh 4.7.3`.
- Separate QA lock SHA-256: `dc65dacdb5367737205a7bbab25d5c94f56c6ec758e8978584cdbf0fec6d64fe`; **10/10 pinned QA wheels** were hash-verified and installed in the isolated build venv (`qa_dependencies_ready=true`). They are build/QA environment inputs, not a requirement to install on the target PC merely to start the EXE.

## Bundled and external prerequisites

The workflow ZIP bundles the two candidate EXEs, background scripts, notices, and receipts listed above. The fast candidate receipt records `no_downloads=true`. No model/provider payload, owner-selected runtime profile, credentials, rights-cleared media pack, consent/revoke receipts, or external trust witness is evidenced as bundled. Do not treat the QA wheelhouse as an AI model or runtime configuration.

Required host class evidenced by the build: Windows x64. Minimum Windows release and clean-machine resource independence have not been established. The candidate was built successfully, but its source QA and native smoke are `NOT_RUN`; release acceptance is false. Real AI, Persona/history isolation, STOP, and standalone clean-folder operation therefore remain unverified.

## Launch from an extracted folder

1. Extract the workflow ZIP, then copy the contents of `work/candidate/dist/` plus the listed support files into one folder outside any source checkout.
2. Open PowerShell in that folder and run:

   ```powershell
   Set-Location -LiteralPath 'C:\path\to\candidate'
   .\NOX_HELION_PRIVATE_CANDIDATE.exe
   ```

3. Keep the receipt and notice files beside the candidate for traceability. Do not register the background worker automatically: its registration is explicitly owner-opt-in. If separately authorized, keep `NOX_HELION_BACKGROUND_CANDIDATE.exe` and its scripts together; registration/launch behavior is not validated by this candidate build.

The command above is a launch instruction, not evidence that clean-folder execution succeeds. Do not label this candidate a release or claim a live AI response from it.
