[CmdletBinding()]
param(
    [string]$GameExe = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DownloadRoot = Join-Path $RepoRoot "tools\external\downloads"
$TelemetryDir = Join-Path $RepoRoot "data\ue4ss"
New-Item -ItemType Directory -Force -Path $DownloadRoot,$TelemetryDir | Out-Null

function Write-Section([string]$Text) { Write-Host ""; Write-Host ("=== " + $Text + " ===") -ForegroundColor Cyan }
function Write-Ok([string]$Text) { Write-Host ("[OK]   " + $Text) -ForegroundColor Green }
function Write-Warn([string]$Text) { Write-Host ("[WARN] " + $Text) -ForegroundColor Yellow }
function Write-Bad([string]$Text) { Write-Host ("[MISS] " + $Text) -ForegroundColor Red }

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Ensure-Elevated {
    if (Test-Admin) { return }
    Write-Host "Administrator access is required to update the WindowsApps Dragonwilds folder."
    Write-Host "Requesting elevation..."
    $args = @("-NoProfile","-ExecutionPolicy","Bypass","-File",$PSCommandPath)
    if ($GameExe) { $args += @("-GameExe",$GameExe) }
    $args += "-NoExit"
    $p = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -ArgumentList $args
    exit $p.ExitCode
}

function Resolve-DragonwildsExe {
    if ($GameExe) {
        if (-not (Test-Path $GameExe)) { throw "-GameExe does not exist: $GameExe" }
        if ([IO.Path]::GetFileName($GameExe) -ine "RSDragonwilds-WinGDK-Shipping.exe") {
            throw "This recovery installer is only for RSDragonwilds-WinGDK-Shipping.exe."
        }
        return (Resolve-Path $GameExe).Path
    }

    $proc = Get-Process -Name "RSDragonwilds-WinGDK-Shipping" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($proc) {
        try {
            $p = $proc.MainModule.FileName
            if ($p -and (Test-Path $p)) { return $p }
        } catch {}
    }

    $wa = Join-Path $env:ProgramFiles "WindowsApps"
    if (Test-Path $wa) {
        $hit = Get-ChildItem $wa -Filter "RSDragonwilds-WinGDK-Shipping.exe" -File -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

function Get-ExperimentalArchive {
    Write-Section "Download current experimental UE4SS"
    $headers = @{ "User-Agent" = "Orcish-UE4SS-Recovery" }
    $release = Invoke-RestMethod -Headers $headers -Uri "https://api.github.com/repos/UE4SS-RE/RE-UE4SS/releases/tags/experimental-latest"
    $asset = $release.assets |
        Where-Object { $_.name -match '^zDEV-UE4SS_.*\.zip$' } |
        Select-Object -First 1
    if (-not $asset) {
        $asset = $release.assets |
            Where-Object { $_.name -match '^UE4SS_.*\.zip$' } |
            Select-Object -First 1
    }
    if (-not $asset) { throw "No experimental UE4SS ZIP asset found." }

    $dest = Join-Path $DownloadRoot $asset.name
    if (-not (Test-Path $dest)) {
        Write-Host "Downloading $($asset.name) ..."
        Invoke-WebRequest -Headers $headers -Uri $asset.browser_download_url -OutFile $dest
    } else {
        Write-Ok "Using cached archive: $dest"
    }

    return [pscustomobject]@{
        Path = $dest
        Name = $asset.name
        Tag = $release.tag_name
        PublishedAt = $release.published_at
    }
}

function New-Ue4ssBackup([string]$GameDir) {
    Write-Section "Backup current UE4SS"
    $backup = Join-Path $GameDir ("orcish_ue4ss_backup_experimental_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
    New-Item -ItemType Directory -Force -Path $backup | Out-Null

    $items = @(
        "dwmapi.dll",
        "UE4SS.dll",
        "UE4SS.pdb",
        "UE4SS-settings.ini",
        "UE4SS.log",
        "Mods",
        "UE4SS_Signatures",
        "CustomGameConfigs",
        "MemberVarLayoutTemplates",
        "VTableLayoutTemplates",
        "MapGenBP",
        "ue4ss"
    )

    $copied = 0
    foreach ($name in $items) {
        $src = Join-Path $GameDir $name
        if (Test-Path $src) {
            Copy-Item -Recurse -Force $src $backup
            $copied++
        }
    }
    Write-Ok "Backup created: $backup"
    Write-Ok "Backed up $copied UE4SS item(s)"
    return $backup
}

function Remove-OldUe4ssLayout([string]$GameDir) {
    $items = @(
        "dwmapi.dll",
        "UE4SS.dll",
        "UE4SS.pdb",
        "UE4SS-settings.ini",
        "UE4SS.log",
        "Mods",
        "UE4SS_Signatures",
        "CustomGameConfigs",
        "MemberVarLayoutTemplates",
        "VTableLayoutTemplates",
        "MapGenBP",
        "ue4ss"
    )
    foreach ($name in $items) {
        $p = Join-Path $GameDir $name
        if (Test-Path $p) { Remove-Item -Recurse -Force $p }
    }
}

function Restore-Ue4ssBackup([string]$GameDir,[string]$BackupDir) {
    Write-Warn "Restoring the previous UE4SS installation..."
    Remove-OldUe4ssLayout $GameDir
    Get-ChildItem $BackupDir -Force | ForEach-Object {
        Copy-Item -Recurse -Force $_.FullName $GameDir
    }
    Write-Ok "Previous UE4SS installation restored."
}

function Install-ExperimentalArchive([string]$GameDir,[string]$ZipPath) {
    Write-Section "Install experimental UE4SS"
    $temp = Join-Path $env:TEMP ("orcish_ue4ss_" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $temp | Out-Null
    try {
        Expand-Archive -Path $ZipPath -DestinationPath $temp -Force

        $proxy = Get-ChildItem $temp -Filter "dwmapi.dll" -File -Recurse | Select-Object -First 1
        $ue4ssDir = Get-ChildItem $temp -Directory -Filter "ue4ss" -Recurse | Select-Object -First 1

        if (-not $proxy) { throw "Experimental archive does not contain dwmapi.dll." }

        if ($ue4ssDir) {
            Copy-Item -Force $proxy.FullName (Join-Path $GameDir "dwmapi.dll")
            Copy-Item -Recurse -Force $ue4ssDir.FullName (Join-Path $GameDir "ue4ss")
        } else {
            $dll = Get-ChildItem $temp -Filter "UE4SS.dll" -File -Recurse | Select-Object -First 1
            if (-not $dll) { throw "Experimental archive does not contain UE4SS.dll." }
            $srcRoot = Split-Path -Parent $dll.FullName
            $dst = Join-Path $GameDir "ue4ss"
            New-Item -ItemType Directory -Force -Path $dst | Out-Null
            Get-ChildItem $srcRoot -Force | ForEach-Object {
                Copy-Item -Recurse -Force $_.FullName $dst
            }
            Copy-Item -Force $proxy.FullName (Join-Path $GameDir "dwmapi.dll")
        }
    } finally {
        if (Test-Path $temp) { Remove-Item -Recurse -Force $temp }
    }

    if (-not (Test-Path (Join-Path $GameDir "dwmapi.dll"))) { throw "dwmapi.dll was not installed." }
    if (-not (Test-Path (Join-Path $GameDir "ue4ss\UE4SS.dll"))) { throw "ue4ss\UE4SS.dll was not installed." }
    Write-Ok "Experimental UE4SS runtime installed in the new ue4ss layout."
}

function Install-OrcishScout([string]$GameDir) {
    Write-Section "Install OrcishScout bridge"
    $modsDir = Join-Path $GameDir "ue4ss\Mods"
    New-Item -ItemType Directory -Force -Path $modsDir | Out-Null

    $src = Join-Path $RepoRoot "tools\ue4ss\OrcishScout"
    $dst = Join-Path $modsDir "OrcishScout"
    if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
    Copy-Item -Recurse -Force $src $dst

    $modsFile = Join-Path $modsDir "mods.txt"
    if (-not (Test-Path $modsFile)) { New-Item -ItemType File -Force -Path $modsFile | Out-Null }
    $lines = @(Get-Content $modsFile -ErrorAction SilentlyContinue)
    $lines = @($lines | Where-Object { $_ -notmatch '^\s*OrcishScout\s*:' })

    $insertAt = -1
    for ($i=0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match '^\s*;\s*Built-in keybinds') { $insertAt = $i; break }
    }
    if ($insertAt -ge 0) {
        $before = if ($insertAt -gt 0) { @($lines[0..($insertAt-1)]) } else { @() }
        $after = @($lines[$insertAt..($lines.Count-1)])
        $lines = @($before + "OrcishScout : 1" + $after)
    } else {
        $lines += "OrcishScout : 1"
    }
    Set-Content $modsFile $lines -Encoding UTF8

    $outFile = Join-Path $TelemetryDir "orcish_scout_ue4ss.jsonl"
    $lua = Join-Path $dst "scripts\main.lua"
    $luaText = Get-Content -Raw $lua
    $luaText = [regex]::Replace($luaText,'local OUTPUT = \[\[.*?\]\]','local OUTPUT = [[' + $outFile + ']]')
    Set-Content $lua $luaText -Encoding UTF8

    if ($luaText -notmatch 'bridge_start' -or $luaText -notmatch 'bridge_ready') {
        throw "Installed OrcishScout bridge does not contain startup heartbeat events."
    }

    Write-Ok "OrcishScout installed: $lua"
    Write-Ok "Telemetry output: $outFile"
}

function Write-InstallManifest([string]$GameExe,[string]$Backup,[object]$Archive) {
    $manifest = [ordered]@{
        installed_at = (Get-Date).ToString("o")
        game_exe = $GameExe
        backup = $Backup
        release_tag = $Archive.Tag
        asset = $Archive.Name
        asset_path = $Archive.Path
        purpose = "Recover UE4SS startup on Dragonwilds WinGDK so OrcishScout can collect game-internal telemetry."
    }
    $manifest | ConvertTo-Json | Set-Content (Join-Path $TelemetryDir "ue4ss_experimental_install.json") -Encoding UTF8
}

Ensure-Elevated

Write-Host ""
Write-Host "Orcish experimental UE4SS recovery" -ForegroundColor Cyan
Write-Host "Purpose: get UE4SS past its startup scan so OrcishScout can begin writing telemetry."
Write-Host ""

$running = Get-Process -Name "RSDragonwilds-WinGDK-Shipping" -ErrorAction SilentlyContinue
if ($running) {
    Write-Bad "Dragonwilds is running. Close the game completely, then run Setup option 9 again."
    exit 2
}

$exe = Resolve-DragonwildsExe
if (-not $exe) {
    Write-Bad "RSDragonwilds-WinGDK-Shipping.exe was not found."
    Write-Host "Start Dragonwilds once, close it, and rerun this option."
    exit 3
}

$gameDir = Split-Path -Parent $exe
Write-Ok "Target: $exe"

$archive = Get-ExperimentalArchive
$backup = New-Ue4ssBackup $gameDir

try {
    Remove-OldUe4ssLayout $gameDir
    Install-ExperimentalArchive $gameDir $archive.Path
    Install-OrcishScout $gameDir
    Write-InstallManifest $exe $backup $archive
} catch {
    Write-Bad "Experimental UE4SS installation failed: $($_.Exception.Message)"
    try { Restore-Ue4ssBackup $gameDir $backup }
    catch { Write-Bad "Automatic rollback also failed: $($_.Exception.Message)" }
    exit 4
}

Write-Section "Ready for runtime test"
Write-Ok "Backup kept at: $backup"
Write-Ok "New runtime: $(Join-Path $gameDir 'ue4ss\UE4SS.dll')"
Write-Ok "Proxy DLL: $(Join-Path $gameDir 'dwmapi.dll')"
Write-Ok "OrcishScout: $(Join-Path $gameDir 'ue4ss\Mods\OrcishScout\scripts\main.lua')"
Write-Host ""
Write-Host "Next:"
Write-Host "  1. Start Dragonwilds."
Write-Host "  2. Wait for the main menu/world."
Write-Host "  3. Close Dragonwilds."
Write-Host "  4. Run Setup.cmd option 8 (Telemetry toolkit status)."
Write-Host ""
Write-Host "Success means UE4SS no longer ends with 'PS scan timed out' and OrcishScout writes bridge_start/bridge_ready."
Write-Host ""
Write-Host "Press Enter to close this elevated recovery window."
[void](Read-Host)
exit 0
