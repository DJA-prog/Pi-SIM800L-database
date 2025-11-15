#!/bin/bash
"""
SMS Manager API Setup Script
Installs dependencies and sets up the SMS Manager API
"""

echo "🚀 Setting up SMS Manager API"
echo "=================================="

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "⚠️  This script should not be run as root (except for system services)"
   echo "   Run as regular user: ./setup_sms_api.sh"
   exit 1
fi

echo "1. Updating package lists..."
sudo apt update

echo "2. Installing system dependencies..."
sudo apt install -y python3-pip python3-venv pigpio

echo "3. Starting pigpio daemon..."
sudo systemctl enable pigpiod
sudo systemctl start pigpiod

echo "4. Creating Python virtual environment..."
python3 -m venv sms_api_env

echo "5. Activating virtual environment and installing Python dependencies..."
source sms_api_env/bin/activate
pip install --upgrade pip
pip install -r requirements_sms_api.txt

echo "6. Setting executable permissions..."
chmod +x sms_manager_api.py
chmod +x test_sms_api.py

echo "7. Creating systemd service file..."
sudo tee /etc/systemd/system/sms-manager-api.service > /dev/null <<EOF
[Unit]
Description=SIM800L SMS Manager API
After=network.target pigpiod.service
Requires=pigpiod.service

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$PWD
Environment=PATH=$PWD/sms_api_env/bin
ExecStart=$PWD/sms_api_env/bin/python $PWD/sms_manager_api.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "8. Reloading systemd..."
sudo systemctl daemon-reload

echo ""
echo "✅ SMS Manager API setup completed!"
echo ""
echo "🔧 Configuration:"
echo "   Set environment variables in ~/.bashrc or create .env file:"
echo "   export SIM_PIN='your_sim_pin'"
echo "   export RX_PIN=13"
echo "   export TX_PIN=12"
echo "   export AUTO_DELETE_SMS=true"
echo ""
echo "🚀 Usage:"
echo "   Manual start: source sms_api_env/bin/activate && python3 sms_manager_api.py"
echo "   Service start: sudo systemctl start sms-manager-api"
echo "   Service enable: sudo systemctl enable sms-manager-api"
echo "   Service status: sudo systemctl status sms-manager-api"
echo ""
echo "🧪 Testing:"
echo "   python3 test_sms_api.py"
echo ""
echo "🌐 API Documentation:"
echo "   http://localhost:8000/docs"
echo "   http://localhost:8000/redoc"