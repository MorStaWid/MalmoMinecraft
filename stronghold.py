from __future__ import annotations

import json
import math
import os
import pickle
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

# === Reinforcement Learning Setup ===
ACTIONS = ["diamond_sword", "diamond_axe", "bow", "stone_sword", "stone_axe", "eat_food"]
HOTBAR_SLOTS = {
    "diamond_sword": 0,
    "diamond_axe": 1,
    "bow": 2,
    "stone_sword": 3,
    "stone_axe": 4,
    "eat_food": 7
}

Q_SAVE_PATH = "q_learning_combat.pkl"
q_table = {}
last_state = None
last_action = None

if os.path.exists(Q_SAVE_PATH):
    with open(Q_SAVE_PATH, "rb") as f:
        q_table = pickle.load(f)

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
                <AllowSpawning>true</AllowSpawning>
                <AllowedMobs>Zombie</AllowedMobs>
                <Weather>clear</Weather>
            </ServerInitialConditions> 
            <ServerHandlers>
                <FileWorldGenerator src="C:\\Malmo-0.37.0-Windows-64bit_withBoost_Python3.7\\Minecraft\\run\\saves\\FlatWorld Stronghold Malmo"/>
                <ServerQuitFromTimeUp timeLimitMs="120000"/>
                <ServerQuitWhenAnyAgentFinishes/>
            </ServerHandlers>
        </ServerSection>
        
        <AgentSection mode="Survival">
            <Name>Golly</Name>
            <AgentStart>
                <Placement x="''' + str(14020 + 0.5) + '''" y="64" z="''' + str(2884.5) + '''"/>
                <Inventory>
                    <InventoryItem slot="0" type="diamond_sword"/>
                    <InventoryItem slot="1" type="diamond_axe"/>
                    <InventoryItem slot="2" type="bow"/>
                    <InventoryItem slot="3" type="stone_sword"/>
                    <InventoryItem slot="4" type="stone_axe"/>
                    <InventoryItem slot="5" type="dirt" quantity="1"/>
                    <InventoryItem slot="6" type="arrow" quantity="30"/>
                    <InventoryItem slot="7" type="cooked_beef" quantity="10"/>
                </Inventory>
            </AgentStart>
            <AgentHandlers>
                <ObservationFromFullStats/>
                <ObservationFromChat/>
                <ObservationFromRay/>
                <ObservationFromHotBar/>
                <RewardForDamagingEntity>
                    <Mob type="Zombie" reward="10"/>
                </RewardForDamagingEntity>
                <ObservationFromNearbyEntities>
                    <Range name="entities" xrange="4" yrange="2" zrange="4" />
                </ObservationFromNearbyEntities>
                <ObservationFromGrid>
                    <Grid name="blocks">
                        <min x="-2" y="-3" z="-2"/>
                        <max x="2" y="3" z="2"/>
                    </Grid>
                </ObservationFromGrid>
                <AbsoluteMovementCommands/>
                <ContinuousMovementCommands turnSpeedDegs="90"/>
                <InventoryCommands/>
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
        self.current_state = "PATHFINDING"

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
        # Give night vision effect to see in the dark
        self.agent_host.sendCommand("chat /effect @p night_vision 99999 255")
        time.sleep(0.5)
        self.agent_host.sendCommand("chat /gamemode 0")
        
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
        accepted_above_block = {"air", "wooden_door", "iron_door", "brown_mushroom", "red_mushroom", "torch", "stone_button"}
        for i in range(len(blocks) // (size ** 2) - 2):
            if blocks[(i * 25) + (index % 25)] != "air" and blocks[(i + 1) * 25 + (index % 25)] in accepted_above_block and blocks[(i + 2) * 25 + (index % 25)] in accepted_above_block:
                y = i - 2

        return y

    def check_clearance(self, curr_block_coord, current_direction: int, blocks: list, observation: dict) -> bool:
        """
        Check if the path in the given direction is clear (not blocked by walls) and has blocks to visit.

        Parameters:
            curr_block_coord: Current block coordinates (x, y, z)
            current_direction: Direction to check (0=North, 1=East, 2=South, 3=West)
             of coordinates that need to be visited
            blocks: List of blocks from observation grid
            observation: Current observation data

        Returns:
            bool: True if path is clear and has blocks to visit, False otherwise
        """
        direction_offset = {
            0: (0, -2),  # North
            1: (2, 0),   # East
            2: (0, 2),   # South
            3: (-2, 0),  # West
        }

        x_offset, z_offset = direction_offset[current_direction]

        # First check if there are blocks to visit in this direction
        has_blocks_to_visit = False
        for y_offset in range(-2, 3):
            check_pos = (curr_block_coord[0] + x_offset, curr_block_coord[1] + y_offset, curr_block_coord[2] + z_offset)
            if check_pos in self.to_be_visited:
                has_blocks_to_visit = True
                break

        if not has_blocks_to_visit:
            return False

        # Now check if the path is physically clear (not blocked by walls)
        # We need to check the immediate next block in the direction
        immediate_offset = {
            0: (0, -1),  # North
            1: (1, 0),   # East
            2: (0, 1),   # South
            3: (-1, 0),  # West
        }

        imm_x_offset, imm_z_offset = immediate_offset[current_direction]

        # Get agent's current position in the grid
        agent_x = math.floor(observation["XPos"])
        agent_z = math.floor(observation["ZPos"])

        # Calculate the position we want to move to
        next_x = agent_x + imm_x_offset
        next_z = agent_z + imm_z_offset

        # Convert world coordinates to grid indices
        # Grid center is at agent's position, so we need to find the relative position
        rel_x = next_x - agent_x + 2  # +2 because grid center is at index 2
        rel_z = next_z - agent_z + 2  # +2 because grid center is at index 2

        # Check if the coordinates are within the 5x5 grid bounds
        if 0 <= rel_x < 5 and 0 <= rel_z < 5:
            # Check blocks at agent level (y=0) and above (y=1) for clearance
            for y_level in [3, 4]:  # y=3 is agent level, y=4 is one block above
                block_index = (y_level * 25) + (rel_z * 5) + rel_x

                if block_index < len(blocks):
                    block_type = blocks[block_index]

                    # Define blocks that block movement
                    solid_blocks = {
                        "stone", "cobblestone", "mossy_cobblestone", "stone_bricks",
                        "mossy_stone_bricks", "cracked_stone_bricks", "sandstone",
                        "oak_planks", "birch_planks", "spruce_planks", "jungle_planks",
                        "acacia_planks", "dark_oak_planks", "bedrock", "obsidian",
                        "iron_block", "gold_block", "diamond_block", "emerald_block",
                        "coal_block", "redstone_block", "lapis_block", "dirt", "grass_block",
                        "gravel", "sand", "glass", "wool", "iron_door", "oak_door",
                        "birch_door", "spruce_door", "jungle_door", "acacia_door",
                        "dark_oak_door", "fence", "iron_bars", "oak_fence", "wall"
                    }

                    # If we hit a solid block at head level (y=4), path is blocked
                    if y_level == 4 and block_type in solid_blocks:
                        return False

                    # If we hit a solid block at feet level (y=3), check if it's a door
                    if y_level == 3 and block_type in solid_blocks:
                        # Allow movement through doors
                        if "door" not in block_type.lower():
                            return False

        return True

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
        # Damn I feel you
        # agent_host.sendCommand("chat /tp ~ ~ ~ {} ~".format(yaw_def[current_direction]))

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

    def adjust_to_center(self, blocks: list, size: int, current_direction: int) -> None:
        """Make the agent center to its hallway for better navigation!"""
        corner_direction_map = {
            0: (-12, -8),
            1: (-8, 12),
            2: (12, 8),
            3: (8, -12)
        }

        curr_corner_direction = corner_direction_map[current_direction]
        if current_direction == 0:
            offset_calc = -1
        elif current_direction == 1:
            offset_calc = -5
        elif current_direction == 2:
            offset_calc = 1
        elif current_direction == 3:
            offset_calc = 5
        else:
            print("ERROR: Unknown direction ID when calculating adjustment!")
            return

        # 112 is the block on player's head

        # For second check, get the y elevation offset
        is_y_offset_left = self.get_y_elevation_offset(blocks, 112 + curr_corner_direction[0], size) is not None
        is_y_offset_right = self.get_y_elevation_offset(blocks, 112 + curr_corner_direction[1], size) is not None

        # Turn left if there's a clearance
        if (blocks[112 + curr_corner_direction[0]] == "air" and is_y_offset_left) and blocks[112 + (curr_corner_direction[1] + offset_calc)] != "air":
            self.agent_host.sendCommand("move 0")
            self.agent_host.sendCommand("strafe -1")
            time.sleep(1 / 4.317)
            self.agent_host.sendCommand("strafe 0")
        # Turn right if there's a clearance
        elif blocks[112 + curr_corner_direction[0] - offset_calc] != "air" and (blocks[112 + curr_corner_direction[1]] == "air" and is_y_offset_right):
            self.agent_host.sendCommand("move 0")
            self.agent_host.sendCommand("strafe 1")
            time.sleep(1 / 4.317)
            self.agent_host.sendCommand("strafe 0")


    def find_button_near_door(self, blocks: list, size: int, observation: dict) -> tuple[int, int, int] | None:
        """
        Search for a stone button near the iron door in the observation grid.
        Returns the button's position (x, y, z) relative to the center if found, None otherwise.
        """
        # The door is typically at y=0 level in the grid (agent's level)
        door_y = 0

        # Search in a 3x3 area around the door position (which is typically in front of agent)
        door_x, door_z = 0, 1  # One block in front of agent

        # Search in a 3x3 area around the door
        for y in range(-1, 2):  # Check one block above and below
            for x in range(-1, 2):  # Check one block on each side
                for z in range(0, 3):  # Check from door position to 2 blocks ahead
                    # Calculate the index in the blocks array
                    # Convert relative coordinates to grid indices
                    grid_x = x + 2  # Shift x by 2 to center (0 -> 2)
                    grid_z = z + 2  # Shift z by 2 to center (0 -> 2)
                    grid_y = y + 3  # Shift y by 3 since y=0 is at index 75-99

                    idx = (grid_y * size * size) + (grid_z * size) + grid_x
                    if 0 <= idx < len(blocks):
                        block_type = blocks[idx]
                        # Calculate absolute coordinates
                        abs_x = math.floor(observation["XPos"]) + x
                        abs_y = math.floor(observation["YPos"]) + y
                        abs_z = math.floor(observation["ZPos"]) + z
                        print(f"Checking coordinates - Relative: (x={x}, y={y}, z={z}), Absolute: (x={abs_x}, y={abs_y}, z={abs_z}), block type: {block_type}")
                        if block_type == "stone_button":
                            # Return relative position from center
                            return (x, y, z)

        # If no button found in immediate vicinity, search in a wider area
        for y in range(-2, 3):  # Check two blocks above and below
            for x in range(-2, 3):  # Check two blocks on each side
                for z in range(-1, 4):  # Check from one block behind to 3 blocks ahead
                    # Skip the inner 3x3 area we already checked
                    if -1 <= x <= 1 and 0 <= z <= 2:
                        continue

                    # Convert relative coordinates to grid indices
                    grid_x = x + 2
                    grid_z = z + 2
                    grid_y = y + 3

                    idx = (grid_y * size * size) + (grid_z * size) + grid_x
                    if 0 <= idx < len(blocks):
                        block_type = blocks[idx]
                        # Calculate absolute coordinates
                        abs_x = math.floor(observation["XPos"]) + x
                        abs_y = math.floor(observation["YPos"]) + y
                        abs_z = math.floor(observation["ZPos"]) + z
                        print(f"Checking coordinates - Relative: (x={x}, y={y}, z={z}), Absolute: (x={abs_x}, y={abs_y}, z={abs_z}), block type: {block_type}")
                        if block_type == "stone_button":
                            return (x, y, z)

        return None

    def handle_door(self, observation: dict) -> bool:
        """
        Handle door interaction if a door is detected in line of sight.
        Returns True if a door was handled, False otherwise.
        """
        if "LineOfSight" not in observation:
            return False

        block_type = observation["LineOfSight"].get("type", "")
        distance = observation["LineOfSight"].get("distance", float('inf'))

        if block_type == "iron_door" and distance < 3.0:
            print(f"\nFound an iron door at distance {distance}")

            self.agent_host.sendCommand("move 0")

            # Check for button near the door
            if "blocks" in observation:
                button_pos = self.find_button_near_door(observation["blocks"], 5, observation)  # 5 is the grid size
                if button_pos:
                    print(f"Found button at relative position {button_pos}")
                    x, y, z = button_pos
                    print(f"x: {x}, y: {y}, z: {z}")

                    # Determine turn direction based on button position
                    # Button is at (-40, 16, 21) relative to agent at (-41, 15, 20)
                    # So button is actually to the right (+x direction)
                    curr_turn = 0
                    if x > 0:  # Button is to the left
                        curr_turn = -1.5
                    elif x < 0:  # Button is to the right
                        curr_turn = 1.5
                    print(f"curr_turn: {curr_turn}")

                    if curr_turn != 0:
                        print(f"Turning {curr_turn} to face button...")
                        self.agent_host.sendCommand("turn {}".format(curr_turn))
                        print("Sleeping for 0.15s after turn command...")
                        time.sleep(0.15)

                    print("Pressing button...")
                    self.agent_host.sendCommand("use 1")
                    print("Sleeping for 0.05s after button press...")
                    time.sleep(0.05)
                    self.agent_host.sendCommand("use 0")
                    print("Sleeping for 0.05s after button release...")
                    time.sleep(0.05)

                    # Turn back to original direction
                    if curr_turn != 0:
                        print(f"Turning back {-curr_turn} to original direction...")
                        self.agent_host.sendCommand("turn {}".format(-curr_turn))
                        print("Sleeping for 0.25s after return turn...")
                        time.sleep(0.25)
                        self.agent_host.sendCommand("turn 0")
                        time.sleep(0.05)
                        self.agent_host.sendCommand("move 2")

                        print("Turn sequence complete")
                    return True
                else:
                    print("No button found near the iron door")
                    return False

        elif block_type == "wooden_door" and distance < 2.0:
            print(f"\nFound a wooden door at distance {distance}")
            # Try to open the door
            self.agent_host.sendCommand("use 1")
            time.sleep(0.5)
            self.agent_host.sendCommand("use 0")
            time.sleep(0.5)
            return True

        return False

    def get_state(self, observation):
        if "entities" in observation:
            for entity in observation["entities"]:
                if entity["name"].lower() == "zombie":
                    distance = math.sqrt(entity["x"]**2 + entity["z"]**2)
                    health = entity.get("life", 20)

                    if distance > 3:
                        return "zombie_far"
                    elif health < 10:
                        return "zombie_low_health"
                    else:
                        return "zombie_high_health"

        return "no_zombie"

    def choose_action(self, state):
        global q_table
        epsilon = 0.2  # More exploration
        if state not in q_table:
            q_table[state] = {action: 0.0 for action in ACTIONS}
            print(f"[INIT] Initialized new state in Q-table: {state}")

        if random.uniform(0, 1) < epsilon:
            chosen_action = random.choice(ACTIONS)
            print(f"[EXPLORE] Randomly chosen action: {chosen_action} for state {state}")
        else:
            max_q = max(q_table[state].values())
            best_actions = [a for a, q in q_table[state].items() if q == max_q]
            chosen_action = random.choice(best_actions)
            print(f"[EXPLOIT] Best action(s): {best_actions} → Chosen: {chosen_action} for state {state}")

        return chosen_action

    def update_q_table(self, state, action, reward, next_state):
        global q_table
        learning_rate = 0.1
        discount_factor = 0.9

        if state not in q_table:
            q_table[state] = {a: 0.0 for a in ACTIONS}
            print(f"[INIT] Initialized state {state} in Q-table.")

        if next_state not in q_table:
            q_table[next_state] = {a: 0.0 for a in ACTIONS}
            print(f"[INIT] Initialized next state {next_state} in Q-table.")

        old_q = q_table[state][action]
        next_max = max(q_table[next_state].values())
        new_q = old_q + learning_rate * (reward + discount_factor * next_max - old_q)

        q_table[state][action] = new_q

        print(f"[UPDATE] {state} --[{action}/{reward}]→ {next_state}, Q: {old_q:.2f} → {new_q:.2f}")

    def combat_behavior(self, observation, current_yaw):

        print("Combat behavior called")

        if "entities" not in observation or not observation["entities"]:
            print("No entities detected in combat_behavior.")
            return

        entities = observation["entities"]
        self_x = observation.get("XPos", 0)
        self_z = observation.get("ZPos", 0)

        nearest_mob = None
        min_dist = float("inf")

        for entity in entities:
            if entity["name"] == "Zombie":
                dist = (entity["x"] - self_x) ** 2 + (entity["z"] - self_z) ** 2
                if dist < min_dist:
                    min_dist = dist
                    nearest_mob = entity

        if nearest_mob:
            dx = nearest_mob["x"] - self_x
            dz = nearest_mob["z"] - self_z

            target_yaw = -math.degrees(math.atan2(dx, dz))
            turn_amount = (target_yaw - current_yaw + 360) % 360
            if turn_amount > 180:
                turn_amount -= 360
            turn_rate = (turn_amount / 180.0) * 3.0  # Multiply by 2.0 to make turn faster

            self.agent_host.sendCommand(f"turn {turn_rate:.2f}")

            distance = math.sqrt(min_dist)

            if distance > 3:
                print("distance > 3")
                self.agent_host.sendCommand("move 1")
            else:
                self.agent_host.sendCommand("move 0")
                print("Getting state...")
                # Choose and execute Q-learned action
                state = self.get_state(observation)
                chosen_action = self.choose_action(state)

                if chosen_action != "eat_food":
                    print(f"Equipping {chosen_action} from hotbar slot {HOTBAR_SLOTS[chosen_action]}")
                    # print(f"Sending command to equip {chosen_action}")
                    if chosen_action == "diamond_sword":
                        print("Sending command to equip diamond sword")
                        self.agent_host.sendCommand("hotbar.1 1")
                        self.agent_host.sendCommand("hotbar.1 0")
                    elif chosen_action == "diamond_axe":
                        print("Sending command to equip diamond axe")
                        self.agent_host.sendCommand("hotbar.2 1")
                        self.agent_host.sendCommand("hotbar.2 0")
                    elif chosen_action == "bow":
                        print("Sending command to equip bow")
                        self.agent_host.sendCommand("hotbar.3 1")
                        self.agent_host.sendCommand("hotbar.3 0")
                    elif chosen_action == "stone_sword":
                        print("Sending command to equip stone sword")
                        self.agent_host.sendCommand("hotbar.4 1")
                        self.agent_host.sendCommand("hotbar.4 0")
                    elif chosen_action == "stone_axe":
                        print("Sending command to equip stone axe")
                        self.agent_host.sendCommand("hotbar.5 1")
                        self.agent_host.sendCommand("hotbar.5 0")
                    time.sleep(0.2)

                if chosen_action in {"diamond_sword", "diamond_axe", "stone_sword", "stone_axe"}:
                    # print(f"Equipping {chosen_action} from hotbar slot {HOTBAR_SLOTS[chosen_action]+1}")
                    self.agent_host.sendCommand("attack 1")
                    time.sleep(0.2)
                    self.agent_host.sendCommand("attack 0")
                elif chosen_action == "bow":
                    self.agent_host.sendCommand("use 1")
                    time.sleep(0.5)
                    self.agent_host.sendCommand("use 0")
                elif chosen_action == "eat_food":
                    self.agent_host.sendCommand("hotbar.8 1")
                    self.agent_host.sendCommand("use 1")
                    time.sleep(1.2)
                    self.agent_host.sendCommand("use 0")
                print("Action taken:", chosen_action)


                last_state = state
                last_action = chosen_action

                return chosen_action

    def navigate_portal_room(self) -> None:

        global last_state, last_action

        pre_combat_position = None
        pre_combat_yaw = None


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

                # ✅ MOB CHECK START
                if "entities" in observation and any(e["name"].lower() == "zombie" for e in observation["entities"]):
                    print("Combat entity detected! Switching to combat mode...")
                    # print("Detected entities:", observation["entities"])
                    if self.current_state == "PATHFINDING":
                        print("FIGHTING STATE ACTIVE")
                        self.current_state = "FIGHTING"

                    if pre_combat_position is None:
                        # Save pre-combat position and yaw
                        if "XPos" in observation and "ZPos" in observation and "Yaw" in observation:
                            pre_combat_position = (observation["XPos"], observation["ZPos"])
                            pre_combat_yaw = observation["Yaw"]
                            print("Pre-combat position:", pre_combat_position)
                            print("Pre-combat yaw:", pre_combat_yaw)

                    if self.current_state == "FIGHTING":
                        next_state = self.get_state(observation)
                        action = self.combat_behavior(observation, observation.get("Yaw", 0))

                        reward = 0
                        if "DamageDealt" in observation and observation["DamageDealt"] > 0:
                            reward += 2
                        if "DamageTaken" in observation and observation["DamageTaken"] > 0:
                            reward -= 3
                        if "MobsKilled" in observation and observation["MobsKilled"] > 0:
                            reward += 10
                        if observation.get("DamageTaken", 0) == 0:
                            reward += 3  # bonus for flawless fight

                        print("State:", next_state)
                        print("Action taken:", action)
                        print("Reward this step:", reward)

                        if last_state is not None and last_action is not None:
                            print(f"Updating Q-table for: {last_state} → {last_action} → {reward}")
                            self.update_q_table(last_state, last_action, reward, next_state)
                        else:
                            print("Skipping Q-update: missing last_state or last_action")

                        last_state = next_state
                        last_action = action

                # ✅ MOB CHECK END

                elif self.current_state == "PATHFINDING":
                    print("PATHFINDING STATE ACTIVE")
                    # Check for grid activation. Will not proceed gameloop if not found.
                    if "blocks" not in observation:
                        print("Failed to retrieve information regarding block surroundings!")
                        break

                    # Check for full stats activation. Will not proceed gameloop if not found.
                    if "XPos" not in observation or "YPos" not in observation or "ZPos" not in observation:
                        print("It seems like FullStat is not activated!")
                        break

                    # Check for end portal frame
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
                            # End the mission
                            self.agent_host.sendCommand("quit")
                            return True

                    if self.is_agent_in_stairs(observation["blocks"]):
                        continue

                    # Handle door interaction if present
                    if self.handle_door(observation):
                        continue

                    # To prevent blocks stacking the same coords, this check will prevent duplicate tuple values.
                    standing_block = (math.floor(observation["XPos"]), math.floor(observation["YPos"]) - 1,
                                      math.floor(observation["ZPos"]))
                    if (not self.is_in_backtrack and standing_block == self.block_visit[-1]) or (self.is_in_backtrack and standing_block != self.block_visit[-1]):
                        continue

                    self.auto_correct_yaw(observation["Yaw"], current_direction)
                    if self.is_in_backtrack:
                        curr_block = self.block_visit.pop()
                        is_forward_cleared = self.check_clearance(curr_block, current_direction % 4, observation["blocks"], observation)
                        if is_forward_cleared:
                            self.is_in_backtrack = False
                            continue
                        is_left_cleared = self.check_clearance(curr_block, (current_direction - 1) % 4, observation["blocks"], observation)
                        is_right_cleared = self.check_clearance(curr_block, (current_direction + 1) % 4, observation["blocks"], observation)
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
                            # auto_correct_yaw(agent_host, current_direction)
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
                        self.block_visit.append(standing_block)
                        # agent_host.sendCommand(f"chat /setblock {block_visit[-1][0]} {block_visit[-1][1]} {block_visit[-1][2]} minecraft:gold_block")
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
                                        # agent_host.sendCommand(
                                        #     f"chat /setblock {curr_block_coord[0]} {curr_block_coord[1]} {curr_block_coord[2]} minecraft:emerald_block")
                                        if curr_block_coord in self.to_be_visited:
                                            self.to_be_visited.remove(curr_block_coord)
                                    continue

                                if curr_block_coord not in self.visited_block_coord and curr_block_coord not in self.to_be_visited:
                                    self.to_be_visited.add(curr_block_coord)
                                    # agent_host.sendCommand(
                                    #     f"chat /setblock {curr_block_coord[0]} {curr_block_coord[1]} {curr_block_coord[2]} minecraft:glowstone")
                            except IndexError:
                                print("Unable to retrieve the block either up or down! Perhaps you had set the y range too low from XML (minimum is 6)!")
                                return

                        # assert len(to_be_visited) == 3
                        if len(self.to_be_visited) <= 0:
                            print("No more blocks to explore to! Exiting loop...")
                            self.agent_host.sendCommand("move 0")
                            break

                        is_forward_cleared = self.check_clearance(self.block_visit[-1], current_direction % 4, observation["blocks"], observation)
                        if not is_forward_cleared:
                            is_left_cleared = self.check_clearance(self.block_visit[-1], (current_direction - 1) % 4, observation["blocks"], observation)
                            is_right_cleared = self.check_clearance(self.block_visit[-1], (current_direction + 1) % 4, observation["blocks"], observation)
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
                            # auto_correct_yaw(agent_host, current_direction)
                        self.adjust_to_center(observation["blocks"], size, current_direction)

                    # print("\nVisited Blocks:", list(visited_block_coord))
                    # print("To Be Visited:", list(to_be_visited))
                    # print("Current Direction: ", current_direction)
                    # print("------------------------------------------------------------------")
                    self.agent_host.sendCommand("move 1")

                elif self.current_state == "FIGHTING" and (len(observation["entities"]) <= 1 or not any(e["name"].lower() == "zombie" for e in observation["entities"])):
                    print("Combat over. Returning to pathfinding...")

                    # Restore pre-combat position
                    if pre_combat_position:
                        x, z = pre_combat_position
                        self.agent_host.sendCommand("move 0")
                        time.sleep(0.2)
                        # Get current y position since ~ doesn't work
                        y = observation.get("YPos", 0)
                        self.agent_host.sendCommand(f"tp {x + 0.5} {y} {z + 0.5}")
                        time.sleep(0.2)

                    # Restore yaw
                    if pre_combat_yaw is not None:
                        # print("Restoring yaw")
                        # print("Pre-combat position:", pre_combat_position)
                        # print("Pre-combat yaw:", pre_combat_yaw)
                        current_yaw = observation.get("Yaw", 0)
                        # print("Current yaw:", current_yaw)
                        yaw_diff = (pre_combat_yaw - current_yaw + 360) % 360
                        # print("Yaw difference:", yaw_diff)
                        if yaw_diff > 180:
                            yaw_diff -= 360
                        turn_rate = yaw_diff / 90
                        self.agent_host.sendCommand(f"turn {turn_rate:.2f}")
                        time.sleep(abs(turn_rate) * 1)  # Scale sleep with amount turned
                        self.agent_host.sendCommand("turn 0")

                    # Reset state
                    last_state = None
                    last_action = None
                    pre_combat_position = None
                    pre_combat_yaw = None
                    self.current_state = "PATHFINDING"
                    print("Returned to PATHFINDING state.")
                    # print("Last line of algorithm")
                # print("Detected entities:", observation["entities"])
                # print("Current state:", self.current_state)

def save_q_table():
    with open("q_learning_rewards.pkl", "wb") as f:
        pickle.dump(q_table, f)

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
        if not world_state.is_mission_running:
            break

        if world_state.number_of_observations_since_last_state > 0:
            observation = json.loads(world_state.observations[-1].text)
            if "Chat" in observation:
                coords = golly.get_stronghold_coords(observation)
                golly.teleport_to_stronghold(coords)
                break
        # NOTE: There's a chance observation could miss retrieving stronghold coords from chat. So using
        # time.sleep() would not be efficient here.
        # time.sleep(1)


    golly.fly_down_to_staircase()
    time.sleep(2)
    golly.pre_start()
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
    # === Save Q-table after mission ends ===
    with open(Q_SAVE_PATH, "wb") as f:
        pickle.dump(q_table, f)
    print("Q-table saved.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nTraining interrupted by user. Saving Q-table...")
        save_q_table()
        print("Q-table saved successfully. Exiting.")
        sys.exit(0)
