# PowerShell build script for Vox Client
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$Venv = Join-Path $ProjectRoot ".venv"

Set-Location $ProjectRoot

# Check for venv
if (-not (Test-Path $Venv)) {
    Write-Error ".venv not found at $Venv`nCreate it with: python -m venv .venv; .venv\Scripts\pip install -e '.[dev]'"
    exit 1
}

$Python = Join-Path $Venv "Scripts\python.exe"
$Pip = Join-Path $Venv "Scripts\pip.exe"

# Install project + SDK (vox-sdk is on PyPI)
Write-Host "Installing dependencies..."
& $Pip install -e ".[dev]" --quiet

# Ensure pyinstaller is installed
try {
    & $Python -m PyInstaller --version 2>&1 | Out-Null
} catch {
    Write-Host "Installing PyInstaller..."
    & $Pip install "pyinstaller>=6.0"
}

# Clean previous builds
Write-Host "Cleaning build/ and dist/..."
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }

# Run PyInstaller
Write-Host "Building with PyInstaller..."
& $Python -m PyInstaller vox-client.spec --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Error "Build failed."
    exit 1
}

Write-Host ""
Write-Host "Build complete!"
Write-Host ""
Write-Host "Distributable: dist\vox-client\"
Write-Host "  Launch: dist\vox-client\vox-client.exe"
