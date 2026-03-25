import hashlib
import json
import os
import re
import subprocess
import sys
import time

import libusb_package
import serial.tools.list_ports
import usb.core
from brother_ql.backends.helpers import send
from brother_ql.conversion import convert
from brother_ql.raster import BrotherQLRaster

from logger import get_app_logger


# --- THE MAGIC WINDOWS USB PATCH ---
# We import usb.core at the top, but apply the monkey-patch here
libusb_backend = libusb_package.get_libusb1_backend()
original_find = usb.core.find

def patched_find(*args, **kwargs):
    kwargs['backend'] = libusb_backend
    return original_find(*args, **kwargs)

usb.core.find = patched_find


# --- Globals and Anchors ---
script_logger = get_app_logger('flash_print', 'flash_print.log')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

BIN_FILE = os.path.join(DATA_DIR, 'sensor.bin')
DB_HASH_FILE = os.path.join(DATA_DIR, 'db_binary_hash.json')
DB_MAC_FILE = os.path.join(DATA_DIR, 'db_sensor_MAC.json')

SCRIPT_DIR = os.path.dirname(__file__)
CSV_SCRIPT = os.path.join(SCRIPT_DIR, 'update_csv.py')
PNG_SCRIPT = os.path.join(SCRIPT_DIR, 'make_png.py')

PYTHON_EXE = sys.executable


def verify_binary_hash(bin_file=BIN_FILE, db_file=DB_HASH_FILE):
    """Validates the SHA256 hash of the binary against the JSON database."""
    try:
        with open(db_file, 'r') as f:
            db = json.load(f)
        
        # Extract expected hash and strip the 'SHA256:' prefix
        expected_hash_raw = db.get("sensor.bin", {}).get("v1.0.0", {}).get("hash", "")
        expected_hash = expected_hash_raw.replace("SHA256:", "").strip().lower()
        
        # Calculate actual hash
        sha256 = hashlib.sha256()
        with open(bin_file, 'rb') as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
                
        actual_hash = sha256.hexdigest().lower()
        bool_valid_hash = (expected_hash == actual_hash)
        
        if not bool_valid_hash:
            script_logger.critical(
                f"Firmware hash mismatch! Expected: {expected_hash}, "
                f"Got: {actual_hash}"
            )
        else:
            script_logger.info("Firmware hash verified successfully.")
            
        return bool_valid_hash, expected_hash, actual_hash
        
    except Exception as e:
        print(f"Hash Check Error: {e}", file=sys.stderr)
        script_logger.critical(f"Hash Check Error: {e}")
        return False, None, None


def get_esp_port(db_file=DB_MAC_FILE):
    """
    Finds the ESP port using the VID dynamically loaded from JSON 
    with fallback safety nets.
    """
    expected_vid = 0x303a  # Default safety net
    
    try:
        with open(db_file, 'r') as f:
            db = json.load(f)
            
        # Safely drill down into the JSON dictionary
        sensor_data = db.get("sensor", {}).get("v1.0.0", {})
        vid_val = sensor_data.get("idVendor", "0x303a")
        
        # Handle whether the user put it in quotes ("0x303a") or as a raw number
        if isinstance(vid_val, str):
            expected_vid = int(vid_val.strip(), 16)
        elif isinstance(vid_val, int):
            expected_vid = vid_val
            
        script_logger.debug(
            f"JSON parsed successfully. Looking for VID: {hex(expected_vid)} "
            f"(Int: {expected_vid})"
        )
        
    except Exception as e:
        script_logger.warning(
            f"Could not parse {db_file}, using default ESP32-C3 VID. Error: {e}"
        )

    # Scan the ports
    ports = serial.tools.list_ports.comports()
    script_logger.debug(f"Scanning {len(ports)} connected COM ports...")
    
    for port in ports:
        port_vid_hex = hex(port.vid) if port.vid else "None"
        script_logger.debug(
            f" - Evaluated Port: {port.device} | VID: {port_vid_hex}"
        )
        
        # Check against JSON VID, CH340 generic (0x1a86), and hardcoded safety (0x303a)
        if port.vid in [expected_vid, 0x1a86, 0x303a]: 
            script_logger.debug(f"Match found. Using port: {port.device}")
            return port.device
            
    return None


