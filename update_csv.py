import sys
import csv
import os

def main():
    args = sys.argv.copy()
    
    if len(args) < 4:
        print("ERROR_MISSING_ARGS")
        sys.exit(1)

    script_name = args.pop(0)
    csv_path = str(args.pop(0)).strip()
    thing_name = str(args.pop(0)).strip()
    target_room = str(args.pop(0)).strip()

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
            
            # If we find the specific room we are targeting, overwrite it
            if not updated and row[0].strip() == target_room:
                row.clear()
                row.append(target_room)
                row.append(thing_name)
                assigned_room = target_room
                updated = True
            
            rows.append(row)

    if updated:
        with open(csv_path, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(rows)
            
        print(assigned_room)
    else:
        print("ROOM_NOT_FOUND")

if __name__ == "__main__":
    main()