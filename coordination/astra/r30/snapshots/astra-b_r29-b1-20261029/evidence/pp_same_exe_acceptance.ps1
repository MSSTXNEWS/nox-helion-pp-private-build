[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$LaunchEvidenceJson,

    [Parameter(Mandatory = $true)]
    [string]$SourceFreezeJson,

    [Parameter(Mandatory = $true)]
    [string]$PortableManifest,

    [Parameter(Mandatory = $true)]
    [string]$QwenBindingJson,

    [string]$EvidenceOut = "pp-c2-runtime-qa-gate-40210839317.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# PP-ONE-037 / C2 / RUNTIME-QA. Receipt-only gate; it never launches the EXE.
# Source-tree and Drive bindings are taken from the supplied manifests, then cross-bound.
$Expected = [ordered]@{
    workflowRunId = 40210839317
    artifactId = 12605282328
    artifactName = 'PP-001-C1-R3-Windows-candidate-40210839317'
    artifactSha256 = 'f7b57520904cb60e17ce91737bb9f2f8af583a4ab769734a851551fa9f4eb625'
    sourceCommit = 'ca1a876018655b7b3d12c7fb8f273def8d1e45ad'
    launchEvidenceSha256 = 'ea4b899c4afa283a617fb43e3b983f987e9f2770860ed051fbc45a3ef91766b5'
    launchEvidenceRunId = 40213466755
    launchEvidenceArtifactId = 12606886034
    launchEvidenceArtifactSha256 = 'e1e81a02b38cdd67aeff3c1799c2dcd986ea8b1d34b0837f85decadbe7bd54a6'
    sourceFreezeManifestId = '1IU-jzYB0xgSTjNd-6cUXjTq-9c6JluDZ'
    sourceFreezeManifestSha256 = '3bbb96a96eb2dcbc4e6c8ea2518417c01178d3fcfdd71776c0eb003af0e7f01b'
    portableManifestId = '1WLRl2k06YOzK8YClxmenNKgecXZ3sVE8'
    qwenBindingId = '1O_punSWA7PvY0QxNTqM_kK-5B2_Qj670'
    acceptanceGateId = '1kPW_9ju_OZW7J325ef2cBSYZWERQP6CE'
    candidateDriveId = '16k8KatJ3vHhbce0hcEwI-SgF5ap6yNDD'
    requiredExe = 'NOX_HELION_PRIVATE_CANDIDATE.exe'
    requiredExeBytes = 79088677
    requiredExeSha256 = '93a329ba1ece9cfd66951b377e04e9c1166ec6ba3ce13a5911ba8e36de99dfb8'
    expectedQwenLayerSha256 = 'c5396e06af294bd101b30dce59131a76d2b773e76950acc870eda801d3ab0515'
    expectedQwenLayerBytes = 397807936
    requirementRefs = @(
        'MAIN_PREPRE!A59:C59 #27 — new product-bearing EXE',
        'MAIN_PREPRE!A60:C60 #28 — real AI, Persona/history isolation, STOP, GUI and WOW',
        'MAIN_PREPRE!A61:C61 #29 — exact source/TREE/SHA, actual checks, independent acceptance',
        'MAIN_PREPRE!A79:C79 #47 — distinguish prepared/integrated/checked stages',
        'MAIN_PREPRE!A83:C83 #51 — GUI→handler→real provider→response/history/STOP',
        'MAIN_PREPRE!A84:C84 #52 — run from outside checkout without hidden local inputs',
        'MAIN_PREPRE!A85:C85 #53 — preserve the last working build'
    )
}

function Get-RequiredField {
    param([object]$Object, [string]$Name)
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        throw "HOLD: required manifest/evidence field '$Name' is absent."
    }
    return $property.Value
}

foreach ($inputPath in @($LaunchEvidenceJson, $SourceFreezeJson, $PortableManifest, $QwenBindingJson)) {
    if (-not (Test-Path -LiteralPath $inputPath -PathType Leaf)) {
        throw "HOLD: required input is absent: '$inputPath'. No application or tests were run."
    }
}

