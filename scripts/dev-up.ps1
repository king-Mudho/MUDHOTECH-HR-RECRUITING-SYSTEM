# MUDHOTECH HR RECRUITING SYSTEM - start the local development stack (Windows PowerShell).
# Usage:  ./scripts/dev-up.ps1 [-Full] [-NoSeed]
#   -Full    also start ClamAV (large image + virus DB download on first run)
#   -NoSeed  skip demo data seeding
param(
    [switch]$Full,
    [switch]$NoSeed
)
# "Continue" (not "Stop"): Windows PowerShell 5.1 turns docker's progress output on stderr into
# terminating errors. Failures are detected through $LASTEXITCODE instead.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is not installed or not on PATH. Install Docker Desktop (WSL2 backend)."
}
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker Desktop is not running. Start it and try again." }

if (-not (Test-Path -LiteralPath (Join-Path $root ".env"))) {
    Copy-Item -LiteralPath (Join-Path $root ".env.example") -Destination (Join-Path $root ".env")
    Write-Host "Created .env from .env.example"
}

$profileArgs = @()
if ($Full) { $profileArgs = @("--profile", "full") }

Write-Host "Building and starting the stack (project 'mhrs')..."
docker compose @profileArgs up -d --build
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }

Write-Host "Waiting for the backend to become healthy..."
$deadline = (Get-Date).AddMinutes(10)
do {
    Start-Sleep -Seconds 5
    $state = docker inspect --format "{{.State.Health.Status}}" mhrs-backend-1 2>$null
} while ($state -ne "healthy" -and (Get-Date) -lt $deadline)
if ($state -ne "healthy") { throw "Backend did not become healthy in time. See: docker compose logs backend" }

docker compose exec -T backend python manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { throw "migrate failed" }
if (-not $NoSeed) {
    docker compose exec -T backend python manage.py help seed_demo *> $null
    if ($LASTEXITCODE -eq 0) { docker compose exec -T backend python manage.py seed_demo }
    else { Write-Host "seed_demo not available yet (added in later phases) - skipping." }
}

Write-Host ""
Write-Host "MUDHOTECH HR RECRUITING SYSTEM is up:"
Write-Host "  Frontend   http://localhost:3000"
Write-Host "  API docs   http://localhost:8000/api/docs/"
Write-Host "  Ready      http://localhost:8000/readyz"
Write-Host "  Mailpit    http://localhost:8025"
Write-Host "  S3 (dev)   http://localhost:9000"
Write-Host "  Flower     http://localhost:5555"
