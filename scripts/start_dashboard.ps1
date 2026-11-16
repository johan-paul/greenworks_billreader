$ErrorActionPreference = 'Stop'
$projectDirectory = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectDirectory
$pythonExecutable = (Get-Command python -ErrorAction Stop).Source
try { $health = Invoke-RestMethod 'http://127.0.0.1:8791/api/health' -TimeoutSec 2 } catch {
    $logDirectory = Join-Path $projectDirectory 'output/dashboard'
    New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
    Start-Process -FilePath $pythonExecutable -ArgumentList '-m','billintel.dashboard' -WorkingDirectory $projectDirectory -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDirectory 'server.log') -RedirectStandardError (Join-Path $logDirectory 'server-errors.log')
}
try { Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 | Out-Null } catch {
    $ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
    if ($ollamaCommand) {
        $env:OLLAMA_NO_CLOUD = '1'
        Start-Process -FilePath $ollamaCommand.Source -ArgumentList 'serve' -WindowStyle Hidden
    }
}
if ($health -and $health.app -ne 'greenworks') { throw 'Port 8791 is occupied by another application.' }
$ready = $false
for ($attempt=0; $attempt -lt 15; $attempt++) {
    try { $probe = Invoke-RestMethod 'http://127.0.0.1:8791/api/health' -TimeoutSec 4; if ($probe.app -eq 'greenworks') { $ready = $true; break } } catch { Start-Sleep -Seconds 1 }
}
if (-not $ready) { throw 'Dashboard did not start. Check output/dashboard/server-errors.log and install dependencies with python -m pip install -e .' }
Start-Process 'http://127.0.0.1:8791'
