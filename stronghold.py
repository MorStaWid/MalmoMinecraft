from __future__ import annotations

import json
import math
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
                <FileWorldGenerator src="C:\\Malmo\\Minecraft\\run\\saves\\FlatWorld Stronghold Malmo"/>
                <ServerQuitFromTimeUp timeLimitMs="10000"/>
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
                        <min x="-2" y="-3" z="-2"/>
                        <max x="2" y="3" z="2"/>
                    </Grid>
                </ObservationFromGrid>
                <AbsoluteMovementCommands/>
                <ContinuousMovementCommands turnSpeedDegs="90"/>
                <ChatCommands/>
                <MissionQuitCommands/>
            </AgentHandlers>
        </AgentSection>
    </Mission>'''

class Golly(object):
    def __init__(self, agent_host: AgentHost):
        self.agent_host = agent_host
        self.visited_block_coord = set()
        self.to_be_visited = set()

        self.block_visit = [(0, 0, 0)]
        self.is_in_backtrack = False

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

    # Start from the bottom of the block x z and compute based on presence. If the initial block is "occupied" and the one
    # above is air or other acceptable blocks, we return the y offset. The purpose is to check for downward and upward blocks around.
    def get_y_elevation_offset(self, blocks: list, index: int, size: int) -> int | None:
        y = None
        accepted_above_block = {"air", "wooden_door", "iron_door", "brown_mushroom", "red_mushroom", "torch"}
        for i in range(len(blocks) // (size ** 2) - 2):
            if blocks[(i * 25) + index] != "air" and blocks[(i + 1) * 25 + index] in accepted_above_block and blocks[(i + 2) * 25 + index] in accepted_above_block:
                y = i - 2

        return y

    def check_clearance(self, curr_block_coord, current_direction: int) -> bool:
        direction_offset = {
            0: (0, -2),
            1: (2, 0),
            2: (0, 2),
            3: (-2, 0),
        }
        x_offset, z_offset = direction_offset[current_direction]
        for y_offset in range(-2, 3):
            check_pos = (curr_block_coord[0] + x_offset, curr_block_coord[1] + y_offset, curr_block_coord[2] + z_offset)
            if check_pos in self.to_be_visited:
                return True

        return False

    def auto_correct_yaw(self, yaw: float, current_direction: int) -> None:
        """Attempt the agent to align to its perfect yaw as there's a chance it can over-rotate or under-rotate!"""
        yaw_def = {
            0: 180,
            1: 270,
            2: 0,
            3: 90,
        }
        margin_threshold = 0.5

        # THIS SHIT DOES NOT RECOGNIZE YAW AND PITCH! AM I FUCKING DREAMING?!!!!!!!!!!
        # self.agent_host.sendCommand("chat /tp ~ ~ ~ {} ~".format(yaw_def[current_direction]))

        curr_yaw = yaw % 360
        counterclockwise_err_margin = (curr_yaw - yaw_def[current_direction]) % 360
        clockwise_err_margin = (yaw_def[current_direction] - curr_yaw) % 360
        if counterclockwise_err_margin <= margin_threshold or clockwise_err_margin <= margin_threshold:
            return
        self.agent_host.sendCommand("turn {}".format(1 if clockwise_err_margin <= counterclockwise_err_margin else -1))
        turn_time = (clockwise_err_margin if clockwise_err_margin <= counterclockwise_err_margin else counterclockwise_err_margin) / 90
        time.sleep(turn_time)
        self.agent_host.sendCommand("turn 0")

    def go_down_spiral_staircase(self, structure_direction: str) -> None:
        # TODO: Uses a fixed instructions to tell an agent to go down spiral. Does not store coords during this operation!
        pass

    def go_up_spiral_staircase(self, structure_direction: str) -> None:
        # Same concept as above.
        pass

    def is_agent_in_stairs(self, blocks: list) -> bool:
        """If the agent appears to be in stairs on the grid, do not proceed! Also helps resolve stair issues!"""
        return blocks[87].endswith("_stairs")

    def adjust_to_center(self, blocks: list, current_direction: int) -> None:
        """Make the agent center to its hallway for better navigation!"""
        pass

    def navigate_portal_room(self) -> None:
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
            world_state = self.agent_host.getWorldState()
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

                if self.is_agent_in_stairs(observation["blocks"]):
                    continue

                # To prevent blocks stacking the same coords, this check will prevent duplicate tuple values.
                if (math.floor(observation["XPos"]), math.floor(observation["YPos"]) - 1,
                    math.floor(observation["ZPos"])) == self.block_visit[-1]:
                    continue

                self.auto_correct_yaw(observation["Yaw"], current_direction)
                if self.is_in_backtrack:
                    curr_block = self.block_visit.pop()
                    is_forward_cleared = self.check_clearance(curr_block, current_direction % 4)
                    if is_forward_cleared:
                        self.is_in_backtrack = False
                        continue
                    is_left_cleared = self.check_clearance(curr_block, (current_direction - 1) % 4)
                    is_right_cleared = self.check_clearance(curr_block, (current_direction + 1) % 4)
                    curr_turn = -1 if is_left_cleared else 1 if is_right_cleared else 0

                    if curr_turn != 0:
                        # Adjust agent to the center block as it doesn't stop immediately.
                        self.agent_host.sendCommand("move 0")
                        time.sleep(0.2)
                        self.agent_host.sendCommand(
                            "tp {} {} {}".format(curr_block[0] + 0.5, curr_block[1] + 1, curr_block[2] + 0.5))
                        current_direction = (current_direction + curr_turn) % 4
                        self.agent_host.sendCommand("turn {}".format(curr_turn))
                        time.sleep(1)
                        self.agent_host.sendCommand("turn 0")
                        # auto_correct_yaw(self.agent_host, current_direction)
                        self.is_in_backtrack = False
                        continue

                    if len(self.block_visit) == 0:
                        print("DEBUG: This agent is now all the way back to the beginning!")
                        self.is_in_backtrack = False
                        break

                    prev_block = self.block_visit[-1]
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
                        self.agent_host.sendCommand("move 0")
                        time.sleep(0.2)
                        self.agent_host.sendCommand("tp {} {} {}".format(curr_block[0] + 0.5, curr_block[1] + 1,
                                                                    curr_block[2] + 0.5))
                        self.agent_host.sendCommand("turn {}".format(turn))
                        time.sleep(1)
                        self.agent_host.sendCommand("turn 0")
                        current_direction = (current_direction + turn) % 4
                else:
                    self.block_visit.append((math.floor(observation["XPos"]), math.floor(observation["YPos"]) - 1,
                                        math.floor(observation["ZPos"])))
                    # self.agent_host.sendCommand(f"chat /setblock {self.block_visit[-1][0]} {self.block_visit[-1][1]} {self.block_visit[-1][2]} minecraft:gold_block")
                    for i in range(size ** 2):
                        r_edge, c_edge = divmod(i, size)
                        is_around_edge = r_edge == 0 or r_edge == size - 1 or c_edge == 0 or c_edge == size - 1       # For stack

                        y_elevation_offset = self.get_y_elevation_offset(observation["blocks"], i, size)
                        if y_elevation_offset is None:
                            continue

                        curr_xpos = math.floor(observation["XPos"]) + center_block_offset[i][0]
                        curr_ypos = math.floor(observation["YPos"] + y_elevation_offset - 1)
                        curr_zpos = math.floor(observation["ZPos"]) - center_block_offset[i][1]
                        curr_block_coord = (curr_xpos, curr_ypos, curr_zpos)
                        try:
                            if not is_around_edge:
                                if curr_block_coord not in self.visited_block_coord:
                                    self.visited_block_coord.add(curr_block_coord)
                                    # self.agent_host.sendCommand(
                                    #     f"chat /setblock {curr_block_coord[0]} {curr_block_coord[1]} {curr_block_coord[2]} minecraft:emerald_block")
                                    if curr_block_coord in self.to_be_visited:
                                        self.to_be_visited.remove(curr_block_coord)
                                continue

                            if curr_block_coord not in self.visited_block_coord and curr_block_coord not in self.to_be_visited:
                                self.to_be_visited.add(curr_block_coord)
                                # self.agent_host.sendCommand(
                                #     f"chat /setblock {curr_block_coord[0]} {curr_block_coord[1]} {curr_block_coord[2]} minecraft:glowstone")
                        except IndexError:
                            print("Unable to retrieve the block either up or down! Perhaps you had set the y range too low from XML (minimum is 6)!")
                            return

                    # assert len(self.to_be_visited) == 3
                    if len(self.to_be_visited) <= 0:
                        print("No more blocks to explore to! Exiting loop...")
                        self.agent_host.sendCommand("move 0")
                        break

                    is_forward_cleared = self.check_clearance(self.block_visit[-1], current_direction % 4)
                    if not is_forward_cleared:
                        is_left_cleared = self.check_clearance(self.block_visit[-1], (current_direction - 1) % 4)
                        is_right_cleared = self.check_clearance(self.block_visit[-1], (current_direction + 1) % 4)
                        curr_turn = -1 if is_left_cleared else 1 if is_right_cleared else 0

                        # Adjust agent to the center block as it doesn't stop immediately.
                        self.agent_host.sendCommand("move 0")
                        time.sleep(0.2)
                        self.agent_host.sendCommand("tp {} {} {}".format(self.block_visit[-1][0] + 0.5, self.block_visit[-1][1] + 1, self.block_visit[-1][2] + 0.5))

                        if curr_turn != 0:
                            current_direction = (current_direction + curr_turn) % 4
                            self.agent_host.sendCommand("turn {}".format(curr_turn))
                            time.sleep(1)
                        else:
                            self.is_in_backtrack = True
                            current_direction = (current_direction + 2) % 4
                            self.agent_host.sendCommand("turn -1")
                            time.sleep(2)
                        self.agent_host.sendCommand("turn 0")
                        # auto_correct_yaw(self.agent_host, current_direction)

                print("\nVisited Blocks:", list(self.visited_block_coord))
                print("To Be Visited:", list(self.to_be_visited))
                print("Current Direction: ", current_direction)
                print("------------------------------------------------------------------")
                self.agent_host.sendCommand("move 1")


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
    time.sleep(2)
    golly.navigate_portal_room()

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