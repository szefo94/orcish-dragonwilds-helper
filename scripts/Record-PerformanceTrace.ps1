[CmdletBinding()]
param(
    [string[]]$Profiles = @("GeneralProfile","CPU")
)

# Records a Windows Performance Recorder (ETW) trace into data\traces for WPA analysis.
# WPR is built into Windows 10/11; WPA (the viewer) comes with Setup option 7.

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$TraceDir = Join-Path $RepoRoot "data\traces"

function Write-Ok([string]$Text) { Write-Host ("[OK]   " + $Text) -ForegroundColor Green }
function Write-Bad([string]$Text) { Write-Host ("[MISS] " + $Text) -ForegroundColor Red }

function Exit-WithPause([int]$Code) {
    Write-Host ""
    Write-Host "Press Enter to close this window."
    [void](Read-Host)
    exit $Code
}

function Test-Admin {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Host "Windows Performance Recorder needs Administrator access. Requesting elevation..."
    $p = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -ArgumentList @(
        "-NoProfile","-ExecutionPolicy","Bypass","-File",$PSCommandPath,"-Profiles",($Profiles -join ","))
    exit $p.ExitCode
}

# -File passes a comma-joined list as one string across the elevation boundary.
$Profiles = @($Profiles | ForEach-Object { $_ -split "," } | Where-Object { $_ })

$wpr = Get-Command wpr.exe -ErrorAction SilentlyContinue
if (-not $wpr) {
    Write-Bad "wpr.exe not found. It ships with Windows 10/11; run Setup.cmd option 7 to install the Windows Performance Toolkit."
    Exit-WithPause 2
}

New-Item -ItemType Directory -Force -Path $TraceDir | Out-Null
$out = Join-Path $TraceDir ("orcish_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".etl")

$startArgs = @()
foreach ($name in $Profiles) { $startArgs += @("-start",$name) }
$startArgs += "-filemode"
& $wpr.Source @startArgs
if ($LASTEXITCODE -ne 0) {
    Write-Bad "wpr could not start (exit $LASTEXITCODE). If another trace is running, 'wpr -cancel' stops it."
    Exit-WithPause 3
}

$stopped = $false
try {
    Write-Ok "Recording ($($Profiles -join ', ')). Play the scene you want to measure in Dragonwilds."
    Write-Host "Keep the recording short (under a few minutes); traces grow quickly."
    Write-Host ""
    Write-Host "Press Enter to stop and save..."
    [void](Read-Host)
    & $wpr.Source -stop $out "Orcish research trace"
    if ($LASTEXITCODE -ne 0) { throw "wpr -stop exited with $LASTEXITCODE" }
    $stopped = $true
    Write-Ok "Trace saved: $out"
    Write-Host "Open it with WPA (Windows Performance Analyzer)."
} finally {
    # Never leave a kernel trace session running if the window is closed or stop failed.
    if (-not $stopped) { & $wpr.Source -cancel 2>$null | Out-Null }
}
Exit-WithPause 0
