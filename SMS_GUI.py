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
    
    def __init__(self, url, method='GET', data=None):
        super().__init__()
        self.url = url
        self.method = method
        self.data = data
    
    def run(self):
        try:
            if self.method == 'GET':
                response = requests.get(self.url, timeout=10)
            elif self.method == 'POST':
                response = requests.post(self.url, json=self.data, timeout=10)
            
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
        self.load_settings()
        self.init_ui()
    
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
        
        self.api_worker = APIWorker(url, method, data)
        self.api_worker.finished.connect(self.on_api_success)
        self.api_worker.error.connect(self.on_api_error)
        self.api_worker.start()
    
    def on_api_success(self, response):
        """Handle successful API response"""
        self.show_loading(False)
        
        if response.get('status') == 'success':
            if 'data' in response:
                data = response['data']
                
                # Check if this is battery data and update status
                if isinstance(data, dict) and 'voltage' in data:
                    self.update_battery_display(data)
                    
                if data and len(data) > 0:
                    self.display_results(data)
                    count = response.get('count', len(data))
                    self.results_count_label.setText(f"{count} results")
                else:
                    # Empty result set
                    self.display_results([])  # Clear table
                    self.results_count_label.setText("0 results")
                    self.display_message("No data found matching your query")
            else:
                # Handle responses without data (like shutdown confirmation)
                message = response.get('message', 'Operation completed successfully')
                self.display_message(message)
                
                # Special handling for system operation responses
                if any(keyword in message.lower() for keyword in ['shutdown', 'reboot', 'restart', 'pin']):
                    QMessageBox.information(self, "System Operation", message)
        else:
            # Handle warning status (partial success)
            if response.get('status') == 'warning':
                message = response.get('message', 'Operation completed with warnings')
                QMessageBox.warning(self, "Warning", message)
                self.display_message(message)
            else:
                self.display_error(response.get('message', 'Unknown error'))
    
    def on_api_error(self, error_msg):
        """Handle API error"""
        self.show_loading(False)
        self.display_error(error_msg)
    
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
                with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                    if isinstance(self.current_data[0], (list, tuple)):
                        writer = csv.writer(csvfile)
                        # Write headers
                        headers = ["ID", "Sender", "Timestamp", "Text"][:len(self.current_data[0])]
                        writer.writerow(headers)
                        # Write data
                        writer.writerows(self.current_data)
                    else:
                        # Handle dictionary data
                        writer = csv.DictWriter(csvfile, fieldnames=self.current_data.keys())
                        writer.writeheader()
                        writer.writerow(self.current_data)
                
                QMessageBox.information(self, "Success", f"Data exported to {filename}")
                self.statusBar().showMessage(f"Exported to {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export: {str(e)}")
    
    def get_battery_status(self):
        """Get battery status from API"""
        self.make_api_request("battery")
    
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
    
    def update_battery_display(self, battery_data):
        """Update battery status display"""
        try:
            voltage = battery_data.get('voltage', 'Unknown')
            status = battery_data.get('status', 'Unknown')
            charge_level = battery_data.get('charge_level', 'Unknown')
            timestamp = battery_data.get('timestamp', 'Unknown')
            warnings = battery_data.get('low_battery_warnings', 0)
            
            # Determine status color and icon based on voltage only
            if isinstance(voltage, (int, float)):
                if voltage >= 4.0:
                    icon = "🔋"
                    color = "green"
                elif voltage >= 3.7:
                    icon = "🔋"
                    color = "orange"
                elif voltage >= 3.3:
                    icon = "🪫"
                    color = "red"
                else:
                    icon = "⚠️"
                    color = "darkred"
            else:
                icon = "❓"
                color = "gray"
            
            # Format display text without charging status
            display_text = f"{icon} Voltage: {voltage}V"
            if isinstance(charge_level, (int, float)):
                display_text += f"\nLevel: {charge_level}%"
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