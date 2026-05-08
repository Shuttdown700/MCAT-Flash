#!/bin/bash
# setup_linux.sh - Automated Linux/Raspberry Pi setup for MCAT Sensor Flashing Tool

echo "=== MCAT Sensor Flasher: Linux Setup Script ==="

# 1. Update system and install required USB libraries
echo ">>> [1/4] Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y libusb-1.0-0-dev libudev-dev python3-pip python3-venv

# 2. Create a virtual environment and install Python packages
echo ">>> [2/4] Setting up Python environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "Created new virtual environment 'venv'."
fi

# Activate venv and install packages
source venv/bin/activate
pip install --upgrade pip
pip install pyusb brother_ql nicegui esptool Pillow libusb-package pyserial
echo "Python dependencies installed successfully."

# 3. Create and apply udev rules for the printer and sensors
echo ">>> [3/4] Configuring USB permissions (udev rules)..."
RULES_FILE="/etc/udev/rules.d/99-mcat-hardware.rules"

sudo bash -c "cat > $RULES_FILE" <<EOF
# Brother QL-800 Printer
SUBSYSTEM=="usb", ATTR{idVendor}=="04f9", ATTR{idProduct}=="209b", MODE="0666", GROUP="plugdev"

# ESP32-C3 Sensor (Standard)
SUBSYSTEM=="usb", ATTR{idVendor}=="303a", ATTR{idProduct}=="1001", MODE="0666", GROUP="plugdev"

# ESP32-C3 (CH340 Serial Chip Fallback)
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", MODE="0666", GROUP="plugdev"
EOF

sudo udevadm control --reload-rules
sudo udevadm trigger
echo "udev rules applied."

# 4. Add the current user to hardware access groups
echo ">>> [4/4] Adding $USER to hardware access groups..."
sudo usermod -a -G plugdev $USER
sudo usermod -a -G dialout $USER

echo "==================================================="
echo "=== Setup Complete!                             ==="
echo "==================================================="
echo "IMPORTANT NEXT STEPS:"
echo "1. Reboot your Raspberry Pi for the group changes to take effect: sudo reboot"
echo "2. To run your app in the future, always activate the virtual environment first:"
echo "   source venv/bin/activate"
echo "   python src/app.py"