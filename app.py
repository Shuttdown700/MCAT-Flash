from concurrent.futures import process

from nicegui import ui, events, app
import asyncio
import os
import subprocess
import logging
from logger import app_logger, LOG_FILE # Import our new custom logger
import sys
import usb.core
import re
import serial.tools.list_ports
import libusb_package
import csv

# --- Configuration ---
UPLOAD_DIR = 'csv_data'
os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- State Management ---
class AppState:
    def __init__(self):
        self.available_files = self.get_uploaded_files()
        self.selected_file = None
        self.rooms = []           
        self.selected_room = None 
        self.status_message = "Please select or upload a CSV file to begin."
        self.status_color = "grey"
        self.is_processing = False
        self.action_prompt = ""
        self.waiting_for_unplug = False
        self.skip_printing = False # NEW: Track skip printing state

    def get_uploaded_files(self):
        return [f for f in os.listdir(UPLOAD_DIR) if f.endswith('.csv')]

    def refresh_files(self):
        self.available_files = self.get_uploaded_files()

state = AppState()

# --- Helper Functions ---
def scan_csv_directory_for_conflicts(target_room=None, target_sensor=None):
    """Scans all CSVs in the UPLOAD_DIR for room or sensor assignments."""
    for filename in os.listdir(UPLOAD_DIR):
        if not filename.endswith('.csv'): continue
        filepath = os.path.join(UPLOAD_DIR, filename)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) < 2: continue
                    room, sensor = row[0].strip(), row[1].strip()
                    
                    if target_room and room == target_room and sensor:
                        return True, sensor, filename
                    
                    if target_sensor and sensor == target_sensor:
                        return True, room, filename
        except Exception as e:
            app_logger.warning(f"Failed to read {filename} during conflict scan: {e}")
            
    return False, None, None

