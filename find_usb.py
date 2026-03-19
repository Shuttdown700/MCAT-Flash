import usb.core

# Find all USB devices
devices = usb.core.find(find_all=True)

# Print information about each device
for device in devices:
    print("Device:", device)
    print("  Manufacturer:", usb.util.get_string(device, device.iManufacturer))
    print("  Product:", usb.util.get_string(device, device.iProduct))
    print("  Serial Number:", usb.util.get_string(device, device.iSerialNumber))
    print("  Identifier:", f"usb://{hex(device.idVendor)}:{hex(device.idProduct)}/{device.serial_number}")
    print()