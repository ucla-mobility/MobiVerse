import xml.etree.ElementTree as ET
import sumolib
import osmium
import json
import re
from collections import defaultdict

class POIExtractor(osmium.SimpleHandler):
    def __init__(self):
        super(POIExtractor, self).__init__()
        self.pois = []

    def node(self, n):
        tags = n.tags
        # Check both amenity and shop tags
        poi_type = None
        name = tags.get('name')

        if 'amenity' in tags:
            if tags['amenity'] in ['cafe', 'restaurant', 'fast_food', 'food_court', 'bar', 'pub', 'ice_cream', 
                                 'coffee_shop', 'bistro', 'dining_hall', 'cafeteria']:
                poi_type = tags['amenity']
        elif 'shop' in tags:
            if tags['shop'] in ['coffee', 'tea', 'beverages', 'bakery', 'convenience', 'supermarket']:
                poi_type = 'cafe' if tags['shop'] in ['coffee', 'tea', 'beverages'] else tags['shop']

        if poi_type and name:  # Only add POIs with names
            print(f"Found POI: {name} (type: {poi_type})")
            
            poi = {
                'id': str(n.id),
                'lat': n.location.lat,
                'lon': n.location.lon,
                'type': 'cafe' if poi_type in ['cafe', 'coffee_shop', 'coffee', 'tea'] else 'restaurant',
                'name': name,
                'has_name': True
            }
            self.pois.append(poi)

def clean_id(name):
    # Replace spaces and special characters with underscores
    clean = re.sub(r'[^a-zA-Z0-9]', '_', name)
    # Ensure it starts with a letter
    if not clean[0].isalpha():
        clean = 'poi_' + clean
    return clean

def is_valid_edge(net, edge_id):
    """Check if an edge is valid for passenger vehicles"""
    try:
        edge = net.getEdge(edge_id)
        # Check if edge has any connections (either incoming or outgoing)
        for lane in edge.getLanes():
            if lane.getOutgoing() or lane.getIncoming():
                return True
        return False
    except:
        return False

def main():
    print("Starting POI extraction...")
    
    # Load SUMO network
    net = sumolib.net.readNet('../sumo_config/westwood.net.xml')
    print("Loaded network file")
    
    # Extract POIs from OSM
    extractor = POIExtractor()
    extractor.apply_file('westwood.osm')
    print(f"Found {len(extractor.pois)} POIs in OSM data")
    
    # Keep track of name occurrences and locations
    name_count = defaultdict(int)
    location_map = {}  # To track POI locations for spacing
    
    # Match POIs to nearest edges
    matched_pois = []
    invalid_pois = []
    
    # Sort POIs by name length to prioritize shorter names
    sorted_pois = sorted(extractor.pois, key=lambda x: len(x['name']))
    
    for poi in sorted_pois:
        radius = 100  # Reduced radius to 100 meters (was 200)
        x, y = net.convertLonLat2XY(poi['lon'], poi['lat'])
        edges = net.getNeighboringEdges(x, y, radius)
        
        if len(edges) > 0:
            edges.sort(key=lambda x: x[1])
            valid_edge = None
            
            for edge, distance in edges:
                if is_valid_edge(net, edge.getID()):
                    valid_edge = edge
                    break
            
            if valid_edge:
                base_name = poi['name']
                
                # Reduced minimum distance to 30 meters
                too_close = False
                for existing_loc in location_map.values():
                    dx = x - existing_loc[0]
                    dy = y - existing_loc[1]
                    if (dx*dx + dy*dy) < 900:  # 30m * 30m
                        too_close = True
                        break
                
                if not too_close:
                    name_count[base_name] += 1
                    if name_count[base_name] > 1:
                        display_name = f"{base_name} ({name_count[base_name]})"
                        poi_id = f"{clean_id(base_name)}_{name_count[base_name]}"
                    else:
                        display_name = base_name
                        poi_id = clean_id(base_name)
                    
                    matched_poi = {
                        'id': poi_id,
                        'original_name': display_name,
                        'type': poi['type'],
                        'edge_id': valid_edge.getID(),
                        'lat': poi['lat'],
                        'lon': poi['lon']
                    }
                    matched_pois.append(matched_poi)
                    location_map[poi_id] = (x, y)
                    print(f"Matched POI: {display_name} (ID: {poi_id}) to edge {valid_edge.getID()}")
            else:
                invalid_pois.append((poi['name'], "No valid edge found"))
        else:
            invalid_pois.append((poi['name'], "No nearby edges"))
    
    print(f"\nSuccessfully matched {len(matched_pois)} POIs to edges")
    
    # Save as JSON for easy use
    with open('matched_pois.json', 'w') as f:
        json.dump(matched_pois, f, indent=2)
    
    # Create SUMO additional file with POIs
    root = ET.Element('additional')
    for poi in matched_pois:
        poi_element = ET.SubElement(root, 'poi')
        poi_element.set('id', poi['id'])
        
        # Set specific type for our POIs
        if poi['type'] == 'restaurant':
            poi_element.set('type', 'restaurant')
        elif poi['type'] == 'cafe':
            poi_element.set('type', 'cafe')
        else:
            poi_element.set('type', poi['type'])
        
        # Set color based on type
        if poi['type'] == 'restaurant':
            poi_element.set('color', "255,0,0")  # Red
        elif poi['type'] == 'cafe':
            poi_element.set('color', "0,255,0")  # Green
        else:
            poi_element.set('color', "255,0,255")  # Magenta
        
        poi_element.set('layer', "10")
        poi_element.set('lat', str(poi['lat']))
        poi_element.set('lon', str(poi['lon']))
        poi_element.set('name', poi['original_name'])
        poi_element.set('edge', poi['edge_id'])
        poi_element.set('width', "5")
        poi_element.set('height', "5")
    
    tree = ET.ElementTree(root)
    with open('pois.add.xml', 'wb') as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(f, encoding='utf-8')
    
    print("Created SUMO POI file")

if __name__ == '__main__':
    main() 