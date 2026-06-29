param(
    [string]$Python = "python"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
New-Item -ItemType Directory -Force -Path (Join-Path $Root "outputs/sample") | Out-Null
& $Python '.\project\run_example.py' '--output-dir' '.\outputs\sample'
if ($LASTEXITCODE -ne 0) { throw "Sample run failed with exit code $LASTEXITCODE" }
