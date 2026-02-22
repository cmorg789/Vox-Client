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
    echo Create it with: python -m venv .venv
    exit /b 1
)

set "PYTHON=%VENV%\Scripts\python.exe"

:: Download SDK wheels from GitHub Releases
echo Fetching SDK wheels...
if not exist sdk-wheels mkdir sdk-wheels
gh release download --repo cmorg789/vox-py-sdk --pattern "*.whl" --dir sdk-wheels --clobber

:: Install project + SDK
echo Installing dependencies...
"%VENV%\Scripts\pip.exe" install --find-links sdk-wheels\ -e ".[dev]" --quiet

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
