import warnings
warnings.filterwarnings("ignore", message="Module 'rtree' not available")

import json
import xml.etree.ElementTree as ET
import random
import sumolib
import numpy as np
import argparse
import subprocess
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
import math

@dataclass
class Demographics:
    age: int
    gender: str
    student_status: str
    income_level: str
    education_level: str
    work_status: str

def generate_random_demographics():
    """Generate random demographic information"""
    return Demographics(
        age=random.randint(18, 65),
        gender=random.choice(['Male', 'Female']),
        student_status=random.choice(['Undergraduate', 'Graduate', 'Not a Student']),
        income_level=random.choice(['Low (<$58,000/year)', 'Medium ($58,000-$153,000/year)', 'High (>$153,000/year)']),
        education_level=random.choice(['High School', 'Bachelor', 'Master', 'PhD']),
        work_status=random.choice(['Full-time', 'Part-time', 'Not Working'])
    )

def load_pois():
    """Load POIs from pois.add.xml"""
    tree = ET.parse('../poi/pois.add.xml')
    root = tree.getroot()
    
    pois = []
    for poi in root.findall('poi'):
        pois.append({
            'id': poi.get('id'),
            'lat': float(poi.get('lat')),
            'lon': float(poi.get('lon')),
            'name': poi.get('name'),
            'type': poi.get('type'),
            'edge': poi.get('edge', '')
        })
    return pois

def get_activity_purpose(poi_type, time_of_day, demographics):
    """
    Assign a meaningful activity purpose to POIs based on type, time of day and demographics
    This helps assign appropriate durations even with limited POI types
    """
    hour = time_of_day.hour
    
    # Morning activities (5am-11am)
    if 5 <= hour < 11:
        if poi_type == "cafe":
            return "breakfast"
        elif poi_type == "restaurant":
            if random.random() < 0.7:  # 70% chance for breakfast
                return "breakfast"
            else:
                return "shopping"  # Some restaurants are used as grocery/shopping in morning
        elif poi_type == "school":
            return "education"
        elif poi_type == "office":
            return "work"
        elif poi_type == "stadium":
            return "exercise"  # Morning exercise at stadium
    
    # Midday activities (11am-2pm)
    elif 11 <= hour < 14:
        if poi_type in ["cafe", "restaurant"]:
            return "lunch"
        elif poi_type == "school":
            return "education"
        elif poi_type == "office":
            return "work"
        elif poi_type == "stadium":
            if demographics.student_status in ["Undergraduate", "Graduate"]:
                return "recreation"  # Students might have recreation time
            else:
                return "work"  # Others might be working at stadium
    
    # Afternoon activities (2pm-5pm)
    elif 14 <= hour < 17:
        if poi_type == "cafe":
            return "coffee_break"
        elif poi_type == "restaurant":
            if random.random() < 0.3:  # 30% chance
                return "coffee_break"
            else:
                return "shopping"  # Using restaurants as shopping/errands
        elif poi_type == "school":
            return "education"
        elif poi_type == "office":
            return "work"
        elif poi_type == "stadium":
            if demographics.student_status in ["Undergraduate", "Graduate"]:
                return "recreation"
            else:
                return "work"
    
    # Evening activities (5pm-8pm)
    elif 17 <= hour < 20:
        if poi_type in ["cafe", "restaurant"]:
            return "dinner"
        elif poi_type == "school":
            if demographics.student_status in ["Undergraduate", "Graduate"]:
                return "study"  # Evening study
            else:
                return "recreation"  # Evening activities at school
        elif poi_type == "office":
            if demographics.work_status == "Full-time" and random.random() < 0.4:
                return "work_late"  # Some people work late
            else:
                return "recreation"  # Using office spaces for evening activities
        elif poi_type == "stadium":
            return "entertainment"  # Evening entertainment at stadium
    
    # Night activities (8pm-midnight)
    elif 20 <= hour < 24:
        if poi_type in ["cafe", "restaurant"]:
            if random.random() < 0.7:  # 70% chance
                return "entertainment"  # Evening entertainment at restaurants
            else:
                return "late_dinner"
        elif poi_type in ["school", "office"]:
            if demographics.student_status in ["Undergraduate", "Graduate"] and random.random() < 0.3:
                return "study_late"  # Some students study late
            else:
                return "entertainment"  # Using these spaces for night activities
        elif poi_type == "stadium":
            return "entertainment"  # Night events at stadium
    
    # Default/fallback
    return "other"

