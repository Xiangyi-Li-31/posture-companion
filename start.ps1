$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "尚未安装依赖，请先运行 .\setup.ps1"
}

$env:PYTHONPATH = Join-Path $ProjectDir "src"
& $VenvPython -m posture_companion.app
