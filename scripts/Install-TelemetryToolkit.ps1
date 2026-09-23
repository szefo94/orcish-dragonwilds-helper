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
    [switch]$AllowWindowsAppsInstall,
    [string]$GameExe,
    [string]$UE4SSZip = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$ExternalRoot = Join-Path $RepoRoot "tools\external"
$DownloadRoot = Join-Path $ExternalRoot "downloads"
$PF86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
New-Item -ItemType Directory -Force -Path $ExternalRoot,$DownloadRoot | Out-Null

function Write-Section([string]$Text) { Write-Host ""; Write-Host ("=== " + $Text + " ===") -ForegroundColor Cyan }
function Write-Ok([string]$Text) { Write-Host ("[OK]   " + $Text) -ForegroundColor Green }
function Write-Warn([string]$Text) { Write-Host ("[WARN] " + $Text) -ForegroundColor Yellow }
function Write-Bad([string]$Text) { Write-Host ("[MISS] " + $Text) -ForegroundColor Red }
function Test-Command([string]$Name) { return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue) }

function Invoke-Step([string]$Name,[scriptblock]$Body) {
    try { & $Body }
    catch {
        Write-Warn "$Name failed: $($_.Exception.Message)"
        $script:HadWarnings = $true
    }
}

function Invoke-GitHubLatestAsset {
    param([string]$Repository,[string[]]$Patterns,[string]$Destination)
    $headers = @{ "User-Agent" = "Orcish-Telemetry-Installer" }
    $release = Invoke-RestMethod -Headers $headers -Uri ("https://api.github.com/repos/" + $Repository + "/releases/latest")
    $asset = $null
    foreach ($pattern in $Patterns) {
        $asset = $release.assets | Where-Object { $_.name -match $pattern } | Select-Object -First 1
        if ($asset) { break }
    }
    if (-not $asset) { throw "No release asset matched: $($Patterns -join ', ')" }
    $dest = Join-Path $Destination $asset.name
    if (-not (Test-Path $dest)) {
        Write-Host "Downloading $($asset.name) from $Repository ..."
        Invoke-WebRequest -Headers $headers -Uri $asset.browser_download_url -OutFile $dest
    } else { Write-Ok "Using already downloaded $($asset.name)" }
    return $dest
}

