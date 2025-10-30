# Define variables
USER="user01"
HOST="192.168.1.65"

# Use them in the SCP commands
scp sim800l_hat_db_api_batt.py ${USER}@${HOST}:/opt/sms_capture/sim800l_hat.py
scp oled_display.py ${USER}@${HOST}:/opt/sms_capture/oled_display.py
