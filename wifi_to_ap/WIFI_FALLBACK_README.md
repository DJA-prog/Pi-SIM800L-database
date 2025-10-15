# WiFi Auto-Fallback System for Raspberry Pi

## Overview
Automatically checks for WiFi connectivity in the first minute after boot. If no connection is found, switches to a lightweight Emergency Access Point mode until reboot.

## Features
- **⏱️ Smart Boot Detection**: Checks WiFi for 60 seconds after boot
- **🔄 Automatic Fallback**: Switches to AP mode if no connection
- **📡 Lightweight AP**: Minimal resource usage for Pi Zero
- **🌐 Simple Web Interface**: Status page accessible at AP IP
- **🔄 Auto-Recovery**: Returns to normal WiFi on reboot
- **📝 Detailed Logging**: All events logged to `/var/log/wifi-fallback.log`

## Quick Start

### 1. Test the System
```bash
sudo ./test_wifi_fallback.sh
```

### 2. Install as Boot Service
```bash
sudo ./install_wifi_fallback.sh
```

### 3. Manual Test (Optional)
```bash
sudo ./wifi_to_ad_hoc.sh
```

## Configuration

### Default Settings
- **Check Timeout**: 60 seconds
- **Emergency SSID**: `RPI-Emergency-[hostname]`
- **Password**: `raspberry123`
- **AP IP Address**: `192.168.4.1`
- **DHCP Range**: `192.168.4.100-200`

### Customize Settings
Edit the script variables at the top of `wifi_to_ad_hoc.sh`:
```bash
CHECK_TIMEOUT=60  # Seconds to wait for WiFi
AP_SSID="Your-Custom-SSID"
AP_PASSWORD="your_password"
AP_CHANNEL=6
AP_IP="192.168.4.1"
```

## How It Works

### Boot Sequence
1. **System boots** → Service starts automatically
2. **Wait 10 seconds** → Allow WiFi services to initialize
3. **Check for 60 seconds** → Look for WiFi connection + internet
4. **Decision point**:
   - ✅ **WiFi Connected** → Exit normally, continue boot
   - ❌ **No WiFi** → Activate Emergency AP mode

### Emergency AP Mode
When activated, provides:
- **WiFi Access Point**: Connect devices to the Pi
- **DHCP Server**: Automatically assigns IP addresses
- **Web Status Page**: View system info at `http://192.168.4.1`
- **SSH Access**: Connect via `ssh pi@192.168.4.1`
- **API Access**: SIM800L API at `http://192.168.4.1:5000`

## Service Management

### Check Status
```bash
sudo systemctl status wifi-fallback
```

### View Live Logs
```bash
sudo journalctl -u wifi-fallback -f
```

### Stop Service
```bash
sudo systemctl stop wifi-fallback
```

### Disable Auto-Start
```bash
sudo systemctl disable wifi-fallback
```

### Re-enable Auto-Start
```bash
sudo systemctl enable wifi-fallback
```

## Log Files

### Main Log
```bash
sudo tail -f /var/log/wifi-fallback.log
```

### System Service Log
```bash
sudo journalctl -u wifi-fallback -f
```

## Emergency Access

### When AP Mode is Active

#### Connect to WiFi
- **SSID**: `RPI-Emergency-[hostname]`
- **Password**: `raspberry123`

#### Access Points
- **Status Page**: `http://192.168.4.1`
- **SSH**: `ssh pi@192.168.4.1`
- **SIM800L API**: `http://192.168.4.1:5000`
- **File Transfer**: `scp files pi@192.168.4.1:/home/pi/`

#### Web Interface
The emergency web page shows:
- Current system status
- Device IP information
- Instructions for recovery
- Links to services

## Troubleshooting

### Script Not Running
```bash
# Check if service is enabled
sudo systemctl is-enabled wifi-fallback

# Check service status
sudo systemctl status wifi-fallback

# Manually start
sudo systemctl start wifi-fallback
```

### AP Mode Not Working
```bash
# Check required packages
sudo apt-get install hostapd dnsmasq wireless-tools

# Check WiFi interface
ip link show wlan0

# Check for conflicts
sudo systemctl stop hostapd
sudo systemctl stop dnsmasq
```

### No Internet in AP Mode
This is expected - AP mode provides local network access only. To restore internet:
1. Reboot the Pi
2. Fix your WiFi configuration
3. Or manually connect via ethernet

### Logs Show Errors
```bash
# Check detailed logs
sudo journalctl -u wifi-fallback --no-pager

# Check system logs
sudo dmesg | grep -i wifi

# Check WiFi hardware
lsusb | grep -i wireless
```

## Files Created

### Scripts
- `wifi_to_ad_hoc.sh` - Main fallback script
- `install_wifi_fallback.sh` - Installation script  
- `test_wifi_fallback.sh` - Test and validation script

### Service Files
- `wifi-fallback.service` - Systemd service definition
- `/etc/systemd/system/wifi-fallback.service` - Installed service

### Runtime Files (Created when AP active)
- `/tmp/hostapd_emergency.conf` - AP configuration
- `/tmp/dnsmasq_emergency.conf` - DHCP configuration
- `/tmp/emergency_web/` - Web status page
- `/var/log/wifi-fallback.log` - Activity log

## Recovery

### Return to Normal WiFi
Simply reboot the Pi:
```bash
sudo reboot
```

### Fix WiFi Configuration
1. Access via emergency AP
2. Edit `/etc/wpa_supplicant/wpa_supplicant.conf`
3. Add your WiFi credentials
4. Reboot

### Disable Emergency Mode
```bash
sudo systemctl stop wifi-fallback
sudo systemctl disable wifi-fallback
```

## Performance Impact
- **CPU Usage**: <1% during monitoring
- **Memory**: ~5MB for AP services
- **Boot Time**: +10 seconds initial delay
- **Network**: No impact on normal WiFi operation

## Compatibility
- Raspberry Pi Zero/3/4
- Raspbian/Raspberry Pi OS
- WiFi dongles with hostapd support
- Works with existing network configurations