import xml.etree.ElementTree as ET
import json
from .activity_chain_modifier import ActivityChainModifier
import traci
import sumolib
import pyproj
import math

class RoadClosureHandler:
    def __init__(self):
        self.closed_edges = set()
        self.pois = self.load_pois()
        self.net = sumolib.net.readNet('../sumo_config/westwood.net.xml')
        
    def load_pois(self):
        """Load POIs from XML file"""
        try:
            poi_path = '../poi/pois.add.xml'
            tree = ET.parse(poi_path)
            root = tree.getroot()
            
            pois = []
            for poi in root.findall('poi'):
                pois.append({
                    'id': poi.get('id'),
                    'name': poi.get('name', poi.get('id')),
                    'lat': float(poi.get('lat', 0)),
                    'lon': float(poi.get('lon', 0)),
                    'edge': poi.get('edge', ''),
                    'type': poi.get('type', 'unknown')
                })
            return pois
        except Exception as e:
            print(f"Error loading POIs: {e}")
            return []

    def close_roads(self, edge_ids):
        """Close specified road edges and identify affected POIs"""
        affected_pois = set()
        
        for edge_id in edge_ids:
            if edge_id not in self.closed_edges:
                try:
                    # Close the edge in SUMO
                    traci.edge.setDisallowed(edge_id, ["all"])
                    self.closed_edges.add(edge_id)
                    print(f"Closed edge: {edge_id}")
                    
                    # Find POIs on this edge
                    edge_pois = [poi['name'] for poi in self.pois if poi['edge'] == edge_id]
                    affected_pois.update(edge_pois)
                    
                except traci.exceptions.TraCIException as e:
                    print(f"Error closing edge {edge_id}: {e}")
                    continue
        
        return list(affected_pois)

    def reopen_roads(self, edge_ids=None):
        """Reopen specified roads or all closed roads if none specified"""
        try:
            edges_to_reopen = edge_ids if edge_ids else list(self.closed_edges)
            
            for edge_id in edges_to_reopen:
                if edge_id in self.closed_edges:
                    try:
                        traci.edge.setAllowed(edge_id, ["all"])
                        self.closed_edges.remove(edge_id)
                        print(f"Reopened edge: {edge_id}")
                    except traci.exceptions.TraCIException as e:
                        print(f"Error reopening edge {edge_id}: {e}")
                        continue
            return True
        except Exception as e:
            print(f"Error reopening roads: {e}")
            return False

    def find_nearby_pois(self, edge_id, max_distance=500):
        """Find POIs that are near a given edge but not on it"""
        try:
            # Get the coordinates of the edge
            edge = self.net.getEdge(edge_id)
            edge_coords = edge.getShape()
            
            # Network offset constants
            net_offset_x = -365398.86
            net_offset_y = -3768588.46
            
            # Set up coordinate transformers
            utm_proj = pyproj.Proj("+proj=utm +zone=11 +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
            wgs84_proj = pyproj.Proj("+proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs")
            transformer = pyproj.Transformer.from_proj(wgs84_proj, utm_proj)
            
            nearby_pois = []
            for poi in self.pois:
                if poi['edge'] == edge_id:
                    continue
                
                try:
                    # Convert POI coordinates
                    poi_x, poi_y = transformer.transform(poi['lon'], poi['lat'])
                    poi_x += net_offset_x
                    poi_y += net_offset_y
                    
                    # Calculate minimum distance to edge
                    min_distance = float('inf')
                    for i in range(len(edge_coords) - 1):
                        distance = sumolib.geomhelper.distancePointToLine(
                            (poi_x, poi_y),
                            edge_coords[i],
                            edge_coords[i + 1]
                        )
                        min_distance = min(min_distance, distance)
                    
                    if min_distance <= max_distance:
                        nearby_pois.append({
                            'name': poi['name'],
                            'type': poi['type'],
                            'distance': min_distance
                        })
                except Exception as e:
                    print(f"Error processing POI {poi['name']}: {e}")
                    continue
            
            # Sort by distance
            nearby_pois.sort(key=lambda x: x['distance'])
            return nearby_pois
            
        except Exception as e:
            print(f"Error finding nearby POIs: {e}")
            return []

    def find_affected_agents(self, route_info, affected_pois, closed_edges, current_vehicles):
        """Find agents affected by road closures or POI changes"""
        affected_agents = {}
        max_current_id = max([int(v.split('_')[1]) for v in current_vehicles if v.startswith('agent_')], default=0)
        print(f"Max current ID: {max_current_id}")
        
        for agent_info in route_info:
            agent_id = agent_info['agent_id']
            
            if not agent_id.startswith('agent_'):
                continue
            
            try:
                agent_id_num = int(agent_id.split('_')[1])
                is_pending = agent_id_num > max_current_id
            except (IndexError, ValueError):
                continue
            
            poi_sequence = [poi['name'] for poi in agent_info['poi_sequence']]
            poi_edges = [poi['edge'] for poi in agent_info['poi_sequence']]
            
            affected_pois_for_agent = [poi for poi in poi_sequence if poi in affected_pois]
            affected_by_closed_edges = any(edge in closed_edges for edge in poi_edges)
            
            if affected_pois_for_agent or affected_by_closed_edges:
                try:
                    if not is_pending:
                        current_edge = traci.vehicle.getRoadID(agent_id)
                        route = traci.vehicle.getRoute(agent_id)
                        route_index = traci.vehicle.getRouteIndex(agent_id)
                    else:
                        current_edge = poi_edges[0]
                        route = []
                        route_index = 0
                    
                    affected_agents[agent_id] = {
                        'current_edge': current_edge,
                        'route': route,
                        'route_index': route_index,
                        'affected_pois': affected_pois_for_agent,
                        'closed_edges': [edge for edge in poi_edges if edge in closed_edges],
                        'current_chain': poi_sequence,
                        'demographics': agent_info.get('demographics', {}),
                        'is_pending': is_pending
                    }
                    print(f"Agent {agent_id} affected by closure. Status: {'Pending' if is_pending else 'Active'}")
                    
                except traci.exceptions.TraCIException as e:
                    print(f"Error getting route info for agent {agent_id}: {e}")
                    continue
        
        return affected_agents

    def get_closed_edges(self):
        """Return the set of currently closed edges"""
        return self.closed_edges

    def is_edge_closed(self, edge_id):
        """Check if a specific edge is closed"""
        return edge_id in self.closed_edges

    def handle_affected_agents(self, affected_pois, closed_edges, situation, activity_modifier, change_agent_route):
        """Handle agents affected by road closures"""
        try:
            # Load route information for all agents
            with open('../data/route_info.json', 'r') as f:
                route_info = json.load(f)

            # Get current vehicles and find affected agents
            current_vehicles = set(traci.vehicle.getIDList())
            affected_agents = self.find_affected_agents(
                route_info, 
                affected_pois, 
                closed_edges, 
                current_vehicles
            )

            # Filter agents to only include those with IDs less than 200
            affected_agents = {
                k: v for k, v in affected_agents.items() 
                if k.startswith('agent_') and int(k.split('_')[1]) < 10000
            }
            
            # Process affected agents
            if affected_agents:
                print(f"Found {len(affected_agents)} affected agents")
                self.process_affected_agents(affected_agents, situation, activity_modifier, change_agent_route)
            else:
                print("No agents affected by the road closure")

        except Exception as e:
            print(f"Error handling affected agents: {e}")

    def process_affected_agents(self, affected_agents, situation, activity_modifier, change_agent_route):
        """Process each affected agent with the LLM"""
        try:
            # Load route information for all agents
            with open('../data/route_info.json', 'r') as f:
                route_info = json.load(f)
            
            # Get traffic information
            traffic_info = self.get_traffic_info()
            
            # Prepare data for batch processing
            agent_data_list = []
            for agent_id, agent_data in affected_agents.items():
                # Get the full route info for this agent
                agent_route_info = next((info for info in route_info if info['agent_id'] == agent_id), None)
                if not agent_route_info:
                    print(f"Warning: No route info found for agent {agent_id}")
                    continue
                
                agent_data_list.append({
                    'agent_id': agent_id,
                    'current_chain': agent_data['current_chain'],
                    'prompt': situation,
                    'vehicle_data': {
                        'current_edge': agent_data['current_edge'],
                        'route': agent_data['route'],
                        'route_index': agent_data['route_index'],
                        'route_info': {
                            'demographics': agent_data['demographics'],
                            'poi_sequence': agent_route_info['poi_sequence']
                        }
                    },
                    'traffic_info': traffic_info
                })
            
            # Process all affected agents in parallel
            print(f"Processing {len(agent_data_list)} affected agents in parallel...")
            results = activity_modifier.modify_activity_chains_parallel(agent_data_list)
            
            # Apply the results
            success_count = 0
            for agent_id, (new_chain, durations) in results.items():
                if new_chain:
                    success = change_agent_route(agent_id, new_chain, durations)
                    if success:
                        success_count += 1
                    print(f"New chain for {agent_id}: {new_chain}")
                    print(f"Durations: {[d//900 for d in durations]} quarters")
                    print(f"Route update for agent {agent_id}: {'Success' if success else 'Failed'}")
            
            print(f"Successfully updated {success_count}/{len(results)} agent routes")
            
        except Exception as e:
            print(f"Error in parallel processing of affected agents: {e}")
            # Fallback to sequential processing
            self._sequential_process_agents(affected_agents, situation, activity_modifier, change_agent_route, traffic_info)
            
    def _sequential_process_agents(self, affected_agents, situation, activity_modifier, change_agent_route, traffic_info=None):
        """Fallback method for sequential processing"""
        try:
            # Load route information for all agents
            with open('../data/route_info.json', 'r') as f:
                route_info = json.load(f)
                
            if traffic_info is None:
                traffic_info = self.get_traffic_info()
                
            for agent_id, agent_data in affected_agents.items():
                try:
                    # Get the full route info for this agent
                    agent_route_info = next((info for info in route_info if info['agent_id'] == agent_id), None)
                    if not agent_route_info:
                        print(f"Warning: No route info found for agent {agent_id}")
                        continue
                    
                    # Use activity modifier with the generated prompt
                    new_chain, durations = activity_modifier.modify_activity_chain_with_llm(
                        agent_id,
                        agent_data['current_chain'],
                        situation,
                        {
                            'current_edge': agent_data['current_edge'],
                            'route': agent_data['route'],
                            'route_index': agent_data['route_index'],
                            'route_info': {
                                'demographics': agent_data['demographics'],
                                'poi_sequence': agent_route_info['poi_sequence']
                            }
                        },
                        traffic_info
                    )

                    if new_chain:
                        # Use the passed change_agent_route function with durations
                        success = change_agent_route(agent_id, new_chain, durations)
                        print(f"New chain: {new_chain}")
                        print(f"Durations: {[d//900 for d in durations]} quarters")
                        print(f"Route update for agent {agent_id}: {'Success' if success else 'Failed'}")

                except Exception as e:
                    print(f"Error processing agent {agent_id}: {e}")
                    
        except Exception as e:
            print(f"Error loading route info: {e}")

    def get_traffic_info(self):
        """Get basic traffic information (occupancy and congestion status) for all edges"""
        traffic_info = {}
        try:
            edges = traci.edge.getIDList()
            
            for edge in edges:
                try:
                    occupancy = traci.edge.getLastStepOccupancy(edge)
                    is_congested = occupancy > 0.5
                    
                    # Only include edges with significant traffic
                    if is_congested or occupancy > 0.3:
                        traffic_info[edge] = {
                            'occupancy': occupancy,
                            'is_congested': is_congested
                        }
                except traci.exceptions.TraCIException:
                    continue
                
        except Exception as e:
            print(f"Error getting traffic info: {e}")
        
        return traffic_info 