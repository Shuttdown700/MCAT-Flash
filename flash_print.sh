#!/bin/bash
export BROTHER_QL_MODEL=QL-800

# Flashing the device using esptool.py
esptool.py -p /dev/cu.usbmodem1101 --chip esp32c3 --baud 115200 --before default_reset --after hard_reset write_flash -z --flash_mode dio --flash_freq 80m --flash_size 4MB 0x0 ./sensor.bin

echo "FLASH COMPLETE"

echo "PRINTING"

# Read the MAC address from the device using esptool.py
mac_info=$(esptool.py read_mac | tr -d '\n')

# Extract the MAC address from the output
mac_address=$(echo "$mac_info" | grep -oE "([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}" | head -n 1)

# Remove colons from the MAC address and trim any leading/trailing spaces or newlines
mac_address_no_colons=$(echo "$mac_address" | tr -d ':' | sed -e 's/^[ \t]*//' -e 's/[ \t]*$//')

# Define thingName with "THE-" appended to the MAC address
thingName="THE-$mac_address_no_colons"

# Output the formatted thing name
echo "Formatted thing name: $thingName"

# Call Python script to update CSV and get existing room
room=$(python3 update_csv.py data.csv "$thingName")

# Use the existing room value in your Bash script
echo "Existing room associated with updated Thing Name: $room"

# Run Python script to generate PNG using thingName
python3 make_png.py "$thingName"

# Send thing name to printer
brother_ql -b pyusb -p usb://0x4f9:0x209b/000A3G174418 print -l 29 label.png

# Clean up: remove temporary PNG file
rm label.png

# Run Python script to generate PNG using thingName
python3 make_png.py "$room"

# Send thing name to printer
brother_ql -b pyusb -p usb://0x4f9:0x209b/000A3G174418 print -l 29 label.png

# Clean up: remove temporary PNG file
rm label.png

echo "PRINT COMPLETE"

echo "READY FOR ANOTHER"
