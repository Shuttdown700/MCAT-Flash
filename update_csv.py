#!/usr/bin/env python3
import csv
import sys

def update_csv(input_file, newThingName):
    existing_room = None
    updated = False

    with open(input_file, 'r', newline='') as csvfile:
        reader = csv.reader(csvfile)
        updated_rows = []
        
        for row in reader:
            if not updated and len(row) >= 2 and row[1] == "":
                row[1] = newThingName
                existing_room = row[0]  # Capture the room name associated with this thingName
                updated = True  # Mark that we've updated the first empty cell
            
            updated_rows.append(row)

    if updated:
        with open(input_file, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(updated_rows)

    return existing_room

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python update_csv.py <input_file> <new_thing_name>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    newThingName = sys.argv[2]

    room_name = update_csv(input_file, newThingName)
    print(room_name)