def round_to_quarter_hour(dt):
    """Round a datetime to the nearest 15-minute quarter"""
    minutes = dt.minute
    rounded_minutes = round(minutes / 15) * 15
    
    # Handle case when rounding to 60 minutes
    if rounded_minutes == 60:
        return dt.replace(minute=0, second=0) + timedelta(hours=1)
    
    return dt.replace(minute=rounded_minutes, second=0)

def time_to_quarter_index(dt):
    """Convert a datetime to a quarter index (0-95)"""
    # Each quarter is 15 minutes
    # 0 = 00:00-00:15, 1 = 00:15-00:30, ..., 95 = 23:45-00:00
    return dt.hour * 4 + dt.minute // 15

def get_activity_duration_in_quarters(purpose, demographics):
    """Return duration in quarters (15-minute blocks) based on activity purpose and demographics"""
    # Get duration in minutes first
    base_durations = {
        "home_morning": (240, 480),    # 4-8 hours at home in morning
        "home_night": (360, 600),      # 6-10 hours at home at night
        "breakfast": (15, 60),         # 15-60 minutes for breakfast
        "lunch": (30, 90),             # 30-90 minutes for lunch
        "dinner": (60, 120),           # 1-2 hours for dinner
        "late_dinner": (60, 150),      # 1-2.5 hours for late dinner
        "coffee_break": (15, 45),      # 15-45 minutes for coffee
        "work": (180, 300),            # 3-5 hours for work sessions
        "work_late": (120, 240),       # 2-4 hours for late work
        "education": (120, 240),       # 2-4 hours for classes
        "study": (60, 180),            # 1-3 hours for study sessions
        "study_late": (60, 150),       # 1-2.5 hours for late study
        "shopping": (30, 120),         # 30-120 minutes for shopping
        "exercise": (45, 90),          # 45-90 minutes for exercise
        "recreation": (60, 180),       # 1-3 hours for recreation
        "entertainment": (90, 240),    # 1.5-4 hours for entertainment
        "other": (30, 120)             # 30-120 minutes for other activities
    }
    
    # Get base duration range
    min_duration, max_duration = base_durations.get(purpose, (30, 120))
    
    # Adjust based on demographics
    if purpose in ["work", "work_late", "education"] and demographics.work_status == "Full-time":
        min_duration += 30  # Full-time workers/students spend more time on these
    
    if purpose in ["entertainment", "recreation"] and demographics.age < 30:
        max_duration += 30  # Younger people spend more time on entertainment
    
    if purpose in ["shopping"] and demographics.gender == "Female" and random.random() < 0.3:
        max_duration += 30  # Slight increase for some female shoppers (based on statistics)
    
    # Randomize within range and then round to nearest quarter hour
    minutes = random.randint(min_duration, max_duration)
    quarters = math.ceil(minutes / 15)  # Round up to nearest quarter
    
    # Ensure minimum of 1 quarter (15 minutes)
    return max(1, quarters)

