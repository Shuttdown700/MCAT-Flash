import logging
import os
from logging.handlers import RotatingFileHandler

# Find the project root (one folder up from /src)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)


def get_app_logger(name='SensorFlasher', filename=None):
    """Creates or retrieves a configured logger instance."""
    logger = logging.getLogger(name)
    
    if not filename:
        filename = f"{name}.log"
        
    log_filepath = os.path.join(LOG_DIR, filename)
    
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(module)s | %(message)s', 
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 1. File Handler (Writes to logs/[name].log)
        file_handler = RotatingFileHandler(
            log_filepath, 
            maxBytes=5 * 1024 * 1024,  # 5 MB limit
            backupCount=2
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG) 

        # 2. Console Handler (Prints to standard terminal)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.INFO) 

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger


# Keep a globally accessible main app instance for app.py backward compatibility
app_logger = get_app_logger('app', 'app.log')