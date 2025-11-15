#!/bin/bash

# SIM800L SMS Manager API with Database - Setup Script
# This script sets up the SMS Manager API with SQLite database support

set -e  # Exit on any error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_NAME="sms_db_api_env"
SERVICE_NAME="sms-manager-db"

echo "🚀 Setting up SIM800L SMS Manager API with Database"
echo "============================================================="

# Check if running as root for system service installation
if [[ $EUID -eq 0 ]]; then
    echo "⚠️  Running as root - will install system service"
    INSTALL_SERVICE=true
    SERVICE_USER="pi"  # Change this if needed
else
    echo "ℹ️  Running as user - will setup local environment only"
    INSTALL_SERVICE=false
    SERVICE_USER=$(whoami)
fi

# Update system packages
echo "📦 Updating system packages..."
if command -v apt &> /dev/null; then
    sudo apt update
    sudo apt install -y python3 python3-venv python3-pip pigpio
elif command -v yum &> /dev/null; then
    sudo yum install -y python3 python3-pip
else
    echo "⚠️  Package manager not detected. Please install Python 3, pip, and pigpio manually."
fi

# Enable and start pigpio daemon
echo "🔌 Setting up pigpio daemon..."
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
sleep 2

# Create virtual environment
echo "🐍 Creating Python virtual environment..."
cd "$SCRIPT_DIR"
if [ -d "$VENV_NAME" ]; then
    echo "   Virtual environment already exists"
else
    python3 -m venv "$VENV_NAME"
    echo "   ✓ Virtual environment created"
fi

# Activate virtual environment and install dependencies
echo "📚 Installing Python dependencies..."
source "$VENV_NAME/bin/activate"
pip install --upgrade pip
pip install -r requirements_sms_db_api.txt
echo "   ✓ Dependencies installed"

# Create database directory with proper permissions
echo "🗄️ Setting up database directory..."
DB_DIR="/var/lib/sms-manager"
if [ "$INSTALL_SERVICE" = true ]; then
    sudo mkdir -p "$DB_DIR"
    sudo chown "$SERVICE_USER:$SERVICE_USER" "$DB_DIR"
    sudo chmod 755 "$DB_DIR"
    DB_PATH="$DB_DIR/sms_manager.db"
else
    mkdir -p "$HOME/.sms-manager"
    DB_PATH="$HOME/.sms-manager/sms_manager.db"
fi

# Create environment configuration file
echo "⚙️ Creating environment configuration..."
ENV_FILE="sms_db_api.env"
cat > "$ENV_FILE" << EOF
# SIM800L SMS Manager API with Database - Environment Configuration
# GPIO Configuration
RX_PIN=13
TX_PIN=12
BAUDRATE=9600

# SIM Configuration
SIM_PIN=9438

# Database Configuration
DB_PATH=$DB_PATH

# Debug Settings
SHOW_RAW_DEBUG=false
AUTO_DELETE_SMS=true

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
EOF

echo "   ✓ Environment file created: $ENV_FILE"

# Create run script
echo "📜 Creating run script..."
RUN_SCRIPT="run_sms_db_api.sh"
cat > "$RUN_SCRIPT" << EOF
#!/bin/bash

# SIM800L SMS Manager API with Database - Run Script
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
cd "\$SCRIPT_DIR"

# Load environment variables
if [ -f "sms_db_api.env" ]; then
    export \$(cat sms_db_api.env | grep -v '^#' | xargs)
fi

# Activate virtual environment
source $VENV_NAME/bin/activate

# Check if pigpio is running
if ! pgrep -x "pigpiod" > /dev/null; then
    echo "⚠️  pigpiod is not running. Starting it..."
    sudo systemctl start pigpiod
    sleep 2
fi

# Start the API
echo "🚀 Starting SIM800L SMS Manager API with Database..."
python3 sms_mgr_db_api.py "\${API_PORT:-8000}"
EOF

chmod +x "$RUN_SCRIPT"
echo "   ✓ Run script created: $RUN_SCRIPT"