def create_24hr_activity_chain(pois, demographics):
    """Create a realistic 24-hour activity chain based on available POIs"""
    # Classify POIs by type
    poi_by_type = {}
    for poi in pois:
        poi_type = poi['type'].lower()
        if poi_type not in poi_by_type:
            poi_by_type[poi_type] = []
        poi_by_type[poi_type].append(poi)
    
    # # Choose home location (apartment or random if no apartments)
    # if 'apartment' in poi_by_type and poi_by_type['apartment']:
    #     home_poi = random.choice(poi_by_type['apartment'])
    # else:
    #     # Fallback: randomly choose a POI to serve as home
    #     home_poi = random.choice(pois)
    home_poi = random.choice(pois)
    
    # Initialize departure time (6-9am) rounded to quarter hour
    raw_departure = datetime(2023, 1, 1, random.randint(6, 9), random.randint(0, 59))
    departure_time = round_to_quarter_hour(raw_departure)
    
    # Calculate quarters for the morning home activity (from midnight until departure)
    midnight = datetime(2023, 1, 1, 0, 0)
    morning_quarters = time_to_quarter_index(departure_time)  # Quarters from midnight to departure
    
    activity_chain = [
        {
            'poi': home_poi,
            'start_time': midnight,
            'end_time': departure_time,
            'start_quarter': 0,  # Midnight is quarter 0
            'end_quarter': morning_quarters,
            'quarters': morning_quarters, 
            'duration_minutes': morning_quarters * 15,
            'purpose': 'home_morning',
            'activity_type': 'home'
        }
    ]
    
    current_time = departure_time
    current_quarter = morning_quarters
    
    # Determine number of activities based on demographics
    if demographics.work_status == 'Full-time':
        num_activities = random.randint(4, 6)
    elif demographics.student_status in ['Undergraduate', 'Graduate'] or demographics.work_status == 'Part-time':
        num_activities = random.randint(3, 5)
    else:
        num_activities = random.randint(2, 4)
    
    # List of POIs to avoid (start with home)
    visited_pois = [home_poi['id']]
    
    # Add activities throughout the day
    for i in range(num_activities):
        # Determine activity types based on time of day
        hour = current_time.hour
        
        # Morning (6am-11am): work, school, breakfast
        if 6 <= hour < 11:
            if demographics.work_status in ['Full-time', 'Part-time']:
                preferred_types = ['office', 'cafe', 'restaurant']
                weights = [0.6, 0.3, 0.1]  # Higher weight for work locations
            elif demographics.student_status in ['Undergraduate', 'Graduate']:
                preferred_types = ['school', 'cafe', 'restaurant']
                weights = [0.6, 0.3, 0.1]  # Higher weight for school
            else:
                preferred_types = ['cafe', 'restaurant', 'stadium']
                weights = [0.4, 0.4, 0.2]
        
        # Midday (11am-2pm): lunch, work/school
        elif 11 <= hour < 14:
            preferred_types = ['restaurant', 'cafe', 'school', 'office']
            if demographics.work_status in ['Full-time', 'Part-time']:
                weights = [0.4, 0.2, 0.1, 0.3]  # Workers more likely to eat at restaurants
            elif demographics.student_status in ['Undergraduate', 'Graduate']:
                weights = [0.3, 0.2, 0.4, 0.1]  # Students more likely to be at school
            else:
                weights = [0.5, 0.3, 0.1, 0.1]  # Others more likely to be at restaurants
        
        # Afternoon (2pm-5pm): work/school, coffee
        elif 14 <= hour < 17:
            if demographics.work_status in ['Full-time', 'Part-time']:
                preferred_types = ['office', 'cafe', 'restaurant']
                weights = [0.6, 0.3, 0.1]
            elif demographics.student_status in ['Undergraduate', 'Graduate']:
                preferred_types = ['school', 'cafe', 'restaurant']
                weights = [0.6, 0.3, 0.1]
            else:
                preferred_types = ['cafe', 'restaurant', 'stadium']
                weights = [0.3, 0.5, 0.2]
        
        # Evening (5pm-8pm): dinner, entertainment
        elif 17 <= hour < 20:
            preferred_types = ['restaurant', 'cafe', 'stadium']
            weights = [0.6, 0.2, 0.2]
        
        # Night (8pm-midnight): entertainment, late dinner
        else:  # 20 <= hour < 24
            preferred_types = ['restaurant', 'stadium', 'cafe']
            if demographics.age < 30:
                weights = [0.5, 0.3, 0.2]  # Younger people more likely at restaurants/entertainment
            else:
                weights = [0.6, 0.2, 0.2]  # Older people slightly more likely at restaurants
        
        # Remove office and school from preferred types and corresponding weights
        if 'office' in preferred_types or 'school' in preferred_types:
            indices_to_remove = [i for i, t in enumerate(preferred_types) if t in ['office', 'school']]
            for idx in reversed(indices_to_remove):
                preferred_types.pop(idx)
                if weights:
                    weights.pop(idx)
            
            # Normalize remaining weights if any exist
            if weights:
                total = sum(weights)
                if total > 0:
                    weights = [w/total for w in weights]
        # Filter available POI types
        available_types = [t for t in preferred_types if t in poi_by_type and poi_by_type[t]]
        
        if not available_types:
            # Fallback if no preferred types available
            available_types = list(poi_by_type.keys())
            weights = None  # Equal weights if falling back
        else:
            # Adjust weights to match available types
            weights = [weights[preferred_types.index(t)] for t in available_types]
            # Normalize weights
            total = sum(weights)
            weights = [w/total for w in weights]
        
        # Select a POI type and then a specific POI
        selected_type = random.choices(available_types, weights=weights, k=1)[0]
        
        # Filter out already visited POIs of this type for variety
        available_pois = [p for p in poi_by_type[selected_type] if p['id'] not in visited_pois]
        
        # If no unvisited POIs of this type, allow revisits
        if not available_pois:
            available_pois = poi_by_type[selected_type]
        
        # Select a specific POI
        selected_poi = random.choice(available_pois)
        
        # Determine activity purpose based on POI type and time
        purpose = get_activity_purpose(selected_type, current_time, demographics)
        
        # Determine activity duration in quarters (15-minute blocks)
        quarters = get_activity_duration_in_quarters(purpose, demographics)
        
        # Calculate travel time in quarters (1-2 quarters = 15-30 minutes)
        travel_quarters = random.randint(1, 2)
        
        # Calculate end time based on quarters
        end_time = current_time + timedelta(minutes=quarters * 15)
        
        # Create activity entry
        activity_chain.append({
            'poi': selected_poi,
            'start_time': current_time,
            'end_time': end_time,
            'start_quarter': current_quarter,
            'end_quarter': current_quarter + quarters,
            'quarters': quarters,
            'duration_minutes': quarters * 15,
            'purpose': purpose,
            'activity_type': purpose.split('_')[0]  # Basic activity type
        })
        
        # Update current time and quarter index
        current_time = end_time + timedelta(minutes=travel_quarters * 15)
        current_quarter = current_quarter + quarters + travel_quarters
        
        # Add POI to visited list (for variety)
        visited_pois.append(selected_poi['id'])
        
        # Check if we've gone past midnight
        if current_quarter >= 96:
            # If we're past midnight, stop adding activities
            break
    
    # Add final home activity
    end_of_day = datetime(2023, 1, 1, 23, 59)
    end_quarter = 96  # End of day (24:00)
    
    # If current time is past midnight, adjust
    if current_quarter >= 96:
        # We're already past midnight, adjust
        current_quarter = 96 - 4  # Back up to 11pm
        current_time = datetime(2023, 1, 1, 23, 0)
    
    evening_quarters = end_quarter - current_quarter
    
    activity_chain.append({
        'poi': home_poi,
        'start_time': current_time,
        'end_time': end_of_day,
        'start_quarter': current_quarter,
        'end_quarter': end_quarter,
        'quarters': evening_quarters,
        'duration_minutes': evening_quarters * 15,
        'purpose': 'home_night',
        'activity_type': 'home'
    })
    
    return activity_chain

