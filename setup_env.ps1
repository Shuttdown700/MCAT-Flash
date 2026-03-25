Write-Host "Setting up MCAT Flasher Virtual Environment..." -ForegroundColor Cyan

# Remove existing virtual environment if it exists
if (Test-Path -Path "flashenv") {
    Write-Host "Removing existing virtual environment..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force flashenv
}

# Create the virtual environment
python -m venv flashenv

# Activate it
.\flashenv\Scripts\Activate.ps1

# Upgrade pip and install requirements
python -m pip install --upgrade pip
pip install -r requirements.txt

Write-Host "Environment setup complete! Run '.\flashenv\Scripts\Activate.ps1' to start working." -ForegroundColor Green