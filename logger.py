import logging
import os
from logging.handlers import RotatingFileHandler

# Ensure a logs directory exists
LOG_DIR = 'logs'
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, 'app.log')

def get_app_logger(name='SensorFlasher'):
    logger = logging.getLogger(name)
    
    # Prevent adding multiple handlers if called multiple times
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)

        # Create a standard format for all logs
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(module)s | %(message)s', 
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 1. File Handler (Writes to logs/app.log)
        file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=2)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG) # Log EVERYTHING to the file

        # 2. Console Handler (Prints to standard terminal)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.INFO) # Only log INFO and above to console

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger

# Create a globally accessible logger instance
app_logger = get_app_logger()