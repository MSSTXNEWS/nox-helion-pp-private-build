param([Parameter(Mandatory=$true)][string]$Source)
$ErrorActionPreference='Stop'
$p=(Resolve-Path -LiteralPath $Source).Path
$s=[IO.File]::ReadAllText($p)
$pre='    private readonly bool selfTestRequested = NativeSelfTestRequested || UiSmokeRequested;'
if (!$s.Contains($pre) -or $s.Contains('ProtocolFixtureRequested')) { throw 'NOX_FIXTURE_PREIMAGE_HOLD' }
$s=$s.Replace($pre,$pre+[Environment]::NewLine+
'    private static readonly bool ProtocolFixtureRequested = NativeSelfTestRequested && Environment.GetCommandLineArgs().Any('+[Environment]::NewLine+
'        arg => arg.Equals("--nox-protocol-fixture", StringComparison.OrdinalIgnoreCase));')
$old='                checks, nativeCoreAccepted = accepted, fullV16Accepted = false,'
$new='                checks, nativeCoreAccepted = accepted && !ProtocolFixtureRequested,'+[Environment]::NewLine+
'                nativeProtocolAccepted = accepted,'+[Environment]::NewLine+
'                providerEvidence = ProtocolFixtureRequested ? "SYNTHETIC_LOOPBACK_FIXTURE" : "REAL_LOCAL_QWEN",'+[Environment]::NewLine+
'                fullV16Accepted = false,'
if (!$s.Contains($old)) { throw 'NOX_FIXTURE_RECEIPT_PREIMAGE_HOLD' }
$s=$s.Replace($old,$new)
[IO.File]::WriteAllText($p,$s,[Text.UTF8Encoding]::new($false))
Write-Host 'NOX_FIXTURE_RECEIPT_SEPARATION_APPLIED'
