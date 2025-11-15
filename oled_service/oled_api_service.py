#!/usr/bin/env python3
"""
OLED Display API Service for Pi Zero W
Provides REST API endpoints to control SSD1306 OLED display
Optimized for low resource usage and reliable operation
"""

import os
import sys
import time
import json
import signal
import logging
import threading
from datetime import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Add current directory to path for local imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from oled_display import OLEDDisplay

# Load environment variables
load_dotenv('.env.oled')

# Configuration from environment
API_HOST = os.getenv('OLED_API_HOST', '0.0.0.0')
API_PORT = int(os.getenv('OLED_API_PORT', 5001))
API_DEBUG = os.getenv('OLED_API_DEBUG', 'false').lower() == 'true'
I2C_ADDRESS = int(os.getenv('OLED_I2C_ADDRESS', '0x3c'), 16)
LOG_LEVEL = os.getenv('OLED_LOG_LEVEL', 'INFO')
AUTO_UPDATE_INTERVAL = int(os.getenv('OLED_AUTO_UPDATE_INTERVAL', 5))

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/oled-service.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('oled-service')

# Flask app
app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

# Global variables
oled_display = None
service_start_time = datetime.now()
display_mode = "custom"  # custom, datetime, startup, off
auto_update_thread = None
running = True

def init_oled():
    """Initialize OLED display"""
    global oled_display
    try:
        oled_display = OLEDDisplay(i2c_address=I2C_ADDRESS)
        if oled_display.is_available():
            logger.info(f"✅ OLED Display initialized successfully on address 0x{I2C_ADDRESS:02x}")
            oled_display.display_startup_message()
            return True
        else:
            logger.error("❌ OLED Display not available")
            return False
    except Exception as e:
        logger.error(f"❌ Failed to initialize OLED: {e}")
        oled_display = None
        return False

def auto_update_worker():
    """Background worker for automatic display updates"""
    global running
    while running:
        try:
            if oled_display and oled_display.is_available():
                if display_mode == "datetime":
                    oled_display.draw_datetime()
                elif display_mode == "custom":
                    oled_display.draw_display()
                time.sleep(AUTO_UPDATE_INTERVAL)
            else:
                time.sleep(10)  # Wait longer if display not available
        except Exception as e:
            logger.error(f"Auto update error: {e}")
            time.sleep(10)

def start_auto_update():
    """Start the auto-update thread"""
    global auto_update_thread
    if auto_update_thread is None or not auto_update_thread.is_alive():
        auto_update_thread = threading.Thread(target=auto_update_worker, daemon=True)
        auto_update_thread.start()
        logger.info("Auto-update thread started")

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global running
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    running = False
    if oled_display:
        oled_display.clear()
    sys.exit(0)

