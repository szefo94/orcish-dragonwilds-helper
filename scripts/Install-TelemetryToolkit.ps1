[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$CheckOnly,
    [switch]$All,
    [switch]$SkipUE4SS,
    [switch]$SkipCheatEngine,
    [switch]$SkipReClass,
    [switch]$SkipX64dbg,
    [switch]$SkipWPT,
    [string]$GameExe,
    [string]$UE4SSZip = "C:\Users\Marcin\OneDrive\Desktop\OrcPresser\RE-UE4SS-main.zip"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$ExternalRoot = Join-Path $RepoRoot "tools\external"
$DownloadRoot = Join-Path $ExternalRoot "downloads"
New-Item -ItemType Directory -Force -Path $ExternalRoot,$DownloadRoot | Out-Null

function Write-Section([string]$Text) { Write-Host ""; Write-Host ("=== " + $Text + " ===") -ForegroundColor Cyan }
function Write-Ok([string]$Text) { Write-Host ("[OK]   " + $Text) -ForegroundColor Green }
function Write-Warn([string]$Text) { Write-Host ("[WARN] " + $Text) -ForegroundColor Yellow }
function Write-Bad([string]$Text) { Write-Host ("[MISS] " + $Text) -ForegroundColor Red }
function Test-Command([string]$Name) { return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue) }

function Invoke-GitHubLatestAsset {
    param([string]$Repository,[string[]]$Patterns,[string]$Destination)
    $headers = @{ "User-Agent" = "Orcish-Telemetry-Installer" }
    $release = Invoke-RestMethod -Headers $headers -Uri ("https://api.github.com/repos/" + $Repository + "/releases/latest")
    $asset = $null
    foreach ($pattern in $Patterns) {
        $asset = $release.assets | Where-Object { $_.name -match $pattern } | Select-Object -First 1
        if ($asset) { break }
    }
    if (-not $asset) { throw "No release asset matched patterns: $($Patterns -join ', ')" }
    $dest = Join-Path $Destination $asset.name
    Write-Host "Downloading $($asset.name) from $Repository ..."
    Invoke-WebRequest -Headers $headers -Uri $asset.browser_download_url -OutFile $dest
    return $dest
}

function Get-SteamLibraries {
    $roots = New-Object System.Collections.Generic.List[string]
    $steam = Join-Path ${env:ProgramFiles(x86)} "Steam"
    if (Test-Path $steam) { $roots.Add($steam) }
    $vdf = Join-Path $steam "steamapps\libraryfolders.vdf"
    if (Test-Path $vdf) {
        $text = Get-Content -Raw $vdf
        [regex]::Matches($text, '"path"\s+"([^"]+)"') | ForEach-Object {
            $p = $_.Groups[1].Value -replace '\\\\','\'
            if ((Test-Path $p) -and -not $roots.Contains($p)) { $roots.Add($p) }
        }
    }
    return $roots
}

function Resolve-DragonwildsExe {
    if ($GameExe -and (Test-Path $GameExe)) { return (Resolve-Path $GameExe).Path }
    $proc = Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $_.ProcessName -like "*Dragonwilds*" -or $_.ProcessName -like "*Win64-Shipping*"
    } | Select-Object -First 1
    if ($proc) {
        try { $p = $proc.MainModule.FileName; if ($p -and (Test-Path $p)) { return $p } } catch {}
    }
    foreach ($root in Get-SteamLibraries) {
        $common = Join-Path $root "steamapps\common"
        if (-not (Test-Path $common)) { continue }
        $hit = Get-ChildItem -Path $common -Filter "Dragonwilds-Win64-Shipping.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

function Test-Ue4ssBinaryZip([string]$ZipPath) {
    if (-not (Test-Path $ZipPath)) { return $false }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        $names = $zip.Entries | ForEach-Object { $_.FullName }
        return [bool]($names | Where-Object { $_ -match '(^|/)(UE4SS\.dll|dwmapi\.dll)$' })
    } finally { $zip.Dispose() }
}

