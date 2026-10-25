param(
    [switch]$Setup,
    [switch]$Demo,
    [switch]$Build,
    [int]$Port = 8000
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create Python virtual environment.' }
    $Setup = $true
}
if ($Setup) {
    & $python -m pip install -e . -r backend\requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
}
if ($Demo) {
    & $python -m app.setup_local --demo
} else {
    & $python -m app.setup_local
}
if ($LASTEXITCODE -ne 0) { throw 'Database initialization failed.' }
if ($Build) {
    Push-Location frontend
    try {
        flutter pub get
        if ($LASTEXITCODE -ne 0) { throw 'Flutter dependency restoration failed.' }
        flutter build web
        if ($LASTEXITCODE -ne 0) { throw 'Flutter web build failed.' }
    } finally {
        Pop-Location
    }
}
if (-not (Test-Path 'frontend\build\web\index.html')) {
    throw 'Build the Flutter frontend first: .\start.ps1 -Build (Flutter must be on PATH).'
}
# Windows PowerShell treats Uvicorn's normal stderr logging as native errors.
$ErrorActionPreference = 'Continue'
& $python -m uvicorn app.main:app --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
