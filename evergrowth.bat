@echo off

REM Evergrowth Launcher with Autonomous Brain Enhancement
REM Smart repository detection and process management

echo Determining working directory...

REM Get the directory of this batch file and determine repository location
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"

set "EXPECTED_REPO_ROOT=C:\\FoxPur-Studios\\evergrowth"

set "POSSIBLE_REPOS=%EXPECTED_REPO_ROOT% %SCRIPT_DIR%..\\evergrowth %SCRIPT_DIR%..\\..\\FoxPur-Studios\\evergrowth"

set "REPO_ROOT="

REM Check each possible location
for "%%repo in (%POSSIBLE_REPOS%)" do (
    if exist "%%repo\" (
        set "REPO_ROOT=%%repo"
        echo Found Evergrowth repository at: %%repo
        goto found
    )
)

echo Error: Could not find Evergrowth repository in any expected location.
echo Searched in:

for "%%repo in (%POSSIBLE_REPOS%)" do (
    echo - %%repo
)

echo.
echo Please ensure the Evergrowth repository is installed at one of the locations above.
echo You can download it from: https://github.com/FoxPur-Studios/evergrowth
pause
exit /b 1

:found
echo Repository based on: Foxpur-Studios github organization (enhanced with autonomous brain)
echo Launching Evergrowth with self-prompt generation and research automation capabilities.
echo.

cd /d "%REPO_ROOT%"

REM Check for virtual environment
if exist ".venv" (
    echo Found virtual environment: .venv
    call .venv\Scripts\activate.bat
) else if exist "venv" (
    echo Found virtual environment: venv
    call venv\Scripts\activate.bat
) else (
    echo Warning: .venv not found. Creating new virtual environment...
    python -m venv .venv
    if errorlevel neq 0 (
        echo Error: Failed to create virtual environment. Please install Python and ensure it's in your PATH.
        pause
        exit /b 1
    )
    call .venv\Scripts\activate.bat
)

echo.
echo Starting Evergrowth with Autonomous Brain and Self-Prompt Generation...
echo.
echo Launching in autonomous mode (enabled by default)...
echo This will generate self-prompts for research, skills, and project management
echo.
echo To temporarily pause autonomous prompts, press Ctrl+C when prompted by the application
echo.

REM Start the application and wait for it to complete
python -m evergrowth --autonomous --verbose

if errorlevel neq 0 (
    echo.
    echo Evergrowth exited with error code: %errorlevel%
    echo Press any key to exit...
    pause > nul
    exit /b %errorlevel%
)

echo.
echo Evergrowth has been shut down successfully.
echo Press any key to exit...
pause > nul
