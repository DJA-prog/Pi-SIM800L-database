RX_PIN = int(os.getenv('RX_PIN', 13))   # GPIO for SIM800L TX -> Pi RX
TX_PIN = int(os.getenv('TX_PIN', 12))   # GPIO for SIM800L RX <- Pi TX
BAUDRATE = int(os.getenv('BAUDRATE', 9600))
SIM_PIN = os.getenv('SIM_PIN', '9438')

