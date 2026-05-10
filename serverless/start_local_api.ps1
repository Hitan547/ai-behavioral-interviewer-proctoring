$ErrorActionPreference = "Continue"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = "C:\Users\Hitan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$outLogPath = Join-Path $scriptDir "_local_server.out.log"
$errLogPath = Join-Path $scriptDir "_local_server.err.log"

Set-Location $scriptDir
& $python "local_server.py" 1> $outLogPath 2> $errLogPath