def precheck_sensor_mac():
    """Quickly grabs the MAC address before the heavy flashing process begins."""
    try:
        ports = serial.tools.list_ports.comports()
        detected_port = next((p.device for p in ports if p.vid in [0x303a, 0x1a86]), None)
        if not detected_port: return None
        
        cmd = [sys.executable, '-m', 'esptool', '-p', detected_port, 'read_mac']
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        match = re.search(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", result.stdout)
        if match:
            mac = match.group(0)
            return f"THE-{mac.replace(':', '').strip()}"
    except Exception as e:
        app_logger.warning(f"MAC precheck failed: {e}")
    return None

async def handle_skip_print_change(e):
    if e.value:
        # User checked the box, prompt for confirmation
        with ui.dialog() as dialog, ui.card():
            ui.label('Are you sure you want to skip printing labels?').classes('text-lg font-bold')
            ui.label('You will need to manually identify this sensor.').classes('text-gray-600 mb-4')
            with ui.row().classes('w-full justify-end mt-4'):
                ui.button('Cancel', color='grey', on_click=lambda: dialog.submit(False))
                ui.button('Yes, Skip', color='negative', on_click=lambda: dialog.submit(True))
        
        result = await dialog
        if result:
            state.skip_printing = True
            app_logger.info("User opted to SKIP label printing.")
        else:
            e.sender.value = False # Revert UI checkbox
            state.skip_printing = False
    else:
        state.skip_printing = False
        app_logger.info("User opted to RESUME label printing.")

async def handle_upload(e: events.UploadEventArguments):
    app_logger.info(f"Uploading new file: {e.file.name}")
    file_path = os.path.join(UPLOAD_DIR, e.file.name)
    
    try:
        with open(file_path, 'wb') as f:
            f.write(await e.file.read())
            
        state.refresh_files()
        ui.notify(f'Uploaded {e.file.name}', type='positive')
        
        file_dropdown.options = state.available_files 
        file_dropdown.update()
        app_logger.info(f"Successfully uploaded {e.file.name}.")
    except Exception as e:
        app_logger.exception(f"Failed to upload file {e.file.name}")
        ui.notify('Upload failed. Check logs.', type='negative')

def delete_selected_file():
    if state.selected_file:
        app_logger.info(f"Deleting file: {state.selected_file}")
        try:
            os.remove(os.path.join(UPLOAD_DIR, state.selected_file))
            ui.notify(f'Deleted {state.selected_file}', type='warning')
            state.selected_file = None
            state.refresh_files()
            
            file_dropdown.options = state.available_files 
            file_dropdown.update()
            update_ui_state()
        except Exception as e:
            app_logger.exception(f"Error deleting file {state.selected_file}")

def load_rooms_from_csv():
    if not state.selected_file:
        state.rooms = []
        state.selected_room = None
        return

    filepath = os.path.join(UPLOAD_DIR, state.selected_file)
    rooms = []
    next_available = None
    all_full = True

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row: continue
                
                room_name = row[0].strip()
                rooms.append(room_name)
                
                # Check if the second column (MCAT ID) is empty or missing
                if all_full and (len(row) < 2 or not row[1].strip()):
                    next_available = room_name
                    all_full = False
        
        state.rooms = rooms
        if all_full and rooms:
            ui.notify(f'All rooms in {state.selected_file} are assigned!', type='warning')
            
            state.selected_room = rooms 
        else:
            state.selected_room = next_available
            
    except Exception as e:
        app_logger.error(f"Failed to read CSV file {state.selected_file}: {e}")

def handle_file_change(e):
    state.selected_file = e.value
    load_rooms_from_csv()
    room_dropdown.options = state.rooms
    room_dropdown.value = state.selected_room
    room_dropdown.update()
    update_ui_state()
    app_logger.info(f"Selected file changed to: {state.selected_file}")

def handle_room_change(e):
    state.selected_room = e.value
    update_ui_state()
    
    # NEW: Trigger amber warning if the selected room is already assigned
    if e.value:
        is_assigned, assigned_sensor, filename = scan_csv_directory_for_conflicts(target_room=e.value)
        if is_assigned:
            ui.notify(
                f"Warning: {e.value} is already assigned to {assigned_sensor} in {filename}", 
                type='warning', # Automatically applies amber/orange styling
                icon='warning',
                timeout=6000,
                position='top'
            )

def update_ui_state():
    if not state.selected_file or not state.selected_room: # Added selected_room check
        state.status_message = "Please select a CSV file and Target Room."
        state.status_color = "grey"
        state.action_prompt = ""
        test_button.disable()
    elif not state.is_processing and not state.waiting_for_unplug:
        state.status_message = f"Ready to flash using {state.selected_file} and Room: {state.selected_room}"
        state.status_color = "blue"
        state.action_prompt = "PLUG IN MCAT SENSOR WHILE HOLDING THE BOOT BUTTON TO GET STARTED"
        test_button.enable()
    
    status_label.set_text(state.status_message)
    status_card.classes(replace=f'bg-{state.status_color}-100')
    action_label.set_text(state.action_prompt)

def is_sensor_connected():
    """Checks if the ESP32-C3 sensor is plugged in via a serial COM port."""
    try:
        ports = serial.tools.list_ports.comports()
        for port in ports:
            # Matches standard ESP32-C3 VID/PID
            if port.vid == 0x303a and port.pid == 0x1001:
                return True
        return False
    except Exception as e:
        app_logger.warning(f"Serial port scan error: {e}")
        return False

def is_printer_connected():
    """Dynamically finds the Brother QL-800 with extra Windows diagnostics."""
    try:
        # Use the libusb-package backend to ensure Python finds the DLL on Windows
        backend = libusb_package.get_libusb1_backend()
        
        # Search for Brother QL-800 (VID: 0x04f9, PID: 0x209b)
        printer = usb.core.find(idVendor=0x04f9, idProduct=0x209b, backend=backend)
        
        if printer is None:
            # Diagnostic: See if ANY Brother devices are on the bus
            all_brother = list(usb.core.find(find_all=True, idVendor=0x04f9, backend=backend))
            if all_brother:
                app_logger.info(f"Found {len(all_brother)} Brother device(s), but none match PID 0x209b.")
            return None
        
        try:
            # Fallback to generic ID if serial string is blocked by Windows
            serial = "UNKNOWN"
            try:
                serial = printer.serial_number
            except Exception:
                app_logger.warning(f"Could not read printer serial number {printer.serial_number}. Using generic ID.")
            
            printer_id = f"usb://0x04f9:0x209b/{serial}"
            app_logger.info(f"Printer verified via WinUSB at {printer_id}")
            return printer_id

        except usb.core.USBError as e:
            app_logger.error(f"Printer found but WinUSB access denied: {e}")
            return None
            
    except Exception as e:
        app_logger.warning(f"USB Discovery Error: {e}")
        return None

async def trigger_flash_process():
    app_logger.info(f"Starting flash process for MCAT sensor: {precheck_sensor_mac()}, Room: {state.selected_room}, File: {state.selected_file}")
    
    if not is_sensor_connected():
        app_logger.warning("Flash aborted: MCAT Sensor disconnected immediately before flashing.")
        ui.notify('MCAT Sensor disconnected! Please plug it back in.', type='negative')
        return

    # --- NEW: Pre-flight Room Conflict Check ---
    is_assigned, assigned_sensor, filename = scan_csv_directory_for_conflicts(target_room=state.selected_room)
    if is_assigned:
        with ui.dialog() as dialog, ui.card().classes('items-center p-6'):
            ui.icon('warning', color='warning').classes('text-5xl mb-2')
            ui.label(f'Target Room Conflict').classes('text-xl font-bold text-orange-500 mb-2')
            ui.label(f'{state.selected_room} is already assigned to {assigned_sensor} in {filename}.')
            ui.label('Do you want to override this and flash anyway?').classes('text-gray-600 mb-4')
            with ui.row().classes('w-full justify-end mt-2'):
                ui.button('Cancel', color='grey', on_click=lambda: dialog.submit(False))
                ui.button('Override', color='negative', on_click=lambda: dialog.submit(True))
        
        if not await dialog:
            app_logger.info("User canceled flash due to room conflict.")
            state.waiting_for_unplug = True
            return

    # --- NEW: Pre-flight Sensor MAC Conflict Check ---
    ui.notify('Checking sensor hardware ID...', type='info', timeout=2000)
    thing_name = await asyncio.to_thread(precheck_sensor_mac)
    
    if thing_name:
        is_assigned, assigned_room, filename = scan_csv_directory_for_conflicts(target_sensor=thing_name)
        if is_assigned:
            with ui.dialog() as dialog, ui.card().classes('items-center p-6'):
                ui.icon('swap_horiz', color='warning').classes('text-5xl mb-2')
                ui.label('Sensor Already Provisioned!').classes('text-xl font-bold text-orange-500 mb-2')
                ui.label(f'This sensor ({thing_name}) is already assigned to {assigned_room} in {filename}.')
                ui.label(f'Continue flashing {thing_name} to {state.selected_room}?').classes('text-gray-600 mb-4')
                with ui.row().classes('w-full justify-end mt-2'):
                    ui.button('Cancel', color='grey', on_click=lambda: dialog.submit(False))
                    ui.button('Continue', color='negative', on_click=lambda: dialog.submit(True))
            
            if not await dialog:
                app_logger.info("User canceled flash due to sensor conflict.")
                state.waiting_for_unplug = True
                return
    # ----------------------------------------------
    
    # Capture printer info ONCE (Bypass if skipping print)
    if state.skip_printing:
        printer_info = "SKIPPED"
    else:
        printer_info = is_printer_connected()
    
    if not printer_info:
        app_logger.warning("Brother QL-800 printer not detected.")
        state.status_message = "Printer Not Found"
        state.status_color = "negative"
        state.action_prompt = "PLEASE PLUG IN AND TURN ON THE LABEL MAKER"
        ui.notify('Brother QL-800 not detected via USB.', type='warning')
        update_ui_state()
        state.waiting_for_unplug = True 
        return

    state.is_processing = True
    file_dropdown.disable()
    delete_button.disable()
    test_button.disable()

    try:
        if not state.skip_printing:
            state.status_message = "Flashing and Printing in progress..."
        else:
            state.status_message = "Flashing in progress..."
        state.status_color = "warning"
        state.action_prompt = "DO NOT UNPLUG THE SENSOR"
        update_ui_state()
        
        target_csv_path = os.path.join(UPLOAD_DIR, state.selected_file)
        
        cmd = [sys.executable, 'flash_print.py']
        if state.skip_printing:
            cmd.append('--skip-print')
        cmd.extend([str(target_csv_path), str(state.selected_room), str(printer_info)])

        process = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            check=True 
        )

        app_logger.info(f"Script (flash_print.py) Output:\n{process.stdout}")
        load_rooms_from_csv()
        room_dropdown.value = state.selected_room
        room_dropdown.update()

        state.status_message = "Success! MCAT Sensor flashed."
        state.status_color = "positive"
        state.action_prompt = "YOU MAY NOW UNPLUG THE MCAT SENSOR"
        state.waiting_for_unplug = True
        update_ui_state()
        app_logger.info(f"Successfully flashed MCAT sensor: {precheck_sensor_mac()} to Room: {state.selected_room}")
        
        # NEW: Satisfying Green Popup
        ui.notify(
            f'SUCCESS: Provisioned {state.selected_room}', 
            type='positive', 
            position='center', 
            icon='check_circle',
            classes='text-2xl p-4 font-bold border-2 border-green-700 shadow-xl',
            timeout=8000,
            close_button=True
        )
        
    except subprocess.CalledProcessError as e:
        app_logger.error("Flashing script failed.")
        
        if not is_sensor_connected():
            app_logger.error(f"MCAT Sensor {precheck_sensor_mac()} was likely unplugged during flashing!")
            state.status_message = "MCAT Sensor Unplugged During Flash!"
            ui.notify('Do not unplug the MCAT Sensor until "Success" is shown.', type='negative')
        else:
            state.status_message = "Flashing Failed. Check logs."
            ui.notify('Script error.', type='negative')
            
        state.status_color = "negative"
        state.action_prompt = "PLEASE UNPLUG MCAT SENSOR AND TRY AGAIN"
        state.waiting_for_unplug = True
        update_ui_state()
        
    except Exception as e:
        app_logger.exception("AN UNEXPECTED SYSTEM ERROR OCCURRED DURING FLASHING")
        state.status_message = "System Error."
        state.status_color = "negative"
        state.action_prompt = "PLEASE UNPLUG MCAT SENSOR AND TRY AGAIN"
        state.waiting_for_unplug = True
        ui.notify('Unexpected error. Check logs tab.', type='negative')
        update_ui_state()
    
    finally:
        state.is_processing = False
        file_dropdown.enable()
        delete_button.enable()