function Install-UE4SS {
    param([string]$ExePath)
    Write-Section "UE4SS"
    if (-not $ExePath) { Write-Bad "Dragonwilds executable not found. Start the game once or rerun with -GameExe <path>."; return }
    $gameDir = Split-Path -Parent $ExePath
    Write-Host "Game executable: $ExePath"

    $zip = $UE4SSZip
    if ($zip -and (Test-Path $zip)) {
        if (Test-Ue4ssBinaryZip $zip) { Write-Ok "Local UE4SS binary archive looks usable: $zip" }
        else { Write-Warn "Local archive looks like SOURCE CODE, not a runnable UE4SS release: $zip"; $zip = $null }
    } elseif ($zip) { Write-Warn "Configured local UE4SS archive not found: $zip"; $zip = $null }

    if (-not $zip) {
        Write-Host "Fetching latest stable zDEV binary release from UE4SS-RE/RE-UE4SS..."
        $zip = Invoke-GitHubLatestAsset -Repository "UE4SS-RE/RE-UE4SS" -Patterns @('^zDEV-UE4SS_v.*\.zip$','(?i)zDEV.*\.zip$') -Destination $DownloadRoot
    }

    $backup = Join-Path $gameDir ("orcish_ue4ss_backup_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
    $existing = @("UE4SS.dll","UE4SS-settings.ini","dwmapi.dll","xinput1_3.dll","Mods","ue4ss") | ForEach-Object { Join-Path $gameDir $_ } | Where-Object { Test-Path $_ }
    if ($existing.Count -gt 0) {
        New-Item -ItemType Directory -Force -Path $backup | Out-Null
        foreach ($item in $existing) { Copy-Item -Recurse -Force $item $backup }
        Write-Ok "Existing UE4SS-related files backed up to $backup"
    }

    Expand-Archive -Path $zip -DestinationPath $gameDir -Force
    $modsDir = if (Test-Path (Join-Path $gameDir "ue4ss\Mods")) { Join-Path $gameDir "ue4ss\Mods" } else { Join-Path $gameDir "Mods" }
    New-Item -ItemType Directory -Force -Path $modsDir | Out-Null

    $bridgeSrc = Join-Path $RepoRoot "tools\ue4ss\OrcishScout"
    $bridgeDst = Join-Path $modsDir "OrcishScout"
    if (Test-Path $bridgeDst) { Remove-Item -Recurse -Force $bridgeDst }
    Copy-Item -Recurse -Force $bridgeSrc $bridgeDst

    $modsFile = Join-Path $modsDir "mods.txt"
    if (-not (Test-Path $modsFile)) { New-Item -ItemType File -Force -Path $modsFile | Out-Null }
    $modsText = Get-Content -Raw $modsFile -ErrorAction SilentlyContinue
    if ($modsText -notmatch '(?im)^\s*OrcishScout\s*:\s*1\s*$') { Add-Content -Path $modsFile -Value "OrcishScout : 1" }

    $telemetryDir = Join-Path $RepoRoot "data\ue4ss"
    New-Item -ItemType Directory -Force -Path $telemetryDir | Out-Null
    $outFile = Join-Path $telemetryDir "orcish_scout_ue4ss.jsonl"
    $lua = Join-Path $bridgeDst "scripts\main.lua"
    if (Test-Path $lua) {
        $luaText = Get-Content -Raw $lua
        $luaText = [regex]::Replace($luaText,'local OUTPUT = \[\[.*?\]\]','local OUTPUT = [[' + $outFile + ']]')
        Set-Content -Path $lua -Value $luaText -Encoding UTF8
    }

    if ((Test-Path (Join-Path $gameDir "dwmapi.dll")) -or (Test-Path (Join-Path $gameDir "UE4SS.dll")) -or (Test-Path (Join-Path $gameDir "ue4ss\UE4SS.dll"))) {
        Write-Ok "UE4SS installed beside the game."
        Write-Ok "OrcishScout bridge installed at $bridgeDst"
        Write-Ok "Bridge output: $outFile"
    } else { Write-Warn "Extraction completed, but runtime DLLs were not found in expected locations." }
}

function Install-Frida {
    Write-Section "Frida"
    if (-not (Test-Path $Py)) { Write-Bad "Orcish virtual environment missing. Run Setup.cmd option 1 first."; return }
    & $Py -m pip install -r (Join-Path $RepoRoot "src\requirements-telemetry.txt")
    if ($LASTEXITCODE -eq 0) {
        $v = & $Py -c "import frida; print(frida.__version__)" 2>$null
        Write-Ok "Frida installed: $v"
    } else { Write-Bad "Frida installation failed." }
}

function Install-X64Dbg {
    Write-Section "x64dbg"
    if (-not (Test-Command "winget")) { Write-Bad "winget not available."; return }
    winget install --id x64dbg.x64dbg --exact --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -eq 0) { Write-Ok "x64dbg installed/updated through winget." } else { Write-Warn "x64dbg install returned code $LASTEXITCODE" }
}

function Install-WPT {
    Write-Section "Windows Performance Toolkit"
    if (Test-Command "wpa.exe") { Write-Ok "WPA already available."; return }
    if (-not (Test-Command "winget")) { Write-Bad "winget not available."; return }
    winget install --id Microsoft.WindowsADK --exact --accept-package-agreements --accept-source-agreements --override "/quiet /norestart /features OptionId.WindowsPerformanceToolkit"
    if ($LASTEXITCODE -eq 0) { Write-Ok "ADK/WPT installer completed. Open a new shell before checking PATH." } else { Write-Warn "Windows ADK install returned code $LASTEXITCODE" }
}

