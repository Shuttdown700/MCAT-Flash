from nicegui import ui, events, app
import asyncio
import os
import subprocess
import logging
from logger import app_logger, LOG_FILE # Import our new custom logger
import sys
import usb.core
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
            self.rooms = []           # NEW: Holds all rooms for the dropdown
            self.selected_room = None # NEW: The currently targeted room
            self.status_message = "Please select or upload a CSV file to begin."
            self.status_color = "grey"
            self.is_processing = False
            self.action_prompt = ""
            self.waiting_for_unplug = False

    def get_uploaded_files(self):
        return [f for f in os.listdir(UPLOAD_DIR) if f.endswith('.csv')]

    def refresh_files(self):
        self.available_files = self.get_uploaded_files()

state = AppState()

# --- Helper Functions ---
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
        app_logger.info("Upload successful.")
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
        app_logger.error(f"Failed to read CSV: {e}")

def handle_file_change(e):
    state.selected_file = e.value
    load_rooms_from_csv()
    room_dropdown.options = state.rooms
    room_dropdown.value = state.selected_room
    room_dropdown.update()
    update_ui_state()

def update_ui_state():
    if not state.selected_file or not state.selected_room: # Added selected_room check
        state.status_message = "Please select a CSV file and Target Room."
        state.status_color = "grey"
        state.action_prompt = ""
        test_button.disable()
    elif not state.is_processing and not state.waiting_for_unplug:
        state.status_message = f"Ready to flash using {state.selected_file}."
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
                app_logger.warning("Could not read printer serial number. Using generic ID.")
            
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
    app_logger.info("=== STARTING HARDWARE FLASH PROCESS ===")
    
    # --- NEW: Pre-flight connection check ---
    if not is_sensor_connected():
        app_logger.warning("Flash aborted: MCAT Sensor disconnected immediately before flashing.")
        ui.notify('MCAT Sensor disconnected! Please plug it back in.', type='negative')
        return
    # ----------------------------------------
    
    # Capture printer info ONCE
    printer_info = is_printer_connected()
    
    if not printer_info:
        app_logger.warning("Brother QL-800 printer not detected.")
        state.status_message = "Printer Not Found"
        state.status_color = "negative"
        state.action_prompt = "PLEASE PLUG IN AND TURN ON THE LABEL MAKER ()"
        ui.notify('Brother QL-800 not detected via USB.', type='warning')
        update_ui_state()
        state.waiting_for_unplug = True 
        return

    state.is_processing = True
    file_dropdown.disable()
    delete_button.disable()
    test_button.disable()

    try:
        state.status_message = "Flashing and Printing in progress..."
        state.status_color = "warning"
        state.action_prompt = "DO NOT UNPLUG THE SENSOR"
        update_ui_state()
        
        target_csv_path = os.path.join(UPLOAD_DIR, state.selected_file)
        
        process = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, 'flash_print.py', str(target_csv_path), str(state.selected_room), str(printer_info)],
            capture_output=True,
            text=True,
            check=True 
        )

        # --- FIX: Check both stdout and stderr since the logger uses stderr ---

        # ----------------------------------------------------------------------

        # Refresh the room list to advance the dropdown
        load_rooms_from_csv()
        room_dropdown.value = state.selected_room
        room_dropdown.update()

        state.status_message = "Success! MCAT Sensor flashed and labels printed."
        state.status_color = "positive"
        state.action_prompt = "YOU MAY NOW UNPLUG THE MCAT SENSOR"
        state.waiting_for_unplug = True
        update_ui_state()
        app_logger.info("Hardware flash process completed successfully.")
        
    except subprocess.CalledProcessError as e:
        app_logger.error(f"Flashing script failed.")
        
        # --- NEW: Mid-flash disconnection handling ---
        if not is_sensor_connected():
            app_logger.error(f"MCAT Sensor was likely unplugged during flashing!")
            state.status_message = "MCAT Sensor Unplugged During Flash!"
            ui.notify('Do not unplug the MCAT Sensor until "Success" is shown.', type='negative')
        else:
            state.status_message = "Flashing Failed. Check logs."
            ui.notify('Script error.', type='negative')
        # ---------------------------------------------
            
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
    app_logger.info("=== STARTING SYSTEM TEST MODE ===")
    
    # Capture printer info ONCE
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

        process = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, 'flash_print.py', '--test', str(target_csv_path), str(state.selected_room), str(printer_info)],
            capture_output=True,
            text=True,
            check=True 
        )
        
        app_logger.info(f"Script Output:\n{process.stdout}")

        state.status_message = "Test Complete! Labels should be printing."
        state.status_color = "positive"
        state.action_prompt = "READY FOR HARDWARE"
        update_ui_state()
        app_logger.info("System test completed successfully.")
        
        await asyncio.sleep(4)
        
    except subprocess.CalledProcessError as e:
        app_logger.error(f"Test script failed with exit code {e.returncode}")
        app_logger.error(f"Script STDERR:\n{e.stderr}")
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
            app_logger.debug("MCAT sensor unplugged. Resetting state.")
            state.waiting_for_unplug = False
            update_ui_state()
    elif connected and not state.waiting_for_unplug:
        app_logger.info("New MCAT sensor detected!")
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
                        on_change=lambda e: (setattr(state, 'selected_room', e.value), update_ui_state())
                    ).classes('w-full')
                    
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