# API Routes
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    uptime = datetime.now() - service_start_time
    return jsonify({
        'status': 'healthy',
        'service': 'OLED Display Service',
        'version': '1.0.0',
        'uptime_seconds': int(uptime.total_seconds()),
        'uptime_human': str(uptime).split('.')[0],
        'display_available': oled_display.is_available() if oled_display else False,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get detailed service status"""
    return jsonify({
        'service': {
            'name': 'OLED Display Service',
            'version': '1.0.0',
            'start_time': service_start_time.isoformat(),
            'uptime_seconds': int((datetime.now() - service_start_time).total_seconds()),
            'pid': os.getpid()
        },
        'display': {
            'available': oled_display.is_available() if oled_display else False,
            'i2c_address': f"0x{I2C_ADDRESS:02x}",
            'mode': display_mode,
            'auto_update_interval': AUTO_UPDATE_INTERVAL
        },
        'configuration': {
            'api_host': API_HOST,
            'api_port': API_PORT,
            'debug_mode': API_DEBUG,
            'log_level': LOG_LEVEL
        },
        'data': {
            'wifi_ip': oled_display.wifi_ip if oled_display else "N/A",
            'battery_percent': oled_display.battery_percent if oled_display else 0,
            'message_count': oled_display.message_count if oled_display else 0
        }
    })

@app.route('/api/display/update', methods=['POST'])
def update_display_data():
    """Update display data"""
    if not oled_display or not oled_display.is_available():
        return jsonify({'error': 'OLED display not available'}), 503
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        # Update display data
        wifi_ip = data.get('wifi_ip', oled_display.wifi_ip)
        battery_percent = data.get('battery_percent', oled_display.battery_percent)
        message_count = data.get('message_count', oled_display.message_count)
        
        oled_display.update_custom1_data(wifi_ip, battery_percent, message_count)
        
        # If in custom mode, update display immediately
        if display_mode == "custom":
            oled_display.draw_display()
        
        logger.info(f"Display data updated: IP={wifi_ip}, Battery={battery_percent}%, Messages={message_count}")
        
        return jsonify({
            'success': True,
            'data': {
                'wifi_ip': wifi_ip,
                'battery_percent': battery_percent,
                'message_count': message_count
            },
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Failed to update display data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/display/mode', methods=['POST'])
def set_display_mode():
    """Set display mode"""
    global display_mode
    
    if not oled_display or not oled_display.is_available():
        return jsonify({'error': 'OLED display not available'}), 503
    
    try:
        data = request.get_json()
        if not data or 'mode' not in data:
            return jsonify({'error': 'Mode not specified'}), 400
        
        new_mode = data['mode'].lower()
        valid_modes = ['custom', 'datetime', 'startup', 'off']
        
        if new_mode not in valid_modes:
            return jsonify({'error': f'Invalid mode. Valid modes: {valid_modes}'}), 400
        
        display_mode = new_mode
        
        # Apply mode immediately
        if display_mode == "custom":
            oled_display.draw_display()
        elif display_mode == "datetime":
            oled_display.draw_datetime()
        elif display_mode == "startup":
            oled_display.display_startup_message()
        elif display_mode == "off":
            oled_display.clear()
        
        logger.info(f"Display mode changed to: {display_mode}")
        
        return jsonify({
            'success': True,
            'mode': display_mode,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Failed to set display mode: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/display/clear', methods=['POST'])
def clear_display():
    """Clear the display"""
    if not oled_display or not oled_display.is_available():
        return jsonify({'error': 'OLED display not available'}), 503
    
    try:
        oled_display.clear()
        logger.info("Display cleared")
        return jsonify({
            'success': True,
            'message': 'Display cleared',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Failed to clear display: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/display/text', methods=['POST'])
def display_custom_text():
    """Display custom text on OLED"""
    if not oled_display or not oled_display.is_available():
        return jsonify({'error': 'OLED display not available'}), 503
    
    try:
        data = request.get_json()
        if not data or 'lines' not in data:
            return jsonify({'error': 'Lines not specified'}), 400
        
        lines = data['lines']
        if not isinstance(lines, list) or len(lines) > 3:
            return jsonify({'error': 'Lines must be a list with max 3 items'}), 400
        
        # Draw custom text
        from luma.core.render import canvas
        with canvas(oled_display.device) as draw:
            for i, line in enumerate(lines):
                y_pos = i * 11
                draw.text((0, y_pos), str(line)[:16], fill="white")  # Limit to 16 chars per line
        
        logger.info(f"Custom text displayed: {lines}")
        
        return jsonify({
            'success': True,
            'lines': lines,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Failed to display custom text: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get service configuration"""
    return jsonify({
        'api': {
            'host': API_HOST,
            'port': API_PORT,
            'debug': API_DEBUG
        },
        'oled': {
            'i2c_address': f"0x{I2C_ADDRESS:02x}",
            'auto_update_interval': AUTO_UPDATE_INTERVAL,
            'available': oled_display.is_available() if oled_display else False
        },
        'logging': {
            'level': LOG_LEVEL,
            'file': '/var/log/oled-service.log'
        },
        'display_mode': display_mode
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

def main():
    """Main service entry point"""
    logger.info("🚀 Starting OLED Display API Service")
    logger.info(f"Configuration: Host={API_HOST}, Port={API_PORT}, I2C=0x{I2C_ADDRESS:02x}")
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Initialize OLED display
    if not init_oled():
        logger.warning("⚠️ OLED display not available, service will run in degraded mode")
    
    # Start auto-update worker
    start_auto_update()
    
    try:
        logger.info(f"🌐 Starting API server on {API_HOST}:{API_PORT}")
        app.run(
            host=API_HOST,
            port=API_PORT,
            debug=API_DEBUG,
            use_reloader=False,  # Disable reloader for service mode
            threaded=True
        )
    except Exception as e:
        logger.error(f"Failed to start API server: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()