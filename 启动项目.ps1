$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $projectRoot "backend"
$frontendDir = Join-Path $projectRoot "frontend"
$pythonExe = Join-Path $backendDir ".venv\Scripts\python.exe"
$envFile = Join-Path $backendDir ".env"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "没有找到后端虚拟环境。请先按照 README.md 安装后端依赖。"
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "没有找到 npm。请先安装 Node.js。"
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendDir "node_modules"))) {
    throw "没有找到前端依赖。请先在 frontend 目录执行 npm install。"
}
if (-not (Test-Path -LiteralPath $envFile)) {
    Write-Warning "没有找到 backend/.env，系统会使用本地降级模式，无法调用百炼真实模型。"
}

$backendListening = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue
if ($backendListening) {
    Write-Host "后端 8000 端口已经在监听，跳过重复启动。" -ForegroundColor Yellow
} else {
    $backendCommand = "& '$pythonExe' -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
    Start-Process -FilePath "powershell.exe" -WorkingDirectory $backendDir -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $backendCommand)
    Write-Host "后端启动命令已发送。" -ForegroundColor Green
}

$frontendListening = Get-NetTCPConnection -State Listen -LocalPort 5173 -ErrorAction SilentlyContinue
if ($frontendListening) {
    Write-Host "前端 5173 端口已经在监听，跳过重复启动。" -ForegroundColor Yellow
} else {
    $frontendCommand = "npm run dev -- --host 127.0.0.1"
    Start-Process -FilePath "powershell.exe" -WorkingDirectory $frontendDir -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $frontendCommand)
    Write-Host "前端启动命令已发送。" -ForegroundColor Green
}

# 等两个服务真正就绪后再打开浏览器（最多 40 秒）。
$backendReady = $false
$frontendReady = $false
foreach ($i in 1..40) {
    Start-Sleep -Seconds 1
    if (-not $backendReady) {
        $backendReady = [bool](Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue)
    }
    if (-not $frontendReady) {
        $frontendReady = [bool](Get-NetTCPConnection -State Listen -LocalPort 5173 -ErrorAction SilentlyContinue)
    }
    if ($backendReady -and $frontendReady) { break }
}
if (-not $backendReady) { Write-Warning "后端 40 秒内未就绪，请查看后端窗口的报错信息。" }
if (-not $frontendReady) { Write-Warning "前端 40 秒内未就绪，请查看前端窗口的报错信息。" }

Start-Process "http://127.0.0.1:5173"
Write-Host "已打开 http://127.0.0.1:5173 ，祝面试顺利！" -ForegroundColor Cyan
