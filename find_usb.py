import serial.tools.list_ports

print("Scanning for connected COM ports...\n")
ports = serial.tools.list_ports.comports()

if not ports:
    print("No COM ports found. Is the sensor plugged in?")
else:
    for port in ports:
        print(f"Port: {port.device}")
        print(f"  Description: {port.description}")
        print(f"  Hardware ID: {port.hwid}")
        if port.vid and port.pid:
            print(f"  VID: {hex(port.vid)} | PID: {hex(port.pid)}")
        print("-" * 50)