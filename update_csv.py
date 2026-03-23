import sys
import csv
import os

def main():
    # --- BRACKET-FREE ARGUMENT PARSING ---
    args = sys.argv.copy()
    
    if len(args) < 3:
        print("ERROR_MISSING_ARGS")
        sys.exit(1)

    script_name = args.pop(0)
    csv_path = str(args.pop(0)).strip()
    thing_name = str(args.pop(0)).strip()

    if not os.path.exists(csv_path):
        print("ERROR_FILE_NOT_FOUND")
        sys.exit(1)

    rows = []
    assigned_room = "UNKNOWN_ROOM"
    updated = False

    with open(csv_path, mode='r', newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        
        for row in reader:
            if not row:
                rows.append(row)
                continue
            
            # --- BRACKET-FREE ROW PARSING ---
            if not updated:
                temp_row = row.copy()
                room_name = temp_row.pop(0) # Grab the first column
                
                sensor_name = ""
                if len(temp_row) > 0:
                    sensor_name = temp_row.pop(0) # Grab the second column if it exists
                    
                if sensor_name.strip() == "":
                    # Found an empty slot! Rebuild the row.
                    row.clear()
                    row.append(room_name)
                    row.append(thing_name)
                    assigned_room = room_name.strip()
                    updated = True
            
            rows.append(row)

    if updated:
        with open(csv_path, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(rows)
            
        print(assigned_room)
    else:
        print("NO_EMPTY_SLOTS")

if __name__ == "__main__":
    main()