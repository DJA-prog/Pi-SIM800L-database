#!/usr/bin/env python3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
import requests
import json
from datetime import datetime
import os
from dotenv import load_dotenv

# Load configuration from .env.server file
load_dotenv('.env.server')
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
API_BASE_URL = f"http://{os.getenv('API_HOST', 'localhost')}:{os.getenv('API_PORT', '5000')}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - show main menu"""
    keyboard = [
        [InlineKeyboardButton("📱 SMS Operations", callback_data="sms_menu")],
        [InlineKeyboardButton("� Battery & SIM", callback_data="system_menu")],
        [InlineKeyboardButton("🗂️ Data Management", callback_data="data_menu")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(
            '🤖 Welcome to the SIM800L SMS Bot!\n\n'
            'Choose an option below to interact with the SMS system:',
            reply_markup=reply_markup
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses"""
    query = update.callback_query
    if not query or not query.data:
        return
        
    await query.answer()
    
    if query.data == "sms_menu":
        await show_sms_menu(query)
    elif query.data == "system_menu":
        await show_system_menu(query)
    elif query.data == "data_menu":
        await show_data_menu(query)
    elif query.data == "help":
        await show_help(query)
    elif query.data == "back_main":
        await show_main_menu(query)
    elif query.data == "confirm_delete_sms":
        try:
            response = requests.post(f"{API_BASE_URL}/delete_sms_only", json={"confirmation": "CONFIRMED"})
            if response.status_code == 200:
                result = response.json()
                await query.edit_message_text(f"✅ {result.get('message', 'SMS deleted successfully')}")
            else:
                await query.edit_message_text("❌ Failed to delete SMS")
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {str(e)}")
    elif query.data == "confirm_clear_logs":
        try:
            response = requests.post(f"{API_BASE_URL}/clear_system_logs", json={"confirmation": "CONFIRMED"})
            if response.status_code == 200:
                result = response.json()
                await query.edit_message_text(f"✅ {result.get('message', 'System logs cleared successfully')}")
            else:
                await query.edit_message_text("❌ Failed to clear logs")
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {str(e)}")
    elif query.data.startswith("sms_"):
        await handle_sms_operations(query, context)
    elif query.data.startswith("system_"):
        await handle_system_operations(query, context)
    elif query.data.startswith("data_"):
        await handle_data_operations(query, context)

async def show_main_menu(query):
    """Show the main menu"""
    keyboard = [
        [InlineKeyboardButton("📱 SMS Operations", callback_data="sms_menu")],
        [InlineKeyboardButton("� Battery & SIM", callback_data="system_menu")],
        [InlineKeyboardButton("🗂️ Data Management", callback_data="data_menu")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        '🤖 Welcome to the SIM800L SMS Bot!\n\n'
        'Choose an option below to interact with the SMS system:',
        reply_markup=reply_markup
    )

async def show_sms_menu(query):
    """Show SMS operations menu"""
    keyboard = [
        [InlineKeyboardButton("📋 Get All SMS", callback_data="sms_get_all")],
        [InlineKeyboardButton("👤 Get by Sender", callback_data="sms_by_sender")],
        [InlineKeyboardButton("� Search by Keyword", callback_data="sms_by_keyword")],
        [InlineKeyboardButton("�📅 Get by Date Range", callback_data="sms_by_date")],
        [InlineKeyboardButton("� Unique Senders", callback_data="sms_unique_senders")],
        [InlineKeyboardButton("📊 SMS Statistics", callback_data="sms_stats")],
        [InlineKeyboardButton("� Date Range Info", callback_data="sms_date_info")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        '📱 SMS Operations\n\n'
        'Choose an SMS operation:',
        reply_markup=reply_markup
    )

async def show_system_menu(query):
    """Show system operations menu"""
    keyboard = [
        [InlineKeyboardButton("🔋 Battery Status", callback_data="system_battery")],
        [InlineKeyboardButton("📶 Signal Strength", callback_data="system_signal")],
        [InlineKeyboardButton("📡 Network Operator", callback_data="system_operator")],
        [InlineKeyboardButton("📱 Full SIM Status", callback_data="system_sim_status")],
        [InlineKeyboardButton("📊 System Config", callback_data="system_config")],
        [InlineKeyboardButton("💾 System Logs", callback_data="system_logs")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        '🔋 Battery & SIM Status\n\n'
        'Choose a system operation:',
        reply_markup=reply_markup
    )

async def show_data_menu(query):
    """Show data management menu"""
    keyboard = [
        [InlineKeyboardButton("📊 Data Statistics", callback_data="data_stats")],
        [InlineKeyboardButton("💾 Create Backup", callback_data="data_backup")],
        [InlineKeyboardButton("⚠️ Delete SMS Only", callback_data="data_delete_sms")],
        [InlineKeyboardButton("🗑️ Clear System Logs", callback_data="data_clear_logs")],
        [InlineKeyboardButton("🔍 Delete by Sender", callback_data="data_delete_sender")],
        [InlineKeyboardButton("💬 Delete by Keyword", callback_data="data_delete_keyword")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        '🗂️ Data Management\n\n'
        '⚠️ Warning: Delete operations are permanent!\n'
        'Choose a data operation:',
        reply_markup=reply_markup
    )

async def show_data_menu_old(query):
    """Show data operations menu"""
    keyboard = [
        [InlineKeyboardButton("📋 Get All Data", callback_data="data_get_all")],
        [InlineKeyboardButton("👤 Get by Username", callback_data="data_by_username")],
        [InlineKeyboardButton("📅 Get by Date Range", callback_data="data_by_date")],
        [InlineKeyboardButton("🏷️ Get by Serial", callback_data="data_by_serial")],
        [InlineKeyboardButton("💳 Get by Credit Range", callback_data="data_by_credit")],
        [InlineKeyboardButton("🏷️📅 Serial + Date", callback_data="data_serial_date")],
        [InlineKeyboardButton("� List All Serials", callback_data="data_list_serials")],
        [InlineKeyboardButton("👥 List All Usernames", callback_data="data_list_usernames")],
        [InlineKeyboardButton("🔗 Serials by Username", callback_data="data_serials_by_user")],
        [InlineKeyboardButton("�🔙 Back to Main Menu", callback_data="back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        '📊 Data Operations\n\n'
        'Choose a data operation:',
        reply_markup=reply_markup
    )

async def show_help(query):
    """Show help information"""
    keyboard = [
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    help_text = """
ℹ️ Help Information

This bot allows you to interact with the SIM800L SMS system via the API.

📱 SMS Operations:
• Get All SMS - Retrieve all SMS messages
• Get by Sender - Find messages from specific sender
• Search by Keyword - Find messages containing text
• Get by Date Range - Messages between two dates
• Unique Senders - List all unique SMS senders
• SMS Statistics - Database statistics
• Date Range Info - Time span of SMS data

� Battery & SIM:
• Battery Status - Current battery voltage and charging status
• Signal Strength - Network signal quality
• Network Operator - Current cellular operator
• Full SIM Status - Comprehensive status report
• System Config - System configuration details
• System Logs - Recent system messages

🗂️ Data Management:
• Data Statistics - Detailed database statistics
• Create Backup - Download database backup
• Delete SMS Only - Remove SMS messages (keep logs)
• Clear System Logs - Remove system logs (keep SMS)
• Delete by Sender - Remove messages from specific sender
• Delete by Keyword - Remove messages containing keyword

💡 Tips:
• Use format YYYY-MM-DD HH:MM:SS for dates
• Delete operations require confirmation
• All operations are real-time from the SIM800L system
• Battery status shows voltage and charging trends
    """
    
    await query.edit_message_text(help_text, reply_markup=reply_markup)

async def handle_sms_operations(query, context):
    """Handle SMS-related operations"""
    operation = query.data
    
    if operation == "sms_get_all":
        await get_all_sms(query)
    elif operation == "sms_stats":
        await get_sms_statistics(query)
    elif operation == "sms_unique_senders":
        await get_unique_senders(query)
    elif operation == "sms_date_info":
        await get_sms_date_info(query)
    elif operation == "sms_by_sender":
        await query.edit_message_text("👤 Please send the sender number/name you want to search for:")
        context.user_data['waiting_for'] = 'sms_sender'
    elif operation == "sms_by_date":
        await query.edit_message_text("📅 Please send the date range in format:\nstart_date,end_date\n\nExample: 2025-09-01 00:00:00,2025-09-27 23:59:59")
        context.user_data['waiting_for'] = 'sms_date_range'
    elif operation == "sms_by_keyword":
        await query.edit_message_text("🔍 Please send the keyword you want to search for in SMS messages:")
        context.user_data['waiting_for'] = 'sms_keyword'

async def handle_system_operations(query, context):
    """Handle system-related operations"""
    operation = query.data
    
    if operation == "system_battery":
        await get_battery_status(query)
    elif operation == "system_signal":
        await get_signal_strength(query)
    elif operation == "system_operator":
        await get_network_operator(query)
    elif operation == "system_sim_status":
        await get_sim_status(query)
    elif operation == "system_config":
        await get_system_config(query)
    elif operation == "system_logs":
        await get_system_logs(query)

async def handle_data_operations(query, context):
    """Handle data management operations"""
    operation = query.data
    
    if operation == "data_stats":
        await get_data_statistics(query)
    elif operation == "data_backup":
        await create_data_backup(query)
    elif operation == "data_delete_sms":
        await confirm_delete_sms(query)
    elif operation == "data_clear_logs":
        await confirm_clear_logs(query)
    elif operation == "data_delete_sender":
        await query.edit_message_text("� Please send the sender number/name to delete all messages from:")
        context.user_data['waiting_for'] = 'delete_sender'
    elif operation == "data_delete_keyword":
        await query.edit_message_text("� Please send the keyword to delete all messages containing it:")
        context.user_data['waiting_for'] = 'delete_keyword'

async def get_all_sms(query):
    """Get all SMS messages"""
    try:
        response = requests.get(f"{API_BASE_URL}/sms", timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'success' and data['data']:
                messages = data['data']
                text = f"📱 All SMS Messages ({len(messages)} total):\n\n"
                
                for msg in messages[-10:]:  # Show last 10 messages
                    text += f"📱 ID: {msg[0]}\n👤 From: {msg[1]}\n📅 Time: {msg[2]}\n💬 Text: {msg[3][:100]}{'...' if len(msg[3]) > 100 else ''}\n\n"
                
                if len(messages) > 10:
                    text += f"... and {len(messages) - 10} more messages\n"
                
                # Add back button
                keyboard = [[InlineKeyboardButton("🔙 Back to SMS Menu", callback_data="sms_menu")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(text, reply_markup=reply_markup)
            else:
                await query.edit_message_text("📱 No SMS messages found.")
        else:
            await query.edit_message_text(f"❌ Error: {response.status_code}")
    except Exception as e:
        await query.edit_message_text(f"❌ Connection error: {str(e)}")

async def get_all_data(query):
    """Get all data entries"""
    try:
        response = requests.get(f"{API_BASE_URL}/data", timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'success' and data['data']:
                entries = data['data']
                text = f"📊 All Data Entries ({len(entries)} total):\n\n"
                
                for entry in entries[-10:]:  # Show last 10 entries
                    text += f"🏷️ ID: {entry[0]}\n📋 Serial: {entry[1]}\n👤 User: {entry[2]}\n💳 Credit: NAD{entry[3]}\n⚡ Units: {entry[4]}kWh\n📅 Time: {entry[5]}\n\n"
                
                if len(entries) > 10:
                    text += f"... and {len(entries) - 10} more entries\n"
                
                # Add back button
                keyboard = [[InlineKeyboardButton("🔙 Back to Data Menu", callback_data="data_menu")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(text, reply_markup=reply_markup)
            else:
                await query.edit_message_text("📊 No data entries found.")
        else:
            await query.edit_message_text(f"❌ Error: {response.status_code}")
    except Exception as e:
        await query.edit_message_text(f"❌ Connection error: {str(e)}")

async def handle_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user text input based on what we're waiting for"""
    if not update.message or not update.message.text:
        return
    
    user_input = update.message.text.strip()
    
    # Check if we have user_data and get waiting_for
    if hasattr(context, 'user_data') and context.user_data:
        waiting_for = context.user_data.get('waiting_for')
    else:
        waiting_for = None
    
    if not waiting_for:
        await update.message.reply_text("ℹ️ Please use /start to begin or select an option from the menu.")
        return
    
    # Clear the waiting state
    if hasattr(context, 'user_data') and context.user_data:
        context.user_data['waiting_for'] = None
    
    try:
        if waiting_for == 'sms_sender':
            await search_sms_by_sender(update, user_input)
        elif waiting_for == 'sms_date_range':
            dates = user_input.split(',')
            if len(dates) == 2:
                await search_sms_by_date(update, dates[0].strip(), dates[1].strip())
            else:
                await update.message.reply_text("❌ Invalid format. Please use: start_date,end_date")
        elif waiting_for == 'sms_keyword':
            await search_sms_by_keyword(update, user_input)
        elif waiting_for == 'sms_sender_date':
            parts = user_input.split(',')
            if len(parts) == 3:
                await search_sms_by_sender_date(update, parts[0].strip(), parts[1].strip(), parts[2].strip())
            else:
                await update.message.reply_text("❌ Invalid format. Please use: sender,start_date,end_date")
        elif waiting_for == 'data_username':
            await search_data_by_username(update, user_input)
        elif waiting_for == 'data_date_range':
            dates = user_input.split(',')
            if len(dates) == 2:
                await search_data_by_date(update, dates[0].strip(), dates[1].strip())
            else:
                await update.message.reply_text("❌ Invalid format. Please use: start_date,end_date")
        elif waiting_for == 'data_serial':
            await search_data_by_serial(update, user_input)
        elif waiting_for == 'data_credit_range':
            credits = user_input.split(',')
            if len(credits) == 2:
                await search_data_by_credit(update, credits[0].strip(), credits[1].strip())
            else:
                await update.message.reply_text("❌ Invalid format. Please use: min_credit,max_credit")
        elif waiting_for == 'data_serial_date':
            parts = user_input.split(',')
            if len(parts) == 3:
                await search_data_by_serial_date(update, parts[0].strip(), parts[1].strip(), parts[2].strip())
            else:
                await update.message.reply_text("❌ Invalid format. Please use: serial,start_date,end_date")
        elif waiting_for == 'delete_sender':
            await delete_by_sender(update, user_input)
        elif waiting_for == 'delete_keyword':
            await delete_by_keyword(update, user_input)
                
    except Exception as e:
        await update.message.reply_text(f"❌ Error processing request: {str(e)}")

async def search_sms_by_sender(update, sender):
    """Search SMS by sender"""
    try:
        response = requests.get(f"{API_BASE_URL}/sms/sender/{sender}", timeout=10)
        await process_sms_response(update, response, f"📱 SMS from {sender}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def search_sms_by_date(update, start_date, end_date):
    """Search SMS by date range"""
    try:
        response = requests.get(f"{API_BASE_URL}/sms/date", 
                              params={'start': start_date, 'end': end_date}, 
                              timeout=10)
        await process_sms_response(update, response, f"📱 SMS from {start_date} to {end_date}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def search_sms_by_keyword(update, keyword):
    """Search SMS by keyword"""
    try:
        response = requests.get(f"{API_BASE_URL}/sms/keyword/{keyword}", timeout=10)
        await process_sms_response(update, response, f"📱 SMS containing '{keyword}'")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def search_sms_by_sender_date(update, sender, start_date, end_date):
    """Search SMS by sender and date range"""
    try:
        response = requests.get(f"{API_BASE_URL}/sms/sender/{sender}/date", 
                              params={'start': start_date, 'end': end_date}, 
                              timeout=10)
        await process_sms_response(update, response, f"📱 SMS from {sender} ({start_date} to {end_date})")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def search_data_by_username(update, username):
    """Search data by username"""
    try:
        response = requests.get(f"{API_BASE_URL}/data/username/{username}", timeout=10)
        await process_data_response(update, response, f"📊 Data for {username}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def search_data_by_date(update, start_date, end_date):
    """Search data by date range"""
    try:
        response = requests.get(f"{API_BASE_URL}/data/date", 
                              params={'start': start_date, 'end': end_date}, 
                              timeout=10)
        await process_data_response(update, response, f"📊 Data from {start_date} to {end_date}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def search_data_by_serial(update, serial):
    """Search data by serial"""
    try:
        response = requests.get(f"{API_BASE_URL}/data/serial/{serial}", timeout=10)
        await process_data_response(update, response, f"📊 Data for serial {serial}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def search_data_by_credit(update, min_credit, max_credit):
    """Search data by credit range"""
    try:
        response = requests.get(f"{API_BASE_URL}/data/credit", 
                              params={'min': min_credit, 'max': max_credit}, 
                              timeout=10)
        await process_data_response(update, response, f"📊 Data with credit NAD{min_credit} - NAD{max_credit}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def search_data_by_serial_date(update, serial, start_date, end_date):
    """Search data by serial and date range"""
    try:
        response = requests.get(f"{API_BASE_URL}/data/serial/{serial}/date", 
                              params={'start': start_date, 'end': end_date}, 
                              timeout=10)
        await process_data_response(update, response, f"📊 Data for {serial} ({start_date} to {end_date})")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def get_unique_serials(query):
    """Get list of all unique serial numbers"""
    try:
        response = requests.get(f"{API_BASE_URL}/data/serials", timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'success' and data['data']:
                serials = data['data']
                text = f"📝 All Serial Numbers ({len(serials)} total):\n\n"
                
                # Group serials in columns for better display
                for i, serial in enumerate(serials, 1):
                    text += f"🏷️ {serial}\n"
                    if i % 20 == 0 and i < len(serials):
                        text += "...\n"
                        break
                
                if len(serials) > 20:
                    text += f"... and {len(serials) - 20} more serials\n"
                
                # Add back button
                keyboard = [[InlineKeyboardButton("🔙 Back to Data Menu", callback_data="data_menu")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(text, reply_markup=reply_markup)
            else:
                await query.edit_message_text("📝 No serial numbers found.")
        else:
            await query.edit_message_text(f"❌ Error: {response.status_code}")
    except Exception as e:
        await query.edit_message_text(f"❌ Connection error: {str(e)}")

async def get_unique_usernames(query):
    """Get list of all unique usernames"""
    try:
        response = requests.get(f"{API_BASE_URL}/data/usernames", timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'success' and data['data']:
                usernames = data['data']
                text = f"👥 All Usernames ({len(usernames)} total):\n\n"
                
                # Group usernames in columns for better display
                for i, username in enumerate(usernames, 1):
                    text += f"👤 {username}\n"
                    if i % 20 == 0 and i < len(usernames):
                        text += "...\n"
                        break
                
                if len(usernames) > 20:
                    text += f"... and {len(usernames) - 20} more usernames\n"
                
                # Add back button
                keyboard = [[InlineKeyboardButton("🔙 Back to Data Menu", callback_data="data_menu")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(text, reply_markup=reply_markup)
            else:
                await query.edit_message_text("👥 No usernames found.")
        else:
            await query.edit_message_text(f"❌ Error: {response.status_code}")
    except Exception as e:
        await query.edit_message_text(f"❌ Connection error: {str(e)}")

async def get_data_statistics(query):
    """Get data statistics"""
    try:
        response = requests.get(f"{API_BASE_URL}/data_stats")
        if response.status_code == 200:
            stats = response.json()
            message = "📊 *Data Statistics*\n\n"
            message += f"📧 Total SMS: {stats.get('total_sms', 0)}\n"
            message += f"🔧 Total System Logs: {stats.get('total_system_logs', 0)}\n"
            message += f"👥 Unique Senders: {stats.get('unique_senders', 0)}\n"
            message += f"📅 Date Range: {stats.get('date_range', 'N/A')}\n"
            message += f"💾 Database Size: {stats.get('db_size', 'N/A')}"
            
            keyboard = [[InlineKeyboardButton("🔙 Back to Data Menu", callback_data="data_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ Failed to get statistics")
    except Exception as e:
        await query.edit_message_text(f"❌ Error: {str(e)}")

async def create_data_backup(query):
    """Create and download data backup"""
    try:
        response = requests.get(f"{API_BASE_URL}/backup")
        if response.status_code == 200:
            # Save backup file temporarily
            backup_filename = response.headers.get('Content-Disposition', 'backup.db').split('filename=')[-1].strip('"')
            
            with open(backup_filename, 'wb') as f:
                f.write(response.content)
            
            # Send file to user
            with open(backup_filename, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=backup_filename,
                    caption="📦 Database backup created successfully"
                )
            
            # Clean up
            os.remove(backup_filename)
            await query.edit_message_text("✅ Backup sent successfully!")
        else:
            await query.edit_message_text("❌ Failed to create backup")
    except Exception as e:
        await query.edit_message_text(f"❌ Error: {str(e)}")

async def confirm_delete_sms(query):
    """Show confirmation for SMS deletion"""
    keyboard = [
        [InlineKeyboardButton("✅ Yes, Delete All SMS", callback_data="confirm_delete_sms")],
        [InlineKeyboardButton("❌ Cancel", callback_data="data_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "⚠️ *Confirm SMS Deletion*\n\nThis will delete ALL SMS messages permanently.\nThis action cannot be undone!\n\nAre you sure?",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def confirm_clear_logs(query):
    """Show confirmation for log clearing"""
    keyboard = [
        [InlineKeyboardButton("✅ Yes, Clear All Logs", callback_data="confirm_clear_logs")],
        [InlineKeyboardButton("❌ Cancel", callback_data="data_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "⚠️ *Confirm Log Clearing*\n\nThis will delete ALL system logs permanently.\nThis action cannot be undone!\n\nAre you sure?",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def delete_by_sender(update, sender):
    """Delete all messages from a specific sender"""
    try:
        # Generate confirmation token
        import secrets
        confirmation_token = secrets.token_hex(16)
        
        # Show confirmation
        keyboard = [
            [InlineKeyboardButton(f"✅ Yes, Delete from {sender}", callback_data=f"confirm_delete_sender_{confirmation_token}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="data_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Store data for confirmation
        context = update.message.bot._callback_query_handlers
        context.user_data['delete_sender_data'] = {
            'sender': sender,
            'confirmation': confirmation_token
        }
        
        await update.message.reply_text(
            f"⚠️ *Confirm Deletion*\n\nDelete ALL messages from: {sender}\n\nThis action cannot be undone!",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def delete_by_keyword(update, keyword):
    """Delete all messages containing a keyword"""
    try:
        # Generate confirmation token
        import secrets
        confirmation_token = secrets.token_hex(16)
        
        # Show confirmation
        keyboard = [
            [InlineKeyboardButton(f"✅ Yes, Delete containing '{keyword}'", callback_data=f"confirm_delete_keyword_{confirmation_token}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="data_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Store data for confirmation
        context = update.message.bot._callback_query_handlers
        context.user_data['delete_keyword_data'] = {
            'keyword': keyword,
            'confirmation': confirmation_token
        }
        
        await update.message.reply_text(
            f"⚠️ *Confirm Deletion*\n\nDelete ALL messages containing: '{keyword}'\n\nThis action cannot be undone!",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def execute_delete_operation(operation_type, confirmation_token, param=None):
    """Execute delete operation with confirmation"""
    data = {"confirmation": confirmation_token}
    if param:
        if operation_type == "delete_by_sender":
            data["sender"] = param
        elif operation_type == "delete_by_keyword":
            data["keyword"] = param
    
    response = requests.post(f"{API_BASE_URL}/{operation_type}", json=data)
    return response

# Main function to run the bot
async def main():
    """Run the bot"""
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_input))
    
    # Start the bot
    print("🤖 Bot starting...")
    await application.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
