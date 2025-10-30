# Define variables
USER="user01"
HOST="192.168.1.65"

# Use them in the SCP commands
scp test_sim800l.py ${USER}@${HOST}:/opt/sms_capture/test_sim800l.py
