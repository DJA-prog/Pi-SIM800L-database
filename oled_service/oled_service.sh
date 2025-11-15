#!/bin/bash

# OLED Service Management Script
# Provides easy commands to manage the OLED display service

SERVICE_NAME="oled-service"
LOG_FILE="/var/log/oled-service.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

case "$1" in
    start)
        echo -e "${BLUE}🚀 Starting OLED service...${NC}"
        sudo systemctl start $SERVICE_NAME
        sleep 2
        if sudo systemctl is-active --quiet $SERVICE_NAME; then
            echo -e "${GREEN}✅ Service started successfully${NC}"
        else
            echo -e "${RED}❌ Failed to start service${NC}"
            exit 1
        fi
        ;;
    stop)
        echo -e "${YELLOW}🛑 Stopping OLED service...${NC}"
        sudo systemctl stop $SERVICE_NAME
        echo -e "${GREEN}✅ Service stopped${NC}"
        ;;
    restart)
        echo -e "${BLUE}🔄 Restarting OLED service...${NC}"
        sudo systemctl restart $SERVICE_NAME
        sleep 2
        if sudo systemctl is-active --quiet $SERVICE_NAME; then
            echo -e "${GREEN}✅ Service restarted successfully${NC}"
        else
            echo -e "${RED}❌ Failed to restart service${NC}"
            exit 1
        fi
        ;;
    status)
        echo -e "${BLUE}📊 OLED Service Status${NC}"
        echo "======================"
        sudo systemctl status $SERVICE_NAME --no-pager
        echo
        echo -e "${BLUE}🌐 API Health Check:${NC}"
        if curl -s http://localhost:5001/api/health >/dev/null 2>&1; then
            echo -e "${GREEN}✅ API is responding${NC}"
            curl -s http://localhost:5001/api/health | python3 -m json.tool 2>/dev/null || echo "API response received"
        else
            echo -e "${RED}❌ API is not responding${NC}"
        fi
        ;;
    enable)
        echo -e "${BLUE}⚡ Enabling OLED service for auto-start...${NC}"
        sudo systemctl enable $SERVICE_NAME
        echo -e "${GREEN}✅ Service enabled for auto-start${NC}"
        ;;
    disable)
        echo -e "${YELLOW}⛔ Disabling OLED service auto-start...${NC}"
        sudo systemctl disable $SERVICE_NAME
        echo -e "${GREEN}✅ Service disabled from auto-start${NC}"
        ;;
    logs)
        echo -e "${BLUE}📝 OLED Service Logs (press Ctrl+C to exit)${NC}"
        echo "============================================="
        if [ "$2" = "follow" ] || [ "$2" = "-f" ]; then
            sudo journalctl -u $SERVICE_NAME -f --no-pager
        else
            sudo journalctl -u $SERVICE_NAME --no-pager | tail -50
        fi
        ;;
    test)
        echo -e "${BLUE}🧪 Testing OLED Service${NC}"
        echo "======================="
        
        # Test health endpoint
        echo "Testing health endpoint..."
        if curl -s http://localhost:5001/api/health >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Health check passed${NC}"
        else
            echo -e "${RED}❌ Health check failed${NC}"
            exit 1
        fi
        
        # Test status endpoint
        echo "Testing status endpoint..."
        if curl -s http://localhost:5001/api/status >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Status endpoint working${NC}"
        else
            echo -e "${RED}❌ Status endpoint failed${NC}"
        fi
        
        # Test display update
        echo "Testing display update..."
        if curl -s -X POST http://localhost:5001/api/display/update \
           -H "Content-Type: application/json" \
           -d '{"wifi_ip":"192.168.1.100","battery_percent":85,"message_count":5}' >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Display update test passed${NC}"
        else
            echo -e "${RED}❌ Display update test failed${NC}"
        fi
        
        echo -e "${GREEN}🎉 All tests completed${NC}"
        ;;
    config)
        echo -e "${BLUE}⚙️  Opening configuration file...${NC}"
        if [ -f "/home/pi/oled_service/.env.oled" ]; then
            nano /home/pi/oled_service/.env.oled
            echo
            echo -e "${YELLOW}⚠️  Restart the service to apply changes:${NC}"
            echo "   $0 restart"
        else
            echo -e "${RED}❌ Configuration file not found${NC}"
            echo "Expected location: /home/pi/oled_service/.env.oled"
        fi
        ;;
    install)
        echo -e "${BLUE}📦 Running installation...${NC}"
        if [ -f "/home/pi/oled_service/install_oled_service.sh" ]; then
            cd /home/pi/oled_service
            ./install_oled_service.sh
        else
            echo -e "${RED}❌ Installation script not found${NC}"
        fi
        ;;
    uninstall)
        echo -e "${YELLOW}🗑️  Uninstalling OLED service...${NC}"
        read -p "Are you sure you want to uninstall the OLED service? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            sudo systemctl stop $SERVICE_NAME 2>/dev/null || true
            sudo systemctl disable $SERVICE_NAME 2>/dev/null || true
            sudo rm -f /etc/systemd/system/$SERVICE_NAME.service
            sudo systemctl daemon-reload
            echo -e "${GREEN}✅ Service uninstalled${NC}"
            echo -e "${BLUE}ℹ️  Service files remain in /home/pi/oled_service${NC}"
        else
            echo "Uninstallation cancelled"
        fi
        ;;
    *)
        echo -e "${BLUE}🔧 OLED Service Management${NC}"
        echo "=========================="
        echo "Usage: $0 {start|stop|restart|status|enable|disable|logs|test|config|install|uninstall}"
        echo
        echo "Commands:"
        echo "  start     - Start the OLED service"
        echo "  stop      - Stop the OLED service"
        echo "  restart   - Restart the OLED service"
        echo "  status    - Show service status and API health"
        echo "  enable    - Enable service to start on boot"
        echo "  disable   - Disable service auto-start"
        echo "  logs      - Show recent service logs"
        echo "  logs -f   - Follow service logs in real-time"
        echo "  test      - Run API tests"
        echo "  config    - Edit configuration file"
        echo "  install   - Run installation script"
        echo "  uninstall - Remove service (keeps files)"
        echo
        echo "Examples:"
        echo "  $0 start"
        echo "  $0 logs -f"
        echo "  $0 test"
        exit 1
        ;;
esac