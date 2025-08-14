import os
import sys
# Add parent directory to path for utilities imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import traci
import json
import time
from threading import Thread
import xml.etree.ElementTree as ET
import socket
import threading
import sumolib
import random
import pyproj
from utilities.road_closure_handler import RoadClosureHandler
from utilities.prompt_manager import PromptManager
from utilities.activity_chain_modifier import ActivityChainModifier
from utilities.event_handler import EventHandler
from datetime import datetime

class SUMOController:
    def __init__(self):
        self.running = True
        self.pois = self.load_pois()
        self.start_time = 20090  # 8:00 AM in seconds
        self.end_time = 86400   # 12:00 PM in seconds
        self.total_steps = self.end_time - self.start_time
        self.viewer_socket = None
        self.server_socket = None
        self.start_socket_server()
        
        # Initialize handlers
        self.road_closure_handler = RoadClosureHandler()
        self.event_handler = EventHandler()
        self.prompt_manager = PromptManager()
        self.activity_modifier = ActivityChainModifier()
        self.closed_edges = set()  # Keep track of closed edges
    
    def load_pois(self):
        try:
            poi_path = '../poi/pois.add.xml'
            tree = ET.parse(poi_path)
            root = tree.getroot()
            
            pois = {}
            for poi in root.findall('poi'):
                poi_id = poi.get('id')
                poi_name = poi.get('name', poi_id)
                poi_edge = poi.get('edge', '')
                
                pois[poi_id] = {
                    'name': poi_name,
                    'edge': poi_edge
                }
            
            return pois
        except Exception as e:
            print(f"Error loading POIs from XML: {e}")
            return {}

    def start_socket_server(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(('localhost', 8814))
        self.server_socket.listen(1)
        
        def accept_connections():
            while self.running:
                try:
                    client, addr = self.server_socket.accept()
                    self.viewer_socket = client
                    print("Viewer connected")
                except:
                    break
            
            # Clean up when thread ends
            if self.server_socket:
                self.server_socket.close()
        
        threading.Thread(target=accept_connections, daemon=True).start()

    def send_to_viewer(self, data):
        if self.viewer_socket:
            try:
                # Ensure we have the required fields
                if 'time' not in data or 'vehicles' not in data:
                    print("Missing required data fields")
                    return

                # Always include time, vehicle list, and closed edges for basic functionality
                filtered_data = {
                    'time': data['time'],
                    'vehicles': data['vehicles'],  # Keep full vehicle list
                    'closed_edges': list(self.closed_edges),  # Always include closed edges
                    'vehicle_data': {}
                }

                # Only process detailed data for the tracked vehicle if one is being tracked
                if 'tracked_agent' in data and data['tracked_agent']:
                    tracked_id = data['tracked_agent']
                    
                    if tracked_id in data['vehicle_data']:
                        filtered_data['vehicle_data'][tracked_id] = data['vehicle_data'][tracked_id]
                        
                        # Initialize route_source as None
                        route_source = None
                        vehicle_info = None

                        # First try to get LLM-modified route info
                        try:
                            with open('../data/route_info_llm_modified.json', 'r') as f:
                                modified_routes = json.load(f)
                                vehicle_info = next((info for info in modified_routes if info['agent_id'] == tracked_id), None)
                                if vehicle_info:
                                    filtered_data['vehicle_data'][tracked_id]['route_info'] = vehicle_info
                                    route_source = 'LLM Modified'
                        except (FileNotFoundError, json.JSONDecodeError):
                            pass

                        # If no modified route found, try original route info
                        if not vehicle_info:
                            try:
                                with open('../data/route_info.json', 'r') as f:
                                    route_info = json.load(f)
                                    vehicle_info = next((info for info in route_info if info['agent_id'] == tracked_id), None)
                                    if vehicle_info:
                                        filtered_data['vehicle_data'][tracked_id]['route_info'] = vehicle_info
                                        route_source = 'Original'
                            except Exception as e:
                                print(f"Error loading original route info: {e}")

                        # Add route source and demographics if we have route info
                        if vehicle_info:
                            filtered_data['vehicle_data'][tracked_id]['route_source'] = route_source
                            # Ensure demographics are included
                            if 'demographics' in vehicle_info:
                                filtered_data['vehicle_data'][tracked_id]['demographics'] = vehicle_info['demographics']
                            else:
                                print(f"Warning: No demographics found for {tracked_id}")

                            # Ensure POI sequence is included
                            if 'poi_sequence' in vehicle_info:
                                filtered_data['vehicle_data'][tracked_id]['poi_sequence'] = vehicle_info['poi_sequence']
                            else:
                                print(f"Warning: No POI sequence found for {tracked_id}")

                        # Add route index for tracked vehicle
                        try:
                            route_index = traci.vehicle.getRouteIndex(tracked_id)
                            filtered_data['vehicle_data'][tracked_id]['route_index'] = route_index
                        except traci.exceptions.TraCIException:
                            filtered_data['vehicle_data'][tracked_id]['route_index'] = 0

                        # Only get traffic info for edges in tracked vehicle's route
                        traffic_info = {}
                        vehicle_route = filtered_data['vehicle_data'][tracked_id].get('route', [])
                        for edge in vehicle_route:
                            try:
                                occupancy = traci.edge.getLastStepOccupancy(edge)
                                is_congested = occupancy > 0.5
                                if is_congested or occupancy > 0.3:
                                    traffic_info[edge] = {
                                        'occupancy': occupancy,
                                        'is_congested': is_congested
                                    }
                            except Exception as e:
                                continue

                        filtered_data['traffic_info'] = traffic_info

                try:
                    # Prepare the message
                    message = json.dumps(filtered_data, ensure_ascii=False) + "<<END>>"
                    
                    # Try to send the entire message at once
                    self.viewer_socket.sendall(message.encode('utf-8'))
                except socket.error as e:
                    # Silently ignore socket errors (especially common on macOS)
                    # The simulation continues to work even if viewer data can't be sent
                    pass
            
            except Exception as e:
                print(f"Error preparing data for viewer: {e}")
                self.viewer_socket = None

    def start_simulation(self):
        # Start SUMO with TraCI
        sumo_cmd = ['sumo-gui', '-c', '../sumo_config/westwood.sumocfg',
                    '--step-length', '1.0',
                    '--start', 'true',
                    '--quit-on-end', 'false',
                    '--device.rerouting.probability', '1.0',
                    '--device.rerouting.period', '30',
                    '--ignore-route-errors', 'true',
                    '--time-to-teleport', '-1']
        
        try:
            print("Starting SUMO...")
            traci.start(sumo_cmd, port=8813)
            traci.setOrder(0)
            print("Connected to SUMO")
            
            # Debug: Check initial state
            sim_time = traci.simulation.getTime()
            print(f"Initial simulation time: {sim_time}")
            routes = traci.route.getIDList()
            print(f"Available routes: {routes}")
            
            # Make sure we're at the start time
            while traci.simulation.getTime() < self.start_time:
                traci.simulationStep()
            
            # Debug: Check vehicles after reaching start time
            vehicles = traci.vehicle.getIDList()
            print(f"Vehicles at start time: {vehicles}")
            
            # Add a variable to track the highlighted vehicle
            highlighted_vehicle = None
            
            step = 0
            last_check = 0
            # Keep track of vehicles we've seen
            processed_vehicles = set()
            
            # Main simulation loop
            while self.running:
                traci.simulationStep()
                
                # Check for new vehicles
                current_vehicles = set(traci.vehicle.getIDList())
                new_vehicles = current_vehicles - processed_vehicles
                
                # Process any new vehicles
                for vehicle_id in new_vehicles:
                    try:
                        self.check_and_apply_midified_routes(vehicle_id)
                        processed_vehicles.add(vehicle_id)
                    except Exception as e:
                        print(f"Error processing new vehicle {vehicle_id}: {e}")
                
                # Remove processed vehicles that are no longer in simulation
                processed_vehicles &= current_vehicles
                
                # Debug: Print every 100 steps
                if step % 100 == 0:
                    current_time = traci.simulation.getTime()
                    vehicles = traci.vehicle.getIDList()
                    print(f"Time {current_time}: {len(vehicles)} vehicles")
                    if len(vehicles) == 0 and step < 1000:
                        print("No vehicles yet, checking simulation state...")
                        print(f"Current routes: {traci.route.getIDList()}")
                        print(f"Simulation time: {traci.simulation.getTime()}")
                        print(f"Pending vehicles: {traci.simulation.getPendingVehicles()}")
                
                # Check for updates every 50 steps
                if step - last_check >= 50:
                    self.check_destination_updates()
                    last_check = step
                    
                    # Print statistics every 1000 steps
                    if step % 1000 == 0:
                        sim_time = traci.simulation.getTime()
                        hours = int(sim_time // 3600)
                        minutes = int((sim_time % 3600) // 60)
                        seconds = int(sim_time % 60)
                        vehicles = traci.vehicle.getIDList()
                        progress = (step / self.total_steps) * 100
                        
                        print(f"Step {step}/{self.total_steps} ({progress:.1f}%) - "
                              f"Time {hours:02d}:{minutes:02d}:{seconds:02d}: "
                              f"{len(vehicles)} vehicles active")
                
                # Send vehicle data to viewer
                if self.viewer_socket:
                    vehicles = traci.vehicle.getIDList()
                    data = {
                        'time': traci.simulation.getTime(),
                        'vehicles': list(vehicles),
                        'tracked_agent': highlighted_vehicle,  # Add tracked agent info
                        'vehicle_data': {
                            vid: {
                                'position': traci.vehicle.getPosition(vid),
                                'lat_lon': traci.vehicle.getPosition3D(vid),
                                'speed': traci.vehicle.getSpeed(vid),
                                'route': traci.vehicle.getRoute(vid),
                                'current_edge': traci.vehicle.getRoadID(vid)
                            } for vid in vehicles if vid == highlighted_vehicle  # Only include tracked vehicle
                        }
                    }
                    self.send_to_viewer(data)
                    
                    # Check for commands from viewer
                    try:
                        self.viewer_socket.settimeout(0)  # Non-blocking
                        command = self.viewer_socket.recv(1024).decode()
                        
                        # Only process command if we actually received data
                        if command:
                            print(f"Received command: {command}")  # Debug print
                            if command.startswith("HIGHLIGHT:"):
                                # Reset previous highlighted vehicle
                                if highlighted_vehicle and highlighted_vehicle in vehicles:
                                    try:
                                        traci.vehicle.setColor(highlighted_vehicle, (255, 255, 255, 255))  # White
                                    except traci.exceptions.TraCIException as e:
                                        print(f"Error resetting color: {e}")
                                
                                # Highlight new vehicle
                                highlighted_vehicle = command.split(":")[1]
                                try:
                                    if highlighted_vehicle in vehicles:
                                        traci.vehicle.setColor(highlighted_vehicle, (255, 0, 0, 255))  # Red
                                        traci.gui.track(highlighted_vehicle)  # Track the vehicle
                                        traci.gui.setZoom("View #0", 3000)  # Set zoom level
                                        print(f"Successfully highlighted vehicle: {highlighted_vehicle}")
                                    else:
                                        print(f"Vehicle {highlighted_vehicle} not found in simulation")
                                except traci.exceptions.TraCIException as e:
                                    print(f"Error highlighting vehicle: {e}")
                                    highlighted_vehicle = None  # Reset if failed
                            elif command.startswith("CHANGE_ROUTE:"):
                                parts = command.split(":", 3)  # Split into up to 4 parts
                                if len(parts) >= 3:
                                    agent_id = parts[1]
                                    new_pois = parts[2].split(",")
                                    durations = None
                                    if len(parts) == 4:  # If durations are provided
                                        try:
                                            durations = [int(d) for d in parts[3].split(",")]
                                        except ValueError as e:
                                            print(f"Error parsing durations: {e}")
                                    self.change_agent_route(agent_id, new_pois, durations)
                            elif command == "GET_VEHICLES":
                                vehicles = traci.vehicle.getIDList()
                                data = {
                                    'time': traci.simulation.getTime(),
                                    'vehicles': list(vehicles),
                                    'vehicle_data': {}
                                }
                                self.send_to_viewer(data)
                            elif command == "GET_PLOT_DATA":
                                # Send all vehicle positions for density plot
                                vehicles = traci.vehicle.getIDList()
                                vehicle_data = {}
                                for vid in vehicles:
                                    try:
                                        pos = traci.vehicle.getPosition(vid)
                                        pos3d = traci.vehicle.getPosition3D(vid)
                                        print(f"Vehicle {vid} position: {pos}, pos3d: {pos3d}")
                                        vehicle_data[vid] = {
                                            'position': [pos[0], pos[1]],  # Ensure 2D coordinates
                                            'lat_lon': [pos3d[0], pos3d[1], pos3d[2]]  # Keep 3D coordinates
                                        }
                                    except traci.exceptions.TraCIException as e:
                                        print(f"Error getting position for {vid}: {e}")
                                        continue
                                
                                data = {
                                    'time': traci.simulation.getTime(),
                                    'vehicles': list(vehicles),
                                    'vehicle_data': vehicle_data
                                }
                                print(f"Sending plot data for {len(vehicle_data)} vehicles")
                                self.send_to_viewer(data)
                            elif command == "GET_ALL_VEHICLES":
                                # Send all vehicle positions for density plot with NO filtering
                                vehicles = traci.vehicle.getIDList()
                                vehicle_data = {}
                                
                                # Collect all vehicle positions without filtering
                                count = 0
                                for vid in vehicles:
                                    try:
                                        pos = traci.vehicle.getPosition(vid)
                                        vehicle_data[vid] = {
                                            'position': [pos[0], pos[1]]
                                        }
                                        count += 1
                                    except traci.exceptions.TraCIException as e:
                                        continue
                                    except Exception as e:
                                        print(f"Error getting position for {vid}: {e}")
                                        continue
                                
                                # Create complete data with ALL vehicles
                                data = {
                                    'time': traci.simulation.getTime(),
                                    'vehicles': list(vehicles),
                                    'vehicle_data': vehicle_data,  # Include ALL vehicle data
                                    'message_type': 'density_data',  # Tag the message type
                                    'vehicle_count': count  # Add explicit count for verification
                                }
                                
                                # Prepare message
                                try:
                                    # Convert to JSON
                                    json_message = json.dumps(data, ensure_ascii=False)
                                    
                                    # Add specific markers with clear separation
                                    full_message = "<<START>>" + json_message + "<<END>>"
                                    
                                    # Send in one operation
                                    self.viewer_socket.sendall(full_message.encode('utf-8'))
                                    print(f"Sent density data for {count} vehicles directly")
                                except Exception as e:
                                    print(f"Error sending density data: {e}")
                            elif command.startswith("GET_VEHICLE_POS:"):
                                # Get position for a specific vehicle
                                vehicle_id = command.split(":")[1]
                                try:
                                    pos = traci.vehicle.getPosition(vehicle_id)
                                    data = {
                                        'position': [pos[0], pos[1]]
                                    }
                                    # Send directly
                                    message = json.dumps(data, ensure_ascii=False) + "<<END>>"
                                    self.viewer_socket.sendall(message.encode('utf-8'))
                                except Exception as e:
                                    # Send empty data on error
                                    self.viewer_socket.sendall("{\"error\": \"" + str(e) + "\"}<<END>>".encode('utf-8'))
                            elif command.startswith("CLOSE_ROADS:"):
                                edge_ids = command.split(":")[1].split(",")
                                self.handle_road_closure(edge_ids)
                            elif command.startswith("REOPEN_ROADS:"):
                                edge_ids = command.split(":")[1].split(",")
                                self.handle_road_opening(edge_ids)
                            elif command == "REOPEN_ALL_ROADS":
                                print("Received reopen all roads command")
                                self.handle_road_opening()
                            elif command.startswith("CREATE_EVENT:"):
                                try:
                                    # Extract event data from command
                                    event_json = command.split("CREATE_EVENT:", 1)[1].strip()
                                    event_data = json.loads(event_json)
                                    # Process event directly without using a thread
                                    self.handle_event_creation(event_data)
                                except Exception as e:
                                    print(f"Error processing event creation command: {e}")
                    except socket.error as e:
                        # Silently ignore socket errors (especially common on macOS)
                        # The simulation continues to work even if viewer communication fails
                        pass
                    except Exception as e:
                        print(f"Error processing command: {e}")
                
                step += 1
                time.sleep(0.01)
                
        finally:
            traci.close()
    
    def check_destination_updates(self):
        """Check and update vehicle destinations"""
        try:
            vehicles = traci.vehicle.getIDList()
            
            # Prepare data to send
            data = {
                'time': traci.simulation.getTime(),
                'vehicle_data': {}
            }
            
            for vehicle_id in vehicles:
                try:
                    # Get vehicle route including internal edges
                    route = traci.vehicle.getRoute(vehicle_id)
                    route_index = traci.vehicle.getRouteIndex(vehicle_id)
                    current_edge = traci.vehicle.getRoadID(vehicle_id)
                    
                    # Get vehicle position
                    x, y = traci.vehicle.getPosition(vehicle_id)
                    lon, lat = traci.simulation.convertGeo(x, y)
                    
                    
                    # Store vehicle data
                    data['vehicle_data'][vehicle_id] = {
                        'edge': current_edge,
                        'route': route,
                        'route_index': route_index,
                        'position': [x, y],
                        'lat_lon': [lat, lon, 0.0],
                        'speed': traci.vehicle.getSpeed(vehicle_id)
                    }
                    
                except traci.exceptions.TraCIException:
                    continue
            
            # Send updates to viewer
            self.send_to_viewer(data)
            
        except traci.exceptions.TraCIException:
            pass

    def cleanup(self):
        self.running = False
        if self.viewer_socket:
            try:
                self.viewer_socket.close()
            except:
                pass
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass

    def change_agent_route(self, agent_id, new_poi_sequence, durations=None):
        """Change an agent's route to visit a new sequence of POIs"""
        try:
            # Load POIs from XML
            tree = ET.parse('../poi/pois.add.xml')
            pois = {poi.get('name'): poi.get('edge') for poi in tree.getroot().findall('poi')}
            
            # Get edges for the new POI sequence
            stop_edges = []
            for poi_name in new_poi_sequence:
                if poi_name in pois:
                    stop_edges.append(pois[poi_name])
                else:
                    print(f"Warning: POI '{poi_name}' not found")
            
            if not stop_edges:
                print(f"No valid POIs found in sequence: {new_poi_sequence}")
                return False
            
            # Get demographics from original route info
            demographics = None
            try:
                with open('../data/route_info.json', 'r') as f:
                    route_info = json.load(f)
                    for info in route_info:
                        if info['agent_id'] == agent_id and 'demographics' in info:
                            demographics = info['demographics']
                            break
            except Exception as e:
                print(f"Warning: Could not load demographics: {e}")

            # Check if vehicle exists in simulation
            vehicle_exists = agent_id in traci.vehicle.getIDList()
            
            if vehicle_exists:
                # Handle existing vehicle
                try:
                    # Get current edge and state
                    current_edge = traci.vehicle.getRoadID(agent_id)
                    current_route = traci.vehicle.getRoute(agent_id)
                    route_index = traci.vehicle.getRouteIndex(agent_id)
                    
                    
                    # If on internal edge, get the next real edge
                    if current_edge.startswith(':'):
                        if route_index + 1 < len(current_route):
                            current_edge = current_route[route_index + 1]
                            print(f"Adjusted current edge (from internal): {current_edge}")
                    
                    # Find the current destination in the route
                    current_destination = None
                    for i in range(route_index, len(current_route)):
                        if current_route[i] in stop_edges:
                            current_destination = current_route[i]
                            break
                    
                    print(f"Current destination: {current_destination}")
                    
                    # If we found the current destination, only modify the route after it
                    if current_destination:
                        # Find the index of the current destination in the new sequence
                        dest_index = stop_edges.index(current_destination)
                    
                        # Keep the route up to the current destination
                        complete_route = list(current_route[:route_index + 1])
                        
                        # Add routes between remaining stops
                        for i in range(dest_index, len(stop_edges) - 1):
                            route = traci.simulation.findRoute(stop_edges[i], stop_edges[i + 1])
                            if route and route.edges:
                                # Ensure the route starts from the current edge
                                if i == dest_index and complete_route and complete_route[-1] != route.edges[0]:
                                    # Find a connecting route
                                    connecting_route = traci.simulation.findRoute(complete_route[-1], route.edges[0])
                                    if connecting_route and connecting_route.edges:
                                        complete_route = complete_route + list(connecting_route.edges[1:])
                                complete_route = complete_route + list(route.edges[1:])
                    else:
                        # If we can't find the current destination, start from current position
                        complete_route = []
                        if current_edge and not current_edge.startswith(':'):
                            complete_route.append(current_edge)
                        
                        # Add route from current edge to first stop
                        if current_edge and stop_edges:
                            route = traci.simulation.findRoute(current_edge, stop_edges[0])
                            if route and route.edges:
                                if route.edges[0] == current_edge:
                                    complete_route = complete_route + list(route.edges[1:])
                                else:
                                    # Find a connecting route
                                    connecting_route = traci.simulation.findRoute(current_edge, route.edges[0])
                                    if connecting_route and connecting_route.edges:
                                        complete_route = complete_route + list(connecting_route.edges[1:])
                                    complete_route = complete_route + list(route.edges)
                        
                        # Add routes between subsequent stops
                        for i in range(len(stop_edges) - 1):
                            route = traci.simulation.findRoute(stop_edges[i], stop_edges[i + 1])
                            if route and route.edges:
                                # Ensure the route connects properly
                                if complete_route and complete_route[-1] != route.edges[0]:
                                    connecting_route = traci.simulation.findRoute(complete_route[-1], route.edges[0])
                                    if connecting_route and connecting_route.edges:
                                        complete_route = complete_route + list(connecting_route.edges[1:])
                                complete_route = complete_route + list(route.edges[1:])
                    
                    if not complete_route:
                        print(f"Could not find valid route for {agent_id}")
                        return False
                    
                    # Update route in SUMO
                    try:
                        # Clear existing stops
                        try:
                            # Get current edge and ensure it's in the temporary route
                            current_edge = traci.vehicle.getRoadID(agent_id)
                            if current_edge.startswith(':'):
                                # If on internal edge, get the next real edge
                                route_index = traci.vehicle.getRouteIndex(agent_id)
                                current_route = traci.vehicle.getRoute(agent_id)
                                if route_index + 1 < len(current_route):
                                    current_edge = current_route[route_index + 1]
                            
                            # Create temporary route that includes current edge
                            temp_route = [current_edge]
                            traci.vehicle.setRoute(agent_id, temp_route)
                            
                            # Now set the complete route
                            traci.vehicle.setRoute(agent_id, complete_route)
                            
                            if traci.vehicle.isStopped(agent_id):
                                traci.vehicle.setStop(
                                    agent_id,
                                    complete_route[0],
                                    duration=0,
                                    flags=0
                                )
                        except traci.exceptions.TraCIException as e:
                            print(f"Warning: Could not clear stops for {agent_id}: {e}")
                        
                        # Add stops for current destination and unvisited POIs
                        if current_destination:
                            # Add stop for current destination first
                            current_stop_index = stop_edges.index(current_destination)
                            current_duration = 900  # Default 15 minutes
                            if durations and current_stop_index < len(durations):
                                current_duration = durations[current_stop_index]
                            
                            remaining_stops = list(zip(
                                stop_edges[current_stop_index + 1:],
                                durations[current_stop_index + 1:] if durations else [900] * (len(stop_edges) - current_stop_index - 1)
                            ))
                            all_stops = [(current_destination, current_duration)] + remaining_stops
                        else:
                            # Add stops for all destinations
                            all_stops = list(zip(
                                stop_edges,
                                durations if durations else [900] * len(stop_edges)
                            ))
                        
                        print(f"Adding stops for {agent_id}: {all_stops}")
                        for edge, duration in all_stops:
                            try:
                                # Find suitable lane for stopping
                                lane_index = -1
                                lane_count = traci.edge.getLaneNumber(edge)
                                
                                for i in range(lane_count):
                                    lane_id = f"{edge}_{i}"
                                    allowed = traci.lane.getAllowed(lane_id)
                                    if not allowed or "passenger" in allowed:
                                        lane_index = i
                                        break
                                
                                if lane_index == -1:
                                    print(f"Warning: No suitable lane found for stopping on edge {edge}")
                                    continue
                                
                                # Calculate stop position
                                edge_length = traci.lane.getLength(f"{edge}_{lane_index}")
                                stop_pos = edge_length * random.random()  # Random position along the edge
                                
                                traci.vehicle.setStop(
                                    agent_id,
                                    edge,
                                    pos=stop_pos,
                                    laneIndex=lane_index,
                                    duration=duration,
                                    flags=1  # parking=true
                                )
                            except traci.exceptions.TraCIException as e:
                                print(f"Warning: Could not set stop at edge {edge}: {e}")
                        
                        # Save the modified route to route_info_llm_modified.json
                        try:
                            modified_route_info = {
                                'agent_id': agent_id,
                                'poi_sequence': [
                                    {
                                        'name': poi_name,
                                        'edge': edge,
                                        'order': i + 1,
                                        'activity_type': self.get_poi_activity_type(poi_name),
                                        'stop_duration': duration
                                        
                                    }
                                    for i, ((poi_name, edge), duration) in enumerate(zip(
                                        zip(new_poi_sequence, stop_edges),
                                        durations if durations else [900] * len(stop_edges)
                                    ))
                                ],
                                'complete_route': complete_route
                            }
                            
                            if demographics:
                                modified_route_info['demographics'] = demographics
                            
                            # Try to load existing modified routes
                            try:
                                with open('../data/route_info_llm_modified.json', 'r') as f:
                                    existing_routes = json.load(f)
                            except (FileNotFoundError, json.JSONDecodeError):
                                existing_routes = []
                            
                            # Remove any existing entry for this agent
                            existing_routes = [r for r in existing_routes if r.get('agent_id') != agent_id]
                            
                            # Add the new route info
                            existing_routes.append(modified_route_info)
                            
                            # Save back to file
                            with open('../data/route_info_llm_modified.json', 'w') as f:
                                json.dump(existing_routes, f, indent=2)
                            
                            print(f"Saved modified route for {agent_id} to route_info_llm_modified.json")
                        except Exception as e:
                            print(f"Error saving modified route to file: {e}")
                        
                    except traci.exceptions.TraCIException as e:
                        print(f"Error updating route for {agent_id}: {e}")
                        return False
                    
                except Exception as e:
                    print(f"Error handling existing vehicle {agent_id}: {e}")
                    return False
            else:
                # Vehicle hasn't entered simulation yet, store for later
                try:
                    # Create complete route for pending vehicle
                    complete_route = []
                    if len(stop_edges) > 0:
                        complete_route.append(stop_edges[0])
                        
                        # Add routes between stops
                        for i in range(len(stop_edges) - 1):
                            route = traci.simulation.findRoute(stop_edges[i], stop_edges[i + 1])
                            if route and route.edges:
                                complete_route.extend(list(route.edges[1:]))
                    
                    # Create stop sequence
                    stops = []
                    for i, edge in enumerate(stop_edges):
                        # Calculate stop position
                        lane_index = 0
                        lane_id = f"{edge}_{lane_index}"
                        edge_length = traci.lane.getLength(lane_id)
                        stop_pos = edge_length * random.random()  # Random position along the edge
                        
                        # Use provided duration if available, otherwise default to 15 minutes
                        duration = durations[i] if durations and i < len(durations) else 900
                        
                        stops.append({
                            'edge': edge,
                            'endPos': stop_pos,
                            'laneIndex': lane_index,
                            'duration': duration
                        })
                
                    
                    # Save to route_info_llm_modified.json
                    try:
                        modified_route_info = {
                            'agent_id': agent_id,
                            'poi_sequence': [
                                {
                                    'name': poi_name,
                                    'edge': edge,
                                    'order': i + 1,
                                    'activity_type': self.get_poi_activity_type(poi_name),
                                    'stop_duration': duration
                                }
                                for i, ((poi_name, edge), duration) in enumerate(zip(
                                    zip(new_poi_sequence, stop_edges),
                                    durations if durations else [900] * len(stop_edges)
                                ))
                            ],
                            'complete_route': complete_route
                        }
                        
                        if demographics:
                            modified_route_info['demographics'] = demographics
                        
                        # Try to load existing modified routes
                        try:
                            with open('../data/route_info_llm_modified.json', 'r') as f:
                                existing_routes = json.load(f)
                        except (FileNotFoundError, json.JSONDecodeError):
                            existing_routes = []
                        
                        # Remove any existing entry for this agent
                        existing_routes = [r for r in existing_routes if r.get('agent_id') != agent_id]
                        
                        # Add the new route info
                        existing_routes.append(modified_route_info)
                        
                        # Save back to file
                        with open('../data/route_info_llm_modified.json', 'w') as f:
                            json.dump(existing_routes, f, indent=2)
                        
                        print(f"Saved pending route for {agent_id} to route_info_llm_modified.json")
                    except Exception as e:
                        print(f"Error saving pending route to file: {e}")
                    
                except Exception as e:
                    print(f"Error handling pending vehicle {agent_id}: {e}")
                    return False
            
            print(f"Successfully updated route for {agent_id}")
            return True
            
        except Exception as e:
            print(f"Error changing route: {e}")
            return False

    def get_poi_activity_type(self, poi_name):
        """Get the activity type for a POI from the XML file"""
        try:
            tree = ET.parse('../poi/pois.add.xml')
            root = tree.getroot()
            for poi in root.findall('poi'):
                if poi.get('name') == poi_name:
                    return poi.get('type', 'unknown')
            return 'unknown'
        except Exception as e:
            print(f"Error getting activity type for POI {poi_name}: {e}")
            return 'unknown'

    def handle_road_closure(self, edge_ids):
        """Handle road closures and affected agents"""
        try:
            # Use road closure handler to manage the closure
            affected_pois = self.road_closure_handler.close_roads(edge_ids)
            self.closed_edges = self.road_closure_handler.get_closed_edges()  # Update local closed edges set
            
            if affected_pois:
                print(f"POIs affected by road closure: {affected_pois}")
                
                # Find alternative POIs using road closure handler
                alternative_pois = {}
                for edge_id in edge_ids:
                    nearby = self.road_closure_handler.find_nearby_pois(edge_id)
                    if nearby:
                        alternative_pois[edge_id] = nearby
                
                # Generate alternatives string for prompt
                alternatives_msg = []
                for edge_id, pois in alternative_pois.items():
                    pois_str = ", ".join([
                        f"{p['name']} ({p['type']}, {p['distance']:.0f}m away)"
                        for p in pois[:3]
                    ])
                    if pois_str:
                        alternatives_msg.append(f"Near {edge_id}: {pois_str}")
                
                # Use prompt manager to generate situation description
                situation = self.prompt_manager.road_closure_prompt(
                    edge_ids,
                    affected_pois,
                    " ".join(alternatives_msg)
                )
                
                # Handle affected agents with the generated prompt using road closure handler
                self.road_closure_handler.handle_affected_agents(
                    affected_pois, 
                    edge_ids, 
                    situation,
                    self.activity_modifier,
                    self.change_agent_route  # Pass the change_agent_route method
                )
            
            return True
        except Exception as e:
            print(f"Error closing roads: {e}")
            return False

    def handle_road_opening(self, edge_ids=None):
        """Handle road reopening - either specific roads or all closed roads"""
        try:
            if edge_ids is None:
                # Reopen all roads
                print("Reopening all closed roads")
                all_closed_edges = list(self.closed_edges.copy())
                if all_closed_edges:
                    self.road_closure_handler.reopen_roads(all_closed_edges)
                    self.closed_edges.clear()
                    print(f"Reopened {len(all_closed_edges)} roads: {all_closed_edges}")
                else:
                    print("No roads are currently closed")
            else:
                # Reopen specific roads
                print(f"Reopening specific roads: {edge_ids}")
                # Filter to only reopen roads that are actually closed
                roads_to_reopen = [edge_id for edge_id in edge_ids if edge_id in self.closed_edges]
                
                if roads_to_reopen:
                    self.road_closure_handler.reopen_roads(roads_to_reopen)
                    # Remove reopened roads from closed_edges set
                    for edge_id in roads_to_reopen:
                        self.closed_edges.discard(edge_id)
                    print(f"Reopened {len(roads_to_reopen)} roads: {roads_to_reopen}")
                else:
                    print(f"None of the specified roads were closed: {edge_ids}")
            
            # Update closed edges from road closure handler
            self.closed_edges = self.road_closure_handler.get_closed_edges()
            
            return True
        except Exception as e:
            print(f"Error reopening roads: {e}")
            return False

    def handle_event_creation(self, event_data):
        """Handle the creation of a new event and modify affected agents' routes"""
        try:
            print(f"Creating event: {event_data}")
            
            # Load route information
            with open('../data/route_info.json', 'r') as f:
                route_info = json.load(f)
            
            # Prepare agents with their route info
            agents = [
                {
                    'id': info['agent_id'],
                    'route_info': info,
                    'demographics': info.get('demographics', {})
                }
                for info in route_info
            ]
            
            # Calculate event interest for each agent
            interested_agents = self.event_handler.select_interested_agents(
                agents, 
                event_data,
                event_data.get('capacity', 100)
            )
            
            if not interested_agents:
                print("No interested agents found for the event")
                return
            
            print(f"Found {len(interested_agents)} interested agents")
            
            # Generate prompt for the event
            prompt = self.prompt_manager.event_creation_prompt(
                event_data,
                interested_agents[0]['demographics']
            )
            
            # Handle affected agents
            agent_results = self.event_handler.handle_affected_agents(
                interested_agents,
                event_data,
                self.activity_modifier,
                prompt
            )
            
            # Process results and update routes
            success_count = 0
            for agent_id, (new_chain, durations) in agent_results.items():
                if new_chain and durations:
                    success = self.change_agent_route(agent_id, new_chain, durations)
                    if success:
                        success_count += 1
                        print(f"Successfully updated route for agent {agent_id}")
                    else:
                        print(f"Failed to update route for agent {agent_id}")
            
            print(f"Successfully updated {success_count}/{len(agent_results)} agent routes")
            
        except Exception as e:
            print(f"Error handling event creation: {e}")
            import traceback
            traceback.print_exc()
    
    

    def check_and_apply_midified_routes(self, vehicle_id):
        """Check if a newly spawned vehicle has a modified route due to road closures and apply it"""
        try:
            # Load modified routes from road closure file
            try:
                with open('../data/route_info_llm_modified.json', 'r') as f:
                    modified_routes = json.load(f)
            except FileNotFoundError:
                return
            except json.JSONDecodeError as e:
                print(f"Error reading route_info_llm_modified.json: {e}")
                return

            # Find if this vehicle has a modified route
            modified_route = next(
                (route for route in modified_routes if route['agent_id'] == vehicle_id),
                None
            )

            if modified_route:
                print(f"Found modified route for newly spawned vehicle {vehicle_id}")
                # Extract POI sequence from modified route
                new_poi_sequence = [poi['name'] for poi in modified_route['poi_sequence']]
                
                # Apply the modified route
                success = self.change_agent_route(vehicle_id, new_poi_sequence)
                if success:
                    print(f"Successfully applied modified route to new vehicle {vehicle_id}")
                else:
                    print(f"Failed to apply modified route to new vehicle {vehicle_id}")

        except Exception as e:
            print(f"Error checking closure routes for vehicle {vehicle_id}: {e}")

def main():
    # Clean the route_info_llm_modified.json file before starting the simulation
    try:
        route_info_path = '../data/route_info_llm_modified.json'
        with open(route_info_path, 'w') as f:
            f.write('[]')
        print(f"Cleaned route_info_llm_modified.json file")
    except Exception as e:
        print(f"Error cleaning route_info_llm_modified.json file: {e}")
    controller = SUMOController()
    try:
        controller.start_simulation()
    finally:
        controller.cleanup()

if __name__ == '__main__':
    main() 