param(
    [string[]]$UvicornArgs = @("app.main:app", "--reload", "--port", "8000")
)

$backendRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $backendRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Backend virtual environment not found at $python"
}

Push-Location $backendRoot
try {
    & $python -m uvicorn @UvicornArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
