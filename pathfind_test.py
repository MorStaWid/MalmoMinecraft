from __future__ import annotations

import json
import math
import random
import re
import sys
import time

from malmo import MalmoPython
from malmo.MalmoPython import AgentHost

INSERT_STRING_HERE = "Up and Down Stairs"

OPTIONS = {
    "Block Surround": (0, 14, -9),
    "1x1 Maze": (0, 14, 0),
    "3x3 Basic Pathfind": (-17, 14, 0),
    "Large Room Corridor": (-17, 14, 16),
    "Chest Pathway": (-25, 14, 36),
    "Up and Down Stairs": (-33, 14, 0),
    "Up and Down Slabs": (-41, 14, 36),
    "Spiral Staircase": (-33, 14, 36),
    "Door Open": (-41, 14, 0),
    "Iron Door Open": (-41, 14, 17),
    "Hidden Path": (-49, 14, 0),
    "Slabbed Hidden Path": (-56, 14, 0),
    "Five-way Crossing": (-60, 14, 21),
    "Fountain": (-59, 14, 45),
    "Portal Room Detection": (-65, 14, 0),
    "Reinforcement Learning Equipment": (-41, 14, -31)
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
                <FileWorldGenerator src="C:\\Malmo\\Minecraft\\run\\saves\\Algorithm World Test"/>
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
def get_y_elevation_offset(blocks: list, index: int, size: int) -> int | None:
    y = None
    accepted_above_block = {"air", "wooden_door", "iron_door", "brown_mushroom", "red_mushroom", "torch"}
    for i in range(len(blocks) // (size ** 2) - 2):
        if blocks[(i * 25) + index] != "air" and blocks[(i + 1) * 25 + index] in accepted_above_block and blocks[(i + 2) * 25 + index] in accepted_above_block:
            y = i - 2

    return y

def check_clearance(curr_block_coord, current_direction: int, to_be_visited: set) -> bool:
    direction_offset = {
        0: (0, -2),
        1: (2, 0),
        2: (0, 2),
        3: (-2, 0),
    }
    x_offset, z_offset = direction_offset[current_direction]
    for y_offset in range(-2, 3):
        check_pos = (curr_block_coord[0] + x_offset, curr_block_coord[1] + y_offset, curr_block_coord[2] + z_offset)
        if check_pos in to_be_visited:
            return True

    return False

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

def is_agent_in_stairs(blocks: list) -> bool:
    """If the agent appears to be in stairs on the grid, do not proceed! Also helps resolve stair issues!"""
    return blocks[87].endswith("_stairs")

def adjust_to_center(agent_host: AgentHost, blocks: list, current_direction: int) -> None:
    """Make the agent center to its hallway for better navigation!"""
    pass

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

            if is_agent_in_stairs(observation["blocks"]):
                continue

            # To prevent blocks stacking the same coords, this check will prevent duplicate tuple values.
            standing_block = (math.floor(observation["XPos"]), math.floor(observation["YPos"]) - 1,
                                    math.floor(observation["ZPos"]))
            if (not is_in_backtrack and standing_block == block_visit[-1]) or (is_in_backtrack and standing_block != block_visit[-1]):
                continue

            auto_correct_yaw(agent_host, observation["Yaw"], current_direction)
            if is_in_backtrack:
                curr_block = block_visit.pop()
                is_forward_cleared = check_clearance(curr_block, current_direction % 4, to_be_visited)
                if is_forward_cleared:
                    is_in_backtrack = False
                    continue
                is_left_cleared = check_clearance(curr_block, (current_direction - 1) % 4, to_be_visited)
                is_right_cleared = check_clearance(curr_block, (current_direction + 1) % 4, to_be_visited)
                curr_turn = -1 if is_left_cleared else 1 if is_right_cleared else 0

                if curr_turn != 0:
                    # Adjust agent to the center block as it doesn't stop immediately.
                    agent_host.sendCommand("move 0")
                    time.sleep(0.2)
                    agent_host.sendCommand(
                        "tp {} {} {}".format(curr_block[0] + 0.5, curr_block[1] + 1, curr_block[2] + 0.5))
                    current_direction = (current_direction + curr_turn) % 4
                    agent_host.sendCommand("turn {}".format(curr_turn))
                    time.sleep(1)
                    agent_host.sendCommand("turn 0")
                    # auto_correct_yaw(agent_host, current_direction)
                    is_in_backtrack = False
                    continue

                if len(block_visit) == 1:
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
                block_visit.append(standing_block)
                # agent_host.sendCommand(f"chat /setblock {block_visit[-1][0]} {block_visit[-1][1]} {block_visit[-1][2]} minecraft:gold_block")
                for i in range(size ** 2):
                    r_edge, c_edge = divmod(i, size)
                    is_around_edge = r_edge == 0 or r_edge == size - 1 or c_edge == 0 or c_edge == size - 1       # For stack

                    y_elevation_offset = get_y_elevation_offset(observation["blocks"], i, size)
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

                # assert len(to_be_visited) == 3
                if len(to_be_visited) <= 0:
                    print("No more blocks to explore to! Exiting loop...")
                    agent_host.sendCommand("move 0")
                    break

                is_forward_cleared = check_clearance(block_visit[-1], current_direction % 4, to_be_visited)
                if not is_forward_cleared:
                    is_left_cleared = check_clearance(block_visit[-1], (current_direction - 1) % 4, to_be_visited)
                    is_right_cleared = check_clearance(block_visit[-1], (current_direction + 1) % 4, to_be_visited)
                    curr_turn = -1 if is_left_cleared else 1 if is_right_cleared else 0

                    # Adjust agent to the center block as it doesn't stop immediately.
                    agent_host.sendCommand("move 0")
                    time.sleep(0.2)
                    agent_host.sendCommand("tp {} {} {}".format(block_visit[-1][0] + 0.5, block_visit[-1][1] + 1, block_visit[-1][2] + 0.5))

                    if curr_turn != 0:
                        current_direction = (current_direction + curr_turn) % 4
                        agent_host.sendCommand("turn {}".format(curr_turn))
                        time.sleep(1)
                    else:
                        is_in_backtrack = True
                        current_direction = (current_direction + 2) % 4
                        agent_host.sendCommand("turn -1")
                        time.sleep(2)
                    agent_host.sendCommand("turn 0")
                    # auto_correct_yaw(agent_host, current_direction)

            print("\nVisited Blocks:", list(visited_block_coord))
            print("To Be Visited:", list(to_be_visited))
            print("Current Direction: ", current_direction)
            print("------------------------------------------------------------------")
            agent_host.sendCommand("move 1")



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