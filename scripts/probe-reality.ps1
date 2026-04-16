param(
    [string]$Region = "us",
    [string]$Domains,
    [switch]$ListRegions,
    [string]$ServerIp
)

$ErrorActionPreference = "Stop"
$repoSlug = if ($env:SBOXCTL_REPO_SLUG) { $env:SBOXCTL_REPO_SLUG } else { "dodo258/sbox-deploy-tool" }
$repoRef = if ($env:SBOXCTL_REPO_REF) { $env:SBOXCTL_REPO_REF } else { "main" }
$archiveUrl = "https://github.com/$repoSlug/archive/refs/heads/$repoRef.zip"

$python = Get-Command py -ErrorAction SilentlyContinue
if ($python) {
    $pythonCmd = @($python.Source, "-3")
} else {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        Write-Host "[ERR] python is required"
        exit 1
    }
    $pythonCmd = @($python.Source)
}

$tempDir = Join-Path $env:TEMP ("sboxctl-probe-" + [guid]::NewGuid().ToString())
$archivePath = Join-Path $tempDir "repo.zip"
New-Item -ItemType Directory -Path $tempDir | Out-Null

try {
    Invoke-WebRequest -Uri $archiveUrl -OutFile $archivePath
    Expand-Archive -Path $archivePath -DestinationPath $tempDir -Force
    $rootDir = Get-ChildItem -Path $tempDir -Directory | Where-Object { $_.Name -like "sbox-deploy-tool-*" } | Select-Object -First 1
    if (-not $rootDir) {
        Write-Host "[ERR] failed to unpack repository"
        exit 1
    }
    $env:PYTHONPATH = Join-Path $rootDir.FullName "lib"
    $probeArgs = @("-m", "sbox_tool.cli", "probe")
    if ($ListRegions) {
        $probeArgs += "--list-regions"
    } elseif ($ServerIp) {
        $probeArgs += @("--server-ip", $ServerIp)
    } elseif ($Domains) {
        $probeArgs += @("--domains", $Domains)
    } else {
        $probeArgs += @("--region", $Region)
    }
    if ($pythonCmd.Count -gt 1) {
        & $pythonCmd[0] $pythonCmd[1] $probeArgs
    } else {
        & $pythonCmd[0] $probeArgs
    }
}
finally {
    Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}
