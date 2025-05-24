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

                # Check if agent is stuck in same position
                if last_position == current_pos:
                    stuck_count += 1
                else:
                    stuck_count = 0
                    recovery_stage = 0
                    last_position = current_pos

                # Check for portal room or doors
                if "LineOfSight" in observation:
                    block_type = observation["LineOfSight"].get("type", "")
                    distance = observation["LineOfSight"].get("distance", float('inf'))
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

                # Handle movement and recovery when stuck
                if stuck_count == 0:
                    # Normal forward movement
                    print("Moving forward")
                    self.agent_host.sendCommand("move 1")
                elif recovery_stage == 0:
                    # Calculate potential new directions
                    right_turn_direction = (current_direction + 1) % 4
                    left_turn_direction = (current_direction - 1) % 4
                    
                    # Determine possible future positions
                    right_pos = self.calculate_future_position(current_pos, right_turn_direction)
                    left_pos = self.calculate_future_position(current_pos, left_turn_direction)
                    
                    # Calculate distances to starting point
                    right_distance = self.calculate_distance(right_pos, original_position)
                    left_distance = self.calculate_distance(left_pos, original_position)
                    
                    # Add randomness to direction choice
                    random_choice = random.random() < 0.2
                    
                    if random_choice or right_distance < left_distance:
                        # Try turning right
                        print("Trying to turn right")
                        self.agent_host.sendCommand("turn 1")
                        time.sleep(0.5)
                        self.agent_host.sendCommand("turn 0")
                        self.agent_host.sendCommand("move 1")
                        current_direction = right_turn_direction
                    else:
                        # Try turning left
                        print("Trying to turn left")
                        self.agent_host.sendCommand("turn -1")
                        time.sleep(0.5)
                        self.agent_host.sendCommand("turn 0")
                        self.agent_host.sendCommand("move 1")
                        current_direction = left_turn_direction
                    
                    recovery_stage = 1
                elif recovery_stage == 1:
                    # Try opposite direction from first attempt
                    if current_direction % 2 == 0:  # If previously went right
                        print("Trying to turn left")
                        self.agent_host.sendCommand("turn -1")
                        time.sleep(0.5)
                        self.agent_host.sendCommand("turn 0")
                        self.agent_host.sendCommand("move 1")
                        current_direction = (current_direction - 1) % 4
                    else:  # If previously went left
                        print("Trying to turn right")
                        self.agent_host.sendCommand("turn 1")
                        time.sleep(0.5)
                        self.agent_host.sendCommand("turn 0")
                        self.agent_host.sendCommand("move 1")
                        current_direction = (current_direction + 1) % 4
                    recovery_stage = 2
                elif recovery_stage == 2:
                    # Last resort: try to mine through
                    print("Mining through")
                    self.agent_host.sendCommand("pitch 0.2")
                    time.sleep(0.5)
                    self.agent_host.sendCommand("attack 1")
                    time.sleep(0.5)
                    self.agent_host.sendCommand("attack 0")
                    self.agent_host.sendCommand("pitch -0.2")
                    self.agent_host.sendCommand("move 1")
                    recovery_stage = 3  # Reset recovery stage

                # Track visited positions
                visited_positions.add(current_pos)

                # Reset if too many positions visited
                if len(visited_positions) > 100:
                    print("Too many visited positions, resetting direction")
                    self.agent_host.sendCommand("turn 1")
                    time.sleep(0.5)
                    visited_positions.clear()

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