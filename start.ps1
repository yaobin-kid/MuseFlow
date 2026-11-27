#requires -Version 5.1
param(
    [string]$PythonExe = "",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not $PythonExe) {
    $candidates = @(
        $env:PYTHON_EXE,
        (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
        "$env:USERPROFILE\miniconda3\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    ) | Where-Object { $_ -and (Test-Path $_) }
    if (-not $candidates) {
        throw "未找到 Python，请通过 -PythonExe 指定 python.exe 路径"
    }
    $PythonExe = $candidates[0]
}

$venvPython = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "创建虚拟环境..." -ForegroundColor Cyan
    & $PythonExe -m venv (Join-Path $root "backend\.venv")
}

Write-Host "安装 / 校验后端依赖..." -ForegroundColor Cyan
& $venvPython -m pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple -r (Join-Path $root "backend\requirements.txt")

$staticIndex = Join-Path $root "backend\app\static\index.html"
if (-not (Test-Path $staticIndex)) {
    Write-Host "构建前端..." -ForegroundColor Cyan
    Push-Location (Join-Path $root "frontend")
    npm install --registry=https://registry.npmmirror.com
    npm run build
    Pop-Location
}

Write-Host "启动 MusicFlow: http://127.0.0.1:$Port" -ForegroundColor Green
Set-Location (Join-Path $root "backend")
& $venvPython -m uvicorn app.main:app --host 0.0.0.0 --port $Port
