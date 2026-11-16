$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if ($env:OS -ne 'Windows_NT') { throw 'Build this application on Windows 10/11.' }
if (!(Test-Path '.venv\Scripts\python.exe')) {
    py -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.11 x64 with the Python launcher.' }
}
$Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $Python -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $Python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed; build stopped.' }
& $Python -m PyInstaller --noconfirm --clean KakaoCaptureAgent.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
Write-Host 'Distribute the entire dist\KakaoCaptureAgent folder. Launch KakaoCaptureAgent.exe.'
