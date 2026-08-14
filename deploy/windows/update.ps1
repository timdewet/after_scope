# Update the installed bundle in place. Run AS ADMINISTRATOR:
#   powershell -ExecutionPolicy Bypass -File update.ps1 -BundleDir C:\path\to\new\AfterScope
#
# Uses the stop.flag protocol: the watchdog checks for it every tick and exits
# cleanly; the scheduled task's 5-minute keep-alive relaunches the new build.

param(
    [Parameter(Mandatory = $true)] [string]$BundleDir,
    [string]$InstallDir = "C:\Program Files\AfterScope",
    [string]$DataDir = "C:\ProgramData\AfterScope"
)
$ErrorActionPreference = "Stop"

$stopFlag = Join-Path $DataDir "stop.flag"
Write-Host "Signalling watchdog to stop ..."
New-Item -ItemType File -Force -Path $stopFlag | Out-Null

# wait for the process to exit (max 60 s)
$deadline = (Get-Date).AddSeconds(60)
while ((Get-Process -Name "AfterScope" -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
}
if (Get-Process -Name "AfterScope" -ErrorAction SilentlyContinue) {
    Write-Warning "Watchdog/wizard still running (wizard in progress?). Aborting update."
    Remove-Item $stopFlag -ErrorAction SilentlyContinue
    exit 1
}

Write-Host "Swapping bundle ..."
Copy-Item -Path (Join-Path $BundleDir "*") -Destination $InstallDir -Recurse -Force
Remove-Item $stopFlag -ErrorAction SilentlyContinue

Start-ScheduledTask -TaskName "AfterScopeWatchdog"
Write-Host "Updated and relaunched."
