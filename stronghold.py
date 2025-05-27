import json
import random
import re
import sys
import time

from malmo import MalmoPython
from malmo.MalmoPython import AgentHost

# This is a small stronghold corridors I found at the moment. Use for debugging things.
# STRONGHOLD_COORDS = (-235.5, 23, -2283.5)

# Random x z spawn. Max is 24,320.
X_COORD = random.randint(-24320, 24320)
Z_COORD = random.randint(-24320, 24320)

def run_xml_mission():
    return '''<?xml version="1.0" encoding="UTF-8" ?>
    <Mission xmlns="http://ProjectMalmo.microsoft.com" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <About>
            <Summary>Stronghold Something</Summary>
        </About>
        
        <ServerSection>
            <ServerInitialConditions>
                <Time>
                    <StartTime>1000</StartTime>
                    <AllowPassageOfTime>false</AllowPassageOfTime>
                </Time>
                <Weather>clear</Weather>
            </ServerInitialConditions> 
            <ServerHandlers>
                <FileWorldGenerator src="C:\\Malmo-0.37.0-Windows-64bit_withBoost_Python3.7\\Minecraft\\run\\saves\\FlatWorld Stronghold Malmo"/>
                <ServerQuitFromTimeUp timeLimitMs="300000"/>
                <ServerQuitWhenAnyAgentFinishes/>
            </ServerHandlers>
        </ServerSection>
        
        <AgentSection mode="Creative">
            <Name>Golly</Name>
            <AgentStart>
                <Placement x="''' + str(X_COORD + 0.5) + '''" y="64" z="''' + str(Z_COORD) + '''"/>
                <Inventory>
                    <InventoryItem slot="0" type="diamond_pickaxe"/>
                </Inventory>
            </AgentStart>
            <AgentHandlers>
                <ObservationFromFullStats/>
                <ObservationFromChat/>
                <ObservationFromRay/>
                <ObservationFromGrid>
                    <Grid name="blocks">
                        <min x="-1" y="-1" z="-1"/>
                        <max x="1" y="1" z="1"/>
                    </Grid>
                </ObservationFromGrid>
                <AbsoluteMovementCommands/>
                <ContinuousMovementCommands turnSpeedDegs="180"/>
                <ChatCommands/>
                <MissionQuitCommands/>
            </AgentHandlers>
        </AgentSection>
    </Mission>'''

