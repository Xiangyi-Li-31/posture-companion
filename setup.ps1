$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $ProjectDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$PythonCommand = Get-Command python -ErrorAction SilentlyContinue

if (-not $PythonCommand) {
    throw "未找到 Python。请安装 Python 3.10-3.12，安装时勾选 Add Python to PATH，然后重新打开 PowerShell。"
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    & $PythonCommand.Source -m venv $VenvDir
}

& $VenvPython --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "现有 .venv 已损坏。请把本目录中的 .venv 文件夹改名或删除，再重新运行 setup.ps1。"
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $ProjectDir "requirements.txt")
& $VenvPython (Join-Path $ProjectDir "scripts\download_model.py")
Write-Host "安装完成。运行 .\start.ps1 启动。" -ForegroundColor Green
