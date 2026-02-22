@echo off
setlocal enabledelayedexpansion

:: Resolve project root (parent of scripts/)
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%.."
set "PROJECT_ROOT=%CD%"
popd

set "VENV=%PROJECT_ROOT%\.venv"

cd /d "%PROJECT_ROOT%"

:: Check for venv
if not exist "%VENV%\" (
    echo ERROR: .venv not found at %VENV%
    echo Create it with: python -m venv .venv ^&^& .venv\Scripts\pip install --find-links https://github.com/cmorg789/vox-py-sdk/releases/latest -e ".[dev]"
    exit /b 1
)

set "PYTHON=%VENV%\Scripts\python.exe"

:: GitHub Releases URL for vox-py-sdk wheels
set "SDK_RELEASES=https://github.com/cmorg789/vox-py-sdk/releases/latest"

:: Install/upgrade project + SDK from GitHub Releases
echo Installing dependencies (SDK from GitHub Releases^)...
"%VENV%\Scripts\pip.exe" install --find-links "%SDK_RELEASES%" -e ".[dev]" --quiet

:: Ensure pyinstaller is installed
"%PYTHON%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    "%VENV%\Scripts\pip.exe" install "pyinstaller>=6.0"
)

:: Clean previous builds
echo Cleaning build\ and dist\...
if exist build\ rmdir /s /q build
if exist dist\ rmdir /s /q dist

:: Run PyInstaller
echo Building with PyInstaller...
"%PYTHON%" -m PyInstaller vox-client.spec --noconfirm
if errorlevel 1 (
    echo.
    echo Build FAILED.
    exit /b 1
)

echo.
echo Build complete!
echo.
echo Distributable: dist\vox-client\
echo   Launch: dist\vox-client\vox-client.exe
