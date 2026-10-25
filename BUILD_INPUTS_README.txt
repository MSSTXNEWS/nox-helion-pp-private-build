NOX HELION PRE-PRE — PRIVATE WINDOWS CANDIDATE BUILD

This repository is private and exists only to run the authorized Windows candidate build.
The manual workflow is pp-windows-candidate.yml under .github/workflows.

Canonical source:
- Reassemble source_00.part, source_01.part, source_02.part in that order.
- Expected ZIP size: 60,364,346 bytes.
- Expected SHA-256: ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a.
- Expected unpatched Git tree: 1454257c66d5107b12091b8e81706e51b0cfb672.

Build repair:
- NOX_A04_BUILD_PATCH.zip SHA-256: 37078f0105f42ff9964a533399a9a71769d0517e8f0e3f49e3e7266ae28eb4eb.
- Apply only after the base-tree check above.
- Expected patched Git tree: d16663f9fd26aa0eab90270fff1bb65bc3f805e6.

Dependencies:
- NOX_PP_BUILD_WHEELHOUSE_18.zip SHA-256: 2b6291a45f7c03c583e2073d069f6a1de5832d3bc54b33150f940b4aa53598ff.
- Its 11 shared wheels byte-match the corrected PP wheelhouse; seven additional pinned wheels provide pytest/trimesh and their dependencies.
- The R1 source-and-toolchain lock is excluded and must not be used for PRE-PRE. The bundled lock pins the 18 offline build wheels only.
- `requirements-qa-win64-hashed.txt` adds ten exact, SHA-pinned Windows-compatible wheels: Pillow 13.0.0, python-docx 1.2.0, python-pptx 1.0.2, XlsxWriter 3.3.0, ReportLab 5.1.0, charset-normalizer 3.5.2, pypdf 6.21.2, lxml 6.1.3, typing_extensions 4.16.0, and tzdata 2026.5.
- On Windows, the runner downloads only binary wheels with `--require-hashes`, verifies each SHA, then installs from its local QA wheel cache with `--no-index` into the isolated interpreter before PyInstaller and the final source QA. This makes the E11 PPTX/PDF imports available to the GUI EXE analysis as well as to QA. The exact lock and wheels are retained in `ci-evidence`; `QA_DEPENDENCY_NOTICES.txt` is copied into the candidate output.

The workflow retains a pre-release candidate and exact logs even when later QA fails.
EXE presence is not release acceptance. Product payload, real AI runtime, profile/rights gates,
full mandatory GUI scenarios, and owner acceptance remain separate release gates.
