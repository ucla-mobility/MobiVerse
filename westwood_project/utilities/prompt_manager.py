class PromptManager:
    def __init__(self):
        self.prompts = {
            'road_closure': self.road_closure_prompt,
            'event_creation': self.event_creation_prompt,
            'route_modification': self.route_modification_prompt
        }

    def road_closure_prompt(self, closed_edges, affected_pois, alternatives):
        """Generate prompt for road closure situation"""
        return (
            f"Roads {', '.join(closed_edges)} are closed. "
            f"The following destinations are no longer accessible: {', '.join(affected_pois)}. "
            f"Alternative locations you might consider: {alternatives} "
            f"Please suggest an alternative route that avoids these locations while maintaining "
            f"the general purpose of the trip."
        )

    def event_creation_prompt(self, event_data, agent_demographics):
        """Generate prompt for event creation"""
        # Format time information
        start_time = event_data.get('start_time', '12:00')
        duration = event_data.get('duration', 2)
        
        # Calculate end time
        try:
            start_hour = int(start_time.split(':')[0])
            end_hour = (start_hour + duration) % 24
            end_time = f"{end_hour:02d}:00"
        except:
            end_time = "14:00"  # Default 2 hours after default start
        
        return (
            f"A {event_data['type']} event is happening at {event_data['location']} in Westwood, Los Angeles. "
            f"The event details:\n"
            f"- Type: {event_data['type']}\n"
            f"- Event Name: {event_data['name']}\n"
            f"- Location: {event_data['location']}\n"
            f"- Start Time: {start_time}\n"
            f"- End Time: {end_time}\n"
            f"- Duration: {duration} hours\n\n"
            f"Agent demographics:\n"
            f"- Age: {agent_demographics.get('age', 'unknown')}\n"
            f"- Gender: {agent_demographics.get('gender', 'unknown')}\n"
            f"- Student Status: {agent_demographics.get('student_status', 'unknown')}\n"
            f"- Income Level: {agent_demographics.get('income_level', 'unknown')}\n\n"
            f"Please modify the agent's current activity chain to include this event at the specified time ({start_time}-{end_time}), "
            f"considering the agent's demographics and existing activities. Make sure to adjust or reschedule any conflicting activities "
            f"to accommodate the event during its scheduled time."
        )

    def route_modification_prompt(self, current_chain, situation, traffic_info):
        """Generate prompt for general route modification"""
        traffic_status = self.format_traffic_info(traffic_info)
        return (
            f"Current activity chain: {', '.join(current_chain)}\n"
            f"Traffic conditions: {traffic_status}\n"
            f"Situation: {situation}\n"
            f"Please suggest an optimized activity chain considering the situation and traffic conditions."
        )

    def format_traffic_info(self, traffic_info):
        """Format traffic information for prompts"""
        if not traffic_info:
            return "No significant traffic congestion reported"
        
        congested_edges = [
            edge for edge, info in traffic_info.items() 
            if info.get('is_congested', False)
        ]
        
        if congested_edges:
            return f"Heavy traffic detected on {len(congested_edges)} road segments"
        return "Normal traffic conditions" 