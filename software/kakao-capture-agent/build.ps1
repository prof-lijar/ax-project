$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if ($env:OS -ne 'Windows_NT') { throw 'Build this application on Windows 10/11.' }
if (!(Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv first: winget install --id=astral-sh.uv -e' }
if (!(Test-Path '.venv\Scripts\python.exe')) {
    uv venv --python 3.12 .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
$Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
uv pip install --python $Python -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $Python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed; build stopped.' }
& $Python -m PyInstaller --noconfirm --clean KakaoCaptureAgent.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
$Report = Join-Path $PSScriptRoot 'dist\self-test.json'
Remove-Item $Report -ErrorAction SilentlyContinue
$Executable = Join-Path $PSScriptRoot 'dist\KakaoCaptureAgent.exe'
$Process = Start-Process -FilePath $Executable -ArgumentList @('--self-test', "`"$Report`"") -PassThru
if (!$Process.WaitForExit(120000)) {
    Stop-Process -Id $Process.Id -Force
    throw 'Packaged application startup check timed out.'
}
if ($Process.ExitCode -ne 0 -or !(Test-Path $Report)) { throw 'Packaged application startup check failed.' }
$Result = Get-Content $Report -Raw | ConvertFrom-Json
if ($Result.status -ne 'passed') { throw 'Packaged application reported a startup failure.' }
Write-Host 'Ready: dist\KakaoCaptureAgent.exe. Users can download and double-click this file without Python or uv.'
