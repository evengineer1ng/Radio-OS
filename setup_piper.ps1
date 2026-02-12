#!/usr/bin/env pwsh
# setup_piper.ps1 - Windows PowerShell Piper Setup Helper
# Quick standalone Piper + Voice setup for Windows users

Write-Host "🎙️  Radio OS - Piper TTS Setup (Windows)" -ForegroundColor Cyan
Write-Host "=" * 50
Write-Host ""

# Check if Python is available
try {
    $pythonVersion = python --version 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Python found: $pythonVersion" -ForegroundColor Green
    } else {
        throw "Python not found"
    }
} catch {
    Write-Host "❌ Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install Python 3.10+ from:" -ForegroundColor Yellow
    Write-Host "   https://www.python.org/downloads/" -ForegroundColor White
    Write-Host "   OR use: winget install Python.Python.3.11" -ForegroundColor White
    Write-Host ""
    Write-Host "Make sure to check 'Add Python to PATH' during installation!" -ForegroundColor Yellow
    pause
    exit 1
}

Write-Host ""
Write-Host "🚀 Starting enhanced Piper setup..." -ForegroundColor Green
Write-Host ""

# Run the main setup script
try {
    python setup.py
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "🎉 Setup completed successfully!" -ForegroundColor Green
        Write-Host ""
        Write-Host "📋 Next steps:" -ForegroundColor Yellow
        Write-Host "   1. Launch Radio OS: python shell_bookmark.py" -ForegroundColor White
        Write-Host "   2. Configure voice paths in station manifests" -ForegroundColor White
        Write-Host "   3. Test TTS in any station!" -ForegroundColor White
        Write-Host ""
    } else {
        throw "Setup failed"
    }
} catch {
    Write-Host "❌ Setup failed. Please check the error above." -ForegroundColor Red
    Write-Host ""
    Write-Host "💡 Try running manually:" -ForegroundColor Yellow
    Write-Host "   python setup.py" -ForegroundColor White
    Write-Host ""
}

Write-Host "Press any key to continue..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")