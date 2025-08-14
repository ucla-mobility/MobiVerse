import xml.etree.ElementTree as ET
import json
import random
import argparse
from typing import List, Dict, Any


def parse_pois(xml_file: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse POIs from the XML file and organize them by type."""
    tree = ET.parse(xml_file)
    root = tree.getroot()

    pois_by_type = {}
    for poi in root.findall("poi"):
        poi_type = poi.get("type")
        if poi_type not in pois_by_type:
            pois_by_type[poi_type] = []

        poi_data = {
            "name": poi.get("name"),
            "edge": poi.get("edge", ""),  # Some POIs might not have edge
            "type": poi_type,
        }
        pois_by_type[poi_type].append(poi_data)

    return pois_by_type


def generate_demographics() -> Dict[str, Any]:
    """Generate random demographics for an agent."""
    age_ranges = {
        "Undergraduate": (18, 23),
        "Graduate": (23, 35),
        "Faculty/Staff": (25, 65),
        "Visitor": (18, 70),
    }

    status = random.choice(list(age_ranges.keys()))
    age_range = age_ranges[status]

    demographics = {
        "age": random.randint(age_range[0], age_range[1]),
        "gender": random.choice(["Male", "Female", "Non-binary"]),
        "student_status": (
            status
            if "graduate" in status.lower() or "undergraduate" in status.lower()
            else "Not a Student"
        ),
        "income_level": random.choice(
            [
                "Low (Below $58,000/year)",
                "Medium ($58,000-$153,000/year)",
                "High (Above $153,000/year)",
            ]
        ),
        "education_level": random.choice(["High School", "Bachelor", "Master", "PhD"]),
        "work_status": random.choice(["Full-time", "Part-time", "Not Working"]),
    }

    return demographics


def generate_poi_sequence(
    pois_by_type: Dict[str, List[Dict[str, Any]]], sequence_length: int
) -> List[Dict[str, Any]]:
    """Generate a sequence of POIs for an agent."""
    sequence = []
    available_types = list(pois_by_type.keys())

    # Activity types mapping
    activity_types = {
        "restaurant": "food",
        "shop": "shopping",
        "parking": "transport",
        "office": "work",
    }

    # Generate sequence
    for order in range(1, sequence_length + 1):
        poi_type = random.choice(available_types)
        poi = random.choice(pois_by_type[poi_type])

        poi_entry = {
            "name": poi["name"],
            "edge": poi["edge"],
            "order": order,
            "type": poi["type"],
            "activity_type": activity_types.get(poi["type"], "other"),
            "stop_duration": random.randint(
                20, 90
            ),  # Random duration between 20-90 minutes
        }
        sequence.append(poi_entry)

    return sequence


def generate_agents(
    num_agents: int,
    pois_file: str,
    min_sequence_length: int = 3,
    max_sequence_length: int = 7,
) -> List[Dict[str, Any]]:
    """Generate a list of agents with POI sequences and demographics."""
    pois_by_type = parse_pois(pois_file)
    agents = []

    for i in range(num_agents):
        sequence_length = random.randint(min_sequence_length, max_sequence_length)
        agent = {
            "agent_id": f"agent_{i}",
            "poi_sequence": generate_poi_sequence(pois_by_type, sequence_length),
            "demographics": generate_demographics(),
        }
        agents.append(agent)

    return agents


def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description="Generate agents with POI sequences and demographics"
    )
    parser.add_argument(
        "-n",
        "--num-agents",
        type=int,
        default=50,
        help="Number of agents to generate (default: 50)",
    )
    parser.add_argument(
        "--min-sequence",
        type=int,
        default=3,
        help="Minimum number of POIs in sequence (default: 3)",
    )
    parser.add_argument(
        "--max-sequence",
        type=int,
        default=7,
        help="Maximum number of POIs in sequence (default: 7)",
    )
    parser.add_argument(
        "--pois-file",
        type=str,
        default="pois.add.xml",
        help="Input POIs XML file (default: pois.add.xml)",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default="route_info.json",
        help="Output JSON file (default: route_info.json)",
    )

    args = parser.parse_args()

    # Generate agents
    agents = generate_agents(
        num_agents=args.num_agents,
        pois_file=args.pois_file,
        min_sequence_length=args.min_sequence,
        max_sequence_length=args.max_sequence,
    )

    # Save to JSON file
    with open(args.output_file, "w") as f:
        json.dump(agents, f, indent=2)

    print(f"Successfully generated {args.num_agents} agents in {args.output_file}")


if __name__ == "__main__":
    main()
