# One-time install on the scope PC. Run AS ADMINISTRATOR:
#   powershell -ExecutionPolicy Bypass -File install.ps1 -ConfigPath "C:\Users\Public\Dropbox (MMRU)\AfterScope\config.yaml"
#
# What it does:
#   1. Copies the unzipped bundle to C:\Program Files\AfterScope
#   2. Creates C:\ProgramData\AfterScope (db/logs/cache/thumbs/xml) with Users:Modify
#   3. Bootstraps the config into Dropbox (from config.example.yaml) if absent,
#      and writes the config pointer file
#   4. Registers the Task Scheduler keep-alive job
#   5. Runs doctor and prints the result

param(
    [Parameter(Mandatory = $true)] [string]$ConfigPath,
    [string]$BundleDir = "",
    [string]$InstallDir = "C:\Program Files\AfterScope",
    [string]$DataDir = "C:\ProgramData\AfterScope"
)
$ErrorActionPreference = "Stop"

# $PSScriptRoot is empty during param() default evaluation in some invocation
# contexts (PS 5.1, elevated -Command wrappers) — resolve defaults here instead.
$scriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $BundleDir) { $BundleDir = Join-Path $scriptRoot "..\..\dist\AfterScope" }

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
        ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this script as Administrator."
}

# 1. program files
Write-Host "Installing to $InstallDir ..."
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -Path (Join-Path $BundleDir "*") -Destination $InstallDir -Recurse -Force

# 2. data dir with user-writable ACL (watchdog runs non-elevated)
Write-Host "Preparing $DataDir ..."
foreach ($sub in @("", "db", "logs", "cache", "thumbs", "xml")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $DataDir $sub) | Out-Null
}
$acl = Get-Acl $DataDir
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    "BUILTIN\Users", "Modify", "ContainerInherit,ObjectInherit", "None", "Allow")
$acl.SetAccessRule($rule)
Set-Acl $DataDir $acl

# 3. config bootstrap + pointer
if (-not (Test-Path $ConfigPath)) {
    Write-Host "Bootstrapping config at $ConfigPath from the example ..."
    New-Item -ItemType Directory -Force -Path (Split-Path $ConfigPath) | Out-Null
    Copy-Item (Join-Path $scriptRoot "..\..\config\config.example.yaml") $ConfigPath
    Write-Warning "EDIT $ConfigPath before first use (watch_dirs, dropbox root, roster)."
}
# WriteAllText writes BOM-less UTF-8 (PS 5.1's `Set-Content -Encoding UTF8` adds a BOM)
[IO.File]::WriteAllText((Join-Path $DataDir "config.path"), $ConfigPath)

# 4. scheduled task
Write-Host "Registering scheduled task AfterScopeWatchdog ..."
$xml = Get-Content (Join-Path $scriptRoot "AfterScopeWatchdog.xml") -Raw
$xml = $xml -replace "C:\\Program Files\\AfterScope\\AfterScope.exe",
                     ($InstallDir + "\AfterScope.exe").Replace("\", "\\")
Register-ScheduledTask -TaskName "AfterScopeWatchdog" -Xml $xml -Force | Out-Null

# 5. doctor
Write-Host "`nRunning doctor ..."
& (Join-Path $InstallDir "AfterScopeCli.exe") --config $ConfigPath doctor

Write-Host @"

Done. Next steps:
  - Edit the config if the doctor flagged anything.
  - Consider a Defender exclusion:  Add-MpPreference -ExclusionPath '$InstallDir'
  - Create the ZEN preset 'AfterScope_DustRef' (100x, brightfield, save prefix dustref_).
  - Start now without re-logging:  Start-ScheduledTask -TaskName AfterScopeWatchdog
"@
