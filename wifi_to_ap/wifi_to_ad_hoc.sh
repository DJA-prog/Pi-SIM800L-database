#!/bin/bash
# WiFi Auto-Fallback Script for Raspberry Pi
# Checks for WiFi connection in first minute after boot
# If no connection, switches to lightweight AP mode until reboot

set -e

# Configuration
CHECK_TIMEOUT=60  # Check for WiFi connection for 60 seconds
WIFI_INTERFACE="wlan0"
AP_SSID="RPI-Emergency-$(hostname | tail -c 5)"
AP_PASSWORD="raspberry123"
AP_CHANNEL=6
AP_IP="192.168.4.1"
AP_SUBNET="192.168.4.0/24"
LOG_FILE="/var/log/wifi-fallback.log"

# Logging function
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "This script must be run as root"
    exit 1
fi

log_message "WiFi fallback script started"

# Function to ensure AP services are stopped during normal operation
ensure_ap_services_stopped() {
    log_message "Ensuring hostapd and dnsmasq are stopped for normal WiFi operation..."
    
    # Stop and disable automatic startup of AP services
    systemctl stop hostapd 2>/dev/null || true
    systemctl stop dnsmasq 2>/dev/null || true
    systemctl disable hostapd 2>/dev/null || true
    systemctl disable dnsmasq 2>/dev/null || true
    
    # Kill any running emergency instances
    pkill -f "hostapd.*emergency" 2>/dev/null || true
    pkill -f "dnsmasq.*emergency" 2>/dev/null || true
    
    log_message "AP services stopped - ready for normal WiFi operation"
}