function Get-SteamLibraries {
    $roots = New-Object System.Collections.Generic.List[string]
    $steam = Join-Path $PF86 "Steam"
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

function Test-DragonwildsExe([string]$Path) {
    if (-not $Path -or -not (Test-Path $Path)) { return $false }
    $name=[IO.Path]::GetFileName($Path)
    return ($name -ieq "RSDragonwilds-Win64-Shipping.exe" -or $name -ieq "RSDragonwilds-WinGDK-Shipping.exe")
}

function Resolve-DragonwildsExe {
    if ($GameExe) {
        if (Test-DragonwildsExe $GameExe) { return (Resolve-Path $GameExe).Path }
        throw "-GameExe must point to RSDragonwilds-Win64-Shipping.exe or RSDragonwilds-WinGDK-Shipping.exe, not '$GameExe'"
    }

    $proc = Get-Process -Name "RSDragonwilds-Win64-Shipping","RSDragonwilds-WinGDK-Shipping" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($proc) {
        try {
            $p = $proc.MainModule.FileName
            if (Test-DragonwildsExe $p) { return $p }
        } catch {}
    }

    foreach ($root in Get-SteamLibraries) {
        $common = Join-Path $root "steamapps\common"
        if (-not (Test-Path $common)) { continue }
        $hit = Get-ChildItem -Path $common -Include "RSDragonwilds-Win64-Shipping.exe","RSDragonwilds-WinGDK-Shipping.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }

    $commonGuesses = @(
        (Join-Path $PF86 "Steam\steamapps\common\RSDragonwilds\RSDragonwilds\Binaries\Win64\RSDragonwilds-Win64-Shipping.exe"),
        (Join-Path $env:ProgramFiles "Steam\steamapps\common\RSDragonwilds\RSDragonwilds\Binaries\Win64\RSDragonwilds-Win64-Shipping.exe")
    )
    foreach ($p in $commonGuesses) { if (Test-DragonwildsExe $p) { return $p } }

    # Microsoft Store / Xbox app (WinGDK) package.
    $wa = Join-Path $env:ProgramFiles "WindowsApps"
    if (Test-Path $wa) {
        $hit = Get-ChildItem $wa -Filter "RSDragonwilds-WinGDK-Shipping.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

function Get-InstalledBridgeInfo([string]$ExePath) {
    if (-not $ExePath) { return $null }

    $dir = Split-Path -Parent $ExePath
    foreach ($mods in @((Join-Path $dir "Mods"), (Join-Path $dir "ue4ss\Mods"))) {
        $lua = Join-Path $mods "OrcishScout\scripts\main.lua"
        if (-not (Test-Path $lua)) { continue }

        $text = Get-Content -Raw $lua -ErrorAction SilentlyContinue
        $modsFile = Join-Path $mods "mods.txt"
        $enabled = $false

        if (Test-Path $modsFile) {
            $enabled = (Get-Content -Raw $modsFile) -match '(?im)^\s*OrcishScout\s*:\s*1\s*$'
        }

        $output = $null
        if ($text -match 'local OUTPUT = \[\[(.*?)\]\]') {
            $output = $Matches[1]
        }

        return [pscustomobject]@{
            LuaPath          = $lua
            ModsPath         = $mods
            Enabled          = $enabled
            Output           = $output
            HasStartupEvents = ($text -match 'bridge_start' -and $text -match 'bridge_ready')
        }
    }

    return $null
}

function Find-MistakenEosInstall {
    $base = Join-Path $PF86 "Epic Games\Epic Online Services\managedArtifacts"
    if (-not (Test-Path $base)) { return $null }

    return Get-ChildItem $base -Filter "main.lua" -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match '\\Mods\\OrcishScout\\scripts\\main\.lua$' } |
        Select-Object -First 1
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

function Resolve-UE4SSArchive {
    if ($UE4SSZip) {
        if (Test-Ue4ssBinaryZip $UE4SSZip) { return (Resolve-Path $UE4SSZip).Path }
        Write-Warn "Configured UE4SS archive is source/non-runtime: $UE4SSZip"
    }
    foreach ($name in @("zDEV-UE4SS_v3.0.1.zip","UE4SS_v3.0.1.zip","zDEV-UE4SS*.zip","UE4SS_v*.zip")) {
        $hit = Get-ChildItem $RepoRoot -Filter $name -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit -and (Test-Ue4ssBinaryZip $hit.FullName)) {
            Write-Ok "Using local UE4SS binary archive: $($hit.FullName)"
            return $hit.FullName
        }
    }
    return Invoke-GitHubLatestAsset -Repository "UE4SS-RE/RE-UE4SS" -Patterns @('^zDEV-UE4SS_v.*\.zip$','^UE4SS_v.*\.zip$') -Destination $DownloadRoot
}

function Install-UE4SS {
    param([string]$ExePath)
    Write-Section "UE4SS"
    if (-not $ExePath) { Write-Bad "Dragonwilds shipping executable not found. Start Dragonwilds or pass -GameExe."; return }
    if (-not (Test-DragonwildsExe $ExePath)) { throw "Refusing UE4SS install: target is not a supported Dragonwilds shipping executable" }

    $gameDir = Split-Path -Parent $ExePath
    $isWindowsApps = $ExePath -like (Join-Path $env:ProgramFiles "WindowsApps\*")
    if ($isWindowsApps -and -not $AllowWindowsAppsInstall) {
        Write-Warn "Detected Microsoft Store/Xbox WinGDK build under WindowsApps."
        Write-Warn "Status/detection is supported, but automatic UE4SS file injection into WindowsApps is disabled by default."
        Write-Warn "Rerun with -AllowWindowsAppsInstall only if you explicitly want the script to attempt writing into the package directory."
        return
    }
    Write-Ok "Correct game executable: $ExePath"
    $zip = Resolve-UE4SSArchive

    $backup = Join-Path $gameDir ("orcish_ue4ss_backup_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
    $existing = @("UE4SS.dll","UE4SS-settings.ini","dwmapi.dll","xinput1_3.dll","Mods","ue4ss") |
        ForEach-Object { Join-Path $gameDir $_ } | Where-Object { Test-Path $_ }
    if ($existing.Count -gt 0) {
        New-Item -ItemType Directory -Force -Path $backup | Out-Null
        foreach ($item in $existing) { Copy-Item -Recurse -Force $item $backup }
        Write-Ok "Existing UE4SS files backed up: $backup"
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
    if ($modsText -notmatch '(?im)^\s*OrcishScout\s*:\s*1\s*$') { Add-Content $modsFile "OrcishScout : 1" }

    $telemetryDir = Join-Path $RepoRoot "data\ue4ss"
    New-Item -ItemType Directory -Force -Path $telemetryDir | Out-Null
    $outFile = Join-Path $telemetryDir "orcish_scout_ue4ss.jsonl"
    $lua = Join-Path $bridgeDst "scripts\main.lua"
    if (Test-Path $lua) {
        $luaText = Get-Content -Raw $lua
        $luaText = [regex]::Replace($luaText,'local OUTPUT = \[\[.*?\]\]','local OUTPUT = [[' + $outFile + ']]')
        Set-Content $lua $luaText -Encoding UTF8
    }
    Write-Ok "UE4SS + OrcishScout installed into the Dragonwilds binary folder."
}

function Find-X64Dbg {
    $cmd = Get-Command x64dbg.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $wingetRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    if (Test-Path $wingetRoot) {
        $hit = Get-ChildItem $wingetRoot -Filter "x64dbg.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

function Find-ReClass {
    $roots = @((Join-Path $ExternalRoot "ReClass.NET"),$RepoRoot)
    foreach ($root in $roots) {
        if (Test-Path $root) {
            $hit = Get-ChildItem $root -Filter "ReClass.NET.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($hit) { return $hit.FullName }
        }
    }
    return $null
}

function Find-SevenZip {
    $cmd = Get-Command 7z.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in @((Join-Path $env:ProgramFiles "7-Zip\7z.exe"),(Join-Path $PF86 "7-Zip\7z.exe"))) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

function Ensure-SevenZip {
    $seven = Find-SevenZip
    if ($seven) { return $seven }
    if (-not (Test-Command winget)) { throw "7-Zip required for ReClass.NET .rar extraction and winget is unavailable." }
    winget install --id 7zip.7zip --exact --silent --accept-package-agreements --accept-source-agreements
    $seven = Find-SevenZip
    if (-not $seven) { throw "7-Zip install completed but 7z.exe was not found." }
    return $seven
}

function Find-CheatEngine {
    $uninstallKeys = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    foreach ($key in $uninstallKeys) {
        foreach ($app in Get-ItemProperty $key -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like "Cheat Engine*" }) {
            if ($app.DisplayIcon) {
                $p = ($app.DisplayIcon -replace '^"|"$','') -replace ',\d+$',''
                if (Test-Path $p) { return $p }
            }
            if ($app.InstallLocation -and (Test-Path $app.InstallLocation)) {
                $hit = Get-ChildItem $app.InstallLocation -Filter "cheatengine*.exe" -File -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($hit) { return $hit.FullName }
            }
        }
    }
    foreach ($root in @($env:ProgramFiles,$PF86)) {
        foreach ($dir in Get-ChildItem $root -Directory -Filter "Cheat Engine*" -ErrorAction SilentlyContinue) {
            $hit = Get-ChildItem $dir.FullName -Filter "cheatengine*.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($hit) { return $hit.FullName }
        }
    }
    return $null
}

function Find-Wpa {
    $cmd = Get-Command wpa.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $root = Join-Path $PF86 "Windows Kits\10\Windows Performance Toolkit"
    $p = Join-Path $root "wpa.exe"
    if (Test-Path $p) { return $p }
    return $null
}

function Install-Frida {
    Write-Section "Frida"
    if (-not (Test-Path $Py)) { throw "Run Setup.cmd option 1 first." }
    & $Py -m pip install -r (Join-Path $RepoRoot "src\requirements-telemetry.txt")
    if ($LASTEXITCODE -ne 0) { throw "pip returned $LASTEXITCODE" }
    $v = & $Py -c "import frida; print(frida.__version__)"
    Write-Ok "Frida $v"
}

function Install-X64Dbg {
    Write-Section "x64dbg"
    $found = Find-X64Dbg
    if ($found) { Write-Ok "Already installed: $found"; return }
    if (-not (Test-Command winget)) { throw "winget unavailable" }
    winget install --id x64dbg.x64dbg --exact --silent --accept-package-agreements --accept-source-agreements
    $found = Find-X64Dbg
    if ($found) { Write-Ok "Installed: $found" } else { throw "x64dbg not found after winget install" }
}

function Install-ReClass {
    Write-Section "ReClass.NET"
    $found = Find-ReClass
    if ($found) { Write-Ok "Already installed: $found"; return }

    $archive = Get-ChildItem $RepoRoot -Filter "ReClass.NET.rar" -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $archive) {
        $path = Invoke-GitHubLatestAsset -Repository "ReClassNET/ReClass.NET" -Patterns @('^ReClass\.NET\.rar$') -Destination $DownloadRoot
        $archive = Get-Item $path
    } else { Write-Ok "Using local archive: $($archive.FullName)" }

    $seven = Ensure-SevenZip
    $target = Join-Path $ExternalRoot "ReClass.NET"
    if (Test-Path $target) { Remove-Item -Recurse -Force $target }
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    & $seven x $archive.FullName "-o$target" -y | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "7-Zip extraction failed with code $LASTEXITCODE" }

    $found = Find-ReClass
    if ($found) { Write-Ok "Installed portable: $found" } else { throw "ReClass.NET.exe not found after extraction" }
}

function Install-CheatEngine {
    Write-Section "Cheat Engine"
    $found = Find-CheatEngine
    if ($found) { Write-Ok "Already installed: $found"; return }

    $installer = Get-ChildItem $RepoRoot -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '(?i)^Cheat.*Engine.*\.(exe|msi)$' } | Select-Object -First 1
    if ($installer) {
        Write-Host "Launching local installer: $($installer.FullName)"
        Start-Process $installer.FullName -Wait
        $found = Find-CheatEngine
        if ($found) { Write-Ok "Installed: $found"; return }
    }

    $sourceZip = Get-ChildItem $RepoRoot -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '(?i)^cheat-engine.*\.zip$' } | Select-Object -First 1
    if ($sourceZip) { Write-Warn "$($sourceZip.Name) is source code, not the Windows installer." }

    Write-Warn "Official Cheat Engine GitHub release 7.5 contains no binary installer asset. Opening the official download page instead."
    Start-Process "https://www.cheatengine.org/downloads.php"
}

function Install-WPT {
    Write-Section "Windows Performance Toolkit"
    $wpa = Find-Wpa
    if ($wpa) { Write-Ok "WPA already installed: $wpa"; return }
    if (-not (Test-Command winget)) { throw "winget unavailable" }
    winget install --id Microsoft.WindowsADK --exact --accept-package-agreements --accept-source-agreements --override "/quiet /norestart /features OptionId.WindowsPerformanceToolkit"
    $wpa = Find-Wpa
    if ($wpa) { Write-Ok "WPA installed: $wpa" } else { Write-Warn "ADK installer completed, but WPA is not visible yet. Reboot/new shell may be required." }
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
        $runtime = (Test-Path (Join-Path $dir "UE4SS.dll")) -or (Test-Path (Join-Path $dir "ue4ss\UE4SS.dll")) -or (Test-Path (Join-Path $dir "dwmapi.dll"))
        if ($runtime) { Write-Ok "UE4SS runtime found at Dragonwilds" } else { Write-Bad "UE4SS runtime not found at Dragonwilds" }
        $bridgeInfo = Get-InstalledBridgeInfo $exe
        if ($bridgeInfo) {
            Write-Ok "OrcishScout bridge found: $($bridgeInfo.LuaPath)"
            if ($bridgeInfo.Enabled) { Write-Ok "OrcishScout enabled in mods.txt" } else { Write-Bad "OrcishScout not enabled in mods.txt" }
            if ($bridgeInfo.HasStartupEvents) { Write-Ok "Bridge contains startup heartbeat events" } else { Write-Warn "Installed bridge is older: no bridge_start/bridge_ready events. Re-run option 7." }
            if ($bridgeInfo.Output) {
                Write-Ok "Bridge output path: $($bridgeInfo.Output)"
                $outDir = Split-Path -Parent $bridgeInfo.Output
                if (Test-Path $outDir) { Write-Ok "Bridge output directory exists" } else { Write-Bad "Bridge output directory missing: $outDir" }
            } else { Write-Bad "Bridge OUTPUT path not found in installed main.lua" }
            $log = Join-Path $dir "UE4SS.log"
            if (Test-Path $log) {
                $hits = Select-String -Path $log -Pattern "OrcishScout|Lua|Mod" -SimpleMatch:$false -ErrorAction SilentlyContinue | Select-Object -Last 8
                if ($hits) {
                    Write-Host "  Recent UE4SS bridge/mod log lines:"
                    $hits | ForEach-Object { Write-Host ("    " + $_.Line) }
                } else { Write-Warn "UE4SS.log exists but contains no OrcishScout/Lua/Mod lines." }
            } else { Write-Warn "UE4SS.log not found next to the game executable." }
        } else { Write-Bad "OrcishScout bridge not found at Dragonwilds" }
    } else { Write-Bad "Dragonwilds shipping executable not auto-detected" }

    $wrong = Find-MistakenEosInstall
    if ($wrong) {
        Write-Warn "A previous installer run put OrcishScout under Epic Online Services, not Dragonwilds:"
        Write-Warn $wrong.FullName
        Write-Warn "Do not treat that as a valid UE4SS install. Remove/restore that EOS folder separately after checking its orcish_ue4ss_backup_* backup."
    }

    $x = Find-X64Dbg; if ($x) { Write-Ok "x64dbg: $x" } else { Write-Bad "x64dbg" }
    $r = Find-ReClass; if ($r) { Write-Ok "ReClass.NET: $r" } else { Write-Bad "ReClass.NET" }
    $ce = Find-CheatEngine; if ($ce) { Write-Ok "Cheat Engine: $ce" } else { Write-Bad "Cheat Engine" }
    if (Test-Command wpr.exe) { Write-Ok "WPR available" } else { Write-Bad "WPR" }
    $wpa = Find-Wpa; if ($wpa) { Write-Ok "WPA: $wpa" } else { Write-Bad "WPA / Windows Performance Toolkit" }

    foreach ($z in Get-ChildItem $RepoRoot -Filter "*UE4SS*.zip" -File -ErrorAction SilentlyContinue) {
        if (Test-Ue4ssBinaryZip $z.FullName) { Write-Ok "UE4SS binary ZIP: $($z.Name)" }
        else { Write-Warn "UE4SS source/non-runtime ZIP: $($z.Name)" }
    }
}

$script:HadWarnings = $false
Show-Status
if ($CheckOnly -or -not $Install) {
    Write-Host ""
    Write-Host "Check complete." -ForegroundColor Cyan
    exit 0
}

Invoke-Step "Frida" { Install-Frida }
$game = $null
try {
    $game = Resolve-DragonwildsExe
    if ($game) { Write-Ok "Installer target: $game" }
    else { Write-Warn "Dragonwilds target could not be resolved for installation." }
} catch {
    Write-Warn "Dragonwilds detection failed: $($_.Exception.Message)"
    $script:HadWarnings = $true
}
if (-not $SkipUE4SS) { Invoke-Step "UE4SS" { Install-UE4SS -ExePath $game } }
if (-not $SkipX64dbg) { Invoke-Step "x64dbg" { Install-X64Dbg } }
if (-not $SkipReClass) { Invoke-Step "ReClass.NET" { Install-ReClass } }
if (-not $SkipCheatEngine) { Invoke-Step "Cheat Engine" { Install-CheatEngine } }
if (-not $SkipWPT) { Invoke-Step "Windows Performance Toolkit" { Install-WPT } }

Show-Status
Write-Host ""
if ($script:HadWarnings) {
    Write-Warn "Toolkit pass completed with one or more warnings; successful tools were kept installed."
    exit 0
}
Write-Ok "Toolkit pass complete."

            }
            $output = $null
            if ($text -match 'local OUTPUT = \[\[(.*?)\]\]') { $output = $Matches[1] }
            return [pscustomobject]@{
                LuaPath=$lua; ModsPath=$mods; Enabled=$enabled; Output=$output;
                HasStartupEvents=($text -match 'bridge_start' -and $text -match 'bridge_ready')
            }
        }
    }
    return $null
}

