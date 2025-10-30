# Define variables
USER="user01"
# HOST="192.168.1.65"
HOST="192.168.188.176"

# Use them in the SCP commands
scp sim800l_hat.py ${USER}@${HOST}:/opt/sms_capture/sim800l_hat.py
scp oled_display.py ${USER}@${HOST}:/opt/sms_capture/oled_display.py
