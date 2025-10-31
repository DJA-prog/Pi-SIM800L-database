#!/usr/bin/env python3
import sys
import json
import csv
import requests
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv, set_key
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                             QTextEdit, QComboBox, QDateTimeEdit, QGroupBox,
                             QTableWidget, QTableWidgetItem, QSplitter,
                             QMessageBox, QFileDialog, QProgressBar,
                             QScrollArea, QFrame, QShortcut)
from PyQt5.QtCore import Qt, QDateTime, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QIcon, QKeySequence

class APIWorker(QThread):
    """Worker thread for API calls to prevent GUI freezing"""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    
    def __init__(self, url, method='GET', data=None, timeout=10):
        super().__init__()
        self.url = url
        self.method = method
        self.data = data
        self.timeout = timeout
    
    def run(self):
        try:
            if self.method == 'GET':
                response = requests.get(self.url, timeout=self.timeout)
            elif self.method == 'POST':
                response = requests.post(self.url, json=self.data, timeout=self.timeout)
            
            if response.status_code == 200:
                self.finished.emit(response.json())
            else:
                self.error.emit(f"HTTP {response.status_code}: {response.text}")
        except requests.exceptions.RequestException as e:
            self.error.emit(f"Connection error: {str(e)}")
        except Exception as e:
            self.error.emit(f"Unexpected error: {str(e)}")

class SMSGUIApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_data = []
        self.env_file = ".env"
        self.active_threads = []  # Track active threads
        self.load_settings()
        self.init_ui()
    
    def closeEvent(self, event):
        """Handle application close event"""
        # Wait for all active threads to finish
        self.cleanup_threads()
        event.accept()
    
    def cleanup_threads(self):
        """Clean up active threads before closing"""
        for thread in self.active_threads[:]:  # Create a copy to iterate
            if thread.isRunning():
                thread.quit()
                thread.wait(3000)  # Wait up to 3 seconds
            self.active_threads.remove(thread)
    
    def create_api_worker(self, url, method='GET', data=None, timeout=10):
        """Create and manage API worker thread"""
        worker = APIWorker(url, method, data, timeout)
        self.active_threads.append(worker)
        
        # Clean up thread when it finishes
        worker.finished.connect(lambda: self.remove_thread(worker))
        worker.error.connect(lambda: self.remove_thread(worker))
        
        return worker
    
    def remove_thread(self, thread):
        """Remove thread from active threads list"""
        if thread in self.active_threads:
            self.active_threads.remove(thread)
    
    def load_settings(self):
        """Load settings from .env file"""
        if os.path.exists(self.env_file):
            load_dotenv(self.env_file)
        
        # Set default values
        self.default_host = os.getenv('SMS_GUI_HOST', 'localhost')
        self.default_port = os.getenv('SMS_GUI_PORT', '5000')
    
    def save_settings(self):
        """Save current settings to .env file"""
        try:
            host = self.host_input.text().strip() or "localhost"
            port = self.port_input.text().strip() or "5000"
            
            # Create .env file if it doesn't exist
            if not os.path.exists(self.env_file):
                with open(self.env_file, 'w') as f:
                    f.write("# SMS GUI Configuration\n")
            
            # Update or add the settings
            set_key(self.env_file, 'SMS_GUI_HOST', host)
            set_key(self.env_file, 'SMS_GUI_PORT', port)
            
            self.statusBar().showMessage(f"Settings saved to {self.env_file}", 3000)
            return True
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Could not save settings: {str(e)}")
            return False
        
    def init_ui(self):
        self.setWindowTitle("SMS Database Viewer with Battery Monitor")
        self.setGeometry(100, 100, 1200, 800)
        self.setMinimumSize(800, 700)  # Set minimum window size
        
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Create splitter for left panel and right panel
        splitter = QSplitter(Qt.Horizontal)
        central_widget.setLayout(QHBoxLayout())
        central_widget.layout().addWidget(splitter)
        
        # Left panel for options
        left_panel = self.create_left_panel()
        splitter.addWidget(left_panel)
        
        # Right panel for results
        right_panel = self.create_right_panel()
        splitter.addWidget(right_panel)
        
        # Set splitter proportions (30% left, 70% right)
        splitter.setSizes([360, 840])
        splitter.setChildrenCollapsible(False)  # Prevent panels from collapsing completely
        
        # Status bar
        self.statusBar().showMessage("Ready")
        
        # Add keyboard shortcuts
        self.setup_shortcuts()
        
        # Initialize API connection
        self.update_connection(check_health=False)
        
        # Try to load initial data (don't fail if API is offline)
        # This will be handled gracefully by the API error handling
    
    def setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        # Ctrl+R to refresh/reconnect
        refresh_shortcut = QShortcut(QKeySequence("Ctrl+R"), self)
        refresh_shortcut.activated.connect(self.update_connection)
        
        # F5 to get all SMS
        refresh_data_shortcut = QShortcut(QKeySequence("F5"), self)
        refresh_data_shortcut.activated.connect(self.get_all_sms)
        
        # Ctrl+E to export
        export_shortcut = QShortcut(QKeySequence("Ctrl+E"), self)
        export_shortcut.activated.connect(self.export_to_csv)
        
        # Ctrl+S to save settings
        save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        save_shortcut.activated.connect(self.save_settings)
        
        # Ctrl+B to get battery status
        battery_shortcut = QShortcut(QKeySequence("Ctrl+B"), self)
        battery_shortcut.activated.connect(self.get_battery_status)
    
    def create_left_panel(self):
        """Create the left panel with query options"""
        # Create scroll area for the left panel
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setMaximumWidth(420)  # Slightly larger to accommodate scrollbar
        
        # Create the actual content widget
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)  # Add some spacing between groups
        
        # Title
        title = QLabel("Query Options")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Connection Settings
        self.create_connection_settings_group(layout)
        
        # API Status
        self.create_api_status_group(layout)
        
        # Basic Queries
        self.create_basic_queries_group(layout)
        
        # Filter Queries
        self.create_filter_queries_group(layout)
        
        # Custom Query
        self.create_custom_query_group(layout)
        
        # Statistics
        self.create_statistics_group(layout)
        
        # Battery Monitoring
        self.create_battery_group(layout)
        
        # SIM Information
        self.create_sim_info_group(layout)
        
        # Data Management
        self.create_data_management_group(layout)
        
        # SMS Reports
        self.create_sms_reports_group(layout)
        
        # System Control
        self.create_system_group(layout)
        
        layout.addStretch()
        
        # Set the panel as the scroll area's widget
        scroll_area.setWidget(panel)
        
        return scroll_area
    
    def create_connection_settings_group(self, layout):
        """Create connection settings group"""
        group = QGroupBox("Connection Settings")
        group.setStyleSheet("QGroupBox { font-weight: bold; }")
        group_layout = QVBoxLayout(group)
        group_layout.setSpacing(5)  # Compact spacing
        
        # Host input
        host_layout = QHBoxLayout()
        host_layout.addWidget(QLabel("Host:"))
        self.host_input = QLineEdit(self.default_host)
        self.host_input.setPlaceholderText("localhost or IP address")
        host_layout.addWidget(self.host_input)
        group_layout.addLayout(host_layout)
        
        # Port input
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("Port:"))
        self.port_input = QLineEdit(self.default_port)
        self.port_input.setPlaceholderText("5000")
        port_layout.addWidget(self.port_input)
        group_layout.addLayout(port_layout)
        
        # URL display
        self.url_display = QLabel()
        self.url_display.setStyleSheet("color: gray; font-size: 10px;")
        self.url_display.setWordWrap(True)
        group_layout.addWidget(self.url_display)
        
        # Connect button
        connect_btn = QPushButton("Update Connection")
        connect_btn.clicked.connect(self.update_connection)
        group_layout.addWidget(connect_btn)
        
        # Save settings button
        save_btn = QPushButton("Save Settings")
        save_btn.setToolTip("Save host and port to .env file")
        save_btn.clicked.connect(self.save_settings)
        group_layout.addWidget(save_btn)
        
        # Preset buttons
        presets_layout = QHBoxLayout()
        localhost_btn = QPushButton("Localhost")
        localhost_btn.setToolTip("localhost:5000")
        localhost_btn.clicked.connect(lambda: self.set_preset("localhost", "5000"))
        presets_layout.addWidget(localhost_btn)
        
        custom_btn = QPushButton("192.168.1.x")
        custom_btn.setToolTip("Set common local network address")
        custom_btn.clicked.connect(lambda: self.set_preset("192.168.1.", "5000"))
        presets_layout.addWidget(custom_btn)
        
        group_layout.addLayout(presets_layout)
        
        layout.addWidget(group)
        
        # Initialize connection (but don't check health yet)
        self.update_connection(check_health=False)
    
    def set_preset(self, host, port):
        """Set preset host and port values"""
        if host.endswith("."):
            # For partial IPs, focus the input for user to complete
            self.host_input.setText(host)
            self.host_input.setFocus()
            self.host_input.setCursorPosition(len(host))
        else:
            self.host_input.setText(host)
            self.port_input.setText(port)
            self.update_connection(auto_save=True)  # Auto-save preset changes
    
    def update_connection(self, check_health=True, auto_save=False):
        """Update API base URL from host and port inputs"""
        host = self.host_input.text().strip() or "localhost"
        port = self.port_input.text().strip() or "5000"
        
        # Validate port
        try:
            port_num = int(port)
            if not (1 <= port_num <= 65535):
                raise ValueError("Port out of range")
        except ValueError:
            QMessageBox.warning(self, "Warning", "Please enter a valid port number (1-65535)")
            self.port_input.setText("5000")
            port = "5000"
        
        # Update API base URL
        self.api_base_url = f"http://{host}:{port}/api"
        self.url_display.setText(f"API URL: {self.api_base_url}")
        
        # Auto-save if requested
        if auto_save:
            self.save_settings()
        
        # Check connection immediately (if status label exists)
        if check_health and hasattr(self, 'status_label'):
            self.check_api_health()
        
        self.statusBar().showMessage(f"Connection updated to {host}:{port}")
    
    @property
    def current_host_port(self):
        """Get current host and port as tuple"""
        host = self.host_input.text().strip() or "localhost"
        port = self.port_input.text().strip() or "5000"
        return host, port
    
    def create_api_status_group(self, layout):
        """Create API status group"""
        group = QGroupBox("API Status")
        group_layout = QVBoxLayout(group)
        
        self.status_label = QLabel("Checking...")
        self.status_label.setStyleSheet("color: orange;")
        group_layout.addWidget(self.status_label)
        
        refresh_btn = QPushButton("Refresh Status")
        refresh_btn.clicked.connect(self.check_api_health)
        group_layout.addWidget(refresh_btn)
        
        layout.addWidget(group)
        
        # Check API health after status label is created
        self.check_api_health()
    
    def create_basic_queries_group(self, layout):
        """Create basic queries group"""
        group = QGroupBox("Basic Queries")
        group_layout = QVBoxLayout(group)
        
        all_sms_btn = QPushButton("Get All SMS")
        all_sms_btn.clicked.connect(self.get_all_sms)
        group_layout.addWidget(all_sms_btn)
        
        stats_btn = QPushButton("Get Statistics")
        stats_btn.clicked.connect(self.get_statistics)
        group_layout.addWidget(stats_btn)
        
        # New buttons for system queries
        unique_senders_btn = QPushButton("Get Unique Senders")
        unique_senders_btn.setToolTip("Get all unique SMS senders with message counts")
        unique_senders_btn.clicked.connect(self.get_unique_senders)
        group_layout.addWidget(unique_senders_btn)
        
        date_range_btn = QPushButton("Get Date Range Info")
        date_range_btn.setToolTip("Get time difference between first and last SMS")
        date_range_btn.clicked.connect(self.get_sms_date_range_info)
        group_layout.addWidget(date_range_btn)
        
        system_logs_btn = QPushButton("Get System Logs")
        system_logs_btn.setToolTip("Get filtered system log messages")
        system_logs_btn.clicked.connect(self.get_system_logs)
        group_layout.addWidget(system_logs_btn)
        
        layout.addWidget(group)
    
    def create_filter_queries_group(self, layout):
        """Create filter queries group"""
        group = QGroupBox("Filter Queries")
        group_layout = QVBoxLayout(group)
        
        # Sender filter
        sender_layout = QHBoxLayout()
        sender_layout.addWidget(QLabel("Sender:"))
        self.sender_input = QLineEdit()
        self.sender_input.setPlaceholderText("+1234567890")
        sender_layout.addWidget(self.sender_input)
        sender_btn = QPushButton("Search")
        sender_btn.clicked.connect(self.get_sms_by_sender)
        sender_layout.addWidget(sender_btn)
        group_layout.addLayout(sender_layout)
        
        # Keyword filter
        keyword_layout = QHBoxLayout()
        keyword_layout.addWidget(QLabel("Keyword:"))
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("hello")
        keyword_layout.addWidget(self.keyword_input)
        keyword_btn = QPushButton("Search")
        keyword_btn.clicked.connect(self.search_sms_by_keyword)
        keyword_layout.addWidget(keyword_btn)
        group_layout.addLayout(keyword_layout)
        
        # Date range filter
        group_layout.addWidget(QLabel("Date Range:"))
        self.start_date = QDateTimeEdit(QDateTime.currentDateTime().addDays(-7))
        self.start_date.setDisplayFormat("yyyy-MM-dd hh:mm:ss")
        group_layout.addWidget(self.start_date)
        
        self.end_date = QDateTimeEdit(QDateTime.currentDateTime())
        self.end_date.setDisplayFormat("yyyy-MM-dd hh:mm:ss")
        group_layout.addWidget(self.end_date)
        
        date_btn = QPushButton("Get SMS by Date Range")
        date_btn.clicked.connect(self.get_sms_by_date_range)
        group_layout.addWidget(date_btn)
        
        layout.addWidget(group)
    
    def create_custom_query_group(self, layout):
        """Create custom query group"""
        group = QGroupBox("Custom Query")
        group_layout = QVBoxLayout(group)
        
        group_layout.addWidget(QLabel("SQL Query:"))
        self.custom_query_input = QTextEdit()
        self.custom_query_input.setMaximumHeight(100)  # Slightly taller for better usability
        self.custom_query_input.setMinimumHeight(60)   # Minimum height
        self.custom_query_input.setPlainText("SELECT * FROM sms LIMIT 10")
        group_layout.addWidget(self.custom_query_input)
        
        group_layout.addWidget(QLabel("Parameters (JSON array):"))
        self.custom_params_input = QLineEdit()
        self.custom_params_input.setPlaceholderText('["param1", "param2"]')
        group_layout.addWidget(self.custom_params_input)
        
        custom_btn = QPushButton("Execute Query")
        custom_btn.clicked.connect(self.execute_custom_query)
        group_layout.addWidget(custom_btn)
        
        layout.addWidget(group)
    
    def create_statistics_group(self, layout):
        """Create statistics group"""
        group = QGroupBox("Quick Stats")
        group_layout = QVBoxLayout(group)
        
        self.stats_label = QLabel("No statistics loaded")
        self.stats_label.setWordWrap(True)
        group_layout.addWidget(self.stats_label)
        
        layout.addWidget(group)
    
    def create_battery_group(self, layout):
        """Create battery monitoring group"""
        group = QGroupBox("Battery Monitoring")
        group.setStyleSheet("QGroupBox { font-weight: bold; color: #2E7D32; }")
        group_layout = QVBoxLayout(group)
        
        # Battery status display
        self.battery_status_label = QLabel("Battery status unknown")
        self.battery_status_label.setWordWrap(True)
        self.battery_status_label.setStyleSheet("font-size: 11px; padding: 5px; background-color: #f5f5f5; border: 1px solid #ddd; border-radius: 3px;")
        group_layout.addWidget(self.battery_status_label)
        
        # Battery action buttons
        battery_buttons_layout = QHBoxLayout()
        
        get_battery_btn = QPushButton("Get Battery")
        get_battery_btn.setToolTip("Get current battery voltage and status")
        get_battery_btn.clicked.connect(self.get_battery_status)
        get_battery_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; }")
        battery_buttons_layout.addWidget(get_battery_btn)
        
        group_layout.addLayout(battery_buttons_layout)
        
        # Auto-refresh option
        auto_refresh_layout = QHBoxLayout()
        self.battery_auto_refresh = QLineEdit("30")
        self.battery_auto_refresh.setPlaceholderText("seconds")
        self.battery_auto_refresh.setMaximumWidth(60)
        auto_refresh_layout.addWidget(QLabel("Auto refresh:"))
        auto_refresh_layout.addWidget(self.battery_auto_refresh)
        auto_refresh_layout.addWidget(QLabel("sec"))
        
        self.battery_timer_btn = QPushButton("Start")
        self.battery_timer_btn.clicked.connect(self.toggle_battery_timer)
        self.battery_timer_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; }")
        auto_refresh_layout.addWidget(self.battery_timer_btn)
        
        group_layout.addLayout(auto_refresh_layout)
        
        layout.addWidget(group)
        
        # Initialize battery timer
        self.battery_timer = QTimer()
        self.battery_timer.timeout.connect(self.get_battery_status)
        self.battery_timer_running = False
    
    def create_sim_info_group(self, layout):
        """Create SIM information group"""
        group = QGroupBox("SIM Information")
        group.setStyleSheet("QGroupBox { font-weight: bold; color: #1976D2; }")
        group_layout = QVBoxLayout(group)
        
        # SIM status display
        self.sim_status_label = QLabel("SIM status unknown")
        self.sim_status_label.setWordWrap(True)
        self.sim_status_label.setStyleSheet("font-size: 10px; padding: 5px; background-color: #f0f8ff; border: 1px solid #1976D2; border-radius: 3px;")
        group_layout.addWidget(self.sim_status_label)
        
        # SIM action buttons
        sim_buttons_layout = QHBoxLayout()
        
        get_sim_status_btn = QPushButton("Get SIM Status")
        get_sim_status_btn.setToolTip("Get comprehensive SIM status (signal, operator, battery)")
        get_sim_status_btn.clicked.connect(self.get_sim_status)
        get_sim_status_btn.setStyleSheet("QPushButton { background-color: #1976D2; color: white; }")
        sim_buttons_layout.addWidget(get_sim_status_btn)
        
        get_signal_btn = QPushButton("Signal")
        get_signal_btn.setToolTip("Get signal strength only")
        get_signal_btn.clicked.connect(self.get_signal_strength)
        get_signal_btn.setStyleSheet("QPushButton { background-color: #388E3C; color: white; }")
        sim_buttons_layout.addWidget(get_signal_btn)
        
        group_layout.addLayout(sim_buttons_layout)
        
        # Second row of buttons
        sim_buttons_layout2 = QHBoxLayout()
        
        get_operator_btn = QPushButton("Operator")
        get_operator_btn.setToolTip("Get network operator information")
        get_operator_btn.clicked.connect(self.get_network_operator)
        get_operator_btn.setStyleSheet("QPushButton { background-color: #F57C00; color: white; }")
        sim_buttons_layout2.addWidget(get_operator_btn)
        
        get_battery_history_btn = QPushButton("Battery History")
        get_battery_history_btn.setToolTip("Get battery voltage history and trends")
        get_battery_history_btn.clicked.connect(self.get_battery_history)
        get_battery_history_btn.setStyleSheet("QPushButton { background-color: #7B1FA2; color: white; }")
        sim_buttons_layout2.addWidget(get_battery_history_btn)
        
        group_layout.addLayout(sim_buttons_layout2)
        
        layout.addWidget(group)
    
    def create_data_management_group(self, layout):
        """Create data management group for delete and backup operations"""
        group = QGroupBox("Data Management")
        group.setStyleSheet("QGroupBox { font-weight: bold; color: #E65100; }")
        group_layout = QVBoxLayout(group)
        
        # Warning label
        warning_label = QLabel("⚠️ Destructive operations!")
        warning_label.setStyleSheet("color: red; font-weight: bold; font-size: 10px;")
        warning_label.setAlignment(Qt.AlignCenter)
        group_layout.addWidget(warning_label)
        
        # Backup button (safe operation)
        backup_btn = QPushButton("📥 Create Backup")
        backup_btn.setToolTip("Download a backup copy of the database")
        backup_btn.clicked.connect(self.create_backup)
        backup_btn.setStyleSheet("QPushButton { background-color: #2E7D32; color: white; font-weight: bold; }")
        group_layout.addWidget(backup_btn)
        
        # Data stats button
        stats_btn = QPushButton("📊 Data Statistics")
        stats_btn.setToolTip("View detailed data statistics")
        stats_btn.clicked.connect(self.get_data_stats)
        stats_btn.setStyleSheet("QPushButton { background-color: #1976D2; color: white; }")
        group_layout.addWidget(stats_btn)
        
        # Delete operations
        delete_layout1 = QHBoxLayout()
        
        delete_sms_btn = QPushButton("Delete SMS")
        delete_sms_btn.setToolTip("Delete only SMS messages (keep system logs)")
        delete_sms_btn.clicked.connect(self.confirm_delete_sms)
        delete_sms_btn.setStyleSheet("QPushButton { background-color: #F57C00; color: white; }")
        delete_layout1.addWidget(delete_sms_btn)
        
        clear_logs_btn = QPushButton("Clear Logs")
        clear_logs_btn.setToolTip("Clear only system log messages")
        clear_logs_btn.clicked.connect(self.confirm_clear_logs)
        clear_logs_btn.setStyleSheet("QPushButton { background-color: #FF5722; color: white; }")
        delete_layout1.addWidget(clear_logs_btn)
        
        group_layout.addLayout(delete_layout1)
        
        # Selective delete operations
        delete_layout2 = QHBoxLayout()
        
        delete_sender_btn = QPushButton("Delete by Sender")
        delete_sender_btn.setToolTip("Delete messages from specific sender")
        delete_sender_btn.clicked.connect(self.prompt_delete_by_sender)
        delete_sender_btn.setStyleSheet("QPushButton { background-color: #7B1FA2; color: white; }")
        delete_layout2.addWidget(delete_sender_btn)
        
        delete_keyword_btn = QPushButton("Delete by Keyword")
        delete_keyword_btn.setToolTip("Delete messages containing keyword")
        delete_keyword_btn.clicked.connect(self.prompt_delete_by_keyword)
        delete_keyword_btn.setStyleSheet("QPushButton { background-color: #C2185B; color: white; }")
        delete_layout2.addWidget(delete_keyword_btn)
        
        group_layout.addLayout(delete_layout2)
        
        # Nuclear option
        delete_all_btn = QPushButton("🗑️ DELETE ALL DATA")
        delete_all_btn.setToolTip("Delete ALL data (SMS + system logs)")
        delete_all_btn.clicked.connect(self.confirm_delete_all)
        delete_all_btn.setStyleSheet("QPushButton { background-color: #D32F2F; color: white; font-weight: bold; }")
        group_layout.addWidget(delete_all_btn)
        
        layout.addWidget(group)
    
    def create_sms_reports_group(self, layout):
        """Create SMS reports group"""
        group = QGroupBox("SMS Reports")
        group.setStyleSheet("QGroupBox { font-weight: bold; color: #4CAF50; }")
        group_layout = QVBoxLayout(group)
        
        # Status display
        self.sms_reports_status = QLabel("Status: Loading...")
        self.sms_reports_status.setStyleSheet("font-size: 10px; color: gray;")
        self.sms_reports_status.setWordWrap(True)
        group_layout.addWidget(self.sms_reports_status)
        
        # Configuration section
        config_frame = QFrame()
        config_layout = QVBoxLayout(config_frame)
        config_layout.setSpacing(3)
        
        # Enable/Disable checkbox
        self.reports_enabled_cb = QPushButton("Enable Reports")
        self.reports_enabled_cb.setCheckable(True)
        self.reports_enabled_cb.setStyleSheet("""
            QPushButton {
                background-color: #E0E0E0;
                border: 1px solid #BDBDBD;
                padding: 5px;
                text-align: center;
            }
            QPushButton:checked {
                background-color: #4CAF50;
                color: white;
            }
        """)
        self.reports_enabled_cb.clicked.connect(self.toggle_reports_enabled)
        config_layout.addWidget(self.reports_enabled_cb)
        
        # Recipient input
        recipient_layout = QHBoxLayout()
        recipient_layout.addWidget(QLabel("Recipient:"))
        self.recipient_input = QLineEdit()
        self.recipient_input.setPlaceholderText("+1234567890")
        self.recipient_input.setToolTip("Phone number with country code")
        recipient_layout.addWidget(self.recipient_input)
        config_layout.addLayout(recipient_layout)
        
        # Interval input
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("Interval (hours):"))
        self.interval_input = QLineEdit()
        self.interval_input.setPlaceholderText("168")
        self.interval_input.setToolTip("Report interval in hours (168 = 1 week)")
        interval_layout.addWidget(self.interval_input)
        config_layout.addLayout(interval_layout)
        
        # Update configuration button
        update_config_btn = QPushButton("Update Configuration")
        update_config_btn.setToolTip("Save SMS reports configuration")
        update_config_btn.clicked.connect(self.update_sms_reports_config)
        update_config_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; }")
        config_layout.addWidget(update_config_btn)
        
        group_layout.addWidget(config_frame)
        
        # Actions section
        actions_frame = QFrame()
        actions_layout = QVBoxLayout(actions_frame)
        actions_layout.setSpacing(3)
        
        # Action buttons row 1
        actions_row1 = QHBoxLayout()
        preview_btn = QPushButton("Preview Report")
        preview_btn.setToolTip("Preview the status report content")
        preview_btn.clicked.connect(self.preview_status_report)
        preview_btn.setStyleSheet("QPushButton { background-color: #607D8B; color: white; }")
        actions_row1.addWidget(preview_btn)
        
        send_now_btn = QPushButton("Send Now")
        send_now_btn.setToolTip("Send status report immediately")
        send_now_btn.clicked.connect(self.send_report_now)
        send_now_btn.setStyleSheet("QPushButton { background-color: #FF9800; color: white; }")
        actions_row1.addWidget(send_now_btn)
        actions_layout.addLayout(actions_row1)
        
        # Action buttons row 2
        actions_row2 = QHBoxLayout()
        test_sms_btn = QPushButton("Test SMS")
        test_sms_btn.setToolTip("Send a test SMS message")
        test_sms_btn.clicked.connect(self.test_sms_send)
        test_sms_btn.setStyleSheet("QPushButton { background-color: #9C27B0; color: white; }")
        actions_row2.addWidget(test_sms_btn)
        
        get_config_btn = QPushButton("Refresh Config")
        get_config_btn.setToolTip("Reload SMS reports configuration")
        get_config_btn.clicked.connect(self.get_sms_reports_config)
        get_config_btn.setStyleSheet("QPushButton { background-color: #009688; color: white; }")
        actions_row2.addWidget(get_config_btn)
        actions_layout.addLayout(actions_row2)
        
        group_layout.addWidget(actions_frame)
        
        # Load initial configuration
        self.get_sms_reports_config()
        
        layout.addWidget(group)
    
    def create_system_group(self, layout):
        """Create system control group"""
        group = QGroupBox("System Control")
        group.setStyleSheet("QGroupBox { font-weight: bold; color: #D32F2F; }")
        group_layout = QVBoxLayout(group)
        
        # Warning label
        warning_label = QLabel("⚠️ Use with caution!")
        warning_label.setStyleSheet("color: red; font-weight: bold; font-size: 11px;")
        warning_label.setAlignment(Qt.AlignCenter)
        group_layout.addWidget(warning_label)
        
        # SIM800 Controls
        sim_layout = QHBoxLayout()
        restart_sim_btn = QPushButton("Restart SIM800")
        restart_sim_btn.setToolTip("Restart the SIM800 module (requires confirmation)")
        restart_sim_btn.clicked.connect(self.confirm_sim_restart)
        restart_sim_btn.setStyleSheet("QPushButton { background-color: #FF9800; color: white; }")
        sim_layout.addWidget(restart_sim_btn)
        
        set_pin_btn = QPushButton("Set SIM PIN")
        set_pin_btn.setToolTip("Change the SIM card PIN")
        set_pin_btn.clicked.connect(self.prompt_sim_pin)
        set_pin_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; }")
        sim_layout.addWidget(set_pin_btn)
        group_layout.addLayout(sim_layout)
        
        # System Controls
        system_layout = QHBoxLayout()
        reboot_btn = QPushButton("Reboot System")
        reboot_btn.setToolTip("Reboot the entire system (requires confirmation)")
        reboot_btn.clicked.connect(self.confirm_system_reboot)
        reboot_btn.setStyleSheet("QPushButton { background-color: #FF5722; color: white; font-weight: bold; }")
        system_layout.addWidget(reboot_btn)
        
        shutdown_btn = QPushButton("Shutdown System")
        shutdown_btn.setToolTip("Shutdown the system (requires confirmation)")
        shutdown_btn.clicked.connect(self.confirm_system_shutdown)
        shutdown_btn.setStyleSheet("QPushButton { background-color: #D32F2F; color: white; font-weight: bold; }")
        system_layout.addWidget(shutdown_btn)
        group_layout.addLayout(system_layout)
        
        # System Messages button
        messages_btn = QPushButton("View System Messages")
        messages_btn.setToolTip("View recent system log messages")
        messages_btn.clicked.connect(self.get_system_messages)
        messages_btn.setStyleSheet("QPushButton { background-color: #607D8B; color: white; }")
        group_layout.addWidget(messages_btn)
        
        layout.addWidget(group)
    
    def create_right_panel(self):
        """Create the right panel for results"""
        # Create the main panel widget
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)  # Add spacing between elements
        
        # Results title
        results_title = QLabel("Results")
        results_title.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(results_title)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Create scroll area for the results table
        table_scroll = QScrollArea()
        table_scroll.setWidgetResizable(True)
        table_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        table_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Results table
        self.results_table = QTableWidget()
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSortingEnabled(True)  # Enable column sorting
        # Set initial empty state
        self.results_table.setRowCount(1)
        self.results_table.setColumnCount(1)
        self.results_table.setHorizontalHeaderLabels(["Status"])
        self.results_table.setItem(0, 0, QTableWidgetItem("No data loaded. Connect to API and run a query."))
        
        # Set the table as the scroll area's widget
        table_scroll.setWidget(self.results_table)
        layout.addWidget(table_scroll)
        
        # Export options
        export_layout = QHBoxLayout()
        
        export_csv_btn = QPushButton("Export to CSV")
        export_csv_btn.clicked.connect(self.export_to_csv)
        export_layout.addWidget(export_csv_btn)
        
        self.results_count_label = QLabel("0 results")
        self.results_count_label.setStyleSheet("font-weight: bold;")
        export_layout.addWidget(self.results_count_label)
        
        export_layout.addStretch()
        layout.addLayout(export_layout)
        
        return panel
    
    def show_loading(self, show=True):
        """Show/hide loading indicator"""
        self.progress_bar.setVisible(show)
        if show:
            self.progress_bar.setRange(0, 0)  # Indeterminate progress
            self.statusBar().showMessage("Loading...")
        else:
            self.progress_bar.setVisible(False)
            self.statusBar().showMessage("Ready")
    
    def make_api_request(self, endpoint, method='GET', data=None):
        """Make API request using worker thread"""
        # Check if API URL is set
        if not hasattr(self, 'api_base_url'):
            self.display_error("API connection not configured. Please set host and port.")
            return
            
        self.show_loading(True)
        url = f"{self.api_base_url}/{endpoint}"
        
        self.api_worker = self.create_api_worker(url, method, data)
        self.api_worker.finished.connect(self.on_api_success)
        self.api_worker.error.connect(self.on_api_error)
        self.api_worker.start()
    
    def on_api_success(self, response):
        """Handle successful API response"""
        self.show_loading(False)
        
        if response.get('status') == 'success':
            if 'data' in response:
                data = response['data']
                
                # Special handling for different API endpoints
                if hasattr(self, 'api_worker') and self.api_worker.url:
                    url = self.api_worker.url
                    
                    if 'sim/status' in url:
                        self.update_sim_status_display(data)
                        # Also display in table for export
                        self.display_results(data)
                    elif 'sim/signal' in url:
                        self.update_sim_status_display(data, signal_only=True)
                        self.display_results(data)
                    elif 'sim/operator' in url:
                        self.update_sim_status_display(data, operator_only=True)
                        self.display_results(data)
                    elif 'battery' in url and isinstance(data, dict) and 'voltage' in data:
                        self.update_battery_display(data)
                        self.display_results(data)
                    else:
                        self.display_results(data)
                else:
                    # Fallback - check data type for battery data
                    if isinstance(data, dict) and 'voltage' in data:
                        self.update_battery_display(data)
                    self.display_results(data)
                    
                if data and len(data) > 0:
                    count = response.get('count', len(data) if isinstance(data, list) else 1)
                    self.results_count_label.setText(f"{count} results")
                else:
                    # Empty result set
                    self.results_count_label.setText("0 results")
                    self.display_message("No data found matching your query")
            else:
                # Handle responses without data (like shutdown confirmation)
                message = response.get('message', 'Operation completed successfully')
                self.display_message(message)
                
                # Special handling for system operation responses
                if any(keyword in message.lower() for keyword in ['shutdown', 'reboot', 'restart', 'pin', 'delete', 'clear']):
                    QMessageBox.information(self, "Operation Result", message)
        else:
            # Handle warning status (partial success)
            if response.get('status') == 'warning':
                message = response.get('message', 'Operation completed with warnings')
                QMessageBox.warning(self, "Warning", message)
                self.display_message(message)
            else:
                self.display_error(response.get('message', 'Unknown error'))
    
    def on_api_error(self, error_msg):
        """Handle API error with enhanced timeout messaging"""
        self.show_loading(False)
        
        # Provide more helpful messages for timeout errors
        if "Read timed out" in error_msg or "timeout" in error_msg.lower():
            if "battery" in error_msg or "sim" in error_msg or "sms-reports" in error_msg:
                enhanced_msg = (
                    f"Operation timed out: {error_msg}\n\n"
                    "This is normal for battery/SIM operations as they require communication with the SIM800L module. "
                    "The module may be busy or the operation may take longer than expected. "
                    "Please try again in a moment."
                )
            else:
                enhanced_msg = f"Request timed out: {error_msg}\n\nThe server may be busy. Please try again."
        else:
            enhanced_msg = error_msg
            
        self.display_error(enhanced_msg)
    
    def display_results(self, data):
        """Display results in the table"""
        self.current_data = data
        
        if not data or len(data) == 0:
            self.results_table.setRowCount(0)
            self.results_table.setColumnCount(4)  # Set standard column count
            # Set default headers for empty table
            self.results_table.setHorizontalHeaderLabels(["ID", "Sender", "Timestamp", "Text"])
            return
        
        # Check if data is a list/tuple and has elements
        if isinstance(data, (list, tuple)) and len(data) > 0:
            # Check if first element is also a list/tuple (tabular data)
            if isinstance(data[0], (list, tuple)):
                self.results_table.setRowCount(len(data))
                self.results_table.setColumnCount(len(data[0]))
                
                # Set headers
                headers = ["ID", "Sender", "Timestamp", "Text"][:len(data[0])]
                self.results_table.setHorizontalHeaderLabels(headers)
                
                # Fill data
                for row, row_data in enumerate(data):
                    for col, cell_data in enumerate(row_data):
                        item = QTableWidgetItem(str(cell_data))
                        self.results_table.setItem(row, col, item)
            else:
                # Data is a list but elements are not lists/tuples
                # Treat as single column data
                self.results_table.setRowCount(len(data))
                self.results_table.setColumnCount(1)
                self.results_table.setHorizontalHeaderLabels(["Value"])
                
                for row, item_data in enumerate(data):
                    item = QTableWidgetItem(str(item_data))
                    self.results_table.setItem(row, 0, item)
        elif isinstance(data, dict):
            # Handle dictionary data
            self.results_table.setRowCount(1)
            self.results_table.setColumnCount(len(data))
            
            headers = list(data.keys())
            self.results_table.setHorizontalHeaderLabels(headers)
            
            for col, (key, value) in enumerate(data.items()):
                item = QTableWidgetItem(str(value))
                self.results_table.setItem(0, col, item)
        else:
            # Fallback for unexpected data types
            self.results_table.setRowCount(1)
            self.results_table.setColumnCount(1)
            self.results_table.setHorizontalHeaderLabels(["Data"])
            item = QTableWidgetItem(str(data))
            self.results_table.setItem(0, 0, item)
        
        # Resize columns to content and enable better scrolling
        self.results_table.resizeColumnsToContents()
        
        # Adjust column widths for better display in scroll area
        header = self.results_table.horizontalHeader()
        if self.results_table.columnCount() >= 4:
            # For SMS data, make text column wider
            header.setStretchLastSection(True)  # Text column stretches
            if self.results_table.columnCount() > 1:
                self.results_table.setColumnWidth(0, 80)   # ID column
                self.results_table.setColumnWidth(1, 120)  # Sender column  
                self.results_table.setColumnWidth(2, 150)  # Timestamp column
    
    def display_message(self, message):
        """Display a message in the results area"""
        self.results_table.setRowCount(1)
        self.results_table.setColumnCount(1)
        self.results_table.setHorizontalHeaderLabels(["Message"])
        item = QTableWidgetItem(message)
        self.results_table.setItem(0, 0, item)
        self.results_count_label.setText("1 result")
    
    def display_error(self, error_msg):
        """Display error message"""
        QMessageBox.critical(self, "Error", error_msg)
        self.statusBar().showMessage(f"Error: {error_msg}")
    
    def check_api_health(self):
        """Check API health status"""
        # Make sure status_label exists
        if not hasattr(self, 'status_label'):
            return
            
        try:
            host, port = self.current_host_port
            health_url = f"http://{host}:{port}/api/health"
            response = requests.get(health_url, timeout=5)
            if response.status_code == 200:
                self.status_label.setText("✓ API Connected")
                self.status_label.setStyleSheet("color: green; font-weight: bold;")
                self.setWindowTitle(f"SMS Database Viewer - Connected to {host}:{port}")
            else:
                self.status_label.setText("✗ API Error")
                self.status_label.setStyleSheet("color: red; font-weight: bold;")
                self.setWindowTitle("SMS Database Viewer - Connection Error")
        except Exception as e:
            self.status_label.setText("✗ API Offline")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            self.setWindowTitle("SMS Database Viewer - Offline")
            # Show error details in status bar
            self.statusBar().showMessage(f"Connection failed: {str(e)}")
    
    def get_all_sms(self):
        """Get all SMS messages"""
        self.make_api_request("sms")
    
    def get_statistics(self):
        """Get database statistics"""
        self.make_api_request("stats")
    
    def get_sms_by_sender(self):
        """Get SMS by sender"""
        sender = self.sender_input.text().strip()
        if not sender:
            QMessageBox.warning(self, "Warning", "Please enter a sender number")
            return
        self.make_api_request(f"sms/sender/{sender}")
    
    def search_sms_by_keyword(self):
        """Search SMS by keyword"""
        keyword = self.keyword_input.text().strip()
        if not keyword:
            QMessageBox.warning(self, "Warning", "Please enter a keyword")
            return
        self.make_api_request(f"sms/search?keyword={keyword}")
    
    def get_sms_by_date_range(self):
        """Get SMS by date range"""
        start = self.start_date.dateTime().toString("yyyy-MM-dd hh:mm:ss")
        end = self.end_date.dateTime().toString("yyyy-MM-dd hh:mm:ss")
        self.make_api_request(f"sms/date-range?start={start}&end={end}")
    
    def execute_custom_query(self):
        """Execute custom query"""
        query = self.custom_query_input.toPlainText().strip()
        if not query:
            QMessageBox.warning(self, "Warning", "Please enter a query")
            return
        
        params = []
        params_text = self.custom_params_input.text().strip()
        if params_text:
            try:
                params = json.loads(params_text)
            except json.JSONDecodeError:
                QMessageBox.warning(self, "Warning", "Invalid JSON in parameters")
                return
        
        data = {"query": query, "params": params}
        self.make_api_request("query", "POST", data)
    
    def export_to_csv(self):
        """Export current results to CSV"""
        if not self.current_data or len(self.current_data) == 0:
            QMessageBox.warning(self, "Warning", "No data to export. Please run a query first.")
            return
        
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save CSV", f"sms_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV Files (*.csv);;All Files (*)"
        )
        
        if filename:
            try:
                import csv
                with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                    
                    # Handle different data types
                    if isinstance(self.current_data, dict):
                        # Single dictionary (like SIM status)
                        self._export_dict_to_csv(csvfile, self.current_data)
                    elif isinstance(self.current_data, list) and len(self.current_data) > 0:
                        if isinstance(self.current_data[0], (list, tuple)):
                            # List of lists/tuples (database rows)
                            self._export_rows_to_csv(csvfile, self.current_data)
                        elif isinstance(self.current_data[0], dict):
                            # List of dictionaries
                            self._export_dict_list_to_csv(csvfile, self.current_data)
                        else:
                            # List of simple values
                            writer = csv.writer(csvfile)
                            writer.writerow(["Value"])
                            for item in self.current_data:
                                writer.writerow([str(item)])
                    else:
                        # Fallback for other types
                        writer = csv.writer(csvfile)
                        writer.writerow(["Data"])
                        writer.writerow([str(self.current_data)])
                
                QMessageBox.information(self, "Success", f"Data exported to {filename}")
                self.statusBar().showMessage(f"Exported to {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export: {str(e)}")
    
    def _export_dict_to_csv(self, csvfile, data_dict):
        """Export a dictionary to CSV in a readable format"""
        import csv
        writer = csv.writer(csvfile)
        
        def flatten_dict(d, parent_key='', sep='_'):
            """Flatten nested dictionary"""
            items = []
            for k, v in d.items():
                new_key = f"{parent_key}{sep}{k}" if parent_key else k
                if isinstance(v, dict):
                    items.extend(flatten_dict(v, new_key, sep=sep).items())
                elif isinstance(v, list):
                    items.append((new_key, str(v)))
                else:
                    items.append((new_key, v))
            return dict(items)
        
        flattened = flatten_dict(data_dict)
        
        # Write headers and values
        writer.writerow(["Field", "Value"])
        for key, value in flattened.items():
            writer.writerow([key, str(value)])
    
    def _export_rows_to_csv(self, csvfile, rows):
        """Export list of rows (tuples/lists) to CSV"""
        import csv
        writer = csv.writer(csvfile)
        
        # Try to determine headers based on data
        if len(rows) > 0:
            num_cols = len(rows[0])
            if num_cols == 4:
                headers = ["ID", "Sender", "Timestamp", "Text"]
            elif num_cols == 3:
                headers = ["ID", "Timestamp", "Message"]
            elif num_cols == 2:
                headers = ["Field", "Value"]
            else:
                headers = [f"Column_{i+1}" for i in range(num_cols)]
            
            writer.writerow(headers)
        
        # Write data rows
        writer.writerows(rows)
    
    def _export_dict_list_to_csv(self, csvfile, dict_list):
        """Export list of dictionaries to CSV"""
        import csv
        
        if not dict_list:
            return
        
        # Get all unique keys from all dictionaries
        all_keys = set()
        for d in dict_list:
            if isinstance(d, dict):
                all_keys.update(d.keys())
        
        fieldnames = sorted(list(all_keys))
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for item in dict_list:
            if isinstance(item, dict):
                # Flatten any nested structures
                flattened_item = {}
                for key, value in item.items():
                    if isinstance(value, (dict, list)):
                        flattened_item[key] = str(value)
                    else:
                        flattened_item[key] = value
                writer.writerow(flattened_item)
    
    def get_battery_status(self):
        """Get battery status from API (with extended timeout for SIM800L communication)"""
        self.statusBar().showMessage("Getting battery status (may take 30+ seconds for SIM800L communication)...")
        self.make_api_request_with_timeout("battery", timeout=30)
    
    def make_api_request_with_timeout(self, endpoint, method='GET', data=None, timeout=30):
        """Make API request with custom timeout for slow operations"""
        # Check if API URL is set
        if not hasattr(self, 'api_base_url'):
            self.display_error("API connection not configured. Please set host and port.")
            return
            
        self.show_loading(True)
        url = f"{self.api_base_url}/{endpoint}"
        
        self.api_worker = self.create_api_worker(url, method, data, timeout)
        self.api_worker.finished.connect(self.on_api_success)
        self.api_worker.error.connect(self.on_api_error)
        self.api_worker.start()
    
    def toggle_battery_timer(self):
        """Toggle auto-refresh timer for battery status"""
        if not self.battery_timer_running:
            try:
                interval = int(self.battery_auto_refresh.text()) * 1000  # Convert to milliseconds
                if interval < 5000:  # Minimum 5 seconds
                    QMessageBox.warning(self, "Warning", "Minimum refresh interval is 5 seconds")
                    self.battery_auto_refresh.setText("5")
                    interval = 5000
                
                self.battery_timer.start(interval)
                self.battery_timer_btn.setText("Stop")
                self.battery_timer_btn.setStyleSheet("QPushButton { background-color: #F44336; color: white; }")
                self.battery_timer_running = True
                self.statusBar().showMessage(f"Battery auto-refresh started ({interval//1000}s intervals)")
                
                # Get initial battery status
                self.get_battery_status()
                
            except ValueError:
                QMessageBox.warning(self, "Warning", "Please enter a valid number for refresh interval")
        else:
            self.battery_timer.stop()
            self.battery_timer_btn.setText("Start")
            self.battery_timer_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; }")
            self.battery_timer_running = False
            self.statusBar().showMessage("Battery auto-refresh stopped")
    
    def confirm_system_shutdown(self):
        """Confirm and execute system shutdown"""
        reply = QMessageBox.question(
            self, 
            "Confirm Shutdown",
            "Are you sure you want to shutdown the system?\n\nThis will immediately power off the device!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Second confirmation for safety
            reply2 = QMessageBox.critical(
                self,
                "FINAL WARNING",
                "LAST CHANCE!\n\nThis will immediately shutdown the system.\nAll unsaved work will be lost!\n\nProceed with shutdown?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply2 == QMessageBox.Yes:
                data = {
                    "confirm": True,
                    "reason": "Manual shutdown requested via SMS GUI"
                }
                self.make_api_request("system/shutdown", "POST", data)
    
    def confirm_system_reboot(self):
        """Confirm and execute system reboot"""
        reply = QMessageBox.question(
            self, 
            "Confirm Reboot",
            "Are you sure you want to reboot the system?\n\nThis will restart the device and all services!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            data = {
                "confirm": True,
                "reason": "Manual reboot requested via SMS GUI"
            }
            self.make_api_request("system/reboot", "POST", data)
    
    def confirm_sim_restart(self):
        """Confirm and restart SIM800 module"""
        reply = QMessageBox.question(
            self, 
            "Confirm SIM800 Restart",
            "Are you sure you want to restart the SIM800 module?\n\nThis may temporarily interrupt SMS services!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            data = {"confirm": True}
            self.make_api_request("sim/restart", "POST", data)
    
    def prompt_sim_pin(self):
        """Prompt for new SIM PIN and set it"""
        from PyQt5.QtWidgets import QInputDialog
        
        pin, ok = QInputDialog.getText(
            self, 
            "Set SIM PIN", 
            "Enter new 4-digit SIM PIN:",
            text=""
        )
        
        if ok and pin:
            # Validate PIN
            if not pin.isdigit() or len(pin) != 4:
                QMessageBox.warning(self, "Invalid PIN", "PIN must be exactly 4 digits!")
                return
            
            # Confirm PIN change
            reply = QMessageBox.question(
                self,
                "Confirm PIN Change",
                f"Are you sure you want to change the SIM PIN to: {pin}?\n\nMake sure you remember this PIN!",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                data = {"pin": pin}
                self.make_api_request("sim/set_pin", "POST", data)
    
    def get_system_messages(self):
        """Get system messages from API"""
        self.make_api_request("system/messages")
    
    def get_unique_senders(self):
        """Get unique SMS senders with message counts"""
        self.make_api_request("sms/unique-senders")
    
    def get_sms_date_range_info(self):
        """Get SMS date range information"""
        self.make_api_request("sms/date-range-info")
    
    def get_system_logs(self):
        """Get system logs with optional filtering"""
        from PyQt5.QtWidgets import QInputDialog
        
        filter_text, ok = QInputDialog.getText(
            self, 
            "Filter System Logs", 
            "Enter filter text (leave empty for all logs):",
            text=""
        )
        
        if ok:
            if filter_text.strip():
                self.make_api_request(f"system/logs?filter={filter_text.strip()}")
            else:
                self.make_api_request("system/logs")
    
    def get_sim_status(self):
        """Get comprehensive SIM status (with extended timeout for SIM800L communication)"""
        self.statusBar().showMessage("Getting SIM status (may take 30+ seconds for SIM800L communication)...")
        self.make_api_request_with_timeout("sim/status", timeout=30)
    
    def get_signal_strength(self):
        """Get signal strength information (with extended timeout for SIM800L communication)"""
        self.statusBar().showMessage("Getting signal strength (may take 25+ seconds for SIM800L communication)...")
        self.make_api_request_with_timeout("sim/signal", timeout=25)
    
    def get_network_operator(self):
        """Get network operator information (with extended timeout for SIM800L communication)"""
        self.statusBar().showMessage("Getting network operator (may take 25+ seconds for SIM800L communication)...")
        self.make_api_request_with_timeout("sim/operator", timeout=25)
    
    def get_battery_history(self):
        """Get battery voltage history (with extended timeout for SIM800L communication)"""
        self.make_api_request_with_timeout("battery/voltage-history", timeout=25)
    
    def get_data_stats(self):
        """Get detailed data statistics"""
        self.make_api_request("data/stats")
    
    def create_backup(self):
        """Create and download database backup"""
        try:
            import requests
            from PyQt5.QtWidgets import QFileDialog
            
            if not hasattr(self, 'api_base_url'):
                self.display_error("API connection not configured. Please set host and port.")
                return
            
            # Show file save dialog
            filename, _ = QFileDialog.getSaveFileName(
                self, 
                "Save Database Backup", 
                f"sms_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
                "SQLite Database (*.db);;All Files (*)"
            )
            
            if not filename:
                return  # User cancelled
            
            # Download backup
            url = f"{self.api_base_url}/data/backup"
            response = requests.get(url, timeout=30)
            
            if response.status_code == 200:
                with open(filename, 'wb') as f:
                    f.write(response.content)
                self.statusBar().showMessage(f"Backup saved to {filename}", 5000)
                QMessageBox.information(self, "Success", f"Database backup saved to:\n{filename}")
            else:
                self.display_error(f"Failed to create backup: HTTP {response.status_code}")
                
        except Exception as e:
            self.display_error(f"Failed to create backup: {str(e)}")
    
    def confirm_delete_all(self):
        """Confirm and delete ALL data"""
        reply = QMessageBox.warning(
            self,
            "⚠️ DELETE ALL DATA",
            "This will permanently delete ALL data:\n"
            "• All SMS messages\n"
            "• All system log messages\n"
            "• Everything in the database\n\n"
            "This action CANNOT be undone!\n\n"
            "Are you absolutely sure?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Second confirmation
            reply2 = QMessageBox.critical(
                self,
                "FINAL WARNING",
                "LAST CHANCE!\n\n"
                "This will delete EVERYTHING!\n"
                "All SMS messages and system logs will be lost forever!\n\n"
                "Type 'DELETE' to confirm:",
                QMessageBox.Ok | QMessageBox.Cancel,
                QMessageBox.Cancel
            )
            
            if reply2 == QMessageBox.Ok:
                from PyQt5.QtWidgets import QInputDialog
                confirm_text, ok = QInputDialog.getText(
                    self, "Type DELETE to confirm", "Type 'DELETE' to proceed:"
                )
                
                if ok and confirm_text.strip().upper() == "DELETE":
                    data = {"confirm": True}
                    self.make_api_request("data/delete-all", "POST", data)
                else:
                    QMessageBox.information(self, "Cancelled", "Delete operation cancelled.")
    
    def confirm_delete_sms(self):
        """Confirm and delete SMS messages only"""
        reply = QMessageBox.question(
            self,
            "Delete SMS Messages",
            "This will delete all SMS messages but keep system logs.\n\n"
            "Are you sure you want to proceed?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            data = {"confirm": True}
            self.make_api_request("data/delete-sms", "POST", data)
    
    def confirm_clear_logs(self):
        """Confirm and clear system logs"""
        reply = QMessageBox.question(
            self,
            "Clear System Logs",
            "This will delete all system log messages but keep SMS messages.\n\n"
            "Are you sure you want to proceed?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            data = {"confirm": True}
            self.make_api_request("data/clear-system-logs", "POST", data)
    
    def prompt_delete_by_sender(self):
        """Prompt for sender and delete messages"""
        from PyQt5.QtWidgets import QInputDialog
        
        sender, ok = QInputDialog.getText(
            self,
            "Delete by Sender",
            "Enter sender number/name to delete all messages from:",
            text=""
        )
        
        if ok and sender.strip():
            reply = QMessageBox.question(
                self,
                "Confirm Delete by Sender",
                f"Delete ALL messages from sender: {sender.strip()}\n\n"
                f"This action cannot be undone!\n\n"
                f"Are you sure?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                data = {
                    "sender": sender.strip(),
                    "confirm": True
                }
                self.make_api_request("data/delete-by-sender", "POST", data)
    
    def prompt_delete_by_keyword(self):
        """Prompt for keyword and delete messages"""
        from PyQt5.QtWidgets import QInputDialog
        
        keyword, ok = QInputDialog.getText(
            self,
            "Delete by Keyword",
            "Enter keyword to delete all messages containing it:",
            text=""
        )
        
        if ok and keyword.strip():
            reply = QMessageBox.question(
                self,
                "Confirm Delete by Keyword",
                f"Delete ALL messages containing: '{keyword.strip()}'\n\n"
                f"This action cannot be undone!\n\n"
                f"Are you sure?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                data = {
                    "keyword": keyword.strip(),
                    "confirm": True
                }
                self.make_api_request("data/delete-by-keyword", "POST", data)
    
    def update_sim_status_display(self, sim_data, signal_only=False, operator_only=False):
        """Update SIM status display with comprehensive information"""
        try:
            if not hasattr(self, 'sim_status_label'):
                return
            
            if signal_only and 'signal_quality' in sim_data:
                # Signal strength only
                rssi = sim_data.get('rssi', 'Unknown')
                signal_quality = sim_data.get('signal_quality', 'Unknown')
                signal_dbm = sim_data.get('signal_dbm', 'Unknown')
                
                display_text = f"📶 Signal: {signal_quality}"
                if signal_dbm != 'Unknown' and signal_dbm is not None:
                    display_text += f"\nStrength: {signal_dbm} dBm (RSSI: {rssi})"
                
                color = "#388E3C" if signal_quality in ["Excellent", "Good"] else "#F57C00" if signal_quality == "Fair" else "#D32F2F"
                
            elif operator_only and 'operator' in sim_data:
                # Operator info only
                operator = sim_data.get('operator', 'Unknown')
                access_tech = sim_data.get('access_technology', 'Unknown')
                
                display_text = f"📡 Operator: {operator}"
                if access_tech != 'Unknown':
                    display_text += f"\nTechnology: {access_tech}"
                
                color = "#F57C00"
                
            else:
                # Comprehensive SIM status
                display_text = "📱 SIM Status:\n"
                
                # Signal information
                if 'signal' in sim_data and sim_data['signal']:
                    signal = sim_data['signal']
                    quality = signal.get('signal_quality', 'Unknown')
                    display_text += f"📶 Signal: {quality}"
                    if signal.get('signal_dbm') is not None:
                        display_text += f" ({signal['signal_dbm']} dBm)"
                    display_text += "\n"
                
                # Operator information
                if 'operator' in sim_data and sim_data['operator']:
                    operator = sim_data['operator']
                    op_name = operator.get('operator', 'Unknown')
                    display_text += f"📡 Operator: {op_name}\n"
                
                # Battery information
                if 'battery' in sim_data and sim_data['battery']:
                    battery = sim_data['battery']
                    voltage = battery.get('voltage', 'Unknown')
                    charging_status = battery.get('charging_status', 'Unknown')
                    if voltage != 'Unknown':
                        display_text += f"🔋 Battery: {voltage}V ({charging_status})\n"
                
                # Status summary
                if 'status_summary' in sim_data:
                    display_text += f"\n{sim_data['status_summary']}"
                
                # Determine overall status color
                if 'signal' in sim_data and sim_data['signal']:
                    quality = sim_data['signal'].get('signal_quality', 'Unknown')
                    if quality in ["Excellent", "Good"]:
                        color = "#2E7D32"
                    elif quality == "Fair":
                        color = "#F57C00"
                    else:
                        color = "#D32F2F"
                else:
                    color = "#1976D2"
            
            # Update the display
            self.sim_status_label.setText(display_text.strip())
            self.sim_status_label.setStyleSheet(
                f"font-size: 10px; padding: 5px; "
                f"background-color: #f0f8ff; border: 2px solid {color}; "
                f"border-radius: 3px; color: {color};"
            )
            
        except Exception as e:
            self.sim_status_label.setText(f"Error updating SIM display: {str(e)}")
            self.sim_status_label.setStyleSheet(
                "font-size: 10px; padding: 5px; background-color: #f0f8ff; "
                "border: 1px solid red; border-radius: 3px; color: red;"
            )
    
    def update_battery_display(self, battery_data):
        """Update battery status display"""
        try:
            voltage = battery_data.get('voltage', 'Unknown')
            status = battery_data.get('status', 'Unknown')
            charge_level = battery_data.get('charge_level', 'Unknown')
            charging_status = battery_data.get('charging_status', 'unknown')
            timestamp = battery_data.get('timestamp', 'Unknown')
            warnings = battery_data.get('low_battery_warnings', 0)
            
            # Determine status color and icon based on voltage and charging status
            if isinstance(voltage, (int, float)):
                if voltage >= 4.0:
                    icon = "🔋" if charging_status != "charging" else "⚡"
                    color = "green"
                elif voltage >= 3.7:
                    icon = "🔋" if charging_status != "charging" else "⚡"
                    color = "orange"
                elif voltage >= 3.3:
                    icon = "🪫" if charging_status != "charging" else "⚡"
                    color = "red"
                else:
                    icon = "⚠️"
                    color = "darkred"
            else:
                icon = "❓"
                color = "gray"
            
            # Format display text with charging status
            display_text = f"{icon} Voltage: {voltage}V"
            if isinstance(charge_level, (int, float)):
                display_text += f"\nLevel: {charge_level}%"
            
            # Add charging status
            charging_icons = {
                "charging": "⚡ Charging",
                "discharging": "↘️ Discharging", 
                "stable": "➖ Stable",
                "insufficient_data": "❔ Unknown",
                "unknown": "❔ Unknown"
            }
            charging_display = charging_icons.get(charging_status, f"❔ {charging_status}")
            display_text += f"\nStatus: {charging_display}"
            
            display_text += f"\nUpdated: {timestamp}"
            
            if warnings > 0:
                display_text += f"\n⚠️ Low battery warnings: {warnings}"
            
            # Update display with appropriate styling
            self.battery_status_label.setText(display_text)
            self.battery_status_label.setStyleSheet(
                f"font-size: 11px; padding: 5px; "
                f"background-color: #f5f5f5; border: 2px solid {color}; "
                f"border-radius: 3px; color: {color};"
            )
            
        except Exception as e:
            self.battery_status_label.setText(f"Error updating battery display: {str(e)}")
            self.battery_status_label.setStyleSheet(
                "font-size: 11px; padding: 5px; background-color: #f5f5f5; "
                "border: 1px solid red; border-radius: 3px; color: red;"
            )
    
    # SMS Reports Methods
    def get_sms_reports_config(self):
        """Get SMS reports configuration"""
        try:
            # Check if API URL is set
            if not hasattr(self, 'api_base_url'):
                self.sms_reports_status.setText("Status: API not connected")
                self.sms_reports_status.setStyleSheet("font-size: 10px; color: red;")
                return
                
            url = f"{self.api_base_url}/sms-reports/config"
            worker = self.create_api_worker(url, 'GET', timeout=20)
            worker.finished.connect(self.on_sms_reports_config_received)
            worker.error.connect(self.display_error)
            worker.start()
            self.statusBar().showMessage("Loading SMS reports configuration (may take 20+ seconds)...")
        except Exception as e:
            self.display_error(f"Failed to get SMS reports config: {str(e)}")
    
    def on_sms_reports_config_received(self, response):
        """Handle SMS reports configuration response"""
        try:
            if response.get('status') == 'success':
                config = response.get('data', {})
                
                # Update UI elements
                self.reports_enabled_cb.setChecked(config.get('enabled', False))
                self.reports_enabled_cb.setText("Disable Reports" if config.get('enabled', False) else "Enable Reports")
                
                self.recipient_input.setText(config.get('recipient', ''))
                self.interval_input.setText(str(config.get('interval_hours', 168)))
                
                # Update status display
                status_text = f"Status: {'Enabled' if config.get('enabled') else 'Disabled'}"
                if config.get('recipient'):
                    status_text += f"\nRecipient: {config.get('recipient')}"
                status_text += f"\nInterval: {config.get('interval_hours', 0):.1f}h"
                
                if config.get('last_sent_formatted') != "Never":
                    status_text += f"\nLast sent: {config.get('last_sent_formatted')}"
                
                if config.get('next_report_time'):
                    status_text += f"\nNext report: {config.get('next_report_time')}"
                
                self.sms_reports_status.setText(status_text)
                self.sms_reports_status.setStyleSheet("font-size: 10px; color: green;")
                
                self.statusBar().showMessage("SMS reports configuration loaded", 3000)
            else:
                self.display_error(f"Failed to load config: {response.get('message', 'Unknown error')}")
        except Exception as e:
            self.display_error(f"Error processing SMS reports config: {str(e)}")
    
    def toggle_reports_enabled(self):
        """Toggle reports enabled status"""
        enabled = self.reports_enabled_cb.isChecked()
        self.reports_enabled_cb.setText("Disable Reports" if enabled else "Enable Reports")
        
        # Update configuration immediately
        self.update_sms_reports_config()
    
    def update_sms_reports_config(self):
        """Update SMS reports configuration"""
        try:
            recipient = self.recipient_input.text().strip()
            interval_text = self.interval_input.text().strip()
            enabled = self.reports_enabled_cb.isChecked()
            
            # Validate inputs
            if enabled and not recipient:
                QMessageBox.warning(self, "Validation Error", "Please enter a recipient phone number")
                return
            
            if not interval_text:
                interval_hours = 168  # Default 1 week
            else:
                try:
                    interval_hours = float(interval_text)
                    if interval_hours < 0.25:
                        QMessageBox.warning(self, "Validation Error", "Interval must be at least 0.25 hours (15 minutes)")
                        return
                except ValueError:
                    QMessageBox.warning(self, "Validation Error", "Please enter a valid number for interval")
                    return
            
            data = {
                'enabled': enabled,
                'recipient': recipient,
                'interval_hours': interval_hours
            }
            
            url = f"{self.api_base_url}/sms-reports/config"
            worker = self.create_api_worker(url, 'POST', data, timeout=20)
            worker.finished.connect(self.on_sms_reports_config_updated)
            worker.error.connect(self.display_error)
            worker.start()
            self.statusBar().showMessage("Updating SMS reports configuration...")
            
        except Exception as e:
            self.display_error(f"Failed to update SMS reports config: {str(e)}")
    
    def on_sms_reports_config_updated(self, response):
        """Handle SMS reports configuration update response"""
        try:
            if response.get('status') == 'success':
                QMessageBox.information(self, "Success", "SMS reports configuration updated successfully!")
                self.get_sms_reports_config()  # Refresh the display
                self.statusBar().showMessage("SMS reports configuration updated", 3000)
            else:
                self.display_error(f"Failed to update config: {response.get('message', 'Unknown error')}")
        except Exception as e:
            self.display_error(f"Error processing config update: {str(e)}")
    
    def preview_status_report(self):
        """Preview the status report content"""
        try:
            url = f"{self.api_base_url}/sms-reports/preview"
            worker = self.create_api_worker(url, 'GET', timeout=30)
            worker.finished.connect(self.on_report_preview_received)
            worker.error.connect(self.display_error)
            worker.start()
            self.statusBar().showMessage("Generating report preview (may take 30+ seconds for SIM800L communication)...")
        except Exception as e:
            self.display_error(f"Failed to preview report: {str(e)}")
    
    def on_report_preview_received(self, response):
        """Handle report preview response"""
        try:
            if response.get('status') == 'success':
                data = response.get('data', {})
                report = data.get('report', 'No report content')
                length = data.get('length', 0)
                sms_count = data.get('estimated_sms_count', 1)
                
                # Show preview in a message box
                QMessageBox.information(
                    self, 
                    f"Status Report Preview ({length} chars, ~{sms_count} SMS)",
                    report
                )
                self.statusBar().showMessage("Report preview generated", 3000)
            else:
                self.display_error(f"Failed to generate preview: {response.get('message', 'Unknown error')}")
        except Exception as e:
            self.display_error(f"Error processing report preview: {str(e)}")
    
    def send_report_now(self):
        """Send status report immediately"""
        try:
            recipient = self.recipient_input.text().strip()
            
            # Ask for confirmation
            reply = QMessageBox.question(
                self,
                "Send Report Now",
                f"Send status report now to:\n{recipient or 'default recipient'}?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
            
            data = {}
            if recipient:
                data['recipient'] = recipient
            
            url = f"{self.api_base_url}/sms-reports/send-now"
            worker = self.create_api_worker(url, 'POST', data, timeout=60)
            worker.finished.connect(self.on_report_sent)
            worker.error.connect(self.display_error)
            worker.start()
            self.statusBar().showMessage("Sending status report (may take 60+ seconds for SMS transmission)...")
            
        except Exception as e:
            self.display_error(f"Failed to send report: {str(e)}")
    
    def on_report_sent(self, response):
        """Handle report sent response"""
        try:
            if response.get('status') == 'success':
                recipient = response.get('recipient', 'unknown')
                QMessageBox.information(self, "Success", f"Status report sent to {recipient}!")
                self.get_sms_reports_config()  # Refresh to update last sent time
                self.statusBar().showMessage("Status report sent successfully", 5000)
            else:
                self.display_error(f"Failed to send report: {response.get('message', 'Unknown error')}")
        except Exception as e:
            self.display_error(f"Error processing report send: {str(e)}")
    
    def test_sms_send(self):
        """Send a test SMS"""
        try:
            from PyQt5.QtWidgets import QInputDialog
            
            # Get recipient (default to current recipient)
            default_recipient = self.recipient_input.text().strip()
            recipient, ok = QInputDialog.getText(
                self,
                "Test SMS",
                "Enter recipient phone number:",
                text=default_recipient
            )
            
            if not ok or not recipient.strip():
                return
            
            # Get test message
            message, ok = QInputDialog.getText(
                self,
                "Test SMS",
                "Enter test message:",
                text="Test message from SIM800L system"
            )
            
            if not ok:
                return
            
            data = {
                'recipient': recipient.strip(),
                'message': message or "Test message from SIM800L system"
            }
            
            url = f"{self.api_base_url}/sms-reports/test-sms"
            worker = self.create_api_worker(url, 'POST', data, timeout=60)
            worker.finished.connect(self.on_test_sms_sent)
            worker.error.connect(self.display_error)
            worker.start()
            self.statusBar().showMessage("Sending test SMS...")
            
        except Exception as e:
            self.display_error(f"Failed to send test SMS: {str(e)}")
    
    def on_test_sms_sent(self, response):
        """Handle test SMS sent response"""
        try:
            if response.get('status') == 'success':
                recipient = response.get('recipient', 'unknown')
                message = response.get('sent_message', 'test message')
                QMessageBox.information(
                    self, 
                    "Success", 
                    f"Test SMS sent to {recipient}!\n\nMessage: {message}"
                )
                self.statusBar().showMessage("Test SMS sent successfully", 5000)
            else:
                self.display_error(f"Failed to send test SMS: {response.get('message', 'Unknown error')}")
        except Exception as e:
            self.display_error(f"Error processing test SMS: {str(e)}")

def main():
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("SMS Database Viewer with Battery Monitor")
    app.setApplicationVersion("1.1")
    
    # Create and show main window
    window = SMSGUIApp()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()