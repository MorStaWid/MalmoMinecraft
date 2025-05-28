"""
This file implements a pathfinding algorithm for Minecraft using the Malmo platform.
It provides functionality to:
1. Navigate through different test environments (mazes, rooms, corridors)
2. Detect and avoid unsafe blocks (water, lava, air)
3. Track visited and safe blocks for exploration
4. Handle agent movement and environment observation
The code uses a grid-based observation system to make navigation decisions.
"""

# Import necessary modules for future Python features
from __future__ import annotations

# Import required libraries for JSON handling, mathematical operations, and system functions
import json
import math
import random
import re
import sys
import time

# Import Malmo-specific modules for Minecraft integration
from malmo import MalmoPython
from malmo.MalmoPython import AgentHost

# Define the current test environment to use
INSERT_STRING_HERE = "Large Room Corridor"

# Dictionary containing all available test environments and their starting coordinates
# Format: "Environment Name": (x, y, z) coordinates
OPTIONS = {
    "Block Surround": (0, 14, -9),        # Simple block arrangement
    "1x1 Maze": (0, 14, 0),              # Basic maze layout
    "3x3 Basic Pathfind": (-17, 14, 0),   # Larger pathfinding test
    "Large Room Corridor": (-17, 14, 16), # Complex room with corridors
    "Up and Down Stairs": (-33, 14, 0),   # Vertical movement test
    "Up and Down Slabs": (-41, 14, 36),   # Slab-based vertical movement
    "Spiral Staircase": (-33, 14, 36),    # Complex vertical navigation
    "Door Open": (-41, 14, 0),           # Door interaction test
    "Iron Door Open": (-41, 14, 17),     # Iron door interaction test
    "Hidden Path": (-49, 14, 0),         # Path with hidden elements
    "Slabbed Hidden Path": (-56, 14, 0), # Hidden path with slabs
    "Five-way Crossing": (-60, 14, 21),  # Complex intersection test
    "Fountain": (-59, 14, 45),           # Water feature navigation
    "Portal Room Detection": (-65, 14, 0) # Portal detection test
}

TURNS = {
    "none",
    "edge",
    "wall",
    "left_corner",
    "right_corner",
    "blocked_middle"
}

def run_xml_mission():
    """
    Generates the XML mission specification for Malmo.
    
    Parameters:
        None
        
    Returns:
        str: Complete XML string for mission initialization
        
    This function creates the XML configuration that defines:
    - Mission properties and time settings
    - World generation parameters
    - Agent properties and capabilities
    - Observation and movement handlers
    """
    # Return the XML string with dynamic positioning based on selected environment
    return '''<?xml version="1.0" encoding="UTF-8" ?>
    <Mission xmlns="http://ProjectMalmo.microsoft.com" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <About>
            <Summary>Stronghold Pathfind Playground</Summary>
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
                <FileWorldGenerator src="C:\\Malmo-0.37.0-Windows-64bit_withBoost_Python3.7\\Minecraft\\run\\saves\\Algorithm World Test"/>
                <ServerQuitFromTimeUp timeLimitMs="10000"/>
                <ServerQuitWhenAnyAgentFinishes/>
            </ServerHandlers>
        </ServerSection>
        
        <AgentSection mode="Creative">
            <Name>Golly</Name>
            <AgentStart>
                <Placement x="''' + str(OPTIONS[INSERT_STRING_HERE][0] + 0.5) + '''" y="''' + str(OPTIONS[INSERT_STRING_HERE][1] + 1) + '''" z="''' + str(OPTIONS[INSERT_STRING_HERE][2] + 0.5) + '''"/>
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
                        <min x="-2" y="-3" z="-2"/>
                        <max x="2" y="2" z="2"/>
                    </Grid>
                </ObservationFromGrid>
                <AbsoluteMovementCommands/>
                <ContinuousMovementCommands turnSpeedDegs="180"/>
                <ChatCommands/>
                <MissionQuitCommands/>
                <AgentQuitFromTouchingBlockType>
                    <Block type="diamond_block"/>
                </AgentQuitFromTouchingBlockType>
            </AgentHandlers>
        </AgentSection>
    </Mission>'''

