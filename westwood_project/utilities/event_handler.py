import math
from typing import Dict, List, Tuple
import json

class EventHandler:
    def __init__(self):
        self.event_types = {
            "sports": {
                "base_interest": 0.7,
                "age_factors": [
                    (lambda age: age < 16, 0.5),
                    (lambda age: 16 <= age <= 18, 0.990),
                    (lambda age: 19 <= age <= 29, 1.002),
                    (lambda age: 30 <= age <= 39, 1.006),
                    (lambda age: 40 <= age <= 49, 1.006),
                    (lambda age: 50 <= age <= 59, 1.003),
                    (lambda age: age >= 60, 1.0001)
                ],
                "sex_factors": {
                    "MALE": 1.002,
                    "FEMALE": 0.998
                }
            },
            "entertainment": {
                "base_interest": 0.8,
                "age_factors": [
                    (lambda age: age < 16, 0.900),
                    (lambda age: 16 <= age < 18, 0.990),
                    (lambda age: 18 <= age < 35, 1.008),
                    (lambda age: 35 <= age < 70, 0.992),
                    (lambda age: age >= 70, 0.990)
                ],
                "income_factor": lambda percentile: 1.2 if percentile > 80 else 1.0
            }
        }

    def haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate the great circle distance between two points in kilometers."""
        R = 6371  # Earth's radius in kilometers

        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        return R * c

    def calculate_distance_factor(self, dist_km: float) -> float:
        """Calculate distance factor based on distance in kilometers."""
        return 1.005 if dist_km <= 20 else 0.995

    def calculate_interest_score(self, agent: Dict, event: Dict) -> float:
        """Calculate interest score for an agent for a specific event."""
        event_type = event['type'].lower()
        event_config = self.event_types[event_type]
        
        # Start with base interest
        interest = event_config['base_interest']

        # Age factor
        age = agent['demographics']['age']
        if event_type == "sports":
            for age_check, factor in event_config['age_factors']:
                if age_check(age):
                    interest *= factor
                    break
                    
            # Sex factor for sports
            sex = agent['demographics']['gender'].upper()
            interest *= event_config['sex_factors'].get(sex, 1.0)
            
        elif event_type == "entertainment":
            for age_check, factor in event_config['age_factors']:
                if age_check(age):
                    interest *= factor
                    break
                    
            # Income factor for entertainment
            income_level = agent['demographics']['income_level']
            # Convert income level to percentile (this is a simplified conversion)
            income_percentile = {
                "Low": 20,
                "Medium": 50,
                "High": 90
            }.get(income_level, 50)
            interest *= event_config['income_factor'](income_percentile)

        # Distance factor - Updated coordinate extraction logic
        try:
            with open('../data/route_info.json', 'r') as f:
                route_info = json.load(f)
                agent_info = next((info for info in route_info if info['agent_id'] == agent['id']), None)
                
                if agent_info and 'poi_sequence' in agent_info and agent_info['poi_sequence']:
                    # Try to get coordinates from the first POI in sequence
                    first_poi = agent_info['poi_sequence'][0]
                    if 'edge' in first_poi:
                        # Load POI coordinates from pois.add.xml
                        try:
                            import xml.etree.ElementTree as ET
                            tree = ET.parse('../poi/pois.add.xml')
                            root = tree.getroot()
                            
                            # Find POI with matching edge
                            for poi in root.findall('poi'):
                                if poi.get('edge') == first_poi['edge']:
                                    agent_lat = float(poi.get('lat'))
                                    agent_lon = float(poi.get('lon'))
                                    break
                            else:
                                # Default to Westwood center if POI not found
                                agent_lat, agent_lon = 34.0689, -118.4452
                        except Exception as e:
                            print(f"Error loading POI coordinates: {e}")
                            agent_lat, agent_lon = 34.0689, -118.4452
                    else:
                        # Default to Westwood center if edge not found
                        agent_lat, agent_lon = 34.0689, -118.4452
                else:
                    # Default to Westwood center if no POI sequence
                    agent_lat, agent_lon = 34.0689, -118.4452
                    
        except Exception as e:
            print(f"Error loading route info: {e}")
            # Use default coordinates if unable to load
            agent_lat, agent_lon = 34.0689, -118.4452  # Default to Westwood center

        dist_km = self.haversine_distance(agent_lat, agent_lon, event['lat'], event['lon'])
        interest *= self.calculate_distance_factor(dist_km)

        return interest

    def select_interested_agents(self, agents: List[Dict], event: Dict, capacity: int) -> List[Dict]:
        """Select the top interested agents based on event capacity."""
        # Calculate interest scores for all agents (without distance factor)
        agent_scores = []
        for agent in agents:
            # Get base interest and demographic factors
            event_type = event['type'].lower()
            event_config = self.event_types[event_type]
            interest = event_config['base_interest']

            # Get demographics
            demographics = agent['demographics']
            age = demographics.get('age', 30)  # default age if not specified

            if event_type == "sports":
                # Apply age factors
                for age_check, factor in event_config['age_factors']:
                    if age_check(age):
                        interest *= factor
                        break
                        
                # Apply sex factor for sports
                sex = demographics.get('gender', '').upper()
                interest *= event_config['sex_factors'].get(sex, 1.0)
                
            elif event_type == "entertainment":
                # Apply age factors
                for age_check, factor in event_config['age_factors']:
                    if age_check(age):
                        interest *= factor
                        break
                        
                # Apply income factor
                income_level = demographics.get('income_level', 'Medium')
                income_percentile = {
                    "Low": 20,
                    "Medium": 50,
                    "High": 90
                }.get(income_level, 50)
                interest *= event_config['income_factor'](income_percentile)

            agent_scores.append((agent, interest))

        # Sort by interest score and select top agents up to capacity
        agent_scores.sort(key=lambda x: x[1], reverse=True)
        selected_agents = [agent for agent, score in agent_scores[:capacity]]

        return selected_agents

    def get_poi_coordinates(self, poi_name: str) -> Tuple[float, float]:
        """Get the coordinates of a POI by name."""
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse('../poi/pois.add.xml')
            root = tree.getroot()
            
            for poi in root.findall('poi'):
                if poi.get('name') == poi_name:
                    return float(poi.get('lat')), float(poi.get('lon'))
            
            # Return Westwood center coordinates if POI not foundroute_info_road_closures
            return 34.0689, -118.4452
        except Exception as e:
            print(f"Error getting POI coordinates: {e}")
            return 34.0689, -118.4452

    def handle_affected_agents(self, agents: List[Dict], event: Dict, activity_modifier, prompt: str) -> Dict[str, List[str]]:
        """Modify agents' routes to include the event using parallel processing when possible."""
        try:
            # Prepare data for batch processing
            agent_data_list = []
            
            # Convert event time to quarters (15-minute blocks)
            try:
                start_time = event.get('start_time', '12:00')
                duration = event.get('duration', 2)
                start_hour = int(start_time.split(':')[0])
                start_quarters = start_hour * 4  # Convert hours to quarters
                duration_quarters = duration * 4  # Convert hours to quarters
            except:
                # Default to noon, 2 hours
                start_quarters = 48  # 12:00
                duration_quarters = 8  # 2 hours
            
            for agent in agents:
                # Get current activity chain
                current_chain = [poi['name'] for poi in agent['route_info']['poi_sequence']]
                print(f"Current chain for agent {agent['id']}: {current_chain}")
                
                # Get timing information for current activities
                current_timing = []
                for poi in agent['route_info']['poi_sequence']:
                    start_time_sec = poi.get('start_time', 0)
                    duration_sec = poi.get('stop_duration', 3600)
                    current_timing.append({
                        'name': poi['name'],
                        'start_quarter': start_time_sec // 900,  # Convert seconds to quarters
                        'duration_quarters': duration_sec // 900  # Convert seconds to quarters
                    })
                
                agent_data_list.append({
                    'agent_id': agent['id'],
                    'current_chain': current_chain,
                    'current_timing': current_timing,
                    'prompt': prompt,
                    'vehicle_data': {
                        **agent,
                        'event_timing': {
                            'start_quarter': start_quarters,
                            'duration_quarters': duration_quarters,
                            'start_time': start_time,
                            'duration_hours': duration
                        }
                    },
                    'traffic_info': {}  # Empty for events
                })
            
            # Process all affected agents in parallel if we have multiple agents
            if len(agent_data_list) > 1 and hasattr(activity_modifier, 'modify_activity_chains_parallel'):
                print(f"Processing {len(agent_data_list)} agents in parallel for event at {event['location']}...")
                return activity_modifier.modify_activity_chains_parallel(agent_data_list)
            
            # Fallback to sequential processing for single agent or if parallel method is not available
            results = {}
            for data in agent_data_list:
                agent_id = data['agent_id']
                try:
                    new_chain, durations = activity_modifier.modify_activity_chain_with_llm(
                        agent_id,
                        data['current_chain'],
                        data['prompt'],
                        data['vehicle_data'],
                        data['traffic_info']
                    )
                    
                    if new_chain:
                        print(f"Received new chain for agent {agent_id}: {new_chain}")
                        results[agent_id] = (new_chain, durations)
                    else:
                        print(f"Warning: LLM returned no route for agent {agent_id}")
                        results[agent_id] = (data['current_chain'], [])  # Keep original
                except Exception as e:
                    print(f"Error modifying route for agent {agent_id}: {e}")
                    results[agent_id] = (data['current_chain'], [])  # Keep original in case of error
            
            return results
                
        except Exception as e:
            print(f"Error in handle_affected_agents: {e}")
            return {}