def create_agent_sequences(num_agents=100):
    """Create agent POI sequences and demographics with realistic 24-hour activity chains"""
    print(f"Creating sequences for {num_agents} agents with realistic 24-hour activity patterns...")
    
    # Load POIs
    pois = load_pois()
    print(f"Found {len(pois)} POIs")
    
    # Create agent sequences
    agent_sequences = []
    for i in range(num_agents):
        # Generate demographics
        demographics = generate_random_demographics()
        
        # Create realistic activity chain
        activity_chain = create_24hr_activity_chain(pois, demographics)
        
        # Convert activity chain to POI sequence
        poi_sequence = []
        for idx, activity in enumerate(activity_chain):
            poi = activity['poi']
            start_time_seconds = int((activity['start_time'] - datetime(2023, 1, 1, 0, 0)).total_seconds())
            end_time_seconds = int((activity['end_time'] - datetime(2023, 1, 1, 0, 0)).total_seconds())
            
            poi_sequence.append({
                'name': poi['name'],
                'id': poi['id'],
                'order': idx + 1,
                'type': poi['type'],
                'activity_type': activity['activity_type'],
                'purpose': activity['purpose'],
                'start_time': start_time_seconds,
                'end_time': end_time_seconds,
                'start_quarter': activity['start_quarter'],
                'end_quarter': activity['end_quarter'],
                'quarters': activity['quarters'],
                'stop_duration': activity['duration_minutes'] * 60,  # Convert minutes to seconds
                'edge': poi.get('edge', '')
            })
        
        # Store sequence and demographics but don't assign agent_id yet
        agent_sequences.append({
            'poi_sequence': poi_sequence,
            'demographics': {
                'age': demographics.age,
                'gender': demographics.gender,
                'student_status': demographics.student_status,
                'income_level': demographics.income_level,
                'education_level': demographics.education_level,
                'work_status': demographics.work_status
            }
        })
    
    # Sort sequences by departure time (start time of second activity)
    agent_sequences.sort(key=lambda x: x['poi_sequence'][1]['start_time'])
    
    # Now assign agent IDs in departure time order
    for i, sequence in enumerate(agent_sequences):
        sequence['agent_id'] = f'agent_{i}'
    
    # Save to file
    with open('../data/agent_sequences.json', 'w') as f:
        json.dump(agent_sequences, f, indent=2)
    
    print(f"Created sequences for {len(agent_sequences)} agents with realistic activity patterns")
    return agent_sequences