def get_y_elevation_offset(observation: dict, index: int, size: int) -> int | None:
    """
    Calculates the vertical offset for a given block position.
    
    Parameters:
        observation (dict): Dictionary containing block observations from the environment
        index (int): Index of the block in the observation grid
        size (int): Size of the observation grid
        
    Returns:
        int | None: Vertical offset if a valid elevation is found, None otherwise
        
    This function analyzes the vertical structure of blocks to determine
    safe navigation heights and detect elevation changes in the environment.
    """
    # Initialize the vertical offset as None
    y = None
    # Define blocks that are considered safe to have above the current block
    accepted_above_block = { "door", "iron_door", "air"}
    
    # Iterate through vertical layers of the observation grid
    for i in range(len(observation["blocks"]) // (size ** 2) - 1):
        # Check if current block is solid and block above is acceptable
        if observation["blocks"][(i * 25) + index] != "air" and observation["blocks"][(i + 1) * 25 + index] in accepted_above_block:
            # Calculate the vertical offset (2 blocks below the current position) 
            y = i - 2

    return y

def log_block_observations(visited_block_coord, to_be_visited, observation):
    """
    Continuously logs the visited blocks and blocks to visit to a file.
    Parameters:
        visited_block_coord (set): Set of visited block coordinates (x, y, z)
        to_be_visited (set): Set of block coordinates queued for exploration
        observation (dict): Dictionary containing current observations
    Returns:
        None
    """
    # Write new observations to file
    with open('block_observations.txt', 'a') as f:
        f.write("\n=== New Observation ===\n")
        
        # Write agent orientation info
        f.write(f"\nAgent Orientation:\n")
        f.write(f"Yaw: {observation.get('Yaw', 'N/A')}\n")
        f.write(f"Pitch: {observation.get('Pitch', 'N/A')}\n")
        
        # Write line of sight info if available
        if "LineOfSight" in observation:
            los = observation["LineOfSight"]
            f.write(f"\nLine of Sight:\n")
            f.write(f"Type: {los.get('type', 'N/A')}\n")
            f.write(f"Distance: {los.get('distance', 'N/A')}\n")
        
        # Group blocks by Y level
        blocks_by_y = {}
        for block in visited_block_coord:
            x, y, z = block
            if y not in blocks_by_y:
                blocks_by_y[y] = []
            blocks_by_y[y].append(block)
            
        # Get agent Y position
        agent_y = math.floor(observation.get("YPos", 0))
        
        # Print blocks for all Y levels in grid range (-3 to +2)
        for relative_y in range(-3, 3):
            y = agent_y + relative_y
                
            f.write(f"\nY = {y} / {relative_y}\n")

            # Calculate base index for this Y level
            base_index = (relative_y + 3) * 25  # 25 blocks per layer (5x5)

            # Print 5x5 grid representation
            f.write("Grid Layout:\n")
            for row in range(5):
                grid_row = []
                for col in range(5):
                    idx = base_index + (row * 5) + col
                    grid_row.append(f"[{idx:3d}]")
                f.write("  ".join(grid_row) + "\n")
            f.write("\n")

            # Print block details
            f.write("Block Details:\n")
            for i in range(25):  # Iterate through all blocks in the 5x5 grid
                idx = base_index + i
                if idx < len(observation["blocks"]):
                    block_type = observation["blocks"][idx]
                    # Calculate relative coordinates for this block
                    rel_x = (i % 5) - 2  # Center is at x=0
                    rel_z = (i // 5) - 2  # Center is at z=0
                    # Calculate absolute coordinates
                    abs_x = math.floor(observation["XPos"]) + rel_x
                    abs_z = math.floor(observation["ZPos"]) + rel_z
                    f.write(f"[{idx}] ({abs_x}, {y}, {abs_z}) - {block_type}")
                    
                    # Agent is at center of grid (x=0,z=0) at y=0 level
                    if relative_y == 0 and rel_x == 0 and rel_z == 0:
                        f.write(" <-- Agent Position")
                    f.write("\n")
            f.write("\n")
        
        # Print visited blocks
        f.write("\nVisited Blocks:\n")
        for block in visited_block_coord:
            f.write(f"{block}\n")
        
        # Print blocks to visit
        f.write("\nBlocks to Visit:\n")
        for block in to_be_visited:
            f.write(f"{block}\n")
        
        f.write("\n" + "-"*50 + "\n")
        f.flush() # Ensure the file is written immediately
        
def yaw_to_direction(yaw):
    # Normalize yaw to [-180, 180)
    yaw = ((yaw + 180) % 360) - 180
    if -45 <= yaw < 45:
        return "S"   # Facing +Z (South)
    elif 45 <= yaw < 135:
        return "W"   # Facing -X (West)
    elif yaw >= 135 or yaw < -135:
        return "N"   # Facing -Z (North)
    elif -135 <= yaw < -45:
        return "E"   # Facing +X (East)
    return "unknown"

def need_to_turn(agent_host, current_direction, direction, observation, center_idx, center_block_offset, to_be_visited, visited_block_coord, size):
    """
    Turns the agent to a new direction and checks for ledges.
    Ensures current_direction matches the agent's yaw.
    Stops the agent if a ledge is detected.
    Returns: updated current_direction, turn_type (from TURNS set)
    """
    # 1. Update current_direction based on agent's current yaw
    yaw = observation.get("Yaw", 0)
    agent_direction = yaw_to_direction(yaw)
    if agent_direction in direction:
        current_direction = agent_direction

    # 2. Check for ledge (air in front and below)
    # The following logic assumes the agent is always facing "forward" in the grid
    front_below_block = observation["blocks"][(2 * 25) + (center_idx + (1 * size))] # y=-1, one blocks ahead
    front_below_block_two = observation["blocks"][(2 * 25) + (center_idx + (2 * size))] # y=-1, two blocks ahead
    front_below_stair = observation["blocks"][(1 * 25) + (center_idx + (1 * size))] # y=-2, one blocks ahead

    if front_below_block_two == "air" and front_below_block == "air" and  front_below_stair == "air":
        print("Danger! Air detected ahead at agent's level and below. Stopping!")
        log_block_observations(visited_block_coord, to_be_visited, observation)
        # Calculate and remove the front block coordinate from to_be_visited
        front_xpos = math.floor(observation["XPos"]) - center_block_offset[center_idx + (2 * size)][0]
        front_ypos = math.floor(observation["YPos"])
        front_zpos = math.floor(observation["ZPos"]) - center_block_offset[center_idx + (2 * size)][1]
        front_block_coord = (front_xpos, front_ypos, front_zpos)
        if front_block_coord in to_be_visited:
            to_be_visited.remove(front_block_coord)
            print(f"Removed front_block_coord:{front_block_coord} from to_be_visited")
        agent_host.sendCommand("move 0")  # Stop movement
        return current_direction, "edge"  # Return edge from TURNS
    
    elif front_below_block_two == "air":
        print("Danger! Air detected ahead at agent's level and below. Stopping!")
        log_block_observations(visited_block_coord, to_be_visited, observation)
        # Calculate and remove the front block coordinate from to_be_visited
        front_xpos = math.floor(observation["XPos"]) - center_block_offset[center_idx + (2 * size)][0]
        front_ypos = math.floor(observation["YPos"])
        front_zpos = math.floor(observation["ZPos"]) - center_block_offset[center_idx + (2 * size)][1]
        front_block_coord = (front_xpos, front_ypos, front_zpos)
        if front_block_coord in to_be_visited:
            to_be_visited.remove(front_block_coord)
            print(f"Removed front_block_coord:{front_block_coord} from to_be_visited")
        agent_host.sendCommand("move 0")  # Stop movement
        return current_direction, "edge"  # Return edge from TURNS

    return current_direction, "none"  # Return none from TURNS if no turn needed

def turn_action(agent_host, turn_type, current_direction, direction, observation):
    """
    Handles different types of turning actions for the agent.
    
    Parameters:
        agent_host (AgentHost): Malmo agent host instance
        turn_type (str): Type of turn to perform (from TURNS set)
        current_direction (str): Current direction the agent is facing
        direction (list): List of possible directions
        observation (dict): Current observation data
        
    Returns:
        str: Updated current direction after turn
    """
    if turn_type not in TURNS:
        return current_direction  # Return unchanged if invalid turn type

    if turn_type == "edge":
        # Step back one block
        agent_host.sendCommand("move -1")  # Move backward
        time.sleep(1 / 4.317)  # Wait for movement to complete
        
        # Turn 180 degrees
        agent_host.sendCommand("turn 1")  # Turn right
        time.sleep(0.5)  # Wait for turn to complete
        agent_host.sendCommand("turn 1")  # Turn right again
        time.sleep(0.5)  # Wait for turn to complete
        # Update current direction (opposite of previous)
        if current_direction == "N":
            return "S"
        elif current_direction == "S":
            return "N"
        elif current_direction == "E":
            return "W"
        elif current_direction == "W":
            return "E"
    
    return current_direction  # Return unchanged direction if no turn was made

def algorithm(agent_host: AgentHost) -> None:
    """
    Main pathfinding algorithm implementation.
    
    Parameters:
        agent_host (AgentHost): Malmo agent host instance for controlling the agent
        
    Returns:
        None
        
    This function implements the core pathfinding logic:
    - Tracks visited and safe blocks
    - Evaluates surrounding blocks for navigation
    - Controls agent movement
    - Handles environment observations and safety checks
    """
    # Initialize sets to track different types of blocks
    visited_block_coord = set()                                                                                     # Tracks coordinates that have been visited
    to_be_visited = set()                                                                                           # Tracks coordinates queued for exploration

    # Configure the observation grid
    size = 5                                                                                                        # Size of the observation grid (5x5)
    center_idx = size ** 2 // 2                                                                                     # Calculate center index of the grid
    center_x, center_z = center_idx % size, center_idx // size                                                      # Calculate center coordinates
    
    center_block_offset = [((i % size) - center_x, center_z - (i // size)) for i in range(size**2)]                 # Create list of offsets for each position in the grid relative to center
 
    # Initialize movement direction configuration
    direction = ["N", "S", "W", "E"]                                                                     # Possible movement directions
    current_direction = direction[1]                                                                                # Start with downward movement

    # Record the time when the agent starts
    start_time = time.time()

    # Main algorithm loop
    while True:
        world_state = agent_host.getWorldState()
        if world_state.is_mission_running and world_state.number_of_observations_since_last_state > 0:
            observation = json.loads(world_state.observations[-1].text)
            
            if "blocks" not in observation:                                                                          # Check for grid activation. Will not proceed gameloop if not found
                print("Failed to retrieve information regarding block surroundings!")
                break

            if "XPos" not in observation or "YPos" not in observation or "ZPos" not in observation:                  # Check for full stats activation. Will not proceed gameloop if not found
                print("It seems like FullStat is not activated!")
                break

            # Process each block position in the 5x5 observation grid around the agent
            # Parameters: observation - Dictionary containing agent's current observations
            #            i - Current grid position index being processed
            #            size - Size of the observation grid (5x5)
            # Returns: None
            # Purpose: Processes each block in the observation grid to track visited blocks and identify blocks to visit.
            #          Handles edge detection and updates exploration queues.
            for i in range(size ** 2):                                                                              # Iterate through each position in the grid
                r_edge, c_edge = divmod(i, size)                                                                    # Calculate row and column indices for current position
                is_around_edge = r_edge == 0 or r_edge == size - 1 or c_edge == 0 or c_edge == size - 1            # Check if current position is on grid edge

                y_elevation_offset = get_y_elevation_offset(observation, i, size)                                    # Get vertical offset for current block position
                if y_elevation_offset is None:                                                                       # Skip processing if no valid elevation found
                    continue

                curr_xpos = math.floor(observation["XPos"]) - center_block_offset[i][0]                             # Calculate absolute x coordinate of current block
                curr_ypos = math.floor(observation["YPos"] + y_elevation_offset - 1)                                # Calculate absolute y coordinate of current block
                curr_zpos = math.floor(observation["ZPos"]) - center_block_offset[i][1]                             # Calculate absolute z coordinate of current block
                curr_block_coord = (curr_xpos, curr_ypos, curr_zpos)                                               # Create tuple of block coordinates

                try:
                    if not is_around_edge:                                                                          # Handle non-edge blocks differently
                        if curr_block_coord not in visited_block_coord:                                             # Check if block hasn't been visited
                            visited_block_coord.add(curr_block_coord)                                               # Add block to visited set
                            if curr_block_coord in to_be_visited:                                                   # Remove from to-visit if present
                                to_be_visited.remove(curr_block_coord)
                                print(f"Removed curr_block_coord:{curr_block_coord} from to_be_visited")
                        continue

                    if curr_block_coord not in visited_block_coord and curr_block_coord not in to_be_visited:       # For edge blocks, check if unvisited and not queued
                        to_be_visited.add(curr_block_coord)                                                         # Add edge block to exploration queue
                except IndexError:                                                                                  # Handle index out of bounds errors
                    print("Unable to retrieve the block either up or down! Perhaps you had set the y range too low from XML (minimum is 4)!")
                    return
                    

            # Only print/log after 1 second has passed since agent started
            if time.time() - start_time >= 1.0:
                log_block_observations(visited_block_coord, to_be_visited, observation)

            if len(to_be_visited) <= 0:                                                                             # Check if exploration is complete
                print("No more blocks to explore to! Exiting loop...")                                             # Print completion message
                agent_host.sendCommand("move 0")                                                                    # Stop agent movement
                break

            # Move agent forward
            current_direction, turn_type = need_to_turn(
                agent_host,
                current_direction,
                direction,
                observation,
                center_idx,
                center_block_offset,
                to_be_visited,
                visited_block_coord,
                size
            )
            if turn_type != "none":
                current_direction = turn_action(agent_host, turn_type, current_direction, direction, observation)
                continue

            # Move agent forward
            agent_host.sendCommand("move 1")  # Send move command
            time.sleep(1 / 4.317)  # Wait for movement to complete

        # Exit if mission is not running
        if not world_state.is_mission_running:
            break

def main():
    """
    Main function to initialize and run the Malmo mission.
    
    Parameters:
        None
        
    Returns:
        None
        
    This function handles:
    - Mission initialization and setup
    - Error handling and retry logic
    - Mission execution and monitoring
    - Cleanup and termination
    """
    # Initialize the Malmo agent host
    agent_host = MalmoPython.AgentHost()
    try:
        agent_host.parse(sys.argv)  # Parse command line arguments
    except RuntimeError as e:
        print('ERROR:', e)
        print(agent_host.getUsage())
        exit(1)
    if agent_host.receivedArgument("help"):  # Check for help argument
        print(agent_host.getUsage())
        exit(0)

    # Create mission specification and record
    my_mission = MalmoPython.MissionSpec(run_xml_mission(), True)
    my_mission_record = MalmoPython.MissionRecordSpec()

    # Attempt to start a mission with retry logic
    max_retries = 3  # Maximum number of retry attempts
    for retry in range(max_retries):
        try:
            agent_host.startMission(my_mission, my_mission_record)  # Start the mission
            break
        except RuntimeError as e:
            if retry == max_retries - 1:  # If last retry attempt
                print("Error starting mission:", e)
                exit(1)
            else:
                time.sleep(2)  # Wait before retrying

    # Loop until mission starts
    print("Waiting for the mission to start ", end=' ')
    world_state = agent_host.getWorldState()
    while not world_state.has_mission_begun:  # Wait until mission starts
        print(".", end="")
        time.sleep(0.1)
        world_state = agent_host.getWorldState()
        for error in world_state.errors:  # Print any errors
            print("Error:", error.text)

    print()
    print("Mission running ", end=' ')

    # Run the pathfinding algorithm
    algorithm(agent_host)

    # Loop until mission ends
    while world_state.is_mission_running:  # Continue until mission ends
        print(".", end="")
        time.sleep(0.1)
        world_state = agent_host.getWorldState()
        for error in world_state.errors:  # Print any errors
            print("Error:", error.text)

    print()
    print("Mission ended")  # Mission completion message

# Entry point of the script
if __name__ == "__main__":
    main()  # Run the main function