# MobiVerse: Scaling Urban Mobility Simulation with Hybrid Lightweight Domain-Specific Generator and Large Language Models

## Demo Video
[![Mobiverse Demo Video](resources/images/video_cover.png)](resources/videos/mobiverse_demo.mp4)

> **Preview Release Notice:** This repository contains a preview version of Mobiverse. The complete codebase will be released following the publication decision of our research paper. The current version demonstrates core functionality while the full system with additional features and comprehensive documentation will be made available upon paper acceptance.

## Overview

MobiVerse is an advanced urban mobility simulation platform that integrates Large Language Models (LLMs) with microscopic traffic simulation to enable realistic human mobility decision-making at scale. The platform addresses critical limitations in existing mobility simulation approaches by providing a flexible framework that supports various activity generation methods while incorporating LLM-powered behavioral adaptation. MobiVerse serves as a comprehensive research platform where users can integrate their own mobility modeling algorithms and test them with dynamic behavioral adaptation capabilities, enabling scalable simulations of up to tens of thousands of agents that can respond to environmental feedback in real-time.

<div align="center">
<img src="resources/images/flow_diagram_1.png" alt="Mobiverse UI showing interactive route modification, simulation environment, and realtime agent monitoring" height="300"/>
</div>

### Key Features
- **Flexible Algorithm Integration**: Open platform supporting various mobility modeling approaches - bring your own activity generation algorithms
- **Scalable Simulation**: Handles up to 53,000 agents with up to 20,000 simultaneously active in real-time simulation
- **LLM-Powered Behavioral Adaptation**: Agents dynamically respond to congestion, road closures, and special events through contextual reasoning
- **Real-time Traffic Simulation**: SUMO-based microscopic traffic modeling with bidirectional feedback integration
- **Interactive Research Environment**: GUI for real-time monitoring, experimental intervention, and algorithm testing
- **Comprehensive Demographic Modeling**: Agent behavior based on socioeconomic profiles including age, income, education, and employment status
- **Modular Design**: Easy integration of custom algorithms for population synthesis, activity generation, and behavioral modeling

### Project Structure
```
mobiverse/
├── westwood_project/           # Main simulation code
│   ├── utilities/             # Core simulation modules
│   ├── data/                  # Generated simulation data
│   ├── runs/                  # Simulation run results
│   ├── poi/                   # Points of Interest data
│   ├── sumo_config/           # SUMO configuration files
│   └── open_ai_api_key.txt    # OpenAI API key (replace with yours)
├── sumo/                      # SUMO installation directory
│   ├── README.md
│   └── sumo/                  # SUMO binaries and tools
└── README.md                  # This file
```

## Use Cases
### 1. Algorithm Development and Testing Platform
- **Scenario**: Test and validate your mobility modeling algorithms within a comprehensive simulation environment
- **Steps**: Integrate your activity generation method → Apply LLM-powered behavioral adaptation → Evaluate performance at scale → Compare with baseline approaches
- **Applications**: Algorithm development, model validation, comparative studies, research reproducibility


### 2. Large-Scale Urban Mobility Simulation
- **Scenario**: Simulate realistic mobility patterns for entire urban populations using various modeling approaches
- **Steps**: Configure activity generation method → Execute real-time traffic simulation → Monitor system-level performance and behavioral patterns
- **Applications**: Transportation system planning, infrastructure capacity analysis, policy evaluation at urban scale

### 3. Demographic Behavior Analysis
- **Scenario**: Analyze how socioeconomic characteristics (age, education, income, employment status) influence mobility decisions and adaptation patterns
- **Steps**: Configure diverse demographic profiles → Introduce environmental changes → LLM generates personalized behavioral responses → Analyze adaptation patterns across demographics
- **Applications**: Transportation equity research, demographic-aware urban planning, personalized mobility services

<div align="center">
<img src="resources/images/flow_diagram_2.png" alt="System architecture with demographic behavior example" height="500"/>
</div>

<div align="center">
<em>System architecture with an example of a college student reacting to different kinds of environment changes</em>
</div>

### 4. Dynamic Behavioral Adaptation Study