def generate_routes_from_sequences(start_time=0, end_time=86400):
    """Generate SUMO routes from pre-defined agent sequences spanning a full 24 hours"""
    print("Generating routes from sequences for full 24-hour simulation...")
    
    # Load sequences (already sorted by departure time)
    with open('../data/agent_sequences.json', 'r') as f:
        agent_sequences = json.load(f)
    
    # Load network and compute POI edges
    net = sumolib.net.readNet('../sumo_config/westwood.net.xml')
    pois = load_pois()
    
    def find_route_between_edges(from_edge, to_edge):
        """Find a direct route between two edges"""
        try:
            route = net.getShortestPath(
                net.getEdge(from_edge),
                net.getEdge(to_edge)
            )[0]
            if route:
                # Get just the direct path
                return [edge.getID() for edge in route]
            return None
        except:
            return None
    
    # Pre-compute all POI edges
    poi_edges = {}
    radius = 100
    for poi in pois:
        # Check if edge is already in the POI data
        if poi.get('edge') and poi.get('edge') != '':
            poi_edges[poi['name']] = poi['edge']
            continue
            
        # Otherwise compute it
        x, y = net.convertLonLat2XY(poi['lon'], poi['lat'])
        edges = net.getNeighboringEdges(x, y, radius)
        if edges:
            edges.sort(key=lambda x: x[1])
            edge = edges[0][0]
            if edge.allows("passenger"):
                poi_edges[poi['name']] = edge.getID()
    
    # Process agents and create vehicles with routes
    valid_vehicles = []
    route_info = []
    
    for agent in agent_sequences:
        agent_id = agent['agent_id']
        
        # Get edges for POI sequence
        stop_edges = []
        valid_sequence = True

        for poi in agent['poi_sequence']:
            poi_name = poi['name']
            if poi_name not in poi_edges:
                valid_sequence = False
                break
            stop_edges.append(poi_edges[poi_name])
            # Update the edge in the POI sequence
            poi['edge'] = poi_edges[poi_name]
        
        if not valid_sequence:
            continue
        
        # Generate route between stops
        complete_route = []
        current_pos = stop_edges[0]
        valid_route = True
        
        # Add first edge
        complete_route.append(current_pos)
        
        # Find routes between consecutive stops
        for next_edge in stop_edges[1:]:
            if current_pos != next_edge:
                segment = find_route_between_edges(current_pos, next_edge)
                if not segment:
                    valid_route = False
                    break
                complete_route.extend(segment[1:])
                current_pos = next_edge
        
        if not valid_route:
            continue
        
        # Use the start time of the second activity (departure from home)
        depart_time = agent['poi_sequence'][1]['start_time'] - 600  # 10 minutes before next activity
        if depart_time < 0:
            depart_time = 0
        
        # Collect valid vehicles
        vehicle_data = {
            'agent_id': agent_id,
            'depart_time': depart_time,
            'route_edges': complete_route,
            'stops': [],
            'poi_sequence': agent['poi_sequence']
        }
        
        # Add stops (skip the first home activity)
        for i, poi in enumerate(agent['poi_sequence'][1:], 1):
            edge = stop_edges[i]
            edge_obj = net.getEdge(edge)
            stop_pos = edge_obj.getLength() - 10
            vehicle_data['stops'].append({
                'edge': edge,
                'endPos': stop_pos,
                #'duration': poi["stop_duration"]
                'duration': 180
            })
        
        valid_vehicles.append(vehicle_data)
        
        # Store route info
        route_info.append({
            'agent_id': agent_id,
            'poi_sequence': agent['poi_sequence'],
            'demographics': agent['demographics']
        })
    
    # Write vehicles to routes file (already sorted by departure time)
    with open('../sumo_config/westwood.activity.xml', 'w') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<routes>\n')
        f.write('    <vType id="car" accel="2.9" decel="4.5" sigma="0.5" length="4.5" minGap="1.5" maxSpeed="15.0"\n')
        f.write('           speedDev="0.1" speedFactor="1.1" lcStrategic="1.0" lcCooperative="1.0"\n')
        f.write('           personCapacity="4" color="255,255,255"/>\n')
        
        # Write each vehicle in sorted order
        for vehicle in valid_vehicles:
            f.write(f'    <vehicle id="{vehicle["agent_id"]}" type="car" depart="{vehicle["depart_time"]}"\n')
            f.write(f'             departLane="best" departSpeed="max">\n')
            f.write(f'        <route edges="{" ".join(vehicle["route_edges"])}"/>\n')
            
            # Add stops
            for stop in vehicle['stops']:
                f.write(f'        <stop edge="{stop["edge"]}" endPos="{stop["endPos"]}" duration="{stop["duration"]}" parking="true"/>\n')
            
            f.write('    </vehicle>\n')
        
        f.write('</routes>\n')
    
    # Save route info
    with open('../data/route_info.json', 'w') as f:
        json.dump(route_info, f, indent=2)
    
    print(f"Generated routes for {len(valid_vehicles)} agents with realistic 24-hour activity patterns")

def main():
    parser = argparse.ArgumentParser(description='Create routes between POIs for SUMO simulation')
    parser.add_argument('-n', '--num-agents', type=int, default=100,
                        help='Number of agents to create (default: 100)')
    parser.add_argument('--start-time', type=float, default=0,
                        help='Simulation start time in seconds (default: 0 = 12:00 AM)')
    parser.add_argument('--end-time', type=float, default=86400,
                        help='Simulation end time in seconds (default: 86400 = 24 hours)')
    parser.add_argument('--generate-sequences', action='store_true',
                        help='Generate new agent sequences')
    
    args = parser.parse_args()
    
    if args.generate_sequences:
        print(args.num_agents)
        create_agent_sequences(args.num_agents)
    generate_routes_from_sequences(args.start_time, args.end_time)

if __name__ == '__main__':
    main() 