def print_to_brother(image_path, printer_id):
    """Native printing function using the dynamically detected USB ID."""
    qlr = BrotherQLRaster('QL-800')
    instructions = convert(
        qlr=qlr, 
        images=[image_path], 
        label='29', 
        rotate=0, 
        threshold=70.0, 
        dither=False, 
        compress=False, 
        red=False, 
        dpi_600=False
    )
    
    send(
        instructions=instructions, 
        printer_identifier=printer_id, 
        backend_identifier='pyusb', 
        blocking=True
    )        


def main():
    # 1. Parse Arguments
    args = sys.argv.copy()
    script_name = args.pop(0) 
    
    # Extract flags
    test_mode = '--test' in args
    if test_mode:
        args.remove('--test')

    skip_print = '--skip-print' in args
    if skip_print:
        args.remove('--skip-print')
        
    # Grab remaining arguments safely
    csv_file = str(args.pop(0)).strip() if args else "data.csv"
    target_room = str(args.pop(0)).strip() if args else "UNKNOWN_ROOM"
    printer_info = str(args.pop(0)).strip() if args else "usb://0x04f9:0x209b"

    # 2. Hardware Flashing or Test Simulation
    if test_mode:
        script_logger.info(
            "Running in TEST MODE - No actual flashing or hardware "
            "interactions will occur."
        )
        time.sleep(1)
        script_logger.info("FLASH COMPLETE (SIMULATED)")
        mac_address = "00:11:22:33:44:55"
    else:
        # Binary Hash Validation
        is_valid, exp_hash, act_hash = verify_binary_hash()
        if not is_valid:
            sys.exit(1)

        detected_port = get_esp_port()
        if not detected_port:
            script_logger.critical(
                "CRITICAL ERROR: No MCAT sensor detected matching the "
                "expected hardware ID."
            )
            sys.exit(1)
            
        script_logger.info(f"Flashing device on port {detected_port}...")
        
        flash_cmd = [
            PYTHON_EXE, '-m', 'esptool', 
            '-p', detected_port, 
            '--chip', 'esp32c3', 
            '--baud', '115200', 
            '--before', 'default_reset', 
            '--after', 'hard_reset', 
            'write_flash', '-z', 
            '--flash_mode', 'dio', 
            '--flash_freq', '80m', 
            '--flash_size', '4MB', 
            '0x0', BIN_FILE
        ]
        
        try:
            subprocess.run(flash_cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            script_logger.critical(
                f"Flashing failed!\n--- ESPTOOL STDOUT ---\n{e.stdout}\n"
                f"--- ESPTOOL STDERR ---\n{e.stderr}"
            )
            sys.exit(1)
        
        script_logger.info("Flash Complete.")
        
        mac_cmd = [PYTHON_EXE, '-m', 'esptool', '-p', detected_port, 'read_mac']
        
        try:
            result = subprocess.run(mac_cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            script_logger.critical(
                f"Could not read MAC address!\n--- ESPTOOL STDOUT ---\n"
                f"{e.stdout}\n--- ESPTOOL STDERR ---\n{e.stderr}"
            )
            sys.exit(1)
            
        match = re.search(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", result.stdout)
        mac_address = match.group(0) if match else "00:00:00:00:00:00"

    # 3. Format the Thing Name
    thing_name = f"THE-{mac_address.replace(':', '').strip()}"

    # 4. Update the CSV (or mock it for tests)
    if test_mode:
        room = target_room
    else:
        csv_cmd = [PYTHON_EXE, CSV_SCRIPT, csv_file, thing_name, target_room]
        try:
            csv_result = subprocess.run(
                csv_cmd, capture_output=True, text=True, check=True
            )
            room = csv_result.stdout.strip()
            script_logger.info(f"Room mapped: {target_room}")
        except subprocess.CalledProcessError as e:
            script_logger.critical("CRITICAL ERROR: update_csv.py crashed!")
            script_logger.critical(f"STDERR: {e.stderr}")
            sys.exit(1)

    # 5. Print the Labels
    if not skip_print:
        # Label 1
        subprocess.run([PYTHON_EXE, PNG_SCRIPT, thing_name], check=True)
        script_logger.info("Label 1 generated.")
        print_to_brother('label.png', printer_info)
        
        if os.path.exists("label.png"): 
            os.remove("label.png")

        # Label 2
        subprocess.run([PYTHON_EXE, PNG_SCRIPT, room], check=True)
        script_logger.info("Label 2 generated.")
        print_to_brother('label.png', printer_info)
        
        if os.path.exists("label.png"): 
            os.remove("label.png")
            
        script_logger.info("Label printing complete.")
    else:
        script_logger.info("Printing skipped.")


if __name__ == "__main__":
    main()