$launchPath = (Resolve-Path -LiteralPath $LaunchEvidenceJson).Path
$sourcePath = (Resolve-Path -LiteralPath $SourceFreezeJson).Path
$portablePath = (Resolve-Path -LiteralPath $PortableManifest).Path
$qwenPath = (Resolve-Path -LiteralPath $QwenBindingJson).Path

$rawLaunchSha256 = (Get-FileHash -LiteralPath $launchPath -Algorithm SHA256).Hash.ToLowerInvariant()
$sourceFreezeSha256 = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
$portableManifestSha256 = (Get-FileHash -LiteralPath $portablePath -Algorithm SHA256).Hash.ToLowerInvariant()
$qwenBindingSha256 = (Get-FileHash -LiteralPath $qwenPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($rawLaunchSha256 -ne $Expected.launchEvidenceSha256) {
    throw "HOLD: raw launch-evidence.json SHA mismatch. Expected $($Expected.launchEvidenceSha256); received $rawLaunchSha256."
}
if ($sourceFreezeSha256 -ne $Expected.sourceFreezeManifestSha256) {
    throw "HOLD: source-freeze manifest SHA mismatch. Expected $($Expected.sourceFreezeManifestSha256); received $sourceFreezeSha256."
}

$launch = Get-Content -LiteralPath $launchPath -Raw | ConvertFrom-Json
$sourceFreeze = Get-Content -LiteralPath $sourcePath -Raw | ConvertFrom-Json
$portableText = Get-Content -LiteralPath $portablePath -Raw
$qwen = Get-Content -LiteralPath $qwenPath -Raw | ConvertFrom-Json

# Map the actual Win64 launch-evidence.json snake_case schema.
$launchStatus = [string](Get-RequiredField $launch 'status')
$sourceRunId = [long](Get-RequiredField $launch 'source_run_id')
$artifactId = [long](Get-RequiredField $launch 'artifact_id')
$expectedZipSha = ([string](Get-RequiredField $launch 'expected_zip_sha256')).ToLowerInvariant()
$actualZipSha = ([string](Get-RequiredField $launch 'actual_zip_sha256')).ToLowerInvariant()
$sourceCommit = ([string](Get-RequiredField $launch 'source_commit')).ToLowerInvariant()
$exeName = [string](Get-RequiredField $launch 'exact_exe_name')
$exePath = [string](Get-RequiredField $launch 'exact_exe_path')
$exeBytes = [long](Get-RequiredField $launch 'exact_exe_bytes')
$exeSha = ([string](Get-RequiredField $launch 'exact_exe_sha256')).ToLowerInvariant()
$processStartedUtc = [string](Get-RequiredField $launch 'process_started_utc')
$processId = [long](Get-RequiredField $launch 'process_id')
$processAlive = [bool](Get-RequiredField $launch 'process_alive_after_observation')

# Derive sourceTree and Drive bindings from the supplied manifests, not constants alone.
$freezeWorkflow = Get-RequiredField $sourceFreeze 'workflow_run'
$freezeArtifact = Get-RequiredField $sourceFreeze 'artifact'
$freezeInputs = Get-RequiredField $sourceFreeze 'pinned_build_inputs'
$freezeRelated = Get-RequiredField $sourceFreeze 'related_drive_files'
$freezeStatus = Get-RequiredField $sourceFreeze 'status'
$sourceTree = ([string](Get-RequiredField $freezeInputs 'patched_tree_expected')).ToLowerInvariant()
$freezeExe = @((Get-RequiredField $freezeArtifact 'executables') | Where-Object { $_.name -eq $Expected.requiredExe })
if ($freezeExe.Count -ne 1) {
    throw "HOLD: source-freeze manifest must contain exactly one $($Expected.requiredExe) entry."
}
$manifestExe = $freezeExe[0]
$candidateDriveId = [string](Get-RequiredField $freezeArtifact 'drive_file_id')
$portableManifestId = [string](Get-RequiredField $freezeRelated 'portable_manifest_id')
$qwenBindingId = [string](Get-RequiredField $freezeRelated 'qwen_layer_binding_manifest_id')
$acceptanceGateId = [string](Get-RequiredField $freezeRelated 'acceptance_gate_id')

# Required cross-source bindings: source freeze ↔ launch receipt ↔ portable/Qwen manifests.
$checks = @(
    [pscustomobject]@{ Name = 'launch status'; Actual = $launchStatus; Expected = 'PROCESS_STARTED' },
    [pscustomobject]@{ Name = 'launch source run'; Actual = [string]$sourceRunId; Expected = [string]$Expected.workflowRunId },
    [pscustomobject]@{ Name = 'launch artifact'; Actual = [string]$artifactId; Expected = [string]$Expected.artifactId },
    [pscustomobject]@{ Name = 'launch expected ZIP SHA'; Actual = $expectedZipSha; Expected = $Expected.artifactSha256 },
    [pscustomobject]@{ Name = 'launch actual ZIP SHA'; Actual = $actualZipSha; Expected = $Expected.artifactSha256 },
    [pscustomobject]@{ Name = 'launch source commit'; Actual = $sourceCommit; Expected = $Expected.sourceCommit },
    [pscustomobject]@{ Name = 'launch EXE name'; Actual = $exeName; Expected = $Expected.requiredExe },
    [pscustomobject]@{ Name = 'launch EXE path leaf'; Actual = [System.IO.Path]::GetFileName($exePath); Expected = $Expected.requiredExe },
    [pscustomobject]@{ Name = 'launch EXE bytes'; Actual = [string]$exeBytes; Expected = [string]$Expected.requiredExeBytes },
    [pscustomobject]@{ Name = 'launch EXE SHA'; Actual = $exeSha; Expected = $Expected.requiredExeSha256 },
    [pscustomobject]@{ Name = 'source-freeze run'; Actual = [string](Get-RequiredField $freezeWorkflow 'run_id'); Expected = [string]$Expected.workflowRunId },
    [pscustomobject]@{ Name = 'source-freeze artifact'; Actual = [string](Get-RequiredField $freezeArtifact 'artifact_id'); Expected = [string]$Expected.artifactId },
    [pscustomobject]@{ Name = 'source-freeze ZIP SHA'; Actual = ([string](Get-RequiredField $freezeArtifact 'zip_sha256')).ToLowerInvariant(); Expected = $Expected.artifactSha256 },
    [pscustomobject]@{ Name = 'source-freeze commit'; Actual = ([string](Get-RequiredField $freezeWorkflow 'head_commit')).ToLowerInvariant(); Expected = $Expected.sourceCommit },
    [pscustomobject]@{ Name = 'source-freeze tree shape'; Actual = [bool]($sourceTree -match '^[a-f0-9]{40}$'); Expected = $true },
    [pscustomobject]@{ Name = 'source-freeze candidate Drive ID'; Actual = $candidateDriveId; Expected = $Expected.candidateDriveId },
    [pscustomobject]@{ Name = 'source-freeze portable ID'; Actual = $portableManifestId; Expected = $Expected.portableManifestId },
    [pscustomobject]@{ Name = 'source-freeze Qwen binding ID'; Actual = $qwenBindingId; Expected = $Expected.qwenBindingId },
    [pscustomobject]@{ Name = 'source-freeze acceptance gate ID'; Actual = $acceptanceGateId; Expected = $Expected.acceptanceGateId },
    [pscustomobject]@{ Name = 'source-freeze EXE bytes'; Actual = [string](Get-RequiredField $manifestExe 'bytes'); Expected = [string]$Expected.requiredExeBytes },
    [pscustomobject]@{ Name = 'source-freeze EXE SHA'; Actual = ([string](Get-RequiredField $manifestExe 'sha256')).ToLowerInvariant(); Expected = $Expected.requiredExeSha256 },
    [pscustomobject]@{ Name = 'portable run binding'; Actual = [bool]($portableText.Contains([string]$Expected.workflowRunId)); Expected = $true },
    [pscustomobject]@{ Name = 'portable artifact binding'; Actual = [bool]($portableText.Contains([string]$Expected.artifactId)); Expected = $true },
    [pscustomobject]@{ Name = 'portable ZIP SHA binding'; Actual = [bool]($portableText.Contains($Expected.artifactSha256)); Expected = $true },
    [pscustomobject]@{ Name = 'portable source-tree binding'; Actual = [bool]($portableText.Contains($sourceTree)); Expected = $true },
    [pscustomobject]@{ Name = 'portable EXE SHA binding'; Actual = [bool]($portableText.Contains($Expected.requiredExeSha256)); Expected = $true },
    [pscustomobject]@{ Name = 'Qwen schema'; Actual = [string](Get-RequiredField $qwen 'schema'); Expected = 'PP_QWEN_LAYER_DRIVE_BINDING_V1' },
    [pscustomobject]@{ Name = 'Qwen layer bytes'; Actual = [string](Get-RequiredField (Get-RequiredField $qwen 'model') 'layer_size_bytes'); Expected = [string]$Expected.expectedQwenLayerBytes },
    [pscustomobject]@{ Name = 'Qwen layer SHA'; Actual = ([string](Get-RequiredField (Get-RequiredField $qwen 'model') 'layer_sha256')).ToLowerInvariant(); Expected = $Expected.expectedQwenLayerSha256 }
)
foreach ($check in $checks) {
    if ($check.Actual -ne $check.Expected) {
        throw "HOLD: '$($check.Name)' mismatch; expected '$($check.Expected)', received '$($check.Actual)'. No application or tests were run."
    }
}
if (-not $processAlive -or $processId -le 0 -or [string]::IsNullOrWhiteSpace($processStartedUtc)) {
    throw 'HOLD: launch process start/alive evidence is absent or invalid. No application or tests were run by this gate.'
}

$result = [ordered]@{
    gateStatus = 'PASS'
    productAcceptance = 'HOLD'
    reason = 'Raw launch receipt is cryptographically linked by SHA-256 and matches the source-freeze, portable, and Qwen manifest bindings. This gate validates provenance/process-start only; source QA, native smoke, GUI/window, real AI, Persona/history, STOP, clean-folder, and independent product acceptance remain open.'
    task = 'PP-ONE-037 / C2 / RUNTIME-QA'
    rawLaunchEvidence = @{ path = $launchPath; sha256 = $rawLaunchSha256 }
    launchEvidenceArtifact = @{ runId = $Expected.launchEvidenceRunId; artifactId = $Expected.launchEvidenceArtifactId; zipSha256 = $Expected.launchEvidenceArtifactSha256 }
    sourceFreezeManifest = @{ id = $Expected.sourceFreezeManifestId; path = $sourcePath; sha256 = $sourceFreezeSha256 }
    portableManifest = @{ id = $portableManifestId; path = $portablePath; sha256 = $portableManifestSha256 }
    qwenBindingManifest = @{ id = $qwenBindingId; path = $qwenPath; sha256 = $qwenBindingSha256 }
    acceptanceGateId = $acceptanceGateId
    sourceRunId = $sourceRunId
    workflowArtifactId = $artifactId
    workflowArtifactName = $Expected.artifactName
    workflowZipSha256 = $actualZipSha
    sourceCommit = $sourceCommit
    sourceTree = $sourceTree
    candidateDriveId = $candidateDriveId
    exeName = $exeName
    exePath = $exePath
    exeBytes = $exeBytes
    exeSha256 = $exeSha
    processStartStatus = $launchStatus
    processStartedUtc = $processStartedUtc
    processId = $processId
    processAliveAfterObservation = $processAlive
    waitForInputIdle = $launch.wait_for_input_idle
    mainWindowHandle = $launch.main_window_handle
    mainWindowTitle = $launch.main_window_title
    sourceQa = [string](Get-RequiredField $freezeStatus 'source_qa')
    nativeSmoke = [string](Get-RequiredField $freezeStatus 'native_smoke')
    aiLayerStatus = [string](Get-RequiredField $freezeStatus 'ai_layer')
    sameExeRuntime = [string](Get-RequiredField $freezeStatus 'same_exe_runtime')
    releaseAccepted = [bool](Get-RequiredField $freezeStatus 'release_accepted')
    requirementRefs = $Expected.requirementRefs
    productTestsRun = $false
}

$outPath = [System.IO.Path]::GetFullPath($EvidenceOut)
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $outPath -Encoding utf8
$result | ConvertTo-Json -Depth 8
Write-Host "Normalized evidence written to $outPath"