- **Scenario**: Test agent adaptation to real-time environmental changes using LLM-powered decision making with your own base activity generation
- **Steps**: Initialize activity chains using your algorithm → Introduce dynamic events (congestion, closures, special events) → LLM processes environmental feedback → Observe behavioral modifications and system responses
- **Applications**: Crisis response planning, adaptive transportation systems, behavioral pattern recognition, algorithm validation under dynamic conditions
- **Processing Rate**: 2,050 agents per minute for activity replanning, 200 agents per minute for route computation

<div align="center">
<img src="resources/images/student_schedule.png" alt="Student daily schedule showing mobility patterns" height="300"/>
</div>

<div align="center">
<em>Daily schedule of a student showing mobility decision patterns and activity chains</em>
</div>

### 5. Special Event Impact Analysis

- **Scenario**: Model large-scale event impacts on urban mobility patterns (e.g., Olympic Games, concerts, sports events) using your mobility models
- **Steps**: Apply your activity generation approach → Configure event parameters (location, capacity, demographics) → Calculate attendee selection → Simulate traffic pattern changes → Analyze system-wide impacts
- **Applications**: Event planning, traffic management, infrastructure assessment, testing event-response algorithms
- **Case Study**: LA 2028 Olympic Soccer Final simulation with 1,000 attendees demonstrating platform capabilities

<div align="center">
<img src="resources/images/heat_map.png" alt="Vehicle density heat map comparison" height="300"/>
</div>

<div align="center">
<em>Vehicle density heat map at 9:30 am: (a) baseline traffic at 9:30am without event, (b) traffic at 9:30am during the Olympic soccer event</em>
</div>

### 6. Emergency Response and Infrastructure Resilience
- **Scenario**: Test system resilience to infrastructure disruptions and emergency situations with your mobility algorithms
- **Steps**: Initialize with your activity generation method → Implement road closures or incidents → LLM-based agent replanning → Monitor rerouting patterns → Analyze network bottlenecks and recovery
- **Applications**: Disaster preparedness, emergency planning, infrastructure resilience assessment, algorithm stress testing

<div align="center">
<img src="resources/images/road_closure.png" alt="Road closure simulation" width="300"/>
</div>
<div align="center">
<em>Road closure simulation showing traffic rerouting patterns</em>
</div>

## Installation

### Requirements
- **SUMO**: 1.8.0+
- **Python**: 3.7+
- **OpenAI API Key**: For LLM route modifications

### 1. Clone SUMO
```bash
# Clone SUMO into the sumo/ directory
cd sumo/
git clone --recursive https://github.com/eclipse-sumo/sumo.git temp_sumo
mv temp_sumo/* .
mv temp_sumo/.* . 2>/dev/null || true
rmdir temp_sumo
```

### 2. Install Dependencies
```bash
# Install Python packages
pip install sumolib networkx osmium pyproj tkinter openai requests

# Install SUMO (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install sumo sumo-tools sumo-doc

# Set SUMO_HOME environment variable
export SUMO_HOME="/usr/share/sumo"
# Add to ~/.bashrc for persistence
echo 'export SUMO_HOME="/usr/share/sumo"' >> ~/.bashrc
```

### 3. Configure API Key
```bash
# Replace the API key file with your OpenAI API key
echo "your-openai-api-key-here" > westwood_project/open_ai_api_key.txt
```

## QuickStart

### 1. Generate Activity Chains and Routes
```bash
cd westwood_project

# Generate agent activity sequences using default method (up to 53,000 agents)
# Or integrate your own activity generation algorithm here
python create_routes.py -n 100 --generate-sequences

# Generate SUMO-compatible routes with time window (8:00 AM - 12:00 PM)
python create_routes.py --start-time 28800 --end-time 43200
```

### 2. Run Simulation with LLM Integration
```bash
# Terminal 1: Start SUMO controller with LLM behavioral adaptation
python dynamic_control.py

# Terminal 2: Launch interactive visualization dashboard
python trajectory_viewer.py
```

### 3. Test Your Algorithms and Interact with Simulation
1. Click "Connect" in the trajectory viewer to establish bidirectional communication
2. Select agents from the dropdown menu to monitor individual behaviors  
3. Click "Track Agent" to observe how your activity generation performs with LLM adaptation
4. Introduce environmental changes: road closures, special events, or traffic incidents
5. Observe real-time LLM-powered behavioral adaptations applied to your base activity chains
6. Compare performance and behavioral realism of different activity generation approaches

