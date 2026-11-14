# NOX V66 Windows owner-side import of existing encrypted Drive V60/V61.
# Copies only encrypted ZIP backups; never decrypts or deletes source files.
# Requires authenticated Google Drive for Desktop OR an already configured rclone remote.
[CmdletBinding()]
param([string]$TargetRoot='',[string]$SourceFolder='',[string]$RcloneRemote='')
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
Add-Type -AssemblyName System.IO.Compression
$folderID='1CK8B-KOasziDFMvcamt8vuNQxpjpmTuR'
$files=@(
 @{Name='NOX_V60_ENCRYPTED_S03_GENESIS_WEB_20261114.zip';Bytes=[long]8109924;ZipSHA='367ce4efbad525f998f282efd63b257413235f5f3f0378ccb707932e1d5f62dc';Part=0;PartSHA=''},
 @{Name='NOX_V61_CIPHERTEXT_PART_01_20261114.zip';Bytes=[long]75001450;ZipSHA='';Part=1;PartSHA='5c0583568fca3ae898a6854dffe9601d6f769e4f1e54586f3ba252a331e68ecf'},
 @{Name='NOX_V61_CIPHERTEXT_PART_02_20261114.zip';Bytes=[long]75001450;ZipSHA='';Part=2;PartSHA='9e9d70d378734e08a03dd9d7b39653be164cb40f27597af0dd29839de0687509'},
 @{Name='NOX_V61_CIPHERTEXT_PART_03_20261114.zip';Bytes=[long]75001450;ZipSHA='';Part=3;PartSHA='401cdd7b7c0b5aa485b3dadd78a63e8fbd7fca791807c558acd35a546da876e3'},
 @{Name='NOX_V61_CIPHERTEXT_PART_04_20261114.zip';Bytes=[long]40877534;ZipSHA='';Part=4;PartSHA='6ffb6653034cb1f1aa96dbbcd5784a4479db159070375992177389b74e761717'},
 @{Name='NOX_V69_OWNER_ENCRYPTED_COLD_INCOMING_20261114.zip';Bytes=[long]85241014;ZipSHA='3cc65b5ddc113316351314328177b7d46644ec09adfabd11616b81ba82ed536d';Part=0;PartSHA=''}
)
function Sha([string]$file){return (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()}
function CheckPart([string]$zipFile,[int]$n,[string]$expected) {
 $zip=[System.IO.Compression.ZipFile]::OpenRead($zipFile)
 try {
   $entry=$zip.GetEntry(('NOX_V61_CIPHER.part{0:D2}' -f $n))
   if($null -eq $entry){throw 'HOLD_PART_MISSING'}
   $size=if($n -eq 4){[long]40876084}else{[long]75000000}
   if($entry.Length -ne $size){throw 'HOLD_PART_SIZE'}
   $stream=$entry.Open()
   try {
      $hasher=[System.Security.Cryptography.SHA256]::Create()
      try{$actual=([BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-','').ToLowerInvariant()}
      finally{$hasher.Dispose()}
   }finally{$stream.Dispose()}
   if($actual -ne $expected){throw 'HOLD_PART_SHA256'}
 } finally {$zip.Dispose()}
}
if(-not $TargetRoot){
 $disks=@(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' |
   Where-Object {[long]$_.FreeSpace -gt 800000000} |
   Sort-Object @{Expression={if($_.DeviceID -eq $env:SystemDrive){0}else{1}};Descending=$true},
               @{Expression={[long]$_.FreeSpace};Descending=$true})
 if($disks.Count -eq 0){throw 'HOLD_NO_LOCAL_PC_DISK_SPACE'}
 $TargetRoot=Join-Path ($disks[0].DeviceID + '\') 'NOX_HELION\OFFSITE\V60_V61_20261114'
}
$TargetRoot=[IO.Path]::GetFullPath($TargetRoot)
if($TargetRoot.StartsWith('\\')){throw 'HOLD_NETWORK_DESTINATION_NOT_REQUESTED'}
New-Item -ItemType Directory -Path $TargetRoot -Force | Out-Null
if(-not $SourceFolder){
 foreach($disk in @(Get-PSDrive -PSProvider FileSystem)){
  foreach($prefix in @('My Drive','Мой диск','MyDrive','')){
   $parent=Join-Path $disk.Root $prefix
   $candidate=Join-Path (Join-Path $parent 'NOX HELION EXPRESS INTEGRATOR') '06_ПАКЕТЫ_И_ЭКСПОРТЫ'
   if(Test-Path -LiteralPath (Join-Path $candidate $files[0].Name) -PathType Leaf){
       $SourceFolder=$candidate;break
   }
  }
  if($SourceFolder){break}
 }
}
if(-not $SourceFolder -and -not $RcloneRemote){
 throw 'HOLD_GOOGLE_DRIVE_DESKTOP_OR_SIGNED_IN_RCLONE_REQUIRED'
}
if($RcloneRemote){
 $RcloneRemote=$RcloneRemote.TrimEnd(':')
 if($RcloneRemote -notmatch '^[A-Za-z0-9_-]{1,50}$'){throw 'HOLD_RCLONE_REMOTE_NAME'}
 if(-not (Get-Command rclone -ErrorAction SilentlyContinue)){throw 'HOLD_RCLONE_NOT_INSTALLED'}
}
$copies=@()
foreach($f in $files){
 $dest=Join-Path $TargetRoot $f.Name
 $verify={
   if(-not (Test-Path -LiteralPath $dest -PathType Leaf)){return $false}
   if((Get-Item -LiteralPath $dest).Length -ne $f.Bytes){return $false}
   if($f.Part -eq 0){return ((Sha $dest) -eq $f.ZipSHA)}
   try {CheckPart $dest $f.Part $f.PartSHA;return $true}catch{return $false}
 }
 $good=& $verify
 if(-not $good){
  if(Test-Path -LiteralPath $dest){throw ('HOLD_UNVERIFIED_EXISTING_DEST_'+$f.Name)}
  $tmp=$dest+'.nox-v66-partial'
  if(Test-Path -LiteralPath $tmp){throw 'HOLD_PARTIAL_PRESENT'}
  if($SourceFolder){
   $origin=Join-Path $SourceFolder $f.Name
   if(-not (Test-Path -LiteralPath $origin -PathType Leaf)){throw 'HOLD_SOURCE_DRIVE_MISSING'}
   Copy-Item -LiteralPath $origin -Destination $tmp
  }else{
   & rclone copyto ('{0}:{1}' -f $RcloneRemote,$f.Name) $tmp '--drive-root-folder-id' $folderID '--retries' '2'
   if($LASTEXITCODE -ne 0){throw 'HOLD_RCLONE_TRANSFER'}
  }
  if((Get-Item -LiteralPath $tmp).Length -ne $f.Bytes){throw 'HOLD_DEST_SIZE'}
  if($f.Part -eq 0){if((Sha $tmp) -ne $f.ZipSHA){throw 'HOLD_V60_ZIP_SHA'}}
  else {CheckPart $tmp $f.Part $f.PartSHA}
  Move-Item -LiteralPath $tmp -Destination $dest
 }
 $copies+=@{name=$f.Name;bytes=$f.Bytes;verified=$true}
 Write-Host ('OFFSITE_ENCRYPTED_COPY_PASS '+$f.Name)
}
$receipt=[ordered]@{
 schema='NOX_PC_OFFSITE_ENCRYPTED_COPIES_V69'
 verified_utc=[DateTimeOffset]::UtcNow.ToString('o')
 target=$TargetRoot
 verified_files=$copies
 v61_ciphertext_whole_sha256='389a1378990a8cc55be09edc7dddecea746ba144ff82011ad71812d1fd9bd6b6'
 v69_ciphertext_sha256='026541c57fc41e11f1d7b77d9dab67c3ada0e28e8f7a953d5672447bd5763699'
 whole_v61_ciphertext_reassembled=$false
 owner_private_key_decryption_verified=$false
 source_vast_files_deleted=$false
}
$marker=Join-Path $TargetRoot 'NOX_V69_PC_OFFSITE_SHA_RECEIPT.json'
$receipt|ConvertTo-Json -Depth 6|Set-Content -LiteralPath ($marker+'.partial') -Encoding UTF8
Move-Item -LiteralPath ($marker+'.partial') -Destination $marker -Force
Write-Host ('NOX_PC_ENCRYPTED_BACKUP_VERIFIED '+$TargetRoot)
