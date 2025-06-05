from __future__ import annotations

import json
import math
import random
import re
import sys
import time

import MalmoPython
from MalmoPython import AgentHost

INSERT_STRING_HERE = "3x3 Basic Pathfind"

OPTIONS = {
    "Block Surround": (0, 14, -9),
    "1x1 Maze": (0, 14, 0),
    "3x3 Basic Pathfind": (-17, 14, 0),
    "Large Room Corridor": (-17, 14, 16),
    "Up and Down Stairs": (-33, 14, 0),
    "Up and Down Slabs": (-41, 14, 36),
    "Spiral Staircase": (-33, 14, 36),
    "Door Open": (-41, 14, 0),
    "Iron Door Open": (-41, 14, 17),
    "Hidden Path": (-49, 14, 0),
    "Slabbed Hidden Path": (-56, 14, 0),
    "Five-way Crossing": (-60, 14, 21),
    "Fountain": (-59, 14, 45),
    "Portal Room Detection": (-65, 14, 0)
}


def run_xml_mission():
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
                <FileWorldGenerator src="C:\\Users\\yovan\\OneDrive\\Desktop\\Malmo\\Minecraft\\run\\saves\\Algorithm World Test"/>
                <ServerQuitFromTimeUp timeLimitMs="40000"/>
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
                        <max x="2" y="3" z="2"/>
                    </Grid>
                </ObservationFromGrid>
                <AbsoluteMovementCommands/>
                <ContinuousMovementCommands turnSpeedDegs="90"/>
                <ChatCommands/>
                <MissionQuitCommands/>
                <AgentQuitFromTouchingBlockType>
                    <Block type="diamond_block"/>
                </AgentQuitFromTouchingBlockType>
            </AgentHandlers>
        </AgentSection>
    </Mission>'''

# Start from the bottom of the block x z and compute based on presence. If the initial block is "occupied" and the one
# above is air or other acceptable blocks, we return the y offset. The purpose is to check for downward and upward blocks around.
def get_y_elevation_offset(observation: dict, index: int, size: int) -> int | None:
    y = None
    accepted_above_block = {"air", "door", "iron_door", "brown_mushroom", "red_mushroom"}
    for i in range(len(observation["blocks"]) // (size ** 2) - 2):
        if observation["blocks"][(i * 25) + index] != "air" and observation["blocks"][(i + 1) * 25 + index] in accepted_above_block and observation["blocks"][(i + 2) * 25 + index] in accepted_above_block:
            y = i - 2

    return y

def is_path_blocked(observation: dict, direction: int) -> bool:
    """Check if the path in the given direction is blocked by a wall"""
    direction_to_index = {
        0: 7,   # North (front-center in 5x5 grid)
        1: 13,  # East (right-center)
        2: 17,  # South (back-center)
        3: 11,  # West (left-center)
    }
    
    if direction not in direction_to_index:
        return True
    
    # Check the block in front at ground level and above
    front_index = direction_to_index[direction]
    size = 5
    
    # Check multiple Y levels for obstacles
    for y_level in range(3, 6):  # Check current level and above (where agent walks)
        block_index = (y_level * size * size) + front_index
        if block_index < len(observation["blocks"]):
            block_type = observation["blocks"][block_index]
            # If it's not air or passable blocks, it's blocked
            if block_type not in {"air", "door", "iron_door", "brown_mushroom", "red_mushroom"}:
                return True
    
    return False

def find_reachable_target(curr_block_coord, current_direction: int, to_be_visited: set) -> tuple | None:
    """Find the closest reachable target in the given direction"""
    direction_offset = {
        0: (0, -1),  # North (negative Z)
        1: (1, 0),   # East (positive X)
        2: (0, 1),   # South (positive Z)
        3: (-1, 0),  # West (negative X)
    }
    
    x_offset, z_offset = direction_offset[current_direction]
    
    # Check multiple distances in the current direction
    for distance in range(1, 10):  # Check up to 10 blocks away
        for y_offset in range(-2, 3):  # Check different Y levels
            check_pos = (
                curr_block_coord[0] + x_offset * distance, 
                curr_block_coord[1] + y_offset, 
                curr_block_coord[2] + z_offset * distance
            )
            if check_pos in to_be_visited:
                return check_pos
    
    return None

def check_clearance(curr_block_coord, current_direction: int, to_be_visited: set) -> bool:
    """Check if there are any reachable targets in the given direction"""
    return find_reachable_target(curr_block_coord, current_direction, to_be_visited) is not None

def find_best_direction(curr_block_coord, current_direction: int, to_be_visited: set, observation: dict = None) -> int:
    """Find the best direction to turn to reach a target, avoiding walls"""
    # Check all four directions and find the one with the closest target
    best_direction = current_direction
    min_distance = float('inf')
    
    for direction in range(4):
        # Skip directions that are blocked by walls
        if observation and is_path_blocked(observation, direction):
            continue
            
        target = find_reachable_target(curr_block_coord, direction, to_be_visited)
        if target is not None:
            # Calculate Manhattan distance
            distance = abs(target[0] - curr_block_coord[0]) + abs(target[2] - curr_block_coord[2])
            if distance < min_distance:
                min_distance = distance
                best_direction = direction
    
    return best_direction

def auto_correct_yaw(agent_host: AgentHost, yaw: float, current_direction: int) -> None:
    """Attempt the agent to align to its perfect yaw as there's a chance it can over-rotate or under-rotate!"""
    yaw_def = {
        0: 180,
        1: 270,
        2: 0,
        3: 90,
    }
    margin_threshold = 0.5

    # THIS SHIT DOES NOT RECOGNIZE YAW AND PITCH! AM I FUCKING DREAMING?!!!!!!!!!!
    # agent_host.sendCommand("chat /tp ~ ~ ~ {} ~".format(yaw_def[current_direction]))

    curr_yaw = yaw % 360
    counterclockwise_err_margin = (curr_yaw - yaw_def[current_direction]) % 360
    clockwise_err_margin = (yaw_def[current_direction] - curr_yaw) % 360
    if counterclockwise_err_margin <= margin_threshold or clockwise_err_margin <= margin_threshold:
        return
    agent_host.sendCommand("turn {}".format(1 if clockwise_err_margin <= counterclockwise_err_margin else -1))
    turn_time = (clockwise_err_margin if clockwise_err_margin <= counterclockwise_err_margin else counterclockwise_err_margin) / 90
    time.sleep(turn_time)
    agent_host.sendCommand("turn 0")

def go_down_spiral_staircase(agent_host: AgentHost, structure_direction: str) -> None:
    # TODO: Uses a fixed instructions to tell an agent to go down spiral. Does not store coords during this operation!
    pass

def go_up_spiral_staircase(agent_host: AgentHost, structure_direction: str) -> None:
    # Same concept as above.
    pass

def is_agent_in_block(observation: dict) -> bool:
    """If the agent appears to be in block on the grid, do not proceed! Also helps resolve stair/slab issues!"""
    return observation["blocks"][87] != "air"

def algorithm(agent_host: AgentHost) -> None:
    visited_block_coord = set()
    to_be_visited = set()

    block_visit = [None]
    is_in_backtrack = False

    size = 5
    center_idx = size ** 2 // 2
    center_x, center_z = center_idx % size, center_idx // size
    center_block_offset = [((i % size) - center_x, center_z - (i // size)) for i in range(size**2)]

    direction = {"N": 0, "E": 1, "S": 2, "W": 3}
    current_direction = direction["S"]

    turn_map = {
        2: {1: 1, -1: -1},  # S
        0: {-1: 1, 1: -1},  # N
        3: {1: 1, -1: -1},  # W
        1: {-1: 1, 1: -1},  # E
    }

    while True:
        world_state = agent_host.getWorldState()
        if not world_state.is_mission_running:
            break

        if world_state.number_of_observations_since_last_state > 0:
            observation = json.loads(world_state.observations[-1].text)
            # print(observation)
            # Check for grid activation. Will not proceed gameloop if not found.
            if "blocks" not in observation:
                print("Failed to retrieve information regarding block surroundings!")
                break

            # Check for full stats activation. Will not proceed gameloop if not found.
            if "XPos" not in observation or "YPos" not in observation or "ZPos" not in observation:
                print("It seems like FullStat is not activated!")
                break

            if is_agent_in_block(observation):
                continue

            # To prevent blocks stacking the same coords, this check will prevent duplicate tuple values.
            current_block = (math.floor(observation["XPos"]), math.floor(observation["YPos"]) - 1, math.floor(observation["ZPos"]))
            if current_block == block_visit[-1]:
                continue

            auto_correct_yaw(agent_host, observation["Yaw"], current_direction)
            
            # IMMEDIATE WALL DETECTION - Check for walls before any other logic
            if is_path_blocked(observation, current_direction):
                print("DEBUG: Wall detected ahead! Finding alternative direction...")
                agent_host.sendCommand("move 0")  # Stop immediately
                time.sleep(0.1)
                
                # Find the best unblocked direction
                best_direction = find_best_direction(current_block, current_direction, to_be_visited, observation)
                
                if best_direction != current_direction:
                    # Calculate turn needed
                    turn_needed = (best_direction - current_direction) % 4
                    if turn_needed > 2:
                        turn_needed -= 4  # Convert to -1 for left turn
                    elif turn_needed == 2:
                        turn_needed = -1  # Prefer left turn for 180 degree turn
                    
                    # Center the agent and turn
                    agent_host.sendCommand("tp {} {} {}".format(current_block[0] + 0.5, current_block[1] + 1, current_block[2] + 0.5))
                    current_direction = best_direction
                    agent_host.sendCommand("turn {}".format(turn_needed))
                    time.sleep(abs(turn_needed))
                    agent_host.sendCommand("turn 0")
                    print(f"DEBUG: Turned to direction {current_direction} to avoid wall")
                else:
                    # No clear direction available, start backtracking
                    print("DEBUG: No clear path available, starting backtrack")
                    is_in_backtrack = True
                    current_direction = (current_direction + 2) % 4
                    agent_host.sendCommand("turn -1")
                    time.sleep(2)
                    agent_host.sendCommand("turn 0")
                
                # Continue to next iteration after handling wall
                print("\nVisited Blocks:", list(visited_block_coord))
                print("To Be Visited:", list(to_be_visited))
                print("Current Direction: ", current_direction)
                print("------------------------------------------------------------------")
                agent_host.sendCommand("move 1")
                time.sleep(0.1)
                continue
            
            if is_in_backtrack:
                curr_block = block_visit.pop()
                
                # Check if we can find a path from current position
                best_direction = find_best_direction(curr_block, current_direction, to_be_visited, observation)
                if best_direction != current_direction and not is_path_blocked(observation, best_direction):
                    # Calculate turn needed
                    turn_needed = (best_direction - current_direction) % 4
                    if turn_needed > 2:
                        turn_needed -= 4  # Convert to -1 for left turn
                    elif turn_needed == 2:
                        turn_needed = -1  # Prefer left turn for 180 degree turn
                    
                    if turn_needed != 0:
                        # Adjust agent to the center block
                        agent_host.sendCommand("move 0")
                        time.sleep(0.2)
                        agent_host.sendCommand(
                            "tp {} {} {}".format(curr_block[0] + 0.5, curr_block[1] + 1, curr_block[2] + 0.5))
                        current_direction = best_direction
                        agent_host.sendCommand("turn {}".format(turn_needed))
                        time.sleep(abs(turn_needed))
                        agent_host.sendCommand("turn 0")
                        is_in_backtrack = False
                        continue

                if len(block_visit) == 0:
                    print("DEBUG: This agent is now all the way back to the beginning!")
                    is_in_backtrack = False
                    break

                prev_block = block_visit[-1]
                x_diff = curr_block[0] - prev_block[0]
                z_diff = curr_block[2] - prev_block[2]
                if current_direction in [0, 2]:
                    diff = x_diff
                elif current_direction in [1, 3]:
                    diff = z_diff
                else:
                    print("ERROR: Unknown direction ID")
                    diff = 0

                if diff in turn_map[current_direction]:
                    turn = turn_map[current_direction][diff]
                    agent_host.sendCommand("move 0")
                    time.sleep(0.2)
                    agent_host.sendCommand("tp {} {} {}".format(curr_block[0] + 0.5, curr_block[1] + 1,
                                                                curr_block[2] + 0.5))
                    agent_host.sendCommand("turn {}".format(turn))
                    time.sleep(1)
                    agent_host.sendCommand("turn 0")
                    current_direction = (current_direction + turn) % 4
            else:
                block_visit.append(current_block)
                # agent_host.sendCommand(f"chat /setblock {block_visit[-1][0]} {block_visit[-1][1]} {block_visit[-1][2]} minecraft:gold_block")
                for i in range(size ** 2):
                    r_edge, c_edge = divmod(i, size)
                    is_around_edge = r_edge == 0 or r_edge == size - 1 or c_edge == 0 or c_edge == size - 1       # For stack

                    y_elevation_offset = get_y_elevation_offset(observation, i, size)
                    if y_elevation_offset is None:
                        continue

                    curr_xpos = math.floor(observation["XPos"]) + center_block_offset[i][0]
                    curr_ypos = math.floor(observation["YPos"] + y_elevation_offset - 1)
                    curr_zpos = math.floor(observation["ZPos"]) - center_block_offset[i][1]
                    curr_block_coord = (curr_xpos, curr_ypos, curr_zpos)
                    try:
                        if not is_around_edge:
                            if curr_block_coord not in visited_block_coord:
                                visited_block_coord.add(curr_block_coord)
                                # agent_host.sendCommand(
                                #     f"chat /setblock {curr_block_coord[0]} {curr_block_coord[1]} {curr_block_coord[2]} minecraft:emerald_block")
                                if curr_block_coord in to_be_visited:
                                    to_be_visited.remove(curr_block_coord)
                            continue

                        if curr_block_coord not in visited_block_coord and curr_block_coord not in to_be_visited:
                            to_be_visited.add(curr_block_coord)
                            # agent_host.sendCommand(
                            #     f"chat /setblock {curr_block_coord[0]} {curr_block_coord[1]} {curr_block_coord[2]} minecraft:glowstone")
                    except IndexError:
                        print("Unable to retrieve the block either up or down! Perhaps you had set the y range too low from XML (minimum is 6)!")
                        return

                if len(to_be_visited) <= 0:
                    print("No more blocks to explore to! Exiting loop...")
                    agent_host.sendCommand("move 0")
                    break

                # Find the best direction to go
                best_direction = find_best_direction(block_visit[-1], current_direction, to_be_visited, observation)
                
                if best_direction != current_direction and not is_path_blocked(observation, best_direction):
                    # Calculate turn needed
                    turn_needed = (best_direction - current_direction) % 4
                    if turn_needed > 2:
                        turn_needed -= 4  # Convert to -1 for left turn
                    elif turn_needed == 2:
                        turn_needed = -1  # Prefer left turn for 180 degree turn
                    
                    # Adjust agent to the center block
                    agent_host.sendCommand("move 0")
                    time.sleep(0.2)
                    agent_host.sendCommand("tp {} {} {}".format(block_visit[-1][0] + 0.5, block_visit[-1][1] + 1, block_visit[-1][2] + 0.5))

                    if turn_needed != 0:
                        current_direction = best_direction
                        agent_host.sendCommand("turn {}".format(turn_needed))
                        time.sleep(abs(turn_needed))
                    else:
                        # No reachable targets, start backtracking
                        is_in_backtrack = True
                        current_direction = (current_direction + 2) % 4
                        agent_host.sendCommand("turn -1")
                        time.sleep(2)
                    agent_host.sendCommand("turn 0")
                else:
                    # Current direction is already optimal, check if we can move forward
                    if not check_clearance(block_visit[-1], current_direction, to_be_visited):
                        # No clear path forward, start backtracking
                        agent_host.sendCommand("move 0")
                        time.sleep(0.2)
                        agent_host.sendCommand("tp {} {} {}".format(block_visit[-1][0] + 0.5, block_visit[-1][1] + 1, block_visit[-1][2] + 0.5))
                        is_in_backtrack = True
                        current_direction = (current_direction + 2) % 4
                        agent_host.sendCommand("turn -1")
                        time.sleep(2)
                        agent_host.sendCommand("turn 0")

            print("\nVisited Blocks:", list(visited_block_coord))
            print("To Be Visited:", list(to_be_visited))
            print("Current Direction: ", current_direction)
            print("------------------------------------------------------------------")
            agent_host.sendCommand("move 1")

            time.sleep(0.1)


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
    algorithm(agent_host)

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
