#!/bin/bash

# SMS Database GUI Launcher
echo "SMS Database GUI Launcher"
echo "========================="

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install requirements
echo "Installing requirements..."
pip install -r requirements_gui.txt

# Check if API is running
echo "Checking API status..."
if curl -s http://localhost:5000/api/health > /dev/null 2>&1; then
    echo "✓ API is running on http://localhost:5000"
else
    echo "⚠ API not detected. Make sure to run sim800l_hat_db_api.py first"
    echo "  You can start it with: python3 sim800l_hat_db_api.py"
fi

echo ""
echo "Starting SMS GUI Application..."
python3 SMS_GUI.py
