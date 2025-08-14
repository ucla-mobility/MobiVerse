"""
Downloads POIs from OpenStreetMap using the Overpass API and converts them to SUMO POI format

Example usage:
python download_and_convert_pois.py \
    --south 34.059512 \
    --west -118.456416 \
    --north 34.076852 \
    --east -118.436379 \
    --net westwood.net.xml \
    --output pois.add.xml
"""

#!/usr/bin/env python3
import argparse
import requests
import json
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom
import sumolib
from collections import defaultdict


def build_overpass_query(south, west, north, east):
    """Build Overpass API query for POIs within the bounding box"""
    # Define the POI types we want to search for
    amenities = ["restaurant", "cafe", "school", "parking"]
    amenity_filter = f'["amenity"~"^({"|".join(amenities)})$"]'

    # Build the complete query
    query = f"""
    [out:json][bbox:{south},{west},{north},{east}];
    (
        // Amenities (restaurants, cafes, schools, parking)
        nwr{amenity_filter};
        // Shops
        nwr["shop"];
        // Offices
        nwr["office"];
        // Entertainment venues
        nwr["leisure"~"^(entertainment|cinema|theatre|arts_centre)$"];
    );
    out body;
    >;
    out skel qt;
    """
    return query


def download_osm_pois(south, west, north, east):
    """Download POIs from OpenStreetMap using Overpass API"""
    # Build the query
    query = build_overpass_query(south, west, north, east)

    # Overpass API endpoint
    overpass_url = "http://overpass-api.de/api/interpreter"

    try:
        print("Downloading POIs from OpenStreetMap...")
        response = requests.post(overpass_url, data={"data": query})
        response.raise_for_status()  # Raise an exception for bad status codes
        print(f"Successfully downloaded POIs")
        print(f"Number of elements: {len(response.json()['elements'])}")
        return response.json()

    except requests.exceptions.RequestException as e:
        print(f"Error downloading POIs: {e}", file=sys.stderr)
        sys.exit(1)


def get_poi_type(tags):
    """Map OSM tags to SUMO POI types"""
    if "amenity" in tags:
        if tags["amenity"] in ["restaurant", "cafe"]:
            return "restaurant"
        elif tags["amenity"] == "school":
            return "school"
        elif tags["amenity"] == "parking":
            return "parking"
    elif "shop" in tags:
        return "shop"
    elif "office" in tags:
        return "office"
    elif "leisure" in tags and tags["leisure"] in [
        "entertainment",
        "cinema",
        "theatre",
        "arts_centre",
    ]:
        return "entertainment"
    return "unknown"


def get_poi_color(poi_type):
    """Define colors for different POI types in RGB format"""
    colors = {
        "restaurant": "255,0,0",  # red
        "school": "255,255,0",  # yellow
        "parking": "0,0,255",  # blue
        "shop": "0,255,0",  # green
        "office": "0,255,255",  # cyan
        "entertainment": "255,0,255",  # magenta
        "unknown": "128,128,128",  # gray
    }
    return colors.get(poi_type, "128,128,128")


def find_nearest_edge(net, x, y, radius=100):
    """Find the nearest edge in the network for given coordinates"""
    edges = net.getNeighboringEdges(x, y, radius)
    if not edges:
        return None
    # Sort by distance and return the closest edge
    edges.sort(key=lambda x: x[1])
    return edges[0][0].getID()


def create_unique_id(base_id, used_ids):
    """Create a unique ID by adding a counter if the base_id already exists"""
    if base_id not in used_ids:
        used_ids[base_id] = 0
        return base_id
    else:
        used_ids[base_id] += 1
        return f"{base_id}_{used_ids[base_id]}"


def convert_to_sumo_poi(osm_data, net):
    """Convert OSM data to SUMO POI format"""
    # Create the root element
    root = ET.Element("additional")

    # Dictionary to track used IDs and their count
    used_ids = defaultdict(int)

    # Process each element in the OSM data
    for element in osm_data["elements"]:
        if element["type"] == "node" and "tags" in element:
            poi_type = get_poi_type(element["tags"])
            if poi_type != "unknown":
                poi = ET.SubElement(root, "poi")

                # Create a clean base ID from name or use node ID
                base_id = element["tags"].get("name", str(element["id"]))
                base_id = "".join(
                    c if c.isalnum() or c == "_" else "_" for c in base_id
                )

                # Ensure unique ID
                unique_id = create_unique_id(base_id, used_ids)
                poi.set("id", unique_id)

                poi.set("type", poi_type)
                poi.set("color", get_poi_color(poi_type))
                poi.set("layer", "10")

                # Set lat/lon attributes
                poi.set("lat", str(element["lat"]))
                poi.set("lon", str(element["lon"]))

                # Find nearest edge
                x, y = net.convertLonLat2XY(element["lon"], element["lat"])
                edge_id = find_nearest_edge(net, x, y)
                if edge_id:
                    poi.set("edge", edge_id)

                # Set name if available
                if "name" in element["tags"]:
                    poi.set("name", element["tags"]["name"])

                # Set width and height
                poi.set("width", "5")
                poi.set("height", "5")

    # Convert to pretty XML
    xmlstr = minidom.parseString(ET.tostring(root)).toprettyxml(indent="    ")
    return xmlstr


def main():
    parser = argparse.ArgumentParser(
        description="Download POIs from OpenStreetMap and convert to SUMO format"
    )
    parser.add_argument(
        "--north", type=float, required=True, help="Northern latitude boundary"
    )
    parser.add_argument(
        "--south", type=float, required=True, help="Southern latitude boundary"
    )
    parser.add_argument(
        "--east", type=float, required=True, help="Eastern longitude boundary"
    )
    parser.add_argument(
        "--west", type=float, required=True, help="Western longitude boundary"
    )
    parser.add_argument(
        "--net",
        type=str,
        required=True,
        help="SUMO network file (.net.xml)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="pois.add.xml",
        help="Output SUMO POI file (default: pois.add.xml)",
    )

    args = parser.parse_args()

    # Validate coordinates
    if not (-90 <= args.south <= 90 and -90 <= args.north <= 90):
        print("Error: Latitude must be between -90 and 90 degrees", file=sys.stderr)
        sys.exit(1)
    if not (-180 <= args.west <= 180 and -180 <= args.east <= 180):
        print("Error: Longitude must be between -180 and 180 degrees", file=sys.stderr)
        sys.exit(1)
    if args.south >= args.north:
        print(
            "Error: Southern boundary must be less than northern boundary",
            file=sys.stderr,
        )
        sys.exit(1)
    if args.west >= args.east:
        print(
            "Error: Western boundary must be less than eastern boundary",
            file=sys.stderr,
        )
        sys.exit(1)

    # Download OSM data
    osm_data = download_osm_pois(args.south, args.west, args.north, args.east)

    # Load SUMO network
    net = sumolib.net.readNet(args.net)

    # Convert to SUMO POI format
    print("Converting to SUMO POI format...")
    sumo_poi = convert_to_sumo_poi(osm_data, net)

    # Write to file
    with open(args.output, "w") as f:
        f.write(sumo_poi)
    print(f"Successfully wrote SUMO POIs to {args.output}")


if __name__ == "__main__":
    main()
