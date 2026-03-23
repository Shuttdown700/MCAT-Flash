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

def print_to_brother(image_path):
    """Native printing function forcing the safe generic USB ID."""
    # We strictly use the generic ID. NO serial numbers allowed.
    safe_printer_id = "usb://0x04f9:0x209b" 
    
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
    send(instructions=instructions, printer_identifier=safe_printer_id, backend_identifier='pyusb', blocking=True)

def main():
    # 1. Parse Arguments
    args = sys.argv.copy()
    script_name = args.pop(0) 
    
    csv_file = "data.csv"
    if len(args) > 0:
        csv_file = str(args.pop(0)).strip() 
        
    test_mode = '--test' in sys.argv

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
        subprocess.run(flash_cmd, check=True)
        
        print("FLASH COMPLETE")
        
        mac_cmd = [PYTHON_EXE, '-m', 'esptool', '-p', detected_port, 'read_mac']
        result = subprocess.run(mac_cmd, capture_output=True, text=True, check=True)
        match = re.search(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", result.stdout)
        mac_address = match.group(0) if match else "00:00:00:00:00:00"

    # 3. Format the Thing Name
    thing_name = f"THE-{mac_address.replace(':', '').strip()}"
    print(f"Provisioning: {thing_name}")

    # 4. Update the CSV
    csv_cmd = [PYTHON_EXE, 'update_csv.py', csv_file, thing_name]
    try:
        csv_result = subprocess.run(csv_cmd, capture_output=True, text=True, check=True)
        room = csv_result.stdout.strip()
        print(f"Room mapped: {room}")
    except subprocess.CalledProcessError as e:
        print("\nCRITICAL ERROR: update_csv.py crashed!")
        print(f"STDERR: {e.stderr}")
        sys.exit(1)

    # 5. Print the Labels
    # Label 1
    subprocess.run([PYTHON_EXE, 'make_png.py', thing_name], check=True)
    print_to_brother('label.png')
    if os.path.exists("label.png"): os.remove("label.png")

    # Label 2
    subprocess.run([PYTHON_EXE, 'make_png.py', room], check=True)
    print_to_brother('label.png')
    if os.path.exists("label.png"): os.remove("label.png")

    print("PRINT COMPLETE")

if __name__ == "__main__":
    main()