## Customize

### 1. Simulation Map

#### Change Geographic Area
**Location**: `westwood_project/`
```bash
# Download new area data (example: Santa Monica)
wget "https://api.openstreetmap.org/api/0.6/map?bbox=-118.5150,34.0050,-118.4750,34.0350" -O new_area.osm

# Generate new network
netconvert --osm new_area.osm -o new_area.net.xml \
    --geometry.remove \
    --roundabouts.guess \
    --ramps.guess \
    --junctions.join \
    --tls.guess-signals

# Update configuration files
# Edit: westwood.sumocfg -> change net-file to new_area.net.xml
```

#### Modify Network Properties
**Files to edit**:
- `westwood_project/sumo_config/westwood.net.xml`: Road network definition
- `westwood_project/sumo_config/westwood.sumocfg`: Main SUMO configuration

### 2. Activity Chain Generation - Bring Your Own Algorithm!

MobiVerse is designed as a flexible platform where you can integrate and test your own activity generation algorithms:

1. **Default Implementation**: Includes a baseline activity generation method for demonstration
2. **Your Algorithm Here**: Easy integration of machine learning models, survey-based methods, rule-based systems, or any custom approach
3. **Data Format**: Standard JSON format in `westwood_project/data/agent_sequences.json` - compatible with any generation method
4. **LLM Integration**: The LLM-powered behavioral adaptation layer works with any base activity chain format
5. **Comparative Testing**: Run multiple algorithms and compare their performance with LLM adaptation

```bash
# Replace the default generation with your algorithm
# Modify create_routes.py or create your own generation script
python create_routes.py --generate-sequences

# Test how your algorithm performs with LLM behavioral adaptation
python dynamic_control.py
```

### 3. LLM-Powered Activity Chain Modification

#### Customize Behavioral Adaptation Prompts
**File**: `westwood_project/utilities/prompt_manager.py`

The LLM component uses structured prompts that include agent demographics, environmental conditions, and contextual information to generate realistic behavioral adaptations.

#### Key Customization Areas:
- **Prompt templates**: Structured prompts for different adaptation scenarios (road closures, congestion, events)
- **Demographic integration**: How agent characteristics influence decision-making
- **Environmental feedback**: Real-time traffic and infrastructure condition integration
- **Event handling**: Special event processing with interest scoring models
- **Model settings**: OpenAI model parameters optimized for behavioral reasoning
- **Parallel processing**: Thread pool configuration for handling thousands of agents

### 4. Visualization and GUI

#### Customize Interface Colors/Layout
**File**: `westwood_project/trajectory_viewer.py`

## System Architecture

<div align="center">
<img src="resources/images/class_diagram.png" alt="System class diagram" width="500"/>
</div>

<div align="center">
<em>System architecture and component relationships</em>
</div>

## Configuration Files

- **`westwood.sumocfg`**: Main SUMO configuration
- **`westwood.net.xml`**: Road network definition  
- **`pois.add.xml`**: Points of Interest
- **`route_info.json`**: Generated routes
- **`matched_pois.json`**: POI data with coordinates

## Troubleshooting

### SUMO Issues
- Ensure `SUMO_HOME` is set correctly
- Check SUMO installation: `sumo --version`

### API Issues
- Confirm valid API key in `open_ai_api_key.txt`
- Check internet connection for LLM requests

### Performance
- Reduce agent count (`-n` parameter) for better performance
- Adjust simulation step length in configuration

## Citation

If you use MobiVerse in your research, please cite our paper:

```bibtex
@article{liu2025mobiverse,
  title={MobiVerse: Scaling Urban Mobility Simulation with Hybrid Lightweight Domain-Specific Generator and Large Language Models},
  author={Liu, Yifan and Liao, Xishun and Ma, Haoxuan and Liu, Jonathan and Jadhav, Rohan and Ma, Jiaqi},
  journal={arXiv preprint arXiv:2506.21784},
  year={2025}
}
```

## License
MIT License - see LICENSE file for details.