function Install-ReClass {
    Write-Section "ReClass.NET"
    $target = Join-Path $ExternalRoot "ReClass.NET"
    $present = Get-ChildItem $target -Filter "ReClass.NET.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($present) { Write-Ok "ReClass.NET already present: $($present.FullName)"; return }
    $zip = Invoke-GitHubLatestAsset -Repository "ReClassNET/ReClass.NET" -Patterns @('(?i)(x64|win64).*\.zip$','(?i)ReClass.*\.zip$') -Destination $DownloadRoot
    if (Test-Path $target) { Remove-Item -Recurse -Force $target }
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Expand-Archive -Path $zip -DestinationPath $target -Force
    $exe = Get-ChildItem $target -Filter "ReClass.NET.exe" -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($exe) { Write-Ok "ReClass.NET installed portable: $($exe.FullName)" } else { Write-Warn "Downloaded ReClass.NET, but executable was not found automatically." }
}

function Install-CheatEngine {
    Write-Section "Cheat Engine"
    $known = Get-ChildItem @($env:ProgramFiles,${env:ProgramFiles(x86)}) -Filter "cheatengine-x86_64.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($known) { Write-Ok "Cheat Engine found: $($known.FullName)"; return }
    Write-Warn "No reliable current winget package. Downloading latest PUBLIC installer from official cheat-engine/cheat-engine GitHub release."
    $exe = Invoke-GitHubLatestAsset -Repository "cheat-engine/cheat-engine" -Patterns @('(?i)\.exe$') -Destination $DownloadRoot
    Write-Host "Launching installer interactively: $exe"
    Start-Process -FilePath $exe -Wait
}

function Show-Status {
    Write-Section "Telemetry toolkit status"
    if (Test-Path $Py) {
        $frida = & $Py -c "import importlib.util; print('yes' if importlib.util.find_spec('frida') else 'no')" 2>$null
        if ($frida -eq "yes") { Write-Ok "Frida Python package" } else { Write-Bad "Frida Python package" }
    } else { Write-Bad "Orcish .venv / Python" }

    $exe = Resolve-DragonwildsExe
    if ($exe) {
        Write-Ok "Dragonwilds executable: $exe"
        $dir = Split-Path -Parent $exe
        if ((Test-Path (Join-Path $dir "UE4SS.dll")) -or (Test-Path (Join-Path $dir "ue4ss\UE4SS.dll"))) { Write-Ok "UE4SS runtime found" } else { Write-Bad "UE4SS runtime not found beside game" }
        if ((Test-Path (Join-Path $dir "Mods\OrcishScout\scripts\main.lua")) -or (Test-Path (Join-Path $dir "ue4ss\Mods\OrcishScout\scripts\main.lua"))) { Write-Ok "OrcishScout bridge found" } else { Write-Bad "OrcishScout bridge not found" }
    } else { Write-Bad "Dragonwilds executable not auto-detected" }

    if (Test-Command "x64dbg.exe") { Write-Ok "x64dbg command available" } else {
        $wingetPkg = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
        $x = Get-ChildItem $wingetPkg -Filter "x64dbg.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($x) { Write-Ok "x64dbg installed: $($x.FullName)" } else { Write-Bad "x64dbg" }
    }

    $reclass = Get-ChildItem (Join-Path $ExternalRoot "ReClass.NET") -Filter "ReClass.NET.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($reclass) { Write-Ok "ReClass.NET: $($reclass.FullName)" } else { Write-Bad "ReClass.NET" }

    $ce = Get-ChildItem @($env:ProgramFiles,${env:ProgramFiles(x86)}) -Filter "cheatengine-x86_64.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($ce) { Write-Ok "Cheat Engine: $($ce.FullName)" } else { Write-Bad "Cheat Engine" }

    if (Test-Command "wpr.exe") { Write-Ok "WPR available" } else { Write-Bad "WPR" }
    if (Test-Command "wpa.exe") { Write-Ok "WPA available" } else {
        $wpa = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits" -Filter "wpa.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($wpa) { Write-Ok "WPA installed: $($wpa.FullName)" } else { Write-Bad "WPA / Windows Performance Toolkit" }
    }

    if (Test-Path $UE4SSZip) {
        if (Test-Ue4ssBinaryZip $UE4SSZip) { Write-Ok "Provided UE4SS ZIP is a binary release: $UE4SSZip" }
        else { Write-Warn "Provided UE4SS ZIP looks like SOURCE CODE and cannot be installed directly: $UE4SSZip" }
    } else { Write-Warn "Provided UE4SS ZIP not found: $UE4SSZip" }
}

Show-Status
if ($CheckOnly -or -not $Install) {
    Write-Host ""
    Write-Host "Check complete. Run with -Install -All to install the supported toolkit." -ForegroundColor Cyan
    exit 0
}

Install-Frida
$game = Resolve-DragonwildsExe
if (-not $SkipUE4SS) { Install-UE4SS -ExePath $game }
if (-not $SkipX64dbg) { Install-X64Dbg }
if (-not $SkipReClass) { Install-ReClass }
if (-not $SkipCheatEngine) { Install-CheatEngine }
if (-not $SkipWPT) { Install-WPT }

Show-Status
Write-Host ""
Write-Host "Toolkit pass complete. Restart PowerShell/Orcish so PATH and optional providers refresh." -ForegroundColor Cyan
