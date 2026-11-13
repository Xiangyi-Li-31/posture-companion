$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "请先运行 setup.ps1 创建项目环境。"
}

& $VenvPython -m pip install -r (Join-Path $ProjectDir "requirements-build.txt")
& $VenvPython (Join-Path $ProjectDir "scripts\generate_icon.py")
& $VenvPython -m PyInstaller --noconfirm --clean `
    --distpath (Join-Path $ProjectDir "dist") `
    --workpath (Join-Path $ProjectDir "build") `
    (Join-Path $ProjectDir "PostureCompanion.spec")

Write-Host "构建完成：$ProjectDir\dist\PostureCompanion\PostureCompanion.exe" -ForegroundColor Green
