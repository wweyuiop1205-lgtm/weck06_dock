$ErrorActionPreference = 'Stop'
$docker = (Get-Command docker -ErrorAction SilentlyContinue).Source
if (-not $docker) {
    $docker = @(
        "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe",
        "$env:ProgramFiles\Docker\Docker\resources\bin\docker.exe"
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $docker) { throw 'Docker CLI was not found.' }
Push-Location -LiteralPath $PSScriptRoot
try {
    & $docker compose -f compose.yaml down
    if ($LASTEXITCODE -ne 0) { throw 'Could not stop the containers.' }
} finally {
    Pop-Location
}
Write-Host 'Containers stopped. The demo data volume is retained.'