function Find-MistakenEosInstall {
    $base = Join-Path $PF86 "Epic Games\Epic Online Services\managedArtifacts"
    if (-not (Test-Path $base)) { return $null }
    return Get-ChildItem $base -Filter "main.lua" -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match '\\Mods\\OrcishScout\\scripts\\main\.lua$' } |
        Select-Object -First 1
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

function Resolve-UE4SSArchive {
    if ($UE4SSZip) {
        if (Test-Ue4ssBinaryZip $UE4SSZip) { return (Resolve-Path $UE4SSZip).Path }
        Write-Warn "Configured UE4SS archive is source/non-runtime: $UE4SSZip"
    }
    foreach ($name in @("zDEV-UE4SS_v3.0.1.zip","UE4SS_v3.0.1.zip","zDEV-UE4SS*.zip","UE4SS_v*.zip")) {
        $hit = Get-ChildItem $RepoRoot -Filter $name -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit -and (Test-Ue4ssBinaryZip $hit.FullName)) {
            Write-Ok "Using local UE4SS binary archive: $($hit.FullName)"
            return $hit.FullName
        }
    }
    return Invoke-GitHubLatestAsset -Repository "UE4SS-RE/RE-UE4SS" -Patterns @('^zDEV-UE4SS_v.*\.zip$','^UE4SS_v.*\.zip$') -Destination $DownloadRoot
}

