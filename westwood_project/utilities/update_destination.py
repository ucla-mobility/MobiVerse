import json
import random
import time

def update_agent_destination(agent_id, destination_name):
    try:
        with open('../data/destination_updates.json', 'r') as f:
            updates = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        updates = []
    
    updates.append({
        "agent_id": f"agent_{agent_id}",
        "destination": destination_name
    })
    
    with open('../data/destination_updates.json', 'w') as f:
        json.dump(updates, f, indent=2)

def get_available_destinations():
    with open('../poi/matched_pois.json', 'r') as f:
        pois = json.load(f)
    return [poi['name'] for poi in pois]

def main():
    destinations = get_available_destinations()
    print("Available destinations:", destinations)
    
    while True:
        print("\nOptions:")
        print("1. Update single agent")
        print("2. Update random agents")
        print("3. List destinations")
        print("4. Exit")
        
        choice = input("Choose an option (1-4): ")
        
        if choice == '1':
            agent_id = input("Enter agent ID (0-19): ")
            print("\nAvailable destinations:")
            for i, dest in enumerate(destinations):
                print(f"{i}: {dest}")
            dest_idx = int(input("Enter destination number: "))
            update_agent_destination(agent_id, destinations[dest_idx])
            print(f"Updated agent_{agent_id} destination to {destinations[dest_idx]}")
        
        elif choice == '2':
            num_updates = int(input("How many random updates to generate? "))
            for _ in range(num_updates):
                agent_id = random.randint(0, 19)
                dest = random.choice(destinations)
                update_agent_destination(agent_id, dest)
                print(f"Updated agent_{agent_id} destination to {dest}")
                time.sleep(0.5)  # Small delay between updates
        
        elif choice == '3':
            print("\nAvailable destinations:")
            for i, dest in enumerate(destinations):
                print(f"{i}: {dest}")
        
        elif choice == '4':
            break

if __name__ == '__main__':
    main() 