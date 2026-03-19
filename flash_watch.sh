#!/bin/bash

# Flag to track if action has been triggered
action_triggered=false

# Function to trigger action when device is plugged in
trigger_action() {
    # Run your script here
    ./flash_print.sh
    # Set the flag to true to indicate action has been triggered
    action_triggered=true
}
echo "PLUG IN SENSOR TO GET STARTED"
# Monitor the port for device events
while true; do
    # Check if the device is connected
    if [ -e "/dev/cu.usbmodem1101" ]; then
        # Trigger action only if it hasn't been triggered before
        if [ "$action_triggered" = false ]; then
            trigger_action
        fi
    else
        # Reset the flag when device is removed
        action_triggered=false
    fi
    # Adjust sleep duration based on your needs
    sleep 1
done