class Golly(object):
    def __init__(self, agent_host: AgentHost):
        self.agent_host = agent_host

    def get_stronghold_coords(self, observation: dict) -> (int, int):
        coords = None
        stronghold_msg = observation["Chat"][-1]
        match = re.search(r"(-?\d+) \(y\?\) (-?\d+)", stronghold_msg)
        if match:
            x = int(match.group(1))
            z = int(match.group(2))

            # Set offsets by -4 since starter staircase always spawn at 4 ~ 4 within its chunk.
            coords = (x - 4, z - 4)

        return coords

    def fly_down_to_staircase(self) -> None:
        self.agent_host.sendCommand("chat /gamemode 3")
        self.agent_host.sendCommand("crouch 1")
        while True:
            world_state = self.agent_host.getWorldState()
            if world_state.is_mission_running and world_state.number_of_observations_since_last_state > 0:
                observation = json.loads(world_state.observations[-1].text)
                print(observation)
                if not "LineOfSight" in observation:
                    continue

                if observation["LineOfSight"]["type"] == "stonebrick":
                    time.sleep(0.25)
                    self.agent_host.sendCommand("crouch 0")
                    self.agent_host.sendCommand("chat /gamemode 0")
                    time.sleep(0.25)
                    self.agent_host.sendCommand("chat /gamemode 1")
                    break

            if not world_state.is_mission_running:
                break

    def teleport_to_stronghold(self, coords: (int, int)) -> None:
        # x_coord = STRONGHOLD_COORDS[0]
        # y_coord = STRONGHOLD_COORDS[1]
        # z_coord = STRONGHOLD_COORDS[2]
        if coords is None:
            print("Failed to retrieve nearby stronghold coordinates!")
            return

        print(f"Teleporting agent to the stronghold starter staircase...")
        tp_command = f"chat /tp {coords[0]} ~ {coords[1]}"
        self.agent_host.sendCommand(tp_command)

    def pre_start(self) -> None:
        self.agent_host.sendCommand("move 1")
        time.sleep(1)
        self.agent_host.sendCommand("move 0")
        world_state = self.agent_host.getWorldState()
        if world_state.is_mission_running and world_state.number_of_observations_since_last_state > 0:
            pass

    def print_observation(self, observation):
        """Print detailed information about what the agent sees"""
        if "LineOfSight" in observation:
            los = observation["LineOfSight"]
            print("\n=== Line of Sight Information ===")
            print(f"Block Type: {los.get('type', 'None')}")
            print(f"Distance: {los.get('distance', 'Unknown')} blocks")
            print(f"Block Position: x={los.get('x', 'Unknown')}, y={los.get('y', 'Unknown')}, z={los.get('z', 'Unknown')}")
            print(f"Block Variant: {los.get('variant', 'None')}")
            print("===============================\n")
        else:
            print("\nNo block in line of sight\n")

    # This file contains the StrongholdFinder class which is responsible for locating and navigating
    # through a Minecraft stronghold structure. It includes functionality for teleporting to stronghold
    # coordinates, finding the portal room, and handling movement/navigation within the stronghold.

    def normalize_yaw(self, yaw):
        """Normalize yaw to nearest cardinal direction (0, 90, 180, 270, -90, -180, -270)"""
        # First normalize to 0-360
        yaw = yaw % 360
        # Round to nearest 90 degrees
        cardinal = round(yaw / 90) * 90
        # Convert to negative if it's closer to negative
        if cardinal > 180:
            cardinal = cardinal - 360
        return cardinal

    def get_cardinal_direction(self, yaw):
        """Convert yaw to nearest cardinal direction (0, 90, 180, 270)"""
        # Normalize yaw to 0-360
        yaw = yaw % 360
        # Round to nearest 90 degrees
        cardinal = round(yaw / 90) * 90
        # Ensure we get exactly 0, 90, 180, or 270
        if cardinal == 360:
            cardinal = 0
        return cardinal

    def is_at_cardinal(self, yaw):
        """Check if the agent is facing a cardinal direction"""
        tolerance = 0.1  # Very small tolerance for exact cardinal directions
        normalized = self.normalize_yaw(yaw)
        return abs(yaw - normalized) <= tolerance

    def turn_to_direction(self, target_yaw):
        """Turn the agent to face the target yaw"""
        print(f"Starting turn to target yaw: {target_yaw}")
        
        while True:
            world_state = self.agent_host.getWorldState()
            if world_state.number_of_observations_since_last_state > 0:
                observation = json.loads(world_state.observations[-1].text)
                current_yaw = observation.get('Yaw', 0)
                normalized_yaw = self.normalize_yaw(current_yaw)
                
                print(f"Current yaw: {current_yaw:.2f}, Normalized: {normalized_yaw}, Target: {target_yaw}")
                
                # Stop if we reach any cardinal direction
                if self.is_at_cardinal(current_yaw):
                    print(f"Reached cardinal direction: {normalized_yaw}")
                    self.agent_host.sendCommand("turn 0")
                    return
                
                # Calculate shortest turn direction
                diff = (target_yaw - current_yaw) % 360
                if diff > 180:
                    print("Turning left")
                    self.agent_host.sendCommand("turn -1")
                else:
                    print("Turning right")
                    self.agent_host.sendCommand("turn 1")
            
            time.sleep(0.05)  # Check more frequently for more precise turning

    def stabilize_direction(self, target_yaw):
        """Stabilize the agent's direction to face exactly the target yaw"""
        print("Stabilizing direction...")
        stabilization_time = 2.0  # Increased time for more precise stabilization
        start_time = time.time()
        tolerance = 0.1  # Very small tolerance for exact yaw matching
        
        while time.time() - start_time < stabilization_time:
            world_state = self.agent_host.getWorldState()
            if world_state.number_of_observations_since_last_state > 0:
                observation = json.loads(world_state.observations[-1].text)
                current_yaw = observation.get('Yaw', 0)
                
                # Normalize current yaw to nearest cardinal direction
                normalized_yaw = self.get_cardinal_direction(current_yaw)
                print(f"Current yaw: {current_yaw:.2f}, Normalized: {normalized_yaw}, Target: {target_yaw}")
                
                # Check if current yaw matches both normalized and target yaw
                if abs(current_yaw - target_yaw) <= tolerance and abs(current_yaw - normalized_yaw) <= tolerance:
                    print(f"Exact yaw match achieved: {current_yaw:.2f}")
                    self.agent_host.sendCommand("turn 0")
                    break
                
                # If not matching, make adjustments
                diff = (target_yaw - current_yaw) % 360
                if diff > 180:
                    print("Turning left to match yaw")
                    self.agent_host.sendCommand("turn -0.1")  # Small left turn
                else:
                    print("Turning right to match yaw")
                    self.agent_host.sendCommand("turn 0.1")   # Small right turn
            
            time.sleep(0.05)
        
        # Final check and stop
        self.agent_host.sendCommand("turn 0")
        
        # Verify final direction
        world_state = self.agent_host.getWorldState()
        if world_state.number_of_observations_since_last_state > 0:
            observation = json.loads(world_state.observations[-1].text)
            final_yaw = observation.get('Yaw', 0)
            final_normalized = self.get_cardinal_direction(final_yaw)
            print(f"Final direction stabilized at: {final_yaw:.2f} degrees (normalized: {final_normalized})")
            
            # If still not matching, make one final adjustment
            if abs(final_yaw - target_yaw) > tolerance:
                print("Making final adjustment to match exact yaw")
                diff = (target_yaw - final_yaw) % 360
                if diff > 180:
                    self.agent_host.sendCommand("turn -0.5")
                else:
                    self.agent_host.sendCommand("turn 0.5")
                time.sleep(0.1)
                self.agent_host.sendCommand("turn 0")

    def find_portal_room(self):
        # Enable creative mode for easier movement and mining
        self.agent_host.sendCommand("chat /gamemode 1")
        time.sleep(0.5)
        
        # Give night vision potion to see better in dark areas
        self.agent_host.sendCommand("chat /effect @p night_vision 999999 1 true")
        time.sleep(0.5)
        
        # Enable flying capability for better navigation
        self.agent_host.sendCommand("chat /ability @p mayfly true")
        time.sleep(0.5)
        
        # Activate flying mode
        self.agent_host.sendCommand("fly 1")
        time.sleep(0.5)

        # Initialize tracking variables
        visited_positions = set()          # Keep track of where we've been
        stuck_count = 0                    # Counter for when agent gets stuck
        last_position = None               # Store previous position
        recovery_stage = 0                 # Different stages of unstuck behavior
        original_position = None           # Starting position reference
        current_direction = 0              # Direction facing (0:forward, 1:right, 2:back, 3:left)
        consecutive_turns = 0              # Track consecutive turns to prevent circles
        last_turn_time = 0                 # Track when we last turned
        turn_cooldown = 2.0               # Minimum time between turns
        is_moving = False                  # Track if agent is currently moving

        while True:
            world_state = self.agent_host.getWorldState()
            if not world_state.is_mission_running:
                break

            if world_state.number_of_observations_since_last_state > 0:
                # Get current observation data
                observation = json.loads(world_state.observations[-1].text)
                
                # Get and round current position coordinates
                current_pos = (
                    round(observation.get('XPos', 0), 1),
                    round(observation.get('YPos', 0), 1),
                    round(observation.get('ZPos', 0), 1)
                )

                # Store initial position if not already saved
                if original_position is None:
                    original_position = current_pos
                    print(f"\nOriginal position saved: x={original_position[0]}, y={original_position[1]}, z={original_position[2]}")

                # Display current position for debugging
                print(f"\nCurrent Position: x={current_pos[0]}, y={current_pos[1]}, z={current_pos[2]}")
                self.print_observation(observation)

                # Check for portal room or doors
                if "LineOfSight" in observation:
                    block_type = observation["LineOfSight"].get("type", "")
                    distance = observation["LineOfSight"].get("distance", float('inf'))
                    
                    # Check if we're about to hit a wall
                    if distance <= 1.0 and block_type not in ["air", "iron_door", "wooden_door"]:
                        print("Wall detected! Starting wall handling sequence...")
                        
                        # Step 1: Stop
                        print("Step 1: Stopping")
                        self.agent_host.sendCommand("move 0")
                        is_moving = False
                        time.sleep(0.25)  # Wait for stop
                        
                        # Step 2: Turn right
                        print("Step 2: Turning right")
                        current_yaw = observation.get('Yaw', 0)
                        print(f"Current yaw before turn: {current_yaw}")
                        current_cardinal = self.get_cardinal_direction(current_yaw)
                        target_yaw = (current_cardinal + 90) % 360
                        print(f"Target yaw for turn: {target_yaw}")
                        
                        # Start turning
                        print("Sending turn command")
                        self.agent_host.sendCommand("turn 1")
                        
                        # Wait for turn to complete
                        start_yaw = current_yaw
                        turn_start_time = time.time()
                        max_turn_time = 1.0  # Maximum time to spend turning
                        
                        while True:
                            # Check if we've been turning too long
                            if time.time() - turn_start_time > max_turn_time:
                                print("Turn timeout - forcing stop")
                                self.agent_host.sendCommand("turn 0")
                                break
                                
                            world_state = self.agent_host.getWorldState()
                            if world_state.number_of_observations_since_last_state > 0:
                                observation = json.loads(world_state.observations[-1].text)
                                current_yaw = observation.get('Yaw', 0)
                                normalized_yaw = self.normalize_yaw(current_yaw)
                                print(f"Turning... Current yaw: {current_yaw:.2f}, Normalized: {normalized_yaw}")
                                
                                # Check if we've reached the target cardinal direction
                                if normalized_yaw == target_yaw:
                                    print(f"Reached target cardinal direction: {normalized_yaw}")
                                    self.agent_host.sendCommand("turn 0")
                                    break
                            
                            time.sleep(0.05)
                        
                        current_direction = (current_direction + 1) % 4
                        time.sleep(0.25)  # Wait after turn
                        
                        # Step 3: Stabilize direction
                        print("Step 3: Stabilizing direction")
                        self.stabilize_direction(target_yaw)
                        
                        # Step 4: Move forward
                        print("Step 4: Moving forward")
                        self.agent_host.sendCommand("move 1")
                        is_moving = True
                        stuck_count = 0
                        
                        # Force a small forward movement
                        time.sleep(0.5)  # Move forward for a short time
                        continue
                    elif block_type == "air" and distance > 1.0:
                        # If there's empty space ahead, prioritize moving forward
                        if not is_moving:
                            print("Empty space ahead, moving forward")
                            self.agent_host.sendCommand("move 1")
                            is_moving = True
                            stuck_count = 0
                            continue
                    
                    if block_type == "end_portal_frame":
                        print(f"\nFound the portal room!")
                        # Clean up effects and return to normal mode
                        self.agent_host.sendCommand("chat /effect @p clear")
                        time.sleep(0.5)
                        self.agent_host.sendCommand("fly 0")
                        self.agent_host.sendCommand("chat /ability @p mayfly false")
                        self.agent_host.sendCommand("chat /gamemode 0")
                        return True
                    elif block_type in ["iron_door", "wooden_door"]:
                        # Attempt to open any doors found
                        print(f"\nFound a door at distance {distance}")
                        self.agent_host.sendCommand("use 1")
                        time.sleep(0.5)
                        self.agent_host.sendCommand("use 0")

                # Check if agent is stuck in same position
                if last_position == current_pos:
                    stuck_count += 1
                else:
                    stuck_count = 0
                    recovery_stage = 0
                    last_position = current_pos

                # Handle movement and recovery when stuck
                current_time = time.time()
                if stuck_count == 0 and not is_moving:
                    # Only move forward if we're not already moving and not stuck
                    print("Moving forward")
                    self.agent_host.sendCommand("move 1")
                    is_moving = True
                    consecutive_turns = 0  # Reset turn counter when moving forward
                elif recovery_stage == 0 and (current_time - last_turn_time) >= turn_cooldown and stuck_count > 0:
                    # Only turn if we're stuck and enough time has passed since last turn
                    # Calculate potential new directions
                    right_turn_direction = (current_direction + 1) % 4
                    left_turn_direction = (current_direction - 1) % 4
                    
                    # Determine possible future positions
                    right_pos = self.calculate_future_position(current_pos, right_turn_direction)
                    left_pos = self.calculate_future_position(current_pos, left_turn_direction)
                    
                    # Calculate distances to starting point
                    right_distance = self.calculate_distance(right_pos, original_position)
                    left_distance = self.calculate_distance(left_pos, original_position)
                    
                    # Add randomness to direction choice, but prefer moving away from start
                    random_choice = random.random() < 0.2
                    
                    # Stop before turning
                    print("Stopping before turn")
                    self.agent_host.sendCommand("move 0")
                    is_moving = False
                    time.sleep(0.25)  # Wait for stop
                    
                    # Choose direction that moves away from start more often
                    if (random_choice and right_distance > left_distance) or (not random_choice and right_distance < left_distance):
                        # Try turning right
                        print("Trying to turn right")
                        current_yaw = observation.get('Yaw', 0)
                        current_cardinal = self.get_cardinal_direction(current_yaw)
                        target_yaw = (current_cardinal + 90) % 360
                        self.turn_to_direction(target_yaw)
                        self.stabilize_direction(target_yaw)
                        current_direction = right_turn_direction
                    else:
                        # Try turning left
                        print("Trying to turn left")
                        current_yaw = observation.get('Yaw', 0)
                        current_cardinal = self.get_cardinal_direction(current_yaw)
                        target_yaw = (current_cardinal - 90) % 360
                        self.turn_to_direction(target_yaw)
                        self.stabilize_direction(target_yaw)
                        current_direction = left_turn_direction
                    
                    consecutive_turns += 1
                    last_turn_time = current_time
                    
                    # If we've turned too many times in a row, try to break the pattern
                    if consecutive_turns >= 3:
                        print("Too many consecutive turns, trying to break pattern")
                        # Turn 180 degrees to go back
                        current_yaw = observation.get('Yaw', 0)
                        current_cardinal = self.get_cardinal_direction(current_yaw)
                        target_yaw = (current_cardinal + 180) % 360
                        self.turn_to_direction(target_yaw)
                        current_direction = (current_direction + 2) % 4
                        consecutive_turns = 0
                    
                    # Check if we can move forward after turning
                    if "LineOfSight" in observation:
                        block_type = observation["LineOfSight"].get("type", "")
                        distance = observation["LineOfSight"].get("distance", float('inf'))
                        if block_type == "air" and distance > 1.0:
                            print("Moving forward after turn")
                            self.agent_host.sendCommand("move 1")
                            is_moving = True
                            recovery_stage = 1

                # Track visited positions
                visited_positions.add(current_pos)

                # Reset if too many positions visited
                if len(visited_positions) > 100:
                    print("Too many visited positions, resetting direction")
                    self.agent_host.sendCommand("move 0")
                    is_moving = False
                    time.sleep(0.25)
                    self.agent_host.sendCommand("turn 1")
                    time.sleep(turn_time * 2)  # Turn 180 degrees
                    self.agent_host.sendCommand("turn 0")
                    current_direction = (current_direction + 2) % 4
                    visited_positions.clear()
                    consecutive_turns = 0

            time.sleep(0.1)

        # Clean up if portal room not found
        print("Failed to find the portal room")
        self.agent_host.sendCommand("chat /effect @p clear")
        return False

    def calculate_future_position(self, current_pos, direction):
        """Calculate the position after moving in the given direction"""
        x, y, z = current_pos
        if direction == 0:  # forward
            return (x + 1, y, z)
        elif direction == 1:  # right
            return (x, y, z + 1)
        elif direction == 2:  # back
            return (x - 1, y, z)
        else:  # left
            return (x, y, z - 1)

    def calculate_distance(self, pos1, pos2):
        """Calculate Euclidean distance between two positions"""
        return ((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2 + (pos1[2] - pos2[2])**2)**0.5

    def mine_hidden_path(self):
        pass

def main():
    agent_host = MalmoPython.AgentHost()
    try:
        agent_host.parse(sys.argv)
    except RuntimeError as e:
        print('ERROR:', e)
        print(agent_host.getUsage())
        exit(1)
    if agent_host.receivedArgument("help"):
        print(agent_host.getUsage())
        exit(0)

    my_mission = MalmoPython.MissionSpec(run_xml_mission(), True)
    my_mission_record = MalmoPython.MissionRecordSpec()

    # Attempt to start a mission:
    max_retries = 3
    for retry in range(max_retries):
        try:
            agent_host.startMission(my_mission, my_mission_record)
            break
        except RuntimeError as e:
            if retry == max_retries - 1:
                print("Error starting mission:", e)
                exit(1)
            else:
                time.sleep(2)

    # Loop until mission starts:
    print("Waiting for the mission to start ", end=' ')
    world_state = agent_host.getWorldState()
    while not world_state.has_mission_begun:
        print(".", end="")
        time.sleep(0.1)
        world_state = agent_host.getWorldState()
        for error in world_state.errors:
            print("Error:", error.text)

    print()
    print("Mission running ", end=' ')

    # ADD SOMETHING HERE...
    golly = Golly(agent_host)

    agent_host.sendCommand("chat /locate Stronghold")
    while True:
        world_state = agent_host.getWorldState()
        if world_state.is_mission_running and world_state.number_of_observations_since_last_state > 0:
            observation = json.loads(world_state.observations[-1].text)
            print(observation)
            if "Chat" in observation:
                coords = golly.get_stronghold_coords(observation)
                golly.teleport_to_stronghold(coords)
                break
        # NOTE: There's a chance observation could miss retrieving stronghold coords from chat. So using
        # time.sleep() would not be efficient here.
        # time.sleep(1)

        if not world_state.is_mission_running:
            break

    golly.fly_down_to_staircase()

    golly.find_portal_room()


    # Loop until mission ends:
    while world_state.is_mission_running:
        print(".", end="")
        time.sleep(0.1)
        world_state = agent_host.getWorldState()
        for error in world_state.errors:
            print("Error:", error.text)

    print()
    print("Mission ended")
    # Mission has ended.

if __name__ == "__main__":
    main()