async def trigger_test_process():
    app_logger.info(f"Starting system test process with simulated data for file: {state.selected_file}")
    
    if state.skip_printing:
        printer_info = "SKIPPED"
    else:
        printer_info = is_printer_connected()
    
    if not printer_info:
        app_logger.warning("Brother QL-800 printer not detected.")
        state.status_message = "Printer Not Found"
        state.status_color = "negative"
        state.action_prompt = "PLEASE PLUG IN AND TURN ON THE LABEL MAKER"
        ui.notify('Brother QL-800 not detected via USB.', type='warning')
        update_ui_state()
        return

    state.is_processing = True
    file_dropdown.disable()
    delete_button.disable()
    test_button.disable()

    try:
        state.status_message = "Running System Test..."
        state.status_color = "info"
        state.action_prompt = "TESTING CSV LOGIC AND PRINTER"
        update_ui_state()
        
        target_csv_path = os.path.join(UPLOAD_DIR, state.selected_file)

        # Build the command dynamically
        cmd = [sys.executable, 'flash_print.py']
        if state.skip_printing:
            cmd.append('--skip-print')
        # Add --test for trigger_test_process ONLY
        cmd.append('--test') 
        cmd.extend([str(target_csv_path), str(state.selected_room), str(printer_info)])

        process = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            check=True 
        )
        
        app_logger.info(f"Script (flash_print.py) Output:\n{process.stdout}")
        if not state.skip_printing:
            state.status_message = "Test Complete! Labels should be printing."
        else:
            state.status_message = "Test Complete! (Printing Skipped)"
        state.status_color = "positive"
        state.action_prompt = "READY FOR HARDWARE"
        update_ui_state()
        app_logger.info("System test completed successfully.")
        
        await asyncio.sleep(4)
        
    except subprocess.CalledProcessError as e:
        app_logger.error(f"Test script failed with exit code {e.returncode}")
        app_logger.error(f"Script (flash_print.py) STDERR:\n{e.stderr}")
        state.status_message = "Test Failed. Check logs."
        state.status_color = "negative"
        ui.notify('Script error.', type='negative')
        
    except Exception as e:
        app_logger.exception("AN UNEXPECTED SYSTEM ERROR OCCURRED DURING TESTING")
        state.status_message = "System Error."
        state.status_color = "negative"
        ui.notify('Unexpected error. Check logs tab.', type='negative')
    
    finally:
        state.is_processing = False
        file_dropdown.enable()
        delete_button.enable()
        update_ui_state()

