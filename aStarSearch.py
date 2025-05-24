import json
import heapq
import math
import time
from enum import Enum
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass
import random

# Different modes our agent can operate in
class AgentMode(Enum):
    SEARCHING = "search"
    GUARDING = "guard"
    ENGAGING = "attack"

# Just a wrapper for block coordinates
@dataclass
class BlockPos:
    x: int
    y: int
    z: int

    def __hash__(self):
        return hash((self.x, self.y, self.z))

    def __eq__(self, other):
        return (self.x, self.y, self.z) == (other.x, other.y, other.z)

    def dist_to(self, other):
        return math.sqrt((self.x - other.x)**2 + (self.y - other.y)**2 + (self.z - other.z)**2)

    def manhattan_to(self, other):
        return abs(self.x - other.x) + abs(self.y - other.y) + abs(self.z - other.z)

class StrongholdWanderer:
    def __init__(self, host_api):
        self.host = host_api
        self.mode = AgentMode.SEARCHING

        self.world = {}  # mapping: BlockPos -> block type
        self.room_anchors = []  # potential room centers
        self.visited = set()

        self.me = None
        self.portal_loc = None
        self.current_goal = None
        self.path = []
        self.seen_players = []

        self.position_history = []
        self.stuck_counter = 0

        self.patrol_index = 0
        self.last_patrol_change = 0

        self.walkables = [
            'air', 'stone_brick_stairs', 'iron_door', 'oak_door', 'stone_brick_slab',
            'cobblestone_stairs', 'stone_stairs', 'brick_stairs'
        ]

        self.walls = [
            'stonebrick', 'stone_bricks', 'mossy_stone_bricks', 'cracked_stone_bricks',
            'cobblestone', 'stone', 'bedrock'
        ]

        self.portal_blocks = ['end_portal_frame', 'end_portal']
        self.hazards = ['lava', 'fire', 'magma_block', 'cactus']

        self.doors = ['iron_door', 'oak_door', 'spruce_door', 'birch_door', 'jungle_door', 'acacia_door', 'dark_oak_door']

        self.move_weights = {
            'air': 1.0,
            'stone_brick_stairs': 1.2,
            'iron_door': 3.0,
            'oak_door': 2.5,
            'water': 4.0,
            'cobweb': 8.0,
            'gravel': 1.5,
            'sand': 1.3
        }

    def update_position_and_blocks(self, obs):
        if 'XPos' in obs:
            pos = BlockPos(int(obs['XPos']), int(obs['YPos']), int(obs['ZPos']))
            self.position_history.append(pos)
            if len(self.position_history) > 10:
                self.position_history.pop(0)

            if len(self.position_history) >= 5:
                recent = set(self.position_history[-5:])
                self.stuck_counter = self.stuck_counter + 1 if len(recent) <= 2 else 0

            self.me = pos
            self.visited.add(self.me)

        if 'blocks' in obs and len(obs['blocks']) >= 27:
            for i, block in enumerate(obs['blocks']):
                dx = (i % 3) - 1
                dy = ((i // 3) % 3) - 1
                dz = (i // 9) - 1
                pos = BlockPos(self.me.x + dx, self.me.y + dy, self.me.z + dz)

                clean = block.replace('minecraft:', '') if block else 'air'
                self.world[pos] = clean

                if not self.portal_loc and clean in self.portal_blocks:
                    self.portal_loc = pos
                    print(f"[+] Portal spotted at {pos} using {clean}")

                if clean == 'air' and self._maybe_room_center(pos):
                    if all(pos.dist_to(p) >= 8 for p in self.room_anchors):
                        self.room_anchors.append(pos)
                        print(f"[+] New potential room center at {pos}")

    def _maybe_room_center(self, pos):
        if not self.me:
            return False
        air_count, total = 0, 0
        for dx in range(-2, 3):
            for dz in range(-2, 3):
                check = BlockPos(pos.x + dx, pos.y, pos.z + dz)
                if check in self.world:
                    total += 1
                    if self.world[check] == 'air':
                        air_count += 1
        return total >= 15 and air_count / total > 0.6

    def get_cost(self, block):
        return float('inf') if block in self.hazards else self.move_weights.get(block, 1.0)

    def find_neighbors(self, pos):
        directions = [
            (1, 0, 0, 1.0), (-1, 0, 0, 1.0),
            (0, 0, 1, 1.0), (0, 0, -1, 1.0),
            (0, 1, 0, 1.8), (0, -1, 0, 1.8)
        ]

        result = []
        for dx, dy, dz, cost in directions:
            neighbor = BlockPos(pos.x + dx, pos.y + dy, pos.z + dz)
            if neighbor in self.world:
                blk = self.world[neighbor]
                if self._is_walkable(blk):
                    result.append((neighbor, cost * self.get_cost(blk)))
            else:
                result.append((neighbor, cost * 2.5))  # mystery blocks
        return result

    def _is_walkable(self, block):
        return (block in self.walkables or block == 'air' or block in self.doors or block.endswith('_stairs') or block.endswith('_slab'))

    def heuristic(self, a, b):
        # Combo of straight-line + boxy distance
        return 0.7 * a.manhattan_to(b) + 0.3 * a.dist_to(b)

    def astar(self, start, goal, max_iterations=2000):
        if start == goal:
            return [start]

        open_heap = [(0, 0, start)]
        came_from = {}
        g_scores = {start: 0}
        visited = set()
        attempts = 0

        while open_heap and attempts < max_iterations:
            attempts += 1
            _, g, current = heapq.heappop(open_heap)
            if current in visited:
                continue
            visited.add(current)

            if current == goal:
                return self._reconstruct_path(came_from, current, start)

            for neighbor, step_cost in self.find_neighbors(current):
                if neighbor in visited:
                    continue

                new_g = g + step_cost
                if neighbor not in g_scores or new_g < g_scores[neighbor]:
                    came_from[neighbor] = current
                    g_scores[neighbor] = new_g
                    heapq.heappush(open_heap, (new_g + self.heuristic(neighbor, goal), new_g, neighbor))

        print(f"[!] Couldn't reach {goal} from {start} in {attempts} tries")
        return []

    def _reconstruct_path(self, came_from, current, start):
        path = []
        while current != start:
            path.append(current)
            current = came_from[current]
        path.append(start)
        return path[::-1]

class GollyAgent:
    def __init__(self, host_api):
        self.host = host_api
        self.brain = StrongholdWanderer(host_api)
        self.active = True

    def run_agent_loop(self):
        print("[+] Booting up stronghold explorer...")
        while self.active:
            try:
                state = self.host.getWorldState()
                if not state.is_mission_running:
                    print("[-] Mission complete. Wrapping up.")
                    break

                if state.number_of_observations_since_last_state > 0:
                    obs = json.loads(state.observations[-1].text)
                    command = self.brain.decide_next_move(obs)
                    if command:
                        self.host.sendCommand(command)
                        print(f"[>] Sent: {command}")
                    time.sleep(0.1)
                else:
                    time.sleep(0.05)
            except Exception as e:
                print(f"[!] Agent loop hiccup: {e}")
                time.sleep(0.5)

    def stop(self):
        self.active = False

    def get_stats(self):
        return {
            'mode': self.brain.mode.value,
            'position': f"({self.brain.me.x}, {self.brain.me.y}, {self.brain.me.z})" if self.brain.me else "Unknown",
            'portal_found': bool(self.brain.portal_loc),
            'rooms_discovered': len(self.brain.room_anchors),
            'blocks_mapped': len(self.brain.world),
            'visited_positions': len(self.brain.visited)
        }
