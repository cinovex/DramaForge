$ErrorActionPreference = "Stop"

$projectRoot = "D:\DramaForge"
$bunPath = Join-Path $projectRoot "tools\bun.exe"
$frontendPath = "D:\DramaForge\frontend"
$logDirectory = Join-Path $projectRoot "storage\serviceLogs"

if (-not (Test-Path -LiteralPath $bunPath)) {
  throw "找不到 Bun 运行环境：$bunPath"
}
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

function testEndpoint([string]$url) {
  try {
    return (Invoke-WebRequest -Uri $url -TimeoutSec 2 -UseBasicParsing).StatusCode -eq 200
  } catch {
    return $false
  }
}

$runStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$serverOut = Join-Path $logDirectory "dramaforge-server-$runStamp.log"
$serverErr = Join-Path $logDirectory "dramaforge-server-error-$runStamp.log"

$env:TOONFLOW_PORT = "3001"
$env:TOONFLOW_DATA_DIR = Join-Path $projectRoot "storage\canvasData"
if (-not (testEndpoint "http://127.0.0.1:3001/api/workspaces/list")) {
  Start-Process -FilePath $bunPath -ArgumentList @("run", "--filter", "@toonflow/server", "dev") `
    -WorkingDirectory $projectRoot -RedirectStandardOutput $serverOut -RedirectStandardError $serverErr -WindowStyle Hidden | Out-Null
}

$toonflowReady = $false
for ($attempt = 0; $attempt -lt 45; $attempt++) {
  if (testEndpoint "http://127.0.0.1:3001/api/workspaces/list") {
    $toonflowReady = $true
    break
  }
  Start-Sleep -Seconds 1
}
if (-not $toonflowReady) {
  throw "画布服务启动超时。请查看 $logDirectory 中的服务日志。"
}

if (testEndpoint "http://127.0.0.1:3000/projects") {
  Write-Host "DramaForge 已运行：http://localhost:3000"
  return
}

Set-Location -LiteralPath $frontendPath
npm run dev