# Function to check internet connectivity
check_internet() {
    # Check if we can reach common DNS servers
    if ping -c 1 -W 5 8.8.8.8 >/dev/null 2>&1 || \
       ping -c 1 -W 5 1.1.1.1 >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Function to check WiFi connection status
check_wifi_connected() {
    # Check if wlan0 has an IP address and is connected
    if ip addr show "$WIFI_INTERFACE" | grep -q "inet " && \
       iwconfig "$WIFI_INTERFACE" 2>/dev/null | grep -q "Access Point"; then
        return 0
    else
        return 1
    fi
}

# Function to setup lightweight AP mode
setup_ap_mode() {
    log_message "Setting up lightweight AP mode..."
    
    # Ensure AP services are stopped first (clean slate)
    systemctl stop hostapd 2>/dev/null || true
    systemctl stop dnsmasq 2>/dev/null || true
    
    # Stop any existing services that might interfere
    systemctl stop wpa_supplicant 2>/dev/null || true
    systemctl stop dhcpcd 2>/dev/null || true
    
    # Configure static IP for AP
    ip link set "$WIFI_INTERFACE" down
    ip addr flush dev "$WIFI_INTERFACE"
    ip link set "$WIFI_INTERFACE" up
    ip addr add "$AP_IP/24" dev "$WIFI_INTERFACE"
    
    # Create minimal hostapd configuration
    cat > /tmp/hostapd_emergency.conf << EOF
interface=$WIFI_INTERFACE
driver=nl80211
ssid=$AP_SSID
hw_mode=g
channel=$AP_CHANNEL
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=$AP_PASSWORD
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF

    # Start hostapd in background
    hostapd /tmp/hostapd_emergency.conf -B -P /tmp/hostapd_emergency.pid
    
    if [ $? -eq 0 ]; then
        log_message "AP mode activated: SSID=$AP_SSID, Password=$AP_PASSWORD, IP=$AP_IP"
        
        # Setup basic DHCP with dnsmasq (lightweight)
        cat > /tmp/dnsmasq_emergency.conf << EOF
interface=$WIFI_INTERFACE
bind-interfaces
server=8.8.8.8
domain-needed
bogus-priv
dhcp-range=192.168.4.100,192.168.4.200,255.255.255.0,12h
EOF
        
        # Start dnsmasq for DHCP
        dnsmasq -C /tmp/dnsmasq_emergency.conf -x /tmp/dnsmasq_emergency.pid
        
        # Create simple status page
        mkdir -p /tmp/emergency_web
        cat > /tmp/emergency_web/index.html << 'EOF'
<!DOCTYPE html>
<html>
<head><title>Emergency WiFi Access</title></head>
<body>
<h1>Raspberry Pi Emergency Access</h1>
<p>WiFi connection failed - Emergency AP mode active</p>
<p>Device will attempt to reconnect to configured WiFi on next reboot</p>
<p><strong>Current Status:</strong> Emergency Access Point</p>
<p><strong>Device IP:</strong> 192.168.4.1</p>
<p><strong>SSH Access:</strong> ssh pi@192.168.4.1</p>
<p><strong>SIM800L API:</strong> <a href="http://192.168.4.1:5000">http://192.168.4.1:5000</a></p>
</body>
</html>
EOF
        
        # Start simple Python web server for status
        cd /tmp/emergency_web
        python3 -m http.server 80 >/dev/null 2>&1 &
        echo $! > /tmp/emergency_web.pid
        
        log_message "Emergency AP setup complete. Access via: http://$AP_IP"
        return 0
    else
        log_message "Failed to start AP mode"
        return 1
    fi
}

# Function to cleanup AP mode (for clean shutdown)
cleanup_ap_mode() {
    log_message "Cleaning up AP mode..."
    
    # Kill emergency processes (not system services)
    [ -f /tmp/hostapd_emergency.pid ] && kill $(cat /tmp/hostapd_emergency.pid) 2>/dev/null || true
    [ -f /tmp/dnsmasq_emergency.pid ] && kill $(cat /tmp/dnsmasq_emergency.pid) 2>/dev/null || true
    [ -f /tmp/emergency_web.pid ] && kill $(cat /tmp/emergency_web.pid) 2>/dev/null || true
    
    # Ensure system services remain stopped
    systemctl stop hostapd 2>/dev/null || true
    systemctl stop dnsmasq 2>/dev/null || true
    
    # Remove temp files
    rm -f /tmp/hostapd_emergency.conf /tmp/dnsmasq_emergency.conf
    rm -f /tmp/hostapd_emergency.pid /tmp/dnsmasq_emergency.pid /tmp/emergency_web.pid
    rm -rf /tmp/emergency_web
    
    # Restore interface
    ip addr flush dev "$WIFI_INTERFACE"
    ip link set "$WIFI_INTERFACE" down
    
    log_message "AP mode cleanup complete"
}

# Setup cleanup trap
trap cleanup_ap_mode EXIT

# Main logic
log_message "Checking WiFi connectivity for $CHECK_TIMEOUT seconds..."

# First, ensure AP services are stopped for normal operation
ensure_ap_services_stopped

# Wait a moment for WiFi to potentially connect
sleep 10

start_time=$(date +%s)
wifi_connected=false

# Check for WiFi connection within timeout period
while [ $(($(date +%s) - start_time)) -lt $CHECK_TIMEOUT ]; do
    if check_wifi_connected; then
        log_message "WiFi interface connected, checking internet..."
        
        if check_internet; then
            log_message "Internet connectivity confirmed - normal operation"
            wifi_connected=true
            break
        else
            log_message "WiFi connected but no internet, continuing to check..."
        fi
    else
        log_message "No WiFi connection detected, waiting..."
    fi
    
    sleep 5
done

# If no WiFi connection established, switch to AP mode
if [ "$wifi_connected" = false ]; then
    log_message "No WiFi connection established within $CHECK_TIMEOUT seconds"
    log_message "Switching to emergency AP mode..."
    
    if setup_ap_mode; then
        log_message "Emergency AP mode active - will restore on reboot"
        
        # Keep the AP running until system shutdown/reboot
        # Create a simple monitoring loop
        while true; do
            sleep 30
            # Check if AP is still running
            if ! pgrep -f "hostapd.*emergency" >/dev/null; then
                log_message "AP process died, attempting restart..."
                setup_ap_mode
            fi
        done
    else
        log_message "Failed to setup AP mode - system will continue with no network"
        exit 1
    fi
else
    log_message "WiFi connection successful - ensuring AP services remain disabled"
    # Double-check that AP services are stopped and disabled
    systemctl stop hostapd 2>/dev/null || true
    systemctl stop dnsmasq 2>/dev/null || true
    systemctl disable hostapd 2>/dev/null || true
    systemctl disable dnsmasq 2>/dev/null || true
    log_message "Normal WiFi operation confirmed - exiting"
    exit 0
fi
