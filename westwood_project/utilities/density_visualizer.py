import tkinter as tk
from tkinter import ttk
import socket
import json
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import seaborn as sns
import sumolib
import threading
import time
import traceback
import errno

class DensityVisualizer:
    def __init__(self, host='localhost', port=8814):
        """Initialize the density visualizer"""
        # Initialize Tkinter window
        self.root = tk.Tk()
        self.root.title("Density Visualizer")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Initialize visualization components with updated bounds based on actual data
        self.bounds = [
            [0, 0],        # min_x, min_y - Full map coverage
            [3000, 3000]   # max_x, max_y
        ]
        self.road_network = None
        self.density_grid = np.zeros((100, 100))  # Increase grid size for better resolution
        self.grid_size = 100
        self.colorbar = None
        
        # Create main frame
        self.main_frame = ttk.Frame(self.root, padding="5")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Create control frame for buttons
        self.control_frame = ttk.Frame(self.main_frame)
        self.control_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E))
        
        # Create connection button
        self.connect_button = ttk.Button(self.control_frame, text="Connect", command=self.toggle_connection)
        self.connect_button.grid(row=0, column=0, padx=5)
        
        # Create update button
        self.update_button = ttk.Button(self.control_frame, text="Update Heatmap", command=self.request_update, state='disabled')
        self.update_button.grid(row=0, column=1, padx=5)
        
        # Initialize matplotlib figure
        self.fig, self.ax = plt.subplots(figsize=(10, 8))
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.main_frame)
        self.canvas.get_tk_widget().grid(row=1, column=0, columnspan=2)
        
        # Initialize socket connection variables
        self.host = host
        self.port = port
        self.socket = None
        self.connected = False
        
        # Extract road network on startup
        self.road_network = self.extract_road_network()
        self.update_visualization()
        
    def extract_road_network(self):
        """Extract road network from SUMO network file"""
        try:
            net = sumolib.net.readNet('../sumo_config/westwood.net.xml')
            
            road_lines = []
            min_x, min_y = self.bounds[0]
            max_x, max_y = self.bounds[1]
            
            for edge in net.getEdges():
                points = []
                lane = edge.getLanes()[0]
                shape = lane.getShape()
                for x, y in shape:
                    if min_x <= x <= max_x and min_y <= y <= max_y:
                        points.append([x, y])
                if len(points) > 1:
                    road_lines.append(np.array(points))
            
            return road_lines
        except Exception as e:
            print(f"Error extracting road network: {e}")
            return []
        
    def connect(self):
        """Establish connection to SUMO controller and get network bounds"""
        try:
            # Create socket and connect
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.socket.setblocking(False)
            self.connected = True
            
            # Update button states
            self.connect_button.config(text="Disconnect")
            self.update_button.config(state='normal')
            
            print("Connected to SUMO controller")
            
            # Set wider bounds covering the entire network
            self.bounds = [
                [0, 0],        # min_x, min_y - Full map coverage
                [3000, 3000]   # max_x, max_y
            ]
            
            print(f"Set visualization bounds to: x=[{self.bounds[0][0]}, {self.bounds[1][0]}], y=[{self.bounds[0][1]}, {self.bounds[1][1]}]")
            
            # Initialize the density grid
            self.density_grid = np.zeros((self.grid_size, self.grid_size))
            self.update_visualization()
            
        except Exception as e:
            print(f"Connection error: {e}")
            self.disconnect()

    def disconnect(self):
        """Close connection to SUMO controller"""
        if self.socket:
            self.socket.close()
            self.socket = None
        self.connected = False
        self.connect_button.config(text="Connect")
        self.update_button.config(state='disabled')

    def toggle_connection(self):
        """Toggle connection state"""
        if self.connected:
            self.disconnect()
        else:
            self.connect()

    def on_closing(self):
        """Handle window closing"""
        self.disconnect()
        self.root.quit()
        self.root.destroy()

    def request_update(self):
        """Request and process vehicle data for updating the heatmap"""
        if not self.connected or not self.socket:
            print("Not connected to SUMO controller")
            return

        try:
            # First, clear our socket buffer to avoid interference
            self.socket.setblocking(False)
            try:
                # Clear any pending data from previous requests
                while True:
                    try:
                        chunk = self.socket.recv(1024)
                        if not chunk:
                            break
                    except:
                        break
            except:
                pass
            
            # Set a short timeout for better control
            self.socket.settimeout(0.5)
            
            # Send request for vehicle data
            print("Requesting all vehicle data...")
            self.socket.send("GET_ALL_VEHICLES".encode())
            
            # Read the complete response with reliable framing
            complete_buffer = ""
            start_found = False
            end_found = False
            
            # Keep receiving until we get a complete message
            timeout_start = time.time()
            timeout_limit = 5  # 5 seconds total timeout
            
            while time.time() - timeout_start < timeout_limit:
                try:
                    chunk = self.socket.recv(16384).decode()  # Increased buffer size
                    if not chunk:
                        time.sleep(0.1)
                        continue
                        
                    complete_buffer += chunk
                    print(f"Received chunk of {len(chunk)} bytes")
                    print(f"Current buffer size: {len(complete_buffer)} bytes")
                    
                    # Check for complete message
                    if "<<START>>" in complete_buffer and "<<END>>" in complete_buffer:
                        start_idx = complete_buffer.find("<<START>>")
                        end_idx = complete_buffer.find("<<END>>", start_idx)
                        if end_idx > start_idx:
                            print("Found complete message")
                            break
                            
                except socket.timeout:
                    print("Socket timeout, continuing...")
                    continue
                except Exception as e:
                    print(f"Socket error: {e}")
                    break
            
            # Reset socket to non-blocking for other operations
            self.socket.setblocking(False)
            
            # Check if we have a complete message
            if not ("<<START>>" in complete_buffer and "<<END>>" in complete_buffer):
                print("Failed to receive a complete message")
                return
                
            # Extract the message between markers
            print("Extracting message between markers...")
            
            try:
                # Split by START marker and take everything after it
                if "<<START>>" not in complete_buffer:
                    print("START marker not found in final buffer")
                    return
                    
                _, after_start = complete_buffer.split("<<START>>", 1)
                
                # Split by END marker and take everything before it
                if "<<END>>" not in after_start:
                    print("END marker not found in message after START")
                    return
                    
                message, _ = after_start.split("<<END>>", 1)
                print(f"Successfully extracted message of length {len(message)}")
                
                # Debug: Show the start and end of the message
                print(f"Message starts with: {message[:50]}")
                print(f"Message ends with: {message[-50:]}")
                
            except Exception as e:
                print(f"Error during message extraction: {e}")
                return
            
            # Process the extracted message
            if not message:
                print("Extracted message is empty")
                return
                
            print(f"Message preview: {message[:100]}...")

            try:
                # Parse the JSON message
                vehicle_data = json.loads(message)
                
                # Get vehicle count
                vehicle_count = vehicle_data.get('vehicle_count', 0)
                print(f"Message contains {vehicle_count} vehicles")
                
                # Get vehicle data dictionary
                vehicles = vehicle_data.get('vehicle_data', {})
                print(f"Received position data for {len(vehicles)} vehicles")
                
                if not vehicles:
                    print("No vehicle position data received")
                    return
                
                # Sample data for debugging
                sample_count = min(5, len(vehicles))
                if sample_count > 0:
                    print(f"Sample of {sample_count} vehicles:")
                    for i, (vid, data) in enumerate(list(vehicles.items())[:sample_count]):
                        print(f"  {vid}: {data}")
                
                # Get bounds
                x_min, y_min = self.bounds[0]
                x_max, y_max = self.bounds[1]
                
                # Clear the density grid
                self.density_grid = np.zeros((self.grid_size, self.grid_size))
                
                # Process each vehicle
                vehicles_processed = 0
                vehicles_out_of_bounds = 0
                
                for vid, data in vehicles.items():
                    if 'position' in data:
                        pos = data['position']
                        x, y = pos[0], pos[1]
                        
                        # Check if position is within bounds
                        if x_min <= x <= x_max and y_min <= y <= y_max:
                            # Convert to grid coordinates
                            grid_x = int((x - x_min) / (x_max - x_min) * (self.grid_size - 1))
                            grid_y = int((y - y_min) / (y_max - y_min) * (self.grid_size - 1))
                            
                            # Apply Gaussian spread
                            sigma = 2.0  # Increased spread for better visibility
                            x_range = np.arange(max(0, grid_x-4), min(self.grid_size, grid_x+5))
                            y_range = np.arange(max(0, grid_y-4), min(self.grid_size, grid_y+5))
                            X, Y = np.meshgrid(x_range, y_range)
                            gaussian = np.exp(-((X-grid_x)**2 + (Y-grid_y)**2)/(2*sigma**2))
                            
                            # Add to density grid
                            x_indices = slice(max(0, grid_x-4), min(self.grid_size, grid_x+5))
                            y_indices = slice(max(0, grid_y-4), min(self.grid_size, grid_y+5))
                            self.density_grid[y_indices, x_indices] += gaussian
                            vehicles_processed += 1
                        else:
                            vehicles_out_of_bounds += 1
                
                print(f"Processed {vehicles_processed} vehicles, {vehicles_out_of_bounds} out of bounds")
                
                if vehicles_processed > 0:
                    self.update_visualization()
                else:
                    print("No vehicles were within the visualization bounds")
                
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON: {e}")
                print(f"Message preview: {message[:100]}...")
            except Exception as e:
                print(f"Error processing data: {e}")
                traceback.print_exc()

        except Exception as e:
            print(f"Error requesting vehicle data: {e}")
            traceback.print_exc()

    def update_visualization(self):
        """Update the visualization with current density grid"""
        if not self.bounds or self.density_grid is None:
            return

        # Clear the current plot
        self.ax.clear()

        # Plot road network if available
        if self.road_network is not None:
            for line in self.road_network:
                self.ax.plot(line[:, 0], line[:, 1], color='lightgray', linewidth=0.8, alpha=0.9)

        # Create heatmap
        x_min, y_min = self.bounds[0]
        x_max, y_max = self.bounds[1]
        extent = [x_min, x_max, y_min, y_max]
        
        # Normalize the density grid for better visualization
        if np.max(self.density_grid) > 0:
            normalized_grid = self.density_grid / np.max(self.density_grid)
        else:
            normalized_grid = self.density_grid
        
        im = self.ax.imshow(normalized_grid, 
                           extent=extent,
                           origin='lower',
                           cmap='viridis',
                           alpha=0.7)

        # Update or create colorbar
        if self.colorbar is None:
            self.colorbar = self.fig.colorbar(im)
            self.colorbar.ax.tick_params(labelsize=20)
        else:
            self.colorbar.update_normal(im)
            self.colorbar.ax.tick_params(labelsize=20)

        # Set plot limits
        # Focus on areas with activity rather than full bounds
        nonzero = np.nonzero(self.density_grid)
        if len(nonzero[0]) > 0 and len(nonzero[1]) > 0:
            # Convert grid indices to map coordinates
            min_y_idx, max_y_idx = np.min(nonzero[0]), np.max(nonzero[0])
            min_x_idx, max_x_idx = np.min(nonzero[1]), np.max(nonzero[1])
            
            # Add some margin
            margin = 5  # grid cells
            min_y_idx = max(0, min_y_idx - margin)
            max_y_idx = min(self.grid_size - 1, max_y_idx + margin)
            min_x_idx = max(0, min_x_idx - margin)
            max_x_idx = min(self.grid_size - 1, max_x_idx + margin)
            
            # Convert to map coordinates
            map_min_x = x_min + (min_x_idx / (self.grid_size - 1)) * (x_max - x_min)
            map_max_x = x_min + (max_x_idx / (self.grid_size - 1)) * (x_max - x_min)
            map_min_y = y_min + (min_y_idx / (self.grid_size - 1)) * (y_max - y_min)
            map_max_y = y_min + (max_y_idx / (self.grid_size - 1)) * (y_max - y_min)
            
            # Add extra margin in map coordinates
            x_margin = (map_max_x - map_min_x) * 0.2
            y_margin = (map_max_y - map_min_y) * 0.2
            
            self.ax.set_xlim(map_min_x - x_margin, map_max_x + x_margin)
            self.ax.set_ylim(map_min_y - y_margin, map_max_y + y_margin)

            self.ax.set_xlim(x_min, x_max)
            self.ax.set_ylim(y_min, y_max)
        else:
            # Fall back to full bounds if no activity
            self.ax.set_xlim(x_min, x_max)
            self.ax.set_ylim(y_min, y_max)
        
        # Add title and labels
        self.ax.set_title('Vehicle Density Heatmap', fontsize=20)
        self.ax.set_xlabel('X Position (m)', fontsize=20)
        self.ax.set_ylabel('Y Position (m)', fontsize=20)
        self.ax.tick_params(axis='both', which='major', labelsize=16)

        # Refresh canvas
        self.canvas.draw()

    def run(self):
        """Start the visualizer"""
        self.root.mainloop()

def main():
    visualizer = DensityVisualizer()
    visualizer.run()

if __name__ == "__main__":
    main() 