function Install-UE4SS {
    param([string]$ExePath)
    Write-Section "UE4SS"
    if (-not $ExePath) { Write-Bad "Dragonwilds shipping executable not found. Start Dragonwilds or pass -GameExe."; return }
    if (-not (Test-DragonwildsExe $ExePath)) { throw "Refusing UE4SS install: target is not a supported Dragonwilds shipping executable" }

    $gameDir = Split-Path -Parent $ExePath
    $isWindowsApps = $ExePath -like (Join-Path $env:ProgramFiles "WindowsApps\*")
    if ($isWindowsApps -and -not $AllowWindowsAppsInstall) {
        Write-Warn "Detected Microsoft Store/Xbox WinGDK build under WindowsApps."
        Write-Warn "Status/detection is supported, but automatic UE4SS file injection into WindowsApps is disabled by default."
        Write-Warn "Rerun with -AllowWindowsAppsInstall only if you explicitly want the script to attempt writing into the package directory."
        return
    }
    Write-Ok "Correct game executable: $ExePath"
    $zip = Resolve-UE4SSArchive

    $backup = Join-Path $gameDir ("orcish_ue4ss_backup_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
    $existing = @("UE4SS.dll","UE4SS-settings.ini","dwmapi.dll","xinput1_3.dll","Mods","ue4ss") |
        ForEach-Object { Join-Path $gameDir $_ } | Where-Object { Test-Path $_ }
    if ($existing.Count -gt 0) {
        New-Item -ItemType Directory -Force -Path $backup | Out-Null
        foreach ($item in $existing) { Copy-Item -Recurse -Force $item $backup }
        Write-Ok "Existing UE4SS files backed up: $backup"
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
    if ($modsText -notmatch '(?im)^\s*OrcishScout\s*:\s*1\s*$') { Add-Content $modsFile "OrcishScout : 1" }

    $telemetryDir = Join-Path $RepoRoot "data\ue4ss"
    New-Item -ItemType Directory -Force -Path $telemetryDir | Out-Null
    $outFile = Join-Path $telemetryDir "orcish_scout_ue4ss.jsonl"
    $lua = Join-Path $bridgeDst "scripts\main.lua"
    if (Test-Path $lua) {
        $luaText = Get-Content -Raw $lua
        $luaText = [regex]::Replace($luaText,'local OUTPUT = \[\[.*?\]\]','local OUTPUT = [[' + $outFile + ']]')
        Set-Content $lua $luaText -Encoding UTF8
    }
    Write-Ok "UE4SS + OrcishScout installed into the Dragonwilds binary folder."
}

function Find-X64Dbg {
    $cmd = Get-Command x64dbg.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $wingetRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    if (Test-Path $wingetRoot) {
        $hit = Get-ChildItem $wingetRoot -Filter "x64dbg.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

function Find-ReClass {
    $roots = @((Join-Path $ExternalRoot "ReClass.NET"),$RepoRoot)
    foreach ($root in $roots) {
        if (Test-Path $root) {
            $hit = Get-ChildItem $root -Filter "ReClass.NET.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($hit) { return $hit.FullName }
        }
    }
    return $null
}

function Find-SevenZip {
    $cmd = Get-Command 7z.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in @((Join-Path $env:ProgramFiles "7-Zip\7z.exe"),(Join-Path $PF86 "7-Zip\7z.exe"))) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

function Ensure-SevenZip {
    $seven = Find-SevenZip
    if ($seven) { return $seven }
    if (-not (Test-Command winget)) { throw "7-Zip required for ReClass.NET .rar extraction and winget is unavailable." }
    winget install --id 7zip.7zip --exact --silent --accept-package-agreements --accept-source-agreements
    $seven = Find-SevenZip
    if (-not $seven) { throw "7-Zip install completed but 7z.exe was not found." }
    return $seven
}

function Find-CheatEngine {
    $uninstallKeys = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    foreach ($key in $uninstallKeys) {
        foreach ($app in Get-ItemProperty $key -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like "Cheat Engine*" }) {
            if ($app.DisplayIcon) {
                $p = ($app.DisplayIcon -replace '^"|"$','') -replace ',\d+$',''
                if (Test-Path $p) { return $p }
            }
            if ($app.InstallLocation -and (Test-Path $app.InstallLocation)) {
                $hit = Get-ChildItem $app.InstallLocation -Filter "cheatengine*.exe" -File -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($hit) { return $hit.FullName }
            }
        }
    }
    foreach ($root in @($env:ProgramFiles,$PF86)) {
        foreach ($dir in Get-ChildItem $root -Directory -Filter "Cheat Engine*" -ErrorAction SilentlyContinue) {
            $hit = Get-ChildItem $dir.FullName -Filter "cheatengine*.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($hit) { return $hit.FullName }
        }
    }
    return $null
}

function Find-Wpa {
    $cmd = Get-Command wpa.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $root = Join-Path $PF86 "Windows Kits\10\Windows Performance Toolkit"
    $p = Join-Path $root "wpa.exe"
    if (Test-Path $p) { return $p }
    return $null
}

function Install-Frida {
    Write-Section "Frida"
    if (-not (Test-Path $Py)) { throw "Run Setup.cmd option 1 first." }
    & $Py -m pip install -r (Join-Path $RepoRoot "src\requirements-telemetry.txt")
    if ($LASTEXITCODE -ne 0) { throw "pip returned $LASTEXITCODE" }
    $v = & $Py -c "import frida; print(frida.__version__)"
    Write-Ok "Frida $v"
}

function Install-X64Dbg {
    Write-Section "x64dbg"
    $found = Find-X64Dbg
    if ($found) { Write-Ok "Already installed: $found"; return }
    if (-not (Test-Command winget)) { throw "winget unavailable" }
    winget install --id x64dbg.x64dbg --exact --silent --accept-package-agreements --accept-source-agreements
    $found = Find-X64Dbg
    if ($found) { Write-Ok "Installed: $found" } else { throw "x64dbg not found after winget install" }
}

function Install-ReClass {
    Write-Section "ReClass.NET"
    $found = Find-ReClass
    if ($found) { Write-Ok "Already installed: $found"; return }

    $archive = Get-ChildItem $RepoRoot -Filter "ReClass.NET.rar" -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $archive) {
        $path = Invoke-GitHubLatestAsset -Repository "ReClassNET/ReClass.NET" -Patterns @('^ReClass\.NET\.rar$') -Destination $DownloadRoot
        $archive = Get-Item $path
    } else { Write-Ok "Using local archive: $($archive.FullName)" }

    $seven = Ensure-SevenZip
    $target = Join-Path $ExternalRoot "ReClass.NET"
    if (Test-Path $target) { Remove-Item -Recurse -Force $target }
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    & $seven x $archive.FullName "-o$target" -y | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "7-Zip extraction failed with code $LASTEXITCODE" }

    $found = Find-ReClass
    if ($found) { Write-Ok "Installed portable: $found" } else { throw "ReClass.NET.exe not found after extraction" }
}

function Install-CheatEngine {
    Write-Section "Cheat Engine"
    $found = Find-CheatEngine
    if ($found) { Write-Ok "Already installed: $found"; return }

    $installer = Get-ChildItem $RepoRoot -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '(?i)^Cheat.*Engine.*\.(exe|msi)$' } | Select-Object -First 1
    if ($installer) {
        Write-Host "Launching local installer: $($installer.FullName)"
        Start-Process $installer.FullName -Wait
        $found = Find-CheatEngine
        if ($found) { Write-Ok "Installed: $found"; return }
    }

    $sourceZip = Get-ChildItem $RepoRoot -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '(?i)^cheat-engine.*\.zip$' } | Select-Object -First 1
    if ($sourceZip) { Write-Warn "$($sourceZip.Name) is source code, not the Windows installer." }

    Write-Warn "Official Cheat Engine GitHub release 7.5 contains no binary installer asset. Opening the official download page instead."
    Start-Process "https://www.cheatengine.org/downloads.php"
}

