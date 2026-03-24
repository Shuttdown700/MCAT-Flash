import sys
import os
import time
import subprocess
import re
import serial.tools.list_ports

# --- THE MAGIC WINDOWS USB PATCH ---
import usb.core
import libusb_package

libusb_backend = libusb_package.get_libusb1_backend()
original_find = usb.core.find

def patched_find(*args, **kwargs):
    kwargs['backend'] = libusb_backend
    return original_find(*args, **kwargs)
    
usb.core.find = patched_find

# Import brother_ql natively
from brother_ql.conversion import convert
from brother_ql.backends.helpers import send
from brother_ql.raster import BrotherQLRaster

PYTHON_EXE = sys.executable

def get_esp_port():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if port.vid in [0x303a, 0x1a86]:
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
    
    # Use the printer_id passed into the function instead of a hardcoded string
    send(instructions=instructions, printer_identifier=printer_id, backend_identifier='pyusb', blocking=True)
        

def main():
    # 1. Parse Arguments
    args = sys.argv.copy()
    script_name = args.pop(0) 
    
    # Extract test mode and remove it from args if present
    test_mode = '--test' in args
    if test_mode:
        args.remove('--test')

    # NEW: Extract skip print mode
    skip_print = '--skip-print' in args
    if skip_print:
        args.remove('--skip-print')
        
    # Grab remaining arguments safely
    csv_file = str(args.pop(0)).strip() if args else "data.csv"
    target_room = str(args.pop(0)).strip() if args else "UNKNOWN_ROOM"
    printer_info = str(args.pop(0)).strip() if args else "usb://0x04f9:0x209b"

    # 2. Hardware Flashing or Test Simulation
    if test_mode:
        print("=== SYSTEM TEST MODE ACTIVE ===")
        time.sleep(1)
        print("FLASH COMPLETE (SIMULATED)")
        mac_address = "00:11:22:33:44:55"
    else:
        detected_port = get_esp_port()
        if not detected_port:
            print("CRITICAL ERROR: No ESP32-C3 sensor detected.")
            sys.exit(1)
            
        print(f"Flashing device on port {detected_port}...")
        flash_cmd = [PYTHON_EXE, '-m', 'esptool', '-p', detected_port, '--chip', 'esp32c3', 'write-flash', '-z', '0x0', './sensor.bin']
        
        # --- NEW: Graceful error handling for the flashing process ---
        try:
            # Added capture_output=True to swallow the raw esptool traceback
            subprocess.run(flash_cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            print("\nCRITICAL ERROR: Flashing failed! The sensor may have been unplugged.", file=sys.stderr)
            sys.exit(1)
        # -------------------------------------------------------------
        
        print("FLASH COMPLETE")
        
        mac_cmd = [PYTHON_EXE, '-m', 'esptool', '-p', detected_port, 'read_mac']
        
        # --- NEW: Graceful error handling for MAC reading ---
        try:
            # Added capture_output=True to swallow the raw esptool traceback
            result = subprocess.run(mac_cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            print("\nCRITICAL ERROR: Could not read MAC address! The sensor may have been unplugged.", file=sys.stderr)
            sys.exit(1)
        # ----------------------------------------------------
            
        match = re.search(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", result.stdout)
        mac_address = match.group(0) if match else "00:00:00:00:00:00"

    # 3. Format the Thing Name
    thing_name = f"THE-{mac_address.replace(':', '').strip()}"
    print(f"Provisioning: {thing_name}")

    # 4. Update the CSV (or mock it for tests)
    if test_mode:
        room = target_room
        print(f"Room mapped: {room} (SIMULATED)")
    else:
        # Pass the target_room to the csv updater
        csv_cmd = [PYTHON_EXE, 'update_csv.py', csv_file, thing_name, target_room]
        try:
            csv_result = subprocess.run(csv_cmd, capture_output=True, text=True, check=True)
            room = csv_result.stdout.strip()
            print(f"Room mapped: {room}")
        except subprocess.CalledProcessError as e:
            print("\nCRITICAL ERROR: update_csv.py crashed!")
            print(f"STDERR: {e.stderr}")
            sys.exit(1)

    # 5. Print the Labels
    if not skip_print:
        # Label 1
        subprocess.run([PYTHON_EXE, 'make_png.py', thing_name], check=True)
        print_to_brother('label.png', printer_info)
        if os.path.exists("label.png"): os.remove("label.png")

        # Label 2
        subprocess.run([PYTHON_EXE, 'make_png.py', room], check=True)
        print_to_brother('label.png', printer_info)
        if os.path.exists("label.png"): os.remove("label.png")

        print("PRINT COMPLETE")
    else:
        print("PRINTING SKIPPED")

    print("PRINT COMPLETE")

if __name__ == "__main__":
    main()