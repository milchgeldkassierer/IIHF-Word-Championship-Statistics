@echo off
echo === Git Commit Script ===
echo.

echo Checking git status...
git status

echo.
echo Adding all files...
git add .

echo.
echo Committing changes...
git commit -m "Fix all-time standings calculation consistency"

echo.
echo Git operations completed!
echo.
echo To test the PowerShell fix:
echo 1. Close current PowerShell window
echo 2. Open new PowerShell window
echo 3. Use short commands: gs, ga, gc

pause 