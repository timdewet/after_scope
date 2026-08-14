# Build the Windows bundle. Run on Windows (or GitHub Actions windows-latest);
# PyInstaller cannot cross-build from macOS.
#
#   powershell -ExecutionPolicy Bypass -File deploy\build.ps1

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path ".venv")) {
    py -3.13 -m venv .venv
}
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\pip install -e ".[dev,build]"

.\.venv\Scripts\pytest
if ($LASTEXITCODE -ne 0) { throw "Tests failed - not building." }

.\.venv\Scripts\pyinstaller deploy\after_scope.spec --noconfirm --distpath dist

$version = (.\.venv\Scripts\python -c "import after_scope; print(after_scope.__version__)")
$zip = "AfterScope-$version-win64.zip"
Compress-Archive -Path "dist\AfterScope\*" -DestinationPath $zip -Force
Write-Host "Built $zip"