async def sensor_watch_loop():
    if not state.selected_file or state.is_processing:
        return 

    connected = is_sensor_connected()

    if state.waiting_for_unplug:
        if not connected:
            app_logger.debug(f"MCAT sensor {precheck_sensor_mac()} unplugged. Resetting state.")
            state.waiting_for_unplug = False
            update_ui_state()
    elif connected and not state.waiting_for_unplug:
        app_logger.info(f"New MCAT sensor {precheck_sensor_mac()} detected!")
        await trigger_flash_process()

# --- UI Layout ---
ui.colors(primary='#2b5cff', secondary='#26da97', accent='#ff5e5e')

with ui.header().classes('items-center justify-between bg-primary text-white shadow-md'):
    ui.label('MCAT Sensor Flashing & Provisioning Tool').classes('text-2xl font-bold p-4')
    
    with ui.tabs() as tabs:
        ui.tab('Flasher', icon='bolt')
        ui.tab('System Logs', icon='list_alt')

with ui.tab_panels(tabs, value='Flasher').classes('w-full bg-transparent'):
    
    with ui.tab_panel('Flasher').classes('p-0'):
        with ui.row().classes('w-full p-6 gap-8'):
            
            with ui.column().classes('w-1/3 min-w-[300px]'):
                ui.label('1. Data Source').classes('text-xl font-bold text-gray-700')
                
                with ui.card().classes('w-full shadow-sm border border-gray-200'):
                    ui.label('Upload New CSV').classes('font-semibold text-gray-600')
                    ui.upload(on_upload=handle_upload, auto_upload=True).classes('w-full')
                    
                    ui.separator().classes('my-4')
                    
                    ui.label('Select Active CSV').classes('font-semibold text-gray-600')
                    file_dropdown = ui.select(
                        options=state.available_files, 
                        value=state.selected_file,
                        on_change=handle_file_change # Point to the new handler
                    ).classes('w-full')
                    
                    ui.separator().classes('my-4')
                    
                    ui.label('Select Target Room').classes('font-semibold text-gray-600')
                    room_dropdown = ui.select(
                        options=state.rooms,
                        value=state.selected_room,
                        on_change=handle_room_change # Point to the new handler here
                    ).classes('w-full')
                    
                    ui.separator().classes('my-4')
                    
                    # NEW: Skip Printing Checkbox
                    ui.checkbox('Skip Label Printing', value=state.skip_printing, on_change=handle_skip_print_change).classes('font-bold text-accent w-full')

                    ui.separator().classes('my-4')
                    
                    delete_button = ui.button('Delete Selected File', color='negative', icon='delete', on_click=delete_selected_file).classes('w-full mt-2')

            with ui.column().classes('w-2/3 min-w-[400px] flex-grow items-center'):
                ui.label('2. Flashing Process').classes('text-xl font-bold text-gray-700 w-full text-left')
                
                status_card = ui.card().classes('w-full items-center justify-center p-12 transition-colors duration-300 bg-grey-100')
                with status_card:
                    status_label = ui.label(state.status_message).classes('text-3xl font-bold text-center text-gray-800')
                    action_label = ui.label(state.action_prompt).classes('text-xl font-bold text-center mt-4 text-gray-600 animate-pulse')

                test_button = ui.button(
                    'Run System Test', 
                    icon='science', 
                    on_click=trigger_test_process
                ).classes('mt-6 px-6 py-2').props('outline')
                test_button.disable()

    with ui.tab_panel('System Logs').classes('w-full'):
        ui.label('Live Application Logs').classes('text-xl font-bold text-gray-700 mb-4')
        
        gui_log = ui.log(max_lines=1000).classes('w-full h-[600px] bg-[#1e1e1e] text-[#d4d4d4] font-mono p-4 rounded-md overflow-y-auto whitespace-pre-wrap')
        
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r') as f:
                for line in f.readlines()[-100:]:
                    gui_log.push(line.strip())

        class NiceGuiLogHandler(logging.Handler):
            def emit(self, record):
                try:
                    if gui_log.client.id in app.clients:
                        msg = self.format(record)
                        gui_log.push(msg)
                except Exception:
                    pass

        app_logger.handlers = [h for h in app_logger.handlers if not isinstance(h, NiceGuiLogHandler)]

        ui_handler = NiceGuiLogHandler()
        ui_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s', datefmt='%H:%M:%S'))
        ui_handler.setLevel(logging.INFO)
        app_logger.addHandler(ui_handler)
        ui.context.client.on_disconnect(lambda: app_logger.removeHandler(ui_handler))

update_ui_state()
ui.timer(1.0, sensor_watch_loop)
ui.timer(0.1, lambda: app_logger.info("=== NICEGUI APPLICATION STARTED ==="), once=True)

ui.run(title="MCAT Sensor Flasher", port=8080, reload=False)