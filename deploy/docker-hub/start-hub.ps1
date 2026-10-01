$ErrorActionPreference = 'Stop'
$docker = (Get-Command docker -ErrorAction SilentlyContinue).Source
if (-not $docker) {
    $docker = @(
        "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe",
        "$env:ProgramFiles\Docker\Docker\resources\bin\docker.exe"
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $docker) {
    throw 'Docker CLI was not found. Install and start Docker Desktop first.'
}

Push-Location -LiteralPath $PSScriptRoot
try {
    & $docker info --format '{{.ServerVersion}}' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Docker Engine is unavailable. Start Docker Desktop first.' }

    Write-Host 'Sign in to Docker Hub with the account that can access the private erp-risk-demo repository.'
    & $docker login
    if ($LASTEXITCODE -ne 0) { throw 'Docker Hub sign-in failed.' }

    & $docker compose -f compose.yaml pull
    if ($LASTEXITCODE -ne 0) { throw 'Image download failed. Check Docker Hub access to the private repository and the image tags.' }

    & $docker compose -f compose.yaml up --detach --no-build --pull never --wait --wait-timeout 180
    if ($LASTEXITCODE -ne 0) { throw 'Container startup or health check failed. Run docker compose -f compose.yaml logs.' }

    $resolvedCompose = & $docker compose -f compose.yaml config --format json
    if ($LASTEXITCODE -ne 0) { throw 'Could not read the Compose port configuration.' }
    $publishedPort = [string]((($resolvedCompose -join "`n") | ConvertFrom-Json).services.web.ports[0].published)
    $parsedPort = 0
    if (-not [int]::TryParse($publishedPort, [ref]$parsedPort) -or $parsedPort -lt 1 -or $parsedPort -gt 65535) {
        throw 'Could not determine the published web port.'
    }
} finally {
    Pop-Location
}

try {
    $ready = Invoke-RestMethod -Uri "http://127.0.0.1:$parsedPort/api/v1/ready" -TimeoutSec 10
    if ($ready.status -ne 'ready') { throw 'API readiness did not return ready.' }
} catch {
    throw "Web-to-API check failed: $($_.Exception.Message)"
}

Write-Host "Open locally: http://localhost:$parsedPort"
Write-Host "Others on the same network: http://<this computer's LAN IPv4 address>:$parsedPort"
if ((Get-Command Get-NetIPAddress -ErrorAction SilentlyContinue) -and (Get-Command Get-NetRoute -ErrorAction SilentlyContinue)) {
    $routeInterfaces = @(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
        Where-Object { $_.NextHop -and $_.NextHop -ne '0.0.0.0' } |
        Sort-Object RouteMetric |
        Select-Object -ExpandProperty InterfaceIndex -Unique)
    foreach ($index in $routeInterfaces) {
        Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $index -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
            ForEach-Object { Write-Host "LAN URL [$($_.InterfaceAlias)]: http://$($_.IPAddress):$parsedPort" }
    }
}
Write-Host "If others cannot connect, check the host firewall for TCP $parsedPort."
