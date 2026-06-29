param(
    [string]$Python = "python",
    [string]$LiveRoot = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
if ([string]::IsNullOrWhiteSpace($LiveRoot) -or -not (Test-Path -LiteralPath $LiveRoot)) {
    Write-Error "Provide -LiveRoot pointing to the Bloomberg CLO contract folder."
    exit 2
}
New-Item -ItemType Directory -Force -Path (Join-Path $Root "outputs\live") | Out-Null
& $Python .\project\run_example.py --live-root $LiveRoot --output-dir .\outputs\live
if ($LASTEXITCODE -ne 0) { throw "Live run failed with exit code $LASTEXITCODE" }
