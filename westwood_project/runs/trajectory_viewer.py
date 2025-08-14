import tkinter as tk
from tkinter import ttk, messagebox
import traci
import json
import threading
import time
import subprocess
import os
import socket
import math
# Add parent directory to path for utilities imports
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utilities.activity_chain_modifier import ActivityChainModifier
from utilities.event_handler import EventHandler
from utilities.road_closure_handler import RoadClosureHandler
from utilities.prompt_manager import PromptManager

class TrajectoryViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("SUMO Trajectory Viewer")
        self.root.geometry("500x800")  # Reduced height for smaller screens
        
        # Create a canvas with scrollbar for the entire GUI
        self.canvas = tk.Canvas(self.root)
        self.scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # Pack the canvas and scrollbar
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        # Bind mouse wheel to scroll
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        
        # Initialize activity chain modifier
        self.activity_modifier = ActivityChainModifier()
        
        # Initialize last_vehicle_data
        self.last_vehicle_data = {'vehicle_data': {}}
        
        # Agent selection
        self.agent_frame = ttk.LabelFrame(self.scrollable_frame, text="Agent Selection", padding="5")
        self.agent_frame.pack(fill="x", padx=5, pady=5)
        
        self.agent_id_var = tk.StringVar()
        self.agent_combo = ttk.Combobox(self.agent_frame, 
                                       textvariable=self.agent_id_var,
                                       state='readonly')  # readonly prevents manual entry
        self.agent_combo.pack(side="left", padx=5, fill="x", expand=True)
        
        self.connect_button = ttk.Button(self.agent_frame, text="Connect", command=self.connect_to_sumo)
        self.connect_button.pack(side="left", padx=5)
        
        self.track_button = ttk.Button(self.agent_frame, text="Track Agent", command=self.track_agent)
        self.track_button.pack(side="left", padx=5)
        
        # Add refresh button
        self.refresh_button = ttk.Button(self.agent_frame, text="↻", width=3, command=self.refresh_agents)
        self.refresh_button.pack(side="left", padx=5)
        
        # Current status - make it shorter
        self.status_frame = ttk.LabelFrame(self.scrollable_frame, text="Current Status", padding="5")
        self.status_frame.pack(fill="x", padx=5, pady=5)
        
        self.status_text = tk.Text(self.status_frame, height=1, width=40)  # Reduced height from 4 to 2
        self.status_text.pack(fill="x", padx=5, pady=5)
        
        # Configure text tags for styling
        self.status_text.tag_configure("title", font=("Arial", 12, "bold"))
        self.status_text.tag_configure("normal", font=("Arial", 12))
        
        # Demographics - moved above route Planning
        self.demographics_frame = ttk.LabelFrame(self.scrollable_frame, text="Demographics", padding="5")
        self.demographics_frame.pack(fill="x", padx=5, pady=5)
        
        self.demographics_text = tk.Text(self.demographics_frame, height=8, width=40)
        self.demographics_text.pack(fill="x", padx=5, pady=5)
        
        # Configure text tags for demographics
        self.demographics_text.tag_configure("title", font=("Arial", 12, "bold"))
        self.demographics_text.tag_configure("label", font=("Arial", 12), foreground="gray")
        self.demographics_text.tag_configure("value", font=("Arial", 12, "bold"))
        
        # Add Route Modification frame - moved here
        self.route_mod_frame = ttk.LabelFrame(self.scrollable_frame, text="Route Modification", padding="5")
        self.route_mod_frame.pack(fill="x", padx=5, pady=5)
        
        # Add help text
        help_text = "Enter POI names separated by commas (e.g., Sterling Apartment, UCLA Parking Lot 2)"
        self.help_label = ttk.Label(self.route_mod_frame, text=help_text, wraplength=400)
        self.help_label.pack(fill="x", padx=5, pady=2)
        
        # Add text entry for new route
        self.route_entry = ttk.Entry(self.route_mod_frame)
        self.route_entry.pack(fill="x", padx=5, pady=2)
        
        # Add button to submit route change
        self.change_route_button = ttk.Button(self.route_mod_frame, text="Change Route", 
                                            command=self.submit_route_change)
        self.change_route_button.pack(padx=5, pady=2)
        
        # Add LLM-based Route Modification frame
        self.llm_route_frame = ttk.LabelFrame(self.scrollable_frame, text="LLM Route Modification", padding="5")
        self.llm_route_frame.pack(fill="x", padx=5, pady=5)
        
        # Add help text
        llm_help_text = "Enter a situation (e.g., 'The lunch place is closed today due to road closure')"
        self.llm_help_label = ttk.Label(self.llm_route_frame, text=llm_help_text, wraplength=400)
        self.llm_help_label.pack(fill="x", padx=5, pady=2)
        
        # Add text entry for prompt
        self.llm_prompt_entry = ttk.Entry(self.llm_route_frame)
        self.llm_prompt_entry.pack(fill="x", padx=5, pady=2)
        
        # Add button to submit LLM route change
        self.llm_change_button = ttk.Button(self.llm_route_frame, text="Modify Route with LLM", 
                                          command=self.modify_route_with_llm)
        self.llm_change_button.pack(padx=5, pady=2)
        
        # Route Planning - make it more compact
        self.route_frame = ttk.LabelFrame(self.scrollable_frame, text="Route Planning", padding="5")
        self.route_frame.pack(fill="x", padx=5, pady=5)  # Changed from fill="both" to fill="x"
        
        self.route_text = tk.Text(self.route_frame, width=40, height=20)  # Added height limit
        self.route_text.pack(fill="x", padx=5, pady=5)  # Changed from fill="both" to fill="x"
        
        # Add scrollbar for route text
        self.route_scrollbar = ttk.Scrollbar(self.route_frame, orient="vertical", command=self.route_text.yview)
        self.route_scrollbar.pack(side="right", fill="y")
        self.route_text.configure(yscrollcommand=self.route_scrollbar.set)
        
        # Configure text tags for route
        self.route_text.tag_configure("title", font=("Arial", 16, "bold"))
        self.route_text.tag_configure("subtitle", font=("Arial", 14, "bold"))
        self.route_text.tag_configure("visited", font=("Arial", 14), foreground="green")
        self.route_text.tag_configure("current", font=("Arial", 14), foreground="blue")
        self.route_text.tag_configure("target", font=("Arial", 14), foreground="orange")
        self.route_text.tag_configure("activity", font=("Arial", 14), foreground="purple")
        self.route_text.tag_configure("normal", font=("Arial", 14))
        
        # Add Road Closure frame - MOVED HERE from _on_mousewheel
        self.road_closure_frame = ttk.LabelFrame(self.scrollable_frame, text="Road Closure", padding="5")
        self.road_closure_frame.pack(fill="x", padx=5, pady=5)
        
        # Add help text
        closure_help_text = "Enter edge IDs separated by commas (e.g., edge1,edge2)"
        self.closure_help_label = ttk.Label(self.road_closure_frame, text=closure_help_text, wraplength=400)
        self.closure_help_label.pack(fill="x", padx=5, pady=2)
        
        # Add text entry for edge IDs
        self.closure_entry = ttk.Entry(self.road_closure_frame)
        self.closure_entry.pack(fill="x", padx=5, pady=2)
        
        # Add buttons for closing and reopening roads
        self.button_frame = ttk.Frame(self.road_closure_frame)
        self.button_frame.pack(fill="x", padx=5, pady=2)
        
        self.close_roads_button = ttk.Button(self.button_frame, text="Close Roads", 
                                           command=self.close_roads)
        self.close_roads_button.pack(side="left", padx=5)
        
        self.reopen_roads_button = ttk.Button(self.button_frame, text="Reopen Roads", 
                                            command=self.reopen_roads)
        self.reopen_roads_button.pack(side="left", padx=5)
        
        self.reopen_all_button = ttk.Button(self.button_frame, text="Reopen All", 
                                          command=lambda: self.reopen_roads(reopen_all=True))
        self.reopen_all_button.pack(side="left", padx=5)
        
        # Add Event Management frame - MOVED HERE from _on_mousewheel
        self.event_frame = ttk.LabelFrame(self.scrollable_frame, text="Event Management", padding="5")
        self.event_frame.pack(fill="x", padx=5, pady=5)
        
        # Event type selection
        self.event_type_frame = ttk.Frame(self.event_frame)
        self.event_type_frame.pack(fill="x", padx=5, pady=2)
        
        # Event type
        self.event_type_label = ttk.Label(self.event_type_frame, text="Event Type:")
        self.event_type_label.pack(side="left")
        self.event_type_var = tk.StringVar()
        self.event_type_combo = ttk.Combobox(self.event_type_frame, 
                                            textvariable=self.event_type_var,
                                            values=["Sports", "Entertainment"],
                                            state='readonly',
                                            width=15)
        self.event_type_combo.pack(side="left", padx=5)
        
        # Start time
        self.start_time_label = ttk.Label(self.event_type_frame, text="Start Time:")
        self.start_time_label.pack(side="left", padx=(10, 0))
        self.start_time_var = tk.StringVar()
        self.start_time_combo = ttk.Combobox(self.event_type_frame,
                                            textvariable=self.start_time_var,
                                            values=[f"{h:02d}:00" for h in range(24)],
                                            state='readonly',
                                            width=8)
        self.start_time_combo.pack(side="left", padx=5)
        
        # Event name entry (optional)
        self.event_name_frame = ttk.Frame(self.event_frame)
        self.event_name_frame.pack(fill="x", padx=5, pady=2)
        
        ttk.Label(self.event_name_frame, text="Event Name (optional):").pack(side="left")
        self.event_name_var = tk.StringVar()
        self.event_name_entry = ttk.Entry(self.event_name_frame, textvariable=self.event_name_var)
        self.event_name_entry.pack(side="left", padx=5, fill="x", expand=True)
        
        # Location entry (changed from lat/lon to POI selection)
        self.location_frame = ttk.Frame(self.event_frame)
        self.location_frame.pack(fill="x", padx=5, pady=2)
        
        ttk.Label(self.location_frame, text="Event Location (POI):").pack(side="left")
        self.poi_var = tk.StringVar()
        self.poi_combo = ttk.Combobox(self.location_frame, 
                                     textvariable=self.poi_var,
                                     state='readonly')
        self.poi_combo.pack(side="left", padx=5, fill="x", expand=True)
        
        # Load POIs directly from pois.add.xml
        try:
            import xml.etree.ElementTree as ET
            poi_path = '../poi/pois.add.xml'
            tree = ET.parse(poi_path)
            root = tree.getroot()
            
            # Store POIs with their names and coordinates
            self.pois = []
            for poi in root.findall('poi'):
                self.pois.append({
                    'id': poi.get('id'),
                    'name': poi.get('name', poi.get('id')),
                    'lat': float(poi.get('lat', 0)),
                    'lon': float(poi.get('lon', 0)),
                    'edge': poi.get('edge', ''),
                    'type': poi.get('type', 'unknown')
                })
            
            # Get POI names for the combobox, using name or id as fallback
            poi_names = sorted([poi['name'] for poi in self.pois])
            self.poi_combo['values'] = poi_names
            
        except Exception as e:
            print(f"Error loading POIs from XML: {e}")
            self.pois = []
            self.poi_combo['values'] = []
        
        # Load POI names into the combobox
        poi_names = sorted([poi['name'] for poi in self.pois])
        self.poi_combo['values'] = poi_names
        
        # Capacity and Duration entry
        self.capacity_frame = ttk.Frame(self.event_frame)
        self.capacity_frame.pack(fill="x", padx=5, pady=2)
        
        ttk.Label(self.capacity_frame, text="Capacity:").pack(side="left")
        self.capacity_entry = ttk.Entry(self.capacity_frame)
        self.capacity_entry.pack(side="left", padx=5, fill="x", expand=True)
        
        # Duration selector
        self.duration_label = ttk.Label(self.capacity_frame, text="Duration (hrs):")
        self.duration_label.pack(side="left", padx=(10, 0))
        self.duration_var = tk.StringVar()
        self.duration_combo = ttk.Combobox(self.capacity_frame,
                                         textvariable=self.duration_var,
                                         values=[str(i) for i in range(1, 9)],
                                         state='readonly',
                                         width=5)
        self.duration_combo.pack(side="left", padx=5)
        
        # Create event button
        self.create_event_button = ttk.Button(self.event_frame, 
                                            text="Create Event", 
                                            command=self.handle_event_creation)
        self.create_event_button.pack(padx=5, pady=5)
        
        # Initialize event handler
        self.event_handler = EventHandler()
        
        # Initialize road closure handler and prompt manager
        self.road_closure_handler = RoadClosureHandler()
        self.prompt_manager = PromptManager()
        
        # Initialize variables
        self.tracked_agent = None
        self.running = True
        self.connected = False
        self.sumo_process = None
        self.update_thread = None
        self.socket = None
        
        # Initial status message with styling
        self.status_text.delete(1.0, "end")
        self.status_text.insert("end", "Status: ", "title")
        self.status_text.insert("end", "Click 'Connect' to connect to SUMO simulation\n", "normal")
    
    def _on_mousewheel(self, event):
        """Handle mouse wheel scrolling"""
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    
    def connect_to_sumo(self):
        try:
            if not self.connected:
                self.status_text.delete(1.0, "end")
                self.status_text.insert("end", "Attempting to connect to viewer socket...\n")
                
                try:
                    self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.socket.connect(('localhost', 8814))
                    self.connected = True
                    self.status_text.delete(1.0, "end")
                    self.status_text.insert("end", "Connected to SUMO simulation\n")
                    self.connect_button.config(text="Disconnect")
                    
                    if not self.update_thread:
                        self.update_thread = threading.Thread(target=self.update_loop)
                        self.update_thread.start()
                        
                except Exception as e:
                    self.status_text.delete(1.0, "end")
                    self.status_text.insert("end", "Could not connect.\nMake sure SUMO is running first.\n")
                    return
            else:
                try:
                    self.socket.close()
                except:
                    pass
                self.connected = False
                self.status_text.delete(1.0, "end")
                self.status_text.insert("end", "Disconnected from SUMO\n")
                self.connect_button.config(text="Connect")
        except Exception as e:
            self.status_text.delete(1.0, "end")
            self.status_text.insert("end", f"Connection error: {e}\n")
    
    def track_agent(self):
        if not self.connected:
            self.status_text.delete(1.0, "end")
            self.status_text.insert("end", "Please connect to SUMO first\n")
            return
        
        agent_id = self.agent_id_var.get()
        if not agent_id:
            return
        
        self.tracked_agent = agent_id
        
        # Send highlight command to SUMO
        try:
            command = f"HIGHLIGHT:{agent_id}"
            # Use sendall to ensure the entire command is sent
            self.socket.sendall(command.encode())
            
            # Wait a bit longer for the command to be processed
            time.sleep(0.2)  
            
            self.status_text.delete(1.0, "end")
            self.status_text.insert("end", f"Tracking agent {agent_id}\n")
        except Exception as e:
            print(f"Failed to send highlight command: {e}")
            self.status_text.delete(1.0, "end")
            self.status_text.insert("end", f"Failed to track agent: {e}\n")
            # Try to reconnect if there was a socket error
            self.connect_to_sumo()
    
    def update_agent_info(self):
        if not self.connected or not self.tracked_agent:
            return
            
        try:
            self.route_text.delete(1.0, "end")
            self.route_text.insert("end", f"Agent: {self.tracked_agent}\n")
            self.route_text.insert("end", "Waiting for vehicle data...\n")
        except:
            pass
    
    def sumo_to_latlon(self, x, y):
        net_offset_x = -365398.86
        net_offset_y = -3768588.46
        
        utm_x = x - net_offset_x
        utm_y = y - net_offset_y
        
        import pyproj
        
        utm_proj = pyproj.Proj("+proj=utm +zone=11 +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
        wgs84_proj = pyproj.Proj("+proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs")
        
        transformer = pyproj.Transformer.from_proj(utm_proj, wgs84_proj)
        lon, lat = transformer.transform(utm_x, utm_y)
        
        return lat, lon

    def find_nearest_poi(self, x, y):
        nearest = None
        min_dist = float('inf')
        
        lat, lon = self.sumo_to_latlon(x, y)
        
        for poi in self.pois:
            try:
                poi_lat = float(poi['lat'])
                poi_lon = float(poi['lon'])
                
                dlat = poi_lat - lat
                dlon = poi_lon - lon
                
                dist = (dlat * dlat + dlon * dlon) * 100000
                
                if dist < min_dist:
                    min_dist = dist
                    nearest = poi
                    
            except Exception:
                continue
            
        return nearest
    
    def find_pois_on_edge(self, edge_id):
        return [poi for poi in self.pois if poi.get('edge_id') == edge_id]
    
    def refresh_agents(self):
        """Update the dropdown with current available agents"""
        if not self.connected:
            self.agent_combo['values'] = []
            return
        
        try:
            # Send request for vehicle list
            self.socket.send("GET_VEHICLES".encode())
            # Wait briefly for response
            self.root.after(100)
            # The response will be handled in update_loop
        except Exception as e:
            print(f"Failed to refresh agents: {e}")

    def update_agent_list(self, vehicles):
        """Update the dropdown menu with new vehicle list"""
        current = self.agent_id_var.get()
        self.agent_combo['values'] = sorted(vehicles)
        if current in vehicles:
            self.agent_combo.set(current)
        elif vehicles:
            self.agent_combo.set(vehicles[0])

    def update_loop(self):
        """Main update loop for receiving and displaying data"""
        buffer = ""
        
        while self.running:
            try:
                # Increase buffer size and handle partial messages
                data = self.socket.recv(16384).decode('utf-8', errors='ignore')
                buffer += data
                
                while "<<END>>" in buffer:
                    message, buffer = buffer.split("<<END>>", 1)
                    try:
                        info = json.loads(message)
                        
                        # Store the last received data
                        self.last_vehicle_data = info
                        
                        # Update agent list first
                        if 'vehicles' in info:
                            self.root.after(0, self.update_agent_list, info['vehicles'])
                        
                        # Clear previous text
                        self.route_text.delete(1.0, "end")
                        self.demographics_text.delete(1.0, "end")
                        
                        # Get tracked vehicle info
                        if self.tracked_agent and self.tracked_agent in info['vehicle_data']:
                            vehicle_data = info['vehicle_data'][self.tracked_agent]
                            agent_info = vehicle_data.get('route_info', {})
                            route = vehicle_data.get('route', [])
                            current_edge = vehicle_data.get('current_edge', '')
                            
                            # Handle internal edges by finding the last real edge
                            if current_edge.startswith(':'):
                                try:
                                    route_idx = route.index(current_edge)
                                    route_until_now = route[:route_idx + 1]
                                    real_edges = [edge for edge in route_until_now if not edge.startswith(':')]
                                    if real_edges:
                                        current_edge = real_edges[-1]
                                except ValueError:
                                    pass
                            
                            # Display basic info
                            self.route_text.insert("end", f"Agent: {self.tracked_agent}\n", "title")
                            self.route_text.insert("end", f"Time: {info['time']:.1f}\n", "normal")
                            
                            # Display position and speed
                            speed = vehicle_data.get('speed', 0)
                            # Handle position data correctly
                            if 'lat_lon' in vehicle_data:
                                lat, lon = vehicle_data['lat_lon'][:2]  # Get first two values (lat, lon)
                            elif 'position' in vehicle_data:
                                lat, lon = vehicle_data['position'][:2]  # Get first two values (x, y)
                            else:
                                lat, lon = 0, 0
                            self.route_text.insert("end", f"Speed: {speed:.1f} m/s\n", "normal")
                            self.route_text.insert("end", f"Position: ({lat:.6f}, {lon:.6f})\n", "normal")
                            
                            # Display demographics if available
                            if 'demographics' in vehicle_data:
                                self.update_demographics(vehicle_data['demographics'])
                            else:
                                self.demographics_text.delete(1.0, "end")
                                self.demographics_text.insert("end", "No demographic information available\n")
                            
                            # Display POI sequence if available
                            if agent_info and 'poi_sequence' in agent_info:
                                # Display route source if available
                                route_source = vehicle_data.get('route_source', 'Original')
                                self.route_text.insert("end", f"\nPOI Sequence ({'LLM Modified'}):\n", "subtitle")
                                
                                # Sort POIs by order
                                poi_sequence = sorted(agent_info['poi_sequence'], key=lambda x: x['order'])
                                
                                # Initialize visited_pois with the first POI
                                visited_pois = []
                                current_target = None
                                
                                # Find current position in sequence
                                route_index = vehicle_data.get('route_index', 0)
                                
                                # Handle internal edges
                                if current_edge.startswith(':'):
                                    try:
                                        if route_index + 1 < len(route):
                                            current_edge = route[route_index + 1]
                                    except Exception:
                                        pass
                                
                                # Determine visited POIs and current target
                                for i, poi in enumerate(poi_sequence):
                                    if i == 0 or poi['edge'] in route[:route_index + 1]:
                                        visited_pois.append(poi)
                                    elif not current_target and poi['edge'] in route[route_index:]:
                                        current_target = poi
                                        break
                                
                                # Display POI sequence with proper status
                                for poi in poi_sequence:
                                    prefix = "✓ " if poi in visited_pois else "  "
                                    activity = f"{poi.get('activity_type', 'Unknown'):12}"
                                    order = f"{poi['order']}.".ljust(3)
                                    duration = f"({poi.get('stop_duration', 30)}s)"
                                    
                                    if poi == current_target:
                                        suffix = " ← Current Destination"
                                        tag = "target"
                                    elif poi['edge'] == current_edge:
                                        suffix = " (Current Location)"
                                        tag = "current"
                                    elif poi in visited_pois:
                                        suffix = ""
                                        tag = "visited"
                                    else:
                                        suffix = ""
                                        tag = "normal"
                                    
                                    self.route_text.insert("end", prefix, tag)
                                    self.route_text.insert("end", activity, "activity")
                                    
                                    self.route_text.insert("end", f"\t\t\t{order} ", tag)
                                    self.route_text.insert("end", poi['name'], tag)
                                    #self.route_text.insert("end", f" {duration}", "normal")
                                    # Display start and end time in 24-hour format
                                    start_time = poi.get('start_time', 0)
                                    end_time = poi.get('end_time', 0)
                                    
                                    # Convert seconds to HH:MM format
                                    start_hours = start_time // 3600
                                    start_minutes = (start_time % 3600) // 60
                                    end_hours = end_time // 3600
                                    end_minutes = (end_time % 3600) // 60
                                    
                                    time_str = f" [{start_hours:02d}:{start_minutes:02d}-{end_hours:02d}:{end_minutes:02d}]"
                                    #self.route_text.insert("end", time_str, "normal")
                                    self.route_text.insert("end", f"{suffix}\n", tag)
                                
                                # Show route details
                                self.route_text.insert("end", "\nRoute Details:\n", "subtitle")
                                for i, edge in enumerate(route):
                                    if edge == current_edge:
                                        self.route_text.insert("end", f"{i+1}. {edge} ← Current\n", "current")
                                    else:
                                        self.route_text.insert("end", f"{i+1}. {edge}\n", "normal")
                            else:
                                self.route_text.insert("end", f"Agent: {self.tracked_agent}\n", "title")
                                self.route_text.insert("end", "No POI sequence information available\n", "normal")
                            
                    except Exception as e:
                        print(f"Error updating display: {e}")
                        continue  # Skip this message and try the next one
                    
            except Exception as e:
                print(f"Socket error: {e}")
                if not self.running:  # Only break if we're meant to stop
                    break
                time.sleep(0.1)  # Wait a bit before retrying
                continue
        
        if self.connected:
            self.root.after(0, self.handle_disconnect)
    
    def handle_disconnect(self):
        self.connected = False
        self.status_text.delete(1.0, "end")
        self.status_text.insert("end", "Lost connection to SUMO\n")
        self.connect_button.config(text="Connect")
    
    def run(self):
        self.root.mainloop()
        self.running = False
        self.update_thread.join()
        if self.sumo_process:
            self.sumo_process.terminate()

    def change_agent_route(self, agent_id, new_poi_sequence, durations=None):
        """Change an agent's route to visit a new sequence of POIs"""
        try:
            if not self.socket:
                self.update_status("Not connected to SUMO")
                return False
            
            # Send the command with both POI sequence and durations
            command = f"CHANGE_ROUTE:{agent_id}:{','.join(new_poi_sequence)}"
            if durations:
                command += f":{','.join(str(d) for d in durations)}"
            
            self.socket.send(command.encode())
            return True
            
        except Exception as e:
            self.update_status(f"Error changing route: {e}")
            return False

    def submit_route_change(self):
        """Handle route change submission from the UI"""
        if not self.connected:
            self.status_text.delete(1.0, "end")
            self.status_text.insert("end", "Please connect to SUMO first\n")
            return
            
        if not self.tracked_agent:
            self.status_text.delete(1.0, "end")
            self.status_text.insert("end", "Please select an agent first\n")
            return
            
        # Get POI sequence from entry
        poi_sequence = [poi.strip() for poi in self.route_entry.get().split(",")]
        
        if not poi_sequence:
            self.status_text.delete(1.0, "end")
            self.status_text.insert("end", "Please enter POI names separated by commas\n")
            return
            
        # Send route change request
        try:
            self.change_agent_route(self.tracked_agent, poi_sequence)
            self.status_text.delete(1.0, "end")
            self.status_text.insert("end", "Route change request sent\n")
        except Exception as e:
            self.status_text.delete(1.0, "end")
            self.status_text.insert("end", f"Error changing route: {e}\n")

    def modify_route_with_llm(self):
        """Handle route modification using LLM based on a prompt"""
        if not self.connected or not self.tracked_agent:
            self.status_text.delete(1.0, "end")
            self.status_text.insert("end", "Please connect to SUMO and select an agent\n")
            return
        
        prompt = self.llm_prompt_entry.get().strip()
        if not prompt:
            self.status_text.delete(1.0, "end")
            self.status_text.insert("end", "Please enter a situation prompt\n")
            return
        
        try:
            # Get vehicle data and traffic info
            vehicle_data = self.last_vehicle_data.get('vehicle_data', {}).get(self.tracked_agent, {})
            traffic_info = self.last_vehicle_data.get('traffic_info', {})
            
            if not vehicle_data or 'route_info' not in vehicle_data:
                self.status_text.delete(1.0, "end")
                self.status_text.insert("end", "Could not find vehicle data\n")
                return
            
            # Extract POI names from route info
            current_chain = [poi['name'] for poi in vehicle_data['route_info'].get('poi_sequence', [])]
            
            if not current_chain:
                self.status_text.delete(1.0, "end")
                self.status_text.insert("end", "Could not find current activity chain\n")
                return
            
            # Update status
            self.status_text.delete(1.0, "end")
            self.status_text.insert("end", "Requesting route modification from LLM...\n")
            
            def process_llm_request():
                try:
                    # Get selected agent
                    selected_agent = self.agent_id_var.get()
                    if not selected_agent:
                        self.update_status("No agent selected")
                        return
                    
                    # Get current chain from route info
                    current_chain = []
                    vehicle_data = {}
                    if selected_agent in self.last_vehicle_data['vehicle_data']:
                        vehicle_data = self.last_vehicle_data['vehicle_data'][selected_agent]
                        if 'route_info' in vehicle_data and 'poi_sequence' in vehicle_data['route_info']:
                            current_chain = [poi['name'] for poi in vehicle_data['route_info']['poi_sequence']]
                    
                    if not current_chain:
                        self.update_status("No route information available for selected agent")
                        return
                    
                    # Get prompt from text box
                    prompt = self.llm_prompt_entry.get().strip()
                    if not prompt:
                        self.update_status("Please enter a prompt")
                        return
                    
                    # Call LLM to modify chain
                    prompt = "Go Ralphs instead of Trader Joe's"
                    new_chain, durations = self.activity_modifier.modify_activity_chain_with_llm(
                        selected_agent,
                        current_chain,
                        prompt,
                        vehicle_data,
                        self.last_vehicle_data.get('traffic_info', {})
                    )
                    
                    if not new_chain:
                        self.update_status("LLM did not return a valid chain")
                        return
                    
                    # Display the new chain
                    chain_str = ", ".join(new_chain)
                    self.update_status(f"LLM suggested new route: {chain_str}")
                    
                    # Update the route entry field with the new chain
                    self.route_entry.delete(0, tk.END)
                    self.route_entry.insert(0, chain_str)
                    
                    # Ask user to confirm
                    if tk.messagebox.askyesno("Confirm Route Change", 
                                            f"Apply the suggested route?\n\n{chain_str}"):
                        try:
                            success = self.change_agent_route(selected_agent, new_chain, durations)
                            if success:
                                self.update_status("Route change request sent")
                            else:
                                self.update_status("Failed to change route")
                        except Exception as e:
                            self.update_status(f"Error changing route: {e}")
                    else:
                        self.update_status("Route change cancelled by user")
                    
                except Exception as e:
                    self.update_status(f"Error processing LLM request: {e}")
                    print(f"Error in process_llm_request: {e}")
                    import traceback
                    traceback.print_exc()
            
            threading.Thread(target=process_llm_request, daemon=True).start()
            
        except Exception as e:
            self.status_text.delete(1.0, "end")
            self.status_text.insert("end", f"Error preparing LLM request: {e}\n")
    
    def update_status(self, message):
        """Update the status text widget"""
        self.status_text.delete(1.0, "end")
        self.status_text.insert("end", message + "\n")

    def update_demographics(self, demo):
        self.demographics_text.delete(1.0, "end")
        self.demographics_text.insert("end", "Demographics:\n", "title")
        self.demographics_text.insert("end", "Age: ", "label")
        self.demographics_text.insert("end", f"{demo['age']}\n", "value")
        self.demographics_text.insert("end", "Gender: ", "label")
        self.demographics_text.insert("end", f"{demo['gender']}\n", "value")
        self.demographics_text.insert("end", "Student: ", "label")
        self.demographics_text.insert("end", f"{demo['student_status']}\n", "value")
        self.demographics_text.insert("end", "Income: ", "label")
        self.demographics_text.insert("end", f"{demo['income_level']}\n", "value")
        self.demographics_text.insert("end", "Education: ", "label")
        self.demographics_text.insert("end", f"{demo['education_level']}\n", "value")
        self.demographics_text.insert("end", "Work: ", "label")
        self.demographics_text.insert("end", f"{demo['work_status']}\n", "value")

    def close_roads(self):
        """Handle road closure request"""
        if not self.connected:
            self.update_status("Please connect to SUMO first")
            return
        
        edge_ids = [edge.strip() for edge in self.closure_entry.get().split(",")]
        if not edge_ids:
            self.update_status("Please enter edge IDs separated by commas")
            return
        
        try:
            command = f"CLOSE_ROADS:{','.join(edge_ids)}"
            self.socket.sendall(command.encode())
            self.update_status("Road closure request sent")
            self.closure_entry.delete(0, tk.END)
        except Exception as e:
            self.update_status(f"Error closing roads: {e}")

    def reopen_roads(self, reopen_all=False):
        """Handle road reopening request"""
        if not self.connected:
            self.status_text.delete(1.0, "end")
            self.status_text.insert("end", "Please connect to SUMO first\n")
            return
        
        try:
            if reopen_all:
                command = "REOPEN_ALL_ROADS"
            else:
                # Get edge IDs from entry
                edge_ids = [edge.strip() for edge in self.closure_entry.get().split(",")]
                if not edge_ids:
                    self.status_text.delete(1.0, "end")
                    self.status_text.insert("end", "Please enter edge IDs separated by commas\n")
                    return
                command = f"REOPEN_ROADS:{','.join(edge_ids)}"
            
            # Use sendall and add delay
            self.socket.sendall(command.encode())
            time.sleep(0.1)
            
            self.status_text.delete(1.0, "end")
            self.status_text.insert("end", "Road reopening request sent\n")
            
            # Clear the entry field after successful command
            if not reopen_all:
                self.closure_entry.delete(0, tk.END)
            
        except Exception as e:
            print(f"Error sending reopen command: {e}")
            self.status_text.delete(1.0, "end")
            self.status_text.insert("end", f"Error reopening roads: {e}\n")

    def handle_event_creation(self):
        """Handle the creation of a new event"""
        if not self.connected:
            self.update_status("Please connect to SUMO first")
            return
        
        try:
            # Validate inputs
            event_type = self.event_type_var.get()
            print(f"Creating {event_type} event...")
            if not event_type:
                self.update_status("Please select an event type")
                return

            # Get POI location
            poi_name = self.poi_var.get()
            if not poi_name:
                self.update_status("Please select an event location (POI)")
                return
            
            try:
                lat, lon = self.event_handler.get_poi_coordinates(poi_name)
                capacity = int(self.capacity_entry.get())
                print(f"Event parameters - Location: {poi_name}, Capacity: {capacity}")
            except ValueError:
                self.update_status("Please enter a valid number for capacity")
                return

            # Create event data
            event_data = {
                'type': event_type,
                'location': poi_name,
                'lat': lat,
                'lon': lon,
                'capacity': capacity,
                'name': 'N/A',
                'start_time': self.start_time_var.get(),
                'duration': int(self.duration_var.get() or "2")  # Default 2 hours if not set
            }
            
            # Add event name if provided
            event_name = self.event_name_var.get().strip()
            if event_name:
                event_data['name'] = event_name
            
            # Send event creation command to dynamic_control
            # First send the command identifier
            command = f"CREATE_EVENT:{json.dumps(event_data)}\n"
            self.socket.sendall(command.encode())
            print("Event creation request sent")
            self.update_status("Processing event...")

        except Exception as e:
            print(f"Error in event creation: {e}")
            self.update_status(f"Error creating event: {e}")

def main():
    root = tk.Tk()
    viewer = TrajectoryViewer(root)
    root.mainloop()

if __name__ == "__main__":
    main() 