# Create systemd service if running as root
if [ "$INSTALL_SERVICE" = true ]; then
    echo "🔧 Creating systemd service..."
    
    SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
    sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=SIM800L SMS Manager API with Database
After=network.target pigpiod.service
Requires=pigpiod.service

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$SCRIPT_DIR
Environment=PATH=$SCRIPT_DIR/$VENV_NAME/bin
EnvironmentFile=-$SCRIPT_DIR/sms_db_api.env
ExecStart=$SCRIPT_DIR/$VENV_NAME/bin/python3 $SCRIPT_DIR/sms_mgr_db_api.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    # Reload systemd and enable service
    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE_NAME"
    
    echo "   ✓ Systemd service created: $SERVICE_NAME"
    echo "   ✓ Service enabled for automatic startup"
fi

# Create test script
echo "🧪 Creating test script..."
TEST_SCRIPT="test_sms_db_api.sh"
cat > "$TEST_SCRIPT" << EOF
#!/bin/bash

# SIM800L SMS Manager API with Database - Test Script
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
cd "\$SCRIPT_DIR"

# Activate virtual environment
source $VENV_NAME/bin/activate

# Run tests
echo "🧪 Running SMS Manager Database API tests..."
python3 test_sms_db_api.py --mode full --output test_results_\$(date +%Y%m%d_%H%M%S).json
EOF

chmod +x "$TEST_SCRIPT"
echo "   ✓ Test script created: $TEST_SCRIPT"

echo ""
echo "✅ Setup completed successfully!"
echo "============================================================="
echo ""
echo "📋 Next Steps:"
echo ""

if [ "$INSTALL_SERVICE" = true ]; then
    echo "🔧 Service Management:"
    echo "   Start service:    sudo systemctl start $SERVICE_NAME"
    echo "   Stop service:     sudo systemctl stop $SERVICE_NAME"
    echo "   View logs:        sudo journalctl -u $SERVICE_NAME -f"
    echo "   Service status:   sudo systemctl status $SERVICE_NAME"
    echo ""
fi

echo "🚀 Manual Execution:"
echo "   Start API:        ./$RUN_SCRIPT"
echo "   Run tests:        ./$TEST_SCRIPT"
echo ""
echo "🌐 API Access:"
echo "   API URL:          http://localhost:8000"
echo "   Documentation:    http://localhost:8000/docs"
echo "   Interactive:      http://localhost:8000/redoc"
echo ""
echo "🗄️ Database:"
echo "   Location:         $DB_PATH"
echo "   Configuration:    $ENV_FILE"
echo ""
echo "📁 Files Created:"
echo "   • $VENV_NAME/              - Python virtual environment"
echo "   • $ENV_FILE               - Environment configuration"
echo "   • $RUN_SCRIPT            - API start script"
echo "   • $TEST_SCRIPT           - Test execution script"
if [ "$INSTALL_SERVICE" = true ]; then
echo "   • $SERVICE_FILE   - Systemd service"
fi
echo ""
echo "💡 Configuration Tips:"
echo "   • Edit $ENV_FILE to customize GPIO pins, database path, etc."
echo "   • Set SIM_PIN in $ENV_FILE if your SIM card requires a PIN"
echo "   • Check pigpio service: sudo systemctl status pigpiod"
echo "   • Database will be created automatically on first run"
echo ""
echo "🔧 Hardware Requirements:"
echo "   • SIM800L module connected to GPIO pins (default: RX=13, TX=12)"
echo "   • SIM card inserted and activated"
echo "   • Antenna connected to SIM800L"
echo "   • Power supply adequate for SIM800L (2A recommended)"
echo ""
echo "🆘 Troubleshooting:"
echo "   • Ensure pigpiod is running: sudo systemctl start pigpiod"
echo "   • Check GPIO connections and power supply"
echo "   • Verify SIM card is inserted and PIN is correct"
echo "   • Check database permissions if using custom DB_PATH"
echo ""
echo "Ready to start! 🚀"