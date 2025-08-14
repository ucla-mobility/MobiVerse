import os
import json
import math
import requests
import socket
import concurrent.futures
from typing import List, Dict, Tuple, Optional, Any

class ActivityChainModifier:
    def __init__(self, max_workers=50):
        """Initialize the activity chain modifier with API key from file"""
        self.api_key = self.load_api_key()
        self.pois = self.load_pois()
        self.route_info = self.load_route_info()
        self.max_workers = max_workers
        
    def load_api_key(self) -> str:
        """Load OpenAI API key from file"""
        try:
            key_path = '../open_ai_api_key.txt'
            with open(key_path, 'r') as f:
                return f.read().strip()
        except Exception as e:
            print(f"Error loading API key: {e}")
            return os.environ.get("OPENAI_API_KEY", "")
            
    def load_pois(self) -> List[Dict]:
        """Load POI data from pois.add.xml"""
        try:
            import xml.etree.ElementTree as ET
            poi_path = '../poi/pois.add.xml'
            tree = ET.parse(poi_path)
            root = tree.getroot()
            
            pois = []
            for poi in root.findall('poi'):
                pois.append({
                    'id': poi.get('id'),
                    'lat': float(poi.get('lat')),
                    'lon': float(poi.get('lon')),
                    'name': poi.get('name', poi.get('id')),
                    'type': poi.get('type', 'unknown')
                })
            return pois
        except Exception as e:
            print(f"Error loading POIs: {e}")
            return []
            
    def load_route_info(self) -> List[Dict]:
        """Load route information from route_info.json"""
        try:
            with open('../data/route_info.json', 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading route info: {e}")
            return []
    
    def get_agent_current_location(self, socket_conn, agent_id: str) -> Optional[Dict]:
        """Get the current location of an agent from SUMO"""
        try:
            # Request vehicle data
            socket_conn.send("GET_VEHICLES".encode())
            
            # Wait for response
            buffer = ""
            while "<<END>>" not in buffer:
                data = socket_conn.recv(16384).decode('utf-8', errors='ignore')
                buffer += data
                if not data:
                    break
            
            if "<<END>>" in buffer:
                message, _ = buffer.split("<<END>>", 1)
                info = json.loads(message)
                
                if agent_id in info.get('vehicle_data', {}):
                    vehicle_data = info['vehicle_data'][agent_id]
                    
                    # Get position
                    if 'lat_lon' in vehicle_data:
                        lat, lon = vehicle_data['lat_lon'][:2]
                    elif 'position' in vehicle_data:
                        lat, lon = vehicle_data['position'][:2]
                    else:
                        return None
                    
                    # Get current edge and route information
                    current_edge = vehicle_data.get('current_edge', '')
                    route = vehicle_data.get('route', [])
                    route_index = vehicle_data.get('route_index', 0)
                    
                    # Find nearest POI
                    nearest_poi = self.find_nearest_poi(lat, lon)
                    
                    return {
                        'position': (lat, lon),
                        'current_edge': current_edge,
                        'nearest_poi': nearest_poi,
                        'route': route,
                        'route_index': route_index
                    }
            
            return None
        except Exception as e:
            print(f"Error getting agent location: {e}")
            return None
    
    def find_nearest_poi(self, lat: float, lon: float) -> Optional[Dict]:
        """Find the nearest POI to a given lat/lon position"""
        nearest = None
        min_dist = float('inf')
        
        for poi in self.pois:
            try:
                poi_lat = float(poi['lat'])
                poi_lon = float(poi['lon'])
                
                dist = self.calculate_distance(lat, lon, poi_lat, poi_lon)
                
                if dist < min_dist:
                    min_dist = dist
                    nearest = poi
            except Exception:
                continue
            
        return nearest
    
    def calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate the Haversine distance between two points in kilometers"""
        # Convert decimal degrees to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        r = 6371  # Radius of earth in kilometers
        
        return c * r
    
    def get_poi_by_name(self, name: str) -> Optional[Dict]:
        """Find a POI by its name"""
        for poi in self.pois:
            if poi.get('name') == name:
                return poi
        return None
    
    def get_distance_between_pois(self, poi1_name: str, poi2_name: str) -> Optional[float]:
        """Calculate the distance between two POIs by name"""
        poi1 = self.get_poi_by_name(poi1_name)
        poi2 = self.get_poi_by_name(poi2_name)
        
        if not poi1 or not poi2:
            return None
            
        try:
            lat1 = float(poi1['lat'])
            lon1 = float(poi1['lon'])
            lat2 = float(poi2['lat'])
            lon2 = float(poi2['lon'])
            
            return self.calculate_distance(lat1, lon1, lat2, lon2)
        except Exception as e:
            print(f"Error calculating distance: {e}")
            return None
    
    def get_agent_route_info(self, agent_id: str) -> Optional[Dict]:
        """Get the route information for a specific agent"""
        for route in self.route_info:
            if route.get('agent_id') == agent_id:
                return route
        return None
    
    def seconds_to_quarters(self, seconds):
        """Convert seconds since midnight to quarter-hour index (0-95)"""
        minutes = seconds // 60
        return minutes // 15

    def seconds_to_time_str(self, seconds):
        """Convert seconds since midnight to HH:MM format"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours:02d}:{minutes:02d}"

    def modify_activity_chain_with_llm(self, agent_id: str, current_chain: List[str], 
                                      prompt: str, vehicle_data: Dict, traffic_info: Dict) -> Tuple[List[str], List[int]]:
        """
        Use LLM to modify an activity chain based on a natural language prompt
        Returns: Tuple of (list of POI names, list of durations in seconds)
        """
        if not self.api_key:
            print("No API key provided for LLM service")
            return current_chain, []

        # Get current location and route information
        current_edge = vehicle_data.get('current_edge', '')
        route = vehicle_data.get('route', [])
        try:
            route_idx = route.index(current_edge)
            remaining_route = route[route_idx:]
        except ValueError:
            remaining_route = route
        
        # Find nearest POI to current location
        current_location = "unknown"
        if 'lat_lon' in vehicle_data:
            lat, lon = vehicle_data['lat_lon'][:2]
            nearest_poi = self.find_nearest_poi(lat, lon)
            if nearest_poi:
                current_location = nearest_poi.get('name', 'unknown')
        poi_sequence = vehicle_data.get('route_info', {}).get('poi_sequence', [])
        timing_info = []
        for poi in poi_sequence:
            start_quarter = self.seconds_to_quarters(poi['start_time'])
            end_quarter = self.seconds_to_quarters(poi['end_time'])
            duration_quarters = (poi['stop_duration'] // 60) // 15  # Convert seconds to quarters
            start_time_str = self.seconds_to_time_str(poi['start_time'])
            end_time_str = self.seconds_to_time_str(poi['end_time'])
            timing_info.append(
                f"{poi['name']}: {start_time_str}-{end_time_str} "
                f"(quarters {start_quarter}-{end_quarter}, duration: {duration_quarters} quarters)"
            )
        # Process traffic information
        traffic_status = []
        print(current_edge)
        print(traffic_info)
        if current_edge and traffic_info:
            # Check congestion on current edge
            if current_edge in traffic_info:
                edge_info = traffic_info[current_edge]
                if edge_info['is_congested']:
                    traffic_status.append(
                        f"Current location has heavy traffic "
                        f"(road occupancy: {edge_info['occupancy']*100:.0f}%)"
                    )
            print(remaining_route)
            # Check congestion on remaining route
            congested_edges = [
                edge for edge in remaining_route 
                if edge in traffic_info and traffic_info[edge]['is_congested']
            ]
            
            if congested_edges:
                avg_occupancy = sum(traffic_info[e]['occupancy'] for e in congested_edges) / len(congested_edges)
                traffic_status.append(
                    f"Heavy traffic detected on {len(congested_edges)} upcoming road segments "
                    f"(average occupancy: {avg_occupancy*100:.0f}%)"
                )

        # Get agent demographics
        demographics = "No demographic information available."
        if 'route_info' in vehicle_data and 'demographics' in vehicle_data['route_info']:
            demo = vehicle_data['route_info']['demographics']
            demographics = (f"Age: {demo.get('age', 'unknown')}, "
                          f"Gender: {demo.get('gender', 'unknown')}, "
                          f"Student: {demo.get('student_status', 'unknown')}, "
                          f"Income: {demo.get('income_level', 'unknown')}")

        # Get distances between POIs
        distance_info = []
        for i in range(len(current_chain) - 1):
            dist = self.get_distance_between_pois(current_chain[i], current_chain[i+1])
            if dist:
                distance_info.append(f"Distance from {current_chain[i]} to {current_chain[i+1]}: {dist:.2f} km")
        
        # Construct the prompt for the LLM
        system_prompt = """
        You are an AI assistant that helps modify activity chains for agents in a simulation.
        Given the current activity chain with timing information, agent's current location, demographics, traffic conditions, and event timing, suggest a modified chain that makes sense.
        
        The activity chain should respect the event timing - make sure the agent is at the event location during the specified event time.
        If there are conflicting activities during the event time, reschedule them to before or after the event.
        
        Only respond with the new activity chain as a comma-separated list of POI names and durations in quarters (15-minute blocks).
        Format: POI_name:quarters, POI_name:quarters, ...
        Example: Falafel Inc.:32, Starbucks:4, UCLA_Parking_Lot_2:16, Ralphs:8, Falafel Inc.:36
        
        Each quarter represents 15 minutes, so:
        - 4 quarters = 1 hour
        - 32 quarters = 8 hours
        - 96 quarters = 24 hours
        
        Do not include any explanations or additional text.
        """
        
        user_prompt = f"""
        Agent ID: {agent_id}
        Current location: {current_location}
        Demographics: {demographics}
        
        Current activity chain with timing:
        {' | '.join(timing_info)}
        
        Traffic conditions:
        {' '.join(traffic_status) if traffic_status else 'No significant traffic congestion reported'}
        
        Situation: {prompt}
        
        Provide the new chain as a comma-separated list of POI names with durations in quarters (15-minute blocks).
        Only include POI names that exist in the current chain or are well-known locations.
        Each quarter represents 15 minutes, so 4 quarters = 1 hour.
        """
        print(f"User prompt: {user_prompt}")

        try:
            # Call OpenAI API
            response = self.call_openai_api(system_prompt, user_prompt)
            print(f"Response: {response}")
            
            # Parse the response (now includes durations in quarters)
            new_chain_with_duration = [item.strip() for item in response.split(',')]
            
            # Convert to list of POIs and durations
            valid_chain = []
            durations = []  # durations in seconds
            
            for item in new_chain_with_duration:
                try:
                    poi_name, quarters = item.split(':')
                    poi_name = poi_name.strip()
                    quarters = int(quarters.strip())
                    
                    if self.get_poi_by_name(poi_name) or poi_name in current_chain:
                        valid_chain.append(poi_name)
                        # Convert quarters to seconds (1 quarter = 15 minutes = 900 seconds)
                        durations.append(quarters * 900)
                except ValueError:
                    print(f"Warning: Invalid format for item '{item}'")
            
            if not valid_chain:
                print("No valid POIs in the modified chain, keeping original")
                return current_chain, []
                
            return valid_chain, durations
            
        except Exception as e:
            print(f"Error modifying activity chain with LLM: {e}")
            return current_chain, []
    
    def call_openai_api(self, system_prompt: str, user_prompt: str) -> str:
        """Call the OpenAI API to get a response"""
        url = "https://api.openai.com/v1/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        data = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 1.0
        }
        
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"].strip()
        else:
            raise Exception(f"API call failed with status {response.status_code}: {response.text}")
    
    def modify_activity_chains_parallel(self, agent_data_list: List[Dict]) -> Dict[str, List[str]]:
        """
        Process multiple agents in parallel using ThreadPoolExecutor
        
        agent_data_list: List of dictionaries with the following structure:
        {
            'agent_id': str,
            'current_chain': List[str],
            'prompt': str,
            'vehicle_data': Dict,
            'traffic_info': Dict
        }
        
        Returns a dictionary mapping agent_id to their new activity chains
        """
        results = {}
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_agent = {
                executor.submit(
                    self.modify_activity_chain_with_llm,
                    data['agent_id'],
                    data['current_chain'],
                    data['prompt'],
                    data.get('vehicle_data', {}),
                    data.get('traffic_info', {})
                ): data['agent_id']
                for data in agent_data_list
            }
            
            # Process results as they complete
            for future in concurrent.futures.as_completed(future_to_agent):
                agent_id = future_to_agent[future]
                try:
                    new_chain, durations = future.result()
                    results[agent_id] = (new_chain, durations)
                    print(f"Completed processing for agent {agent_id}")
                except Exception as e:
                    print(f"Error processing agent {agent_id}: {e}")
                    # In case of error, keep the original chain
                    agent_data = next((data for data in agent_data_list if data['agent_id'] == agent_id), None)
                    if agent_data:
                        results[agent_id] = (agent_data['current_chain'], [])
        
        return results 