function Install-WPT {
    Write-Section "Windows Performance Toolkit"
    $wpa = Find-Wpa
    if ($wpa) { Write-Ok "WPA already installed: $wpa"; return }
    if (-not (Test-Command winget)) { throw "winget unavailable" }
    winget install --id Microsoft.WindowsADK --exact --accept-package-agreements --accept-source-agreements --override "/quiet /norestart /features OptionId.WindowsPerformanceToolkit"
    $wpa = Find-Wpa
    if ($wpa) { Write-Ok "WPA installed: $wpa" } else { Write-Warn "ADK installer completed, but WPA is not visible yet. Reboot/new shell may be required." }
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
        $runtime = (Test-Path (Join-Path $dir "UE4SS.dll")) -or (Test-Path (Join-Path $dir "ue4ss\UE4SS.dll")) -or (Test-Path (Join-Path $dir "dwmapi.dll"))
        if ($runtime) { Write-Ok "UE4SS runtime found at Dragonwilds" } else { Write-Bad "UE4SS runtime not found at Dragonwilds" }
        $bridge = (Test-Path (Join-Path $dir "Mods\OrcishScout\scripts\main.lua")) -or (Test-Path (Join-Path $dir "ue4ss\Mods\OrcishScout\scripts\main.lua"))
        if ($bridge) { Write-Ok "OrcishScout bridge found at Dragonwilds" } else { Write-Bad "OrcishScout bridge not found at Dragonwilds" }
    } else { Write-Bad "Dragonwilds shipping executable not auto-detected" }

    $wrong = Find-MistakenEosInstall
    if ($wrong) {
        Write-Warn "A previous installer run put OrcishScout under Epic Online Services, not Dragonwilds:"
        Write-Warn $wrong.FullName
        Write-Warn "Do not treat that as a valid UE4SS install. Remove/restore that EOS folder separately after checking its orcish_ue4ss_backup_* backup."
    }

    $x = Find-X64Dbg; if ($x) { Write-Ok "x64dbg: $x" } else { Write-Bad "x64dbg" }
    $r = Find-ReClass; if ($r) { Write-Ok "ReClass.NET: $r" } else { Write-Bad "ReClass.NET" }
    $ce = Find-CheatEngine; if ($ce) { Write-Ok "Cheat Engine: $ce" } else { Write-Bad "Cheat Engine" }
    if (Test-Command wpr.exe) { Write-Ok "WPR available" } else { Write-Bad "WPR" }
    $wpa = Find-Wpa; if ($wpa) { Write-Ok "WPA: $wpa" } else { Write-Bad "WPA / Windows Performance Toolkit" }

    foreach ($z in Get-ChildItem $RepoRoot -Filter "*UE4SS*.zip" -File -ErrorAction SilentlyContinue) {
        if (Test-Ue4ssBinaryZip $z.FullName) { Write-Ok "UE4SS binary ZIP: $($z.Name)" }
        else { Write-Warn "UE4SS source/non-runtime ZIP: $($z.Name)" }
    }
}

$script:HadWarnings = $false
Show-Status
if ($CheckOnly -or -not $Install) {
    Write-Host ""
    Write-Host "Check complete." -ForegroundColor Cyan
    exit 0
}

Invoke-Step "Frida" { Install-Frida }
$game = $null
try {
    $game = Resolve-DragonwildsExe
    if ($game) { Write-Ok "Installer target: $game" }
    else { Write-Warn "Dragonwilds target could not be resolved for installation." }
} catch {
    Write-Warn "Dragonwilds detection failed: $($_.Exception.Message)"
    $script:HadWarnings = $true
}
if (-not $SkipUE4SS) { Invoke-Step "UE4SS" { Install-UE4SS -ExePath $game } }
if (-not $SkipX64dbg) { Invoke-Step "x64dbg" { Install-X64Dbg } }
if (-not $SkipReClass) { Invoke-Step "ReClass.NET" { Install-ReClass } }
if (-not $SkipCheatEngine) { Invoke-Step "Cheat Engine" { Install-CheatEngine } }
if (-not $SkipWPT) { Invoke-Step "Windows Performance Toolkit" { Install-WPT } }

Show-Status
Write-Host ""
if ($script:HadWarnings) {
    Write-Warn "Toolkit pass completed with one or more warnings; successful tools were kept installed."
    exit 0
}
Write-Ok "Toolkit pass complete."
