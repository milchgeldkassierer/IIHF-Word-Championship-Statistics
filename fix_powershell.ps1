# PowerShell PSReadLine Fix Script
# This script creates a permanent fix for PSReadLine crashes

Write-Host "=== PowerShell PSReadLine Fix ===" -ForegroundColor Green

# Get PowerShell profile path
$ProfilePath = $PROFILE

# Create profile directory if it doesn't exist
$ProfileDir = Split-Path $ProfilePath
if (!(Test-Path $ProfileDir)) {
    New-Item -ItemType Directory -Path $ProfileDir -Force
    Write-Host "Created profile directory: $ProfileDir" -ForegroundColor Yellow
}

# Create or update PowerShell profile
$ProfileContent = @"
# PowerShell Profile - PSReadLine Fix
# This configuration prevents PSReadLine crashes

# Option 1: Disable PSReadLine completely (most reliable)
if (`$Host.Name -eq 'ConsoleHost') {
    try {
        Remove-Module PSReadLine -ErrorAction SilentlyContinue
        Import-Module PSReadLine -Force -ErrorAction SilentlyContinue
        
        # Safe PSReadLine configuration
        Set-PSReadLineOption -EditMode Windows
        Set-PSReadLineOption -HistorySearchCursorMovesToEnd
        Set-PSReadLineOption -PredictionSource None
        Set-PSReadLineOption -MaximumHistoryCount 1000
        
        # Disable problematic features
        Set-PSReadLineKeyHandler -Key Tab -Function Complete
        Set-PSReadLineKeyHandler -Key Ctrl+d -Function DeleteChar
        
        Write-Host "PSReadLine konfiguriert - Verbesserte Konfiguration aktiv" -ForegroundColor Green
    }
    catch {
        # If PSReadLine still causes issues, disable it completely
        Remove-Module PSReadLine -ErrorAction SilentlyContinue
        Write-Host "PSReadLine deaktiviert - Fallback-Modus aktiv" -ForegroundColor Yellow
    }
}

# Git aliases for easier usage
function Git-Status { git status }
function Git-Add { git add `$args }
function Git-Commit { git commit `$args }
function Git-Push { git push `$args }
function Git-Pull { git pull `$args }

Set-Alias -Name gs -Value Git-Status
Set-Alias -Name ga -Value Git-Add
Set-Alias -Name gc -Value Git-Commit
Set-Alias -Name gp -Value Git-Push
Set-Alias -Name gl -Value Git-Pull

# Python shortcut
function py { python `$args }

Write-Host "PowerShell-Profil geladen - Verbesserte PSReadLine-Konfiguration aktiv" -ForegroundColor Green
"@

# Write profile content
Set-Content -Path $ProfilePath -Value $ProfileContent -Encoding UTF8

Write-Host "PowerShell-Profil erstellt/aktualisiert: $ProfilePath" -ForegroundColor Green
Write-Host ""
Write-Host "=== Lösung 1: Profil-basierte Lösung ===" -ForegroundColor Cyan
Write-Host "Das PowerShell-Profil wurde erstellt/aktualisiert."
Write-Host "Bei neuen PowerShell-Sitzungen wird PSReadLine korrekt konfiguriert."
Write-Host ""
Write-Host "=== Lösung 2: Alternativ CMD verwenden ===" -ForegroundColor Cyan
Write-Host "Für Git-Befehle können Sie auch direkt CMD verwenden:"
Write-Host "  cmd /c 'git status'"
Write-Host "  cmd /c 'git add .'"
Write-Host "  cmd /c 'git commit -m \"message\"'"
Write-Host ""
Write-Host "=== Test der Lösung ===" -ForegroundColor Cyan
Write-Host "Starten Sie eine neue PowerShell-Sitzung und testen Sie:"
Write-Host "  gs              # Git Status"
Write-Host "  ga .            # Git Add All"
Write-Host "  gc -m \"test\"   # Git Commit"
Write-Host ""
Write-Host "Führen Sie 'powershell -NoProfile' aus, um PowerShell ohne Profil zu starten."
Write-Host "=== Fix komplett ===" -ForegroundColor Green 