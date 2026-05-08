#!/bin/bash
echo "Setting up MCAT Flasher Virtual Environment..."

# Remove existing virtual environment if it exists
if [ -d "flashenv" ]; then
    echo "Removing existing virtual environment..."
    rm -rf flashenv
fi

# Create the virtual environment
python3 -m venv flashenv

# Activate it
source flashenv/bin/activate

# Upgrade pip and install requirements
pip install --upgrade pip
pip install -r requirements.txt

echo "Environment setup complete! Run 'source flashenv/bin/activate' to start working."