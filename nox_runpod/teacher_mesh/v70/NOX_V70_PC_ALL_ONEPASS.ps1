# NOX V70: ONE Windows invocation copies ALL encrypted archives V60 V61 V69 V70.
# Works only on owner's Windows PC with existing authenticated Drive Desktop or rclone.
# No plaintext decryption, server deletion, scheduler, GPU or remote shell.
[CmdletBinding()]
param([string]$TargetRoot='',[string]$SourceFolder='',[string]$RcloneRemote='')
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
Add-Type -AssemblyName 'System.IO.Compression'
$folderID='1CK8B-KOasziDFMvcamt8vuNQxpjpmTuR'
$checkpointReserveLocal=[long]1300000000
if(-not $TargetRoot){
 $disks=@(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' |
          Where-Object { [long]$_.FreeSpace -ge $checkpointReserveLocal } |
          Sort-Object @{Expression={if($_.DeviceID -eq $env:SystemDrive){0}else{1}};Descending=$true},
                      @{Expression={[long]$_.FreeSpace};Descending=$true})
 if($disks.Count -eq 0){throw 'HOLD_NO_LOCAL_PC_DISK_SPACE'}
 $TargetRoot=Join-Path ($disks[0].DeviceID+'\') 'NOX_HELION\OFFSITE\V70_ONEPASS_20261114'
}
$TargetRoot=[System.IO.Path]::GetFullPath($TargetRoot)
if($TargetRoot.StartsWith('\\')){throw 'HOLD_NETWORK_PC_DRIVE'}
New-Item -Path $TargetRoot -ItemType Directory -Force|Out-Null
if(-not $SourceFolder){
 foreach($d in @(Get-PSDrive -PSProvider FileSystem)){
  foreach($prefix in @('My Drive','Мой диск','MyDrive','')){
   $p=Join-Path $d.Root $prefix
   $p=Join-Path (Join-Path $p 'NOX HELION EXPRESS INTEGRATOR') '06_ПАКЕТЫ_И_ЭКСПОРТЫ'
   if(Test-Path -LiteralPath (Join-Path $p 'NOX_V60_ENCRYPTED_S03_GENESIS_WEB_20261114.zip') -PathType Leaf) {
    $SourceFolder=$p;break
   }
  }
  if($SourceFolder){break}
 }
}
if(-not $SourceFolder -and -not $RcloneRemote){
 if(Get-Command rclone -ErrorAction SilentlyContinue){
  $r=@(& rclone listremotes 2>$null)
  if($LASTEXITCODE -eq 0 -and $r.Count -eq 1 -and $r[0] -match '^[A-Za-z0-9_-]{1,50}:$'){
   $RcloneRemote=$r[0].TrimEnd(':')
  }
 }
}
if(-not $SourceFolder -and -not $RcloneRemote){
 throw 'HOLD_SIGNED_IN_GOOGLE_DRIVE_DESKTOP_OR_RCLONE_REQUIRED'
}
if($RcloneRemote -and $RcloneRemote -notmatch '^[A-Za-z0-9_-]{1,50}$'){
 throw 'HOLD_RCLONE_REMOTE_NOT_TRUSTED'
}
function Get-SHA([string]$p){
 return (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Transfer([string]$name,[string]$destination){
 if(Test-Path -LiteralPath $destination -PathType Leaf){return}
 $part=$destination+'.noxpart'
 if(Test-Path -LiteralPath $part){throw 'HOLD_PRIOR_PARTIAL_DOWNLOAD'}
 if($SourceFolder){
  $src=Join-Path $SourceFolder $name
  if(-not (Test-Path -LiteralPath $src -PathType Leaf)){throw ('HOLD_SOURCE_NOT_IN_DRIVE_'+$name)}
  Copy-Item -LiteralPath $src -Destination $part -ErrorAction Stop
 }else{
  & rclone copyto ('{0}:{1}' -f $RcloneRemote,$name) $part '--drive-root-folder-id' $folderID '--retries' '2'
  if($LASTEXITCODE -ne 0){throw 'HOLD_GOOGLE_RCLONE_COPY'}
 }
 Move-Item -LiteralPath $part -Destination $destination -ErrorAction Stop
}
# First transfer and verify the V60/V61/V69 archives using existing accepted receiver.
$existing=Join-Path $PSScriptRoot 'windows_offsite_receiver.ps1'
if(-not (Test-Path -LiteralPath $existing -PathType Leaf)){throw 'HOLD_EXISTING_V69_RECEIVER_MISSING'}
& $existing -TargetRoot $TargetRoot -SourceFolder $SourceFolder -RcloneRemote $RcloneRemote
$prior=Join-Path $TargetRoot 'NOX_V69_PC_OFFSITE_SHA_RECEIPT.json'
if(-not (Test-Path -LiteralPath $prior)){throw 'HOLD_V60_V61_V69_READBACK'}
$previous=Get-Content -LiteralPath $prior -Raw|ConvertFrom-Json
if($previous.schema -ne 'NOX_PC_OFFSITE_ENCRYPTED_COPIES_V69' -or @($previous.verified_files).Count -ne 6){
 throw 'HOLD_V69_RECEIPT_NOT_ACCEPTED'
}
$srcIndex=$null
$checks=@()
$chunkNames=1..6 | ForEach-Object {'NOX_V70_OWNER_CIPHER_PART_{0:D2}_20261114.zip' -f $_}
$targetChunks=@()
foreach($n in 1..6){
 $zipName=$chunkNames[$n-1]
 $destination=Join-Path $TargetRoot $zipName
 Transfer $zipName $destination
 $zip=[System.IO.Compression.ZipFile]::OpenRead($destination)
 try{
  $indexMember=$zip.GetEntry('NOX_V70_PARTS_INDEX.json')
  $dataMember=$zip.GetEntry(('NOX_V70_CIPHER.part{0:D2}' -f $n))
  if($null -eq $indexMember -or $null -eq $dataMember){throw 'HOLD_V70_ZIP_ENTRIES'}
  $stream=$indexMember.Open()
  try{
   $reader=[System.IO.StreamReader]::new($stream)
   try{$raw=$reader.ReadToEnd()}finally{$reader.Dispose()}
  }finally{$stream.Dispose()}
  $index=$raw|ConvertFrom-Json
  if($index.schema -ne 'NOX_V70_SIX_CIPHER_PARTS_V1' -or $index.part_count -ne 6){
   throw 'HOLD_V70_MANIFEST_SCHEMA'
  }
  if($null -eq $srcIndex){$srcIndex=$raw}else{if($raw -cne $srcIndex){throw 'HOLD_V70_MISMATCHED_MANIFEST'}}
  $record=@($index.parts)[$n-1]
  if($record.name -ne $dataMember.Name -or [long]$record.bytes -ne [long]$dataMember.Length){
   throw 'HOLD_V70_PART_SIZE'
  }
  if([long]$record.bytes -gt 70000000 -or [long]$record.bytes -lt 15000000){
   throw 'HOLD_V70_PART_BOUNDS'
  }
  $source=$dataMember.Open()
  try {
   $sha=[System.Security.Cryptography.SHA256]::Create()
   try{$observed=([BitConverter]::ToString($sha.ComputeHash($source))).Replace('-','').ToLowerInvariant()}
   finally{$sha.Dispose()}
  }finally{$source.Dispose()}
  if($observed -cne [string]$record.sha256){throw 'HOLD_V70_SOURCE_CHUNK_SHA'}
  $targetChunks+=@{name=$zipName;bytes=(Get-Item -LiteralPath $destination).Length;sha256=(Get-SHA $destination)}
  Write-Host ('V70_COPY_AND_CHUNK_SHA_PASS '+$zipName)
 }finally{$zip.Dispose()}
}
$index=$srcIndex|ConvertFrom-Json
if([long]$index.ciphertext_bytes -lt 415000000 -or [long]$index.ciphertext_bytes -gt 435000000){
 throw 'HOLD_V70_CIPHER_SIZE'
}
if([string]$index.ciphertext_sha256 -notmatch '^[a-f0-9]{64}$'){throw 'HOLD_V70_CIPHER_SHA_FORMAT'}
# Reassemble ciphertext once on PC using binary streams, never extracting private weights.
$cipher=Join-Path $TargetRoot 'NOX_V70_COLD_3_ENCRYPTED_20261114.tar.age'
if(Test-Path -LiteralPath $cipher){
 if((Get-SHA $cipher) -cne $index.ciphertext_sha256){throw 'HOLD_EXISTING_V70_ARCHIVE_MISMATCH'}
}else{
 $partial=$cipher+'.noxpart'
 if(Test-Path -LiteralPath $partial){throw 'HOLD_EXISTING_V70_REASSEMBLY_PART'}
 $out=[System.IO.File]::Create($partial)
 try {
  foreach($n in 1..6){
   $z=[System.IO.Compression.ZipFile]::OpenRead((Join-Path $TargetRoot $chunkNames[$n-1]))
   try{
    $part=$z.GetEntry(('NOX_V70_CIPHER.part{0:D2}' -f $n))
    if($null -eq $part){throw 'HOLD_V70_REASSEMBLY_ENTRY'}
    $inputStream=$part.Open()
    try{$inputStream.CopyTo($out)}finally{$inputStream.Dispose()}
   }finally{$z.Dispose()}
  }
 }finally{$out.Dispose()}
 if((Get-Item -LiteralPath $partial).Length -ne [long]$index.ciphertext_bytes -or
    (Get-SHA $partial) -cne $index.ciphertext_sha256){
   throw 'HOLD_V70_REASSEMBLY_SHA'
 }
 Move-Item -LiteralPath $partial -Destination $cipher
}
$accepted=[ordered]@{
 schema='NOX_PC_ONEPASS_V70_ALL_ENCRYPTED_OFFSITE_SHA_VERIFIED'
 verified_utc=[DateTimeOffset]::UtcNow.ToString('o')
 target_root=$TargetRoot
 old_v60_v61_v69_receipt=$prior
 v70_chunks_verified=$targetChunks
 v70_cipher_sha256=$index.ciphertext_sha256
 v70_cipher_size_bytes=$index.ciphertext_bytes
 original_vast_sources_deleted=$false
 actual_owner_key_decryption_verified=$false
 all_model_weights_backed_up=$false
}
$receipt=Join-Path $TargetRoot 'NOX_PC_V70_ALL_OFFSITE_SHA_RECEIPT.json'
$accepted|ConvertTo-Json -Depth 8|Set-Content -LiteralPath ($receipt+'.tmp') -Encoding UTF8
Move-Item -LiteralPath ($receipt+'.tmp') -Destination $receipt -Force
Write-Host ('NOX_V70_PC_ONEPASS_CIPHERTEXT_SHA_VERIFIED '+$TargetRoot)
Write-Host 'NOX_V70_OWNER_PRIVATE_KEY_RESTORE_UNVERIFIED'
