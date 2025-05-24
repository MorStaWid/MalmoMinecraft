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
                <FileWorldGenerator src="C:\\Malmo\\Minecraft\\run\\saves\\Algorithm World Test"/>
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

# Start from the bottom of the block x z and compute based on presence. If the initial block is "occupied" and the one
# above is air or other acceptable blocks, we return the y offset. The purpose is to check for downward and upward blocks around.
def get_y_elevation_offset(observation: dict, index: int, size: int) -> int | None:
    y = None
    accepted_above_block = {"air", "door", "iron_door"}
    for i in range(len(observation["blocks"]) // (size ** 2) - 1):
        if observation["blocks"][(i * 25) + index] != "air" and observation["blocks"][(i + 1) * 25 + index] in accepted_above_block:
            y = i - 2

    return y

def algorithm(agent_host: AgentHost) -> None:
    visited_block_coord = set()
    to_be_visited = set()

    size = 5
    center_idx = size ** 2 // 2
    center_x, center_z = center_idx % size, center_idx // size
    center_block_offset = [((i % size) - center_x, center_z - (i // size)) for i in range(size**2)]

    direction = ["up", "down", "left", "right"]
    current_direction = direction[1]

    while True:
        world_state = agent_host.getWorldState()

        if world_state.is_mission_running and world_state.number_of_observations_since_last_state > 0:
            observation = json.loads(world_state.observations[-1].text)
            print(observation)
            # Check for grid activation. Will not proceed gameloop if not found.
            if "blocks" not in observation:
                print("Failed to retrieve information regarding block surroundings!")
                break

            # Check for full stats activation. Will not proceed gameloop if not found.
            if "XPos" not in observation or "YPos" not in observation or "ZPos" not in observation:
                print("It seems like FullStat is not activated!")
                break

            print("{} | {} | {}".format(observation["XPos"], observation["YPos"], observation["ZPos"]))
            for i in range(size ** 2):
                r_edge, c_edge = divmod(i, size)
                is_around_edge = r_edge == 0 or r_edge == size - 1 or c_edge == 0 or c_edge == size - 1       # For stack

                y_elevation_offset = get_y_elevation_offset(observation, i, size)
                if y_elevation_offset is None:
                    continue

                curr_xpos = math.floor(observation["XPos"]) - center_block_offset[i][0]
                curr_ypos = math.floor(observation["YPos"] + y_elevation_offset - 1)
                curr_zpos = math.floor(observation["ZPos"]) - center_block_offset[i][1]
                curr_block_coord = (curr_xpos, curr_ypos, curr_zpos)
                try:
                    if not is_around_edge:
                        if curr_block_coord not in visited_block_coord:
                            visited_block_coord.add(curr_block_coord)
                            if curr_block_coord in to_be_visited:
                                to_be_visited.remove(curr_block_coord)
                        continue

                    if curr_block_coord not in visited_block_coord and curr_block_coord not in to_be_visited:
                        to_be_visited.add(curr_block_coord)
                except IndexError:
                    print("Unable to retrieve the block either up or down! Perhaps you had set the y range too low from XML (minimum is 4)!")
                    return

            # print(f"Visit Block Coord: {list(visited_block_coord)}")
            print(f"Visit Stack: {to_be_visited}")
            # assert len(to_be_visited) == 3
            if len(to_be_visited) <= 0:
                print("No more blocks to explore to! Exiting loop...")
                agent_host.sendCommand("move 0")
                break

            agent_host.sendCommand("move 1")
            time.sleep(1 / 4.317)

        if not world_state.is_mission_running:
            break

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