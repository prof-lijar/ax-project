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
New-Item -ItemType Directory -Path dist -Force | Out-Null
$SourceReport = Join-Path $PSScriptRoot 'dist\source-self-test.json'
& $Python -m app.main --self-test $SourceReport
$SourceExitCode = $LASTEXITCODE
if (Test-Path $SourceReport) { Get-Content $SourceReport -Raw | Write-Host }
if ($SourceExitCode -ne 0) { throw 'Source application startup check failed.' }
& $Python -m PyInstaller --noconfirm --clean KakaoCaptureAgent.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
$Report = Join-Path $PSScriptRoot 'dist\self-test.json'
Remove-Item $Report -ErrorAction SilentlyContinue
$Executable = Join-Path $PSScriptRoot 'dist\KakaoCaptureAgent.exe'
$Process = [System.Diagnostics.Process]::new()
$Process.StartInfo.FileName = $Executable
$Process.StartInfo.UseShellExecute = $false
$Process.StartInfo.ArgumentList.Add('--self-test')
$Process.StartInfo.ArgumentList.Add($Report)
$null = $Process.Start()
if (!$Process.WaitForExit(120000)) {
    Stop-Process -Id $Process.Id -Force
    throw 'Packaged application startup check timed out.'
}
Write-Host "Packaged application exit code: $($Process.ExitCode)"
if (Test-Path $Report) { Get-Content $Report -Raw | Write-Host }
if ($Process.ExitCode -ne 0 -or !(Test-Path $Report)) { throw 'Packaged application startup check failed.' }
$Result = Get-Content $Report -Raw | ConvertFrom-Json
if ($Result.status -ne 'passed') { throw 'Packaged application reported a startup failure.' }
Write-Host 'Ready: dist\KakaoCaptureAgent.exe. Users can download and double-click this file without Python or uv.'
