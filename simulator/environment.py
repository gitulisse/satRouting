import constants
from direction import Direction
import environment as env
from geopy import distance
from skyfield.api import Timescale
from strategy import Strategy
import utils
import networkx as nx
import math
import heapq
from scipy.spatial import KDTree
import numpy as np


main_graph = None
satellites: dict
ground_stations: dict

# Cache for satellite positions to avoid redundant calculations
_position_cache = {}
_distance_cache = {}
_graph_cache = {'edges': set(), 'graph': None}

class PriorityQueue:
    __slots__ = ['queue', 'counter']
    
    def __init__(self):
        self.queue = []
        self.counter = 0

    def put(self, priority, function, **kwargs):
         heapq.heappush(self.queue, (priority, self.counter, function, kwargs))
         self.counter += 1

    def get(self):
        priority, _, function, kwargs = heapq.heappop(self.queue)
        return priority, function, kwargs

    def is_not_empty(self):
        return len(self.queue) > 0

    def clear(self):
        self.queue.clear()

actions_queue = PriorityQueue()
ready = False
elapsed_time = 0
control_traffic_data = 0

def put(time, function, **kwargs):
    env.actions_queue.put(time, function, **kwargs)

#used to configure the environment before the simulation
def prepare():
    if env.ready == True:
        raise RuntimeError("Environment is already prepared. Call prepare() just once before start().")

    print("Preparing environment...")
    
    # Schedule topology updates more efficiently - single event per time slot
    for i in range(0, constants.SIMULATION_DURATION, constants.TOPOLOGY_UPDATE_TIME):
        env.put(i, topology_builder)

    # Only schedule position and neighbor updates for strategies that need them
    # Combine position update + neighbor update into single scheduled event
    if constants.ROUTING_STRATEGY in constants.ACTIVE_STRATEGIES:
        # Schedule combined update for all satellites at once (reduces event queue size)
        for i in range(0, constants.SIMULATION_DURATION, constants.SATELLITE_NEIGHBORS_UPDATE_TIME):
            env.put(i, update_all_satellites_positions_and_neighbors)

    env.ready = True
    print("Simulation ready to run.")

def start():
    if env.ready == False:
        raise RuntimeError("Environment is not ready to start. Call prepare() before start().")
    
    print("Simulation started. Configuraton:")
    print("- Routing strategy:", constants.ROUTING_STRATEGY.name)
    print("- Simulation time:", utils.get_current_time().utc_strftime())
    print("- Duration:", constants.SIMULATION_DURATION, "seconds")
    print("- Total traffic in network:", constants.TOTAL_VOLUME_OF_TRAFFIC, "Gbps")
    print("- Involved ground stations:", len(env.ground_stations))
    print("- Topology update scheduled each", constants.TOPOLOGY_UPDATE_TIME, "seconds")

    if constants.ROUTING_STRATEGY in constants.ACTIVE_STRATEGIES:
        print("- Satellite neighbors information update scheduled each", constants.SATELLITE_NEIGHBORS_UPDATE_TIME, "seconds")

    if constants.ROUTING_STRATEGY == Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB:
        print("- Adaptive load balancing weight factor:", constants.LOAD_BALANCING_WEIGHT_FACTOR)
    
    if constants.ROUTING_STRATEGY in constants.DISTRIBUTED_STRATEGIES:
        print("- Launching Simulation on Distributed Paradigm.")

    if constants.ROUTING_STRATEGY in constants.SOURCE_STRATEGIES:
        print("- Launching Simulation on Source Routing Paradigm.")
   
    while env.actions_queue.is_not_empty():

        #extract actions
        time, action, kwargs = env.actions_queue.get()
        if time != env.elapsed_time: 
            env.elapsed_time = time
            print("\n|||Simulating", time, "/", constants.SIMULATION_DURATION, "seconds|||")
            
        if kwargs:
            action(kwargs)
        else:
            action()

    if constants.DEBUG:
        print("\n=== DEBUG: Ground Stations final state ===")
        for gs_id, gs in env.ground_stations.items():
            print(f"\nGround Station {gs.get_name()} (ID: {gs_id}):")

            print("  → OUTGOING FLOWS:")
            for flow, start_time, end_time in gs.outgoing_flows:
                if start_time is None or end_time is None:
                    continue
                start_str = start_time.utc_strftime()
                end_str = end_time.utc_strftime()
                print(f"    - Flow ID {flow.id}, rate: {flow.rate} Gbps, start: {start_str}, end: {end_str}")

            print("  → INCOMING FLOWS (DELIVERED):")
            for flow, start_time, end_time in gs.incoming_flows:
                if start_time is None or end_time is None:
                    continue
                start_str = start_time.utc_strftime()
                end_str = end_time.utc_strftime()
                print(f"    - Flow ID {flow.id}, rate: {flow.rate} Gbps, start: {start_str}, end: {end_str}")

            print("  → DROPPED FLOWS:")
            for flow, start_time, end_time in gs.DEBUG_dropped_incoming_flows:
                if start_time is None or end_time is None:
                    continue
                start_str = start_time.utc_strftime()
                end_str = end_time.utc_strftime()
                reason = flow.state.name if hasattr(flow.state, "name") else str(flow.state)
                print(f"    - Flow ID {flow.id}, rate: {flow.rate} Gbps, start: {start_str}, end: {end_str}, reason: {reason}")

    print("Simulation ended.")

#reset the environment
def reset():
    print("Resetting environment...")
    env.actions_queue.clear()
    env.elapsed_time = 0
    env.control_traffic_data = 0
    # Clear caches
    _position_cache.clear()
    _distance_cache.clear()
    _graph_cache['edges'].clear()
    _graph_cache['graph'] = None
    update_satellites_position() #update positions of satellites
    for satellite in env.satellites.values():
        satellite.remove_link(Direction.NORTH)
        satellite.remove_link(Direction.SOUTH)
        satellite.remove_link(Direction.EAST)
        satellite.remove_link(Direction.WEST)
        satellite.state = 0.0
    for gs in env.ground_stations.values(): #for all GS close the outoging flows without end_time
        for flow, _, end_time in gs.outgoing_flows:
            if end_time == None:
                gs.close_outgoing_flow(flow)
        gs.outgoing_flows.clear() #cleare outgoing flows
        gs.incoming_flows.clear() #clear incoming flows
        gs.DEBUG_dropped_incoming_flows.clear() #clear dropped flows
    env.ready = False
    print("Environment reset.")

# Combined update function for all satellites (reduces event queue overhead)
def update_all_satellites_positions_and_neighbors():
    """Update positions and neighbors for all satellites in a single call."""
    update_satellites_position()
    for sat in env.satellites.values():
        sat.update_neighbors()

#updater of satellites position
def update_satellites_position():
    for sat in env.satellites.values():
        sat._update_position() #update position
        sat._update_gs_link() #update link to GS
    for gs in env.ground_stations.values():
        gs.reattach() #reattach with GS

#topology builder - optimized with KDTree for spatial indexing
def topology_builder():
    """Build network topology using KDTree for efficient neighbor finding (O(n log n) vs O(n²))."""
    update_satellites_position()
    
    # Clear distance cache each topology update (positions changed)
    _distance_cache.clear()
    
    # Build position arrays for KDTree (only for satellites in valid latitude range)
    valid_satellites = {}
    coords_list = []
    
    for key, sat in env.satellites.items():
        lat = sat.get_latitude()
        lon = sat.get_longitude()
        if lat is None or lon is None or not (math.isfinite(lat) and math.isfinite(lon)):
            print(f"Satellite {sat.get_name()} has invalid coordinates: {lat}, {lon}")
            continue
        # Only consider satellites within latitude cutoff for ISL links
        if lat > constants.LATITUDE_CUTOFF or lat < -constants.LATITUDE_CUTOFF:
            valid_satellites[key] = None  # Mark as out of range
            continue
        valid_satellites[key] = [lat, lon, None, None, None, None]  # lat, lon, N, S, E, W
        coords_list.append((lat, lon))
    
    # Use KDTree for efficient neighbor search (much faster than O(n²) distance calculations)
    if len(coords_list) > 0:
        coords_array = np.array(coords_list)
        tree = KDTree(coords_array)  # ball_radius removed in scipy >= 1.11
        
        # For each satellite, find neighbors within 5100km using KDTree query_ball_point
        valid_keys = [key for key, val in valid_satellites.items() if val is not None]
        
        for i, key in enumerate(valid_keys):
            sat = valid_satellites[key]
            neighbors_idx = tree.query_ball_point(coords_array[i], r=5100)
            for j in neighbors_idx:
                if i == j:
                    continue
                key_link = valid_keys[j]
                sat_link = valid_satellites[key_link]
                
                # Calculate actual distance (cached)
                dist_key = (min(key, key_link), max(key, key_link))
                if dist_key not in _distance_cache:
                    _distance_cache[dist_key] = distance.distance(
                        (sat_link[0], sat_link[1]), (sat[0], sat[1])).km
                
                dist = _distance_cache[dist_key]
                if dist > 5100:
                    continue
                
                # Check longitude proximity for link creation
                if _should_create_link(sat, sat_link):
                    _assign_link(valid_satellites, key, key_link, sat, sat_link)
    
    # Apply the computed topology to actual satellites
    _apply_topology(valid_satellites)
    
    # Build networkx graph incrementally
    _build_graph_incremental()
    
    print("Applied. Main graph successfully updated by topology_builder.")

def _should_create_link(sat, sat_link):
    """Check if two satellites should be linked based on longitude criteria."""
    # North/South check
    if (sat[1] + 7 > sat_link[1] and sat[1] - 7 < sat_link[1] or 
        sat[1] < -173 and sat_link[1] > 173 or 
        sat[1] > 173 and sat_link[1] < -173):
        return True
    # East/West check
    elif ((sat[1] < sat_link[1] or (sat[1] > 150 and sat_link[1] < -150 and sat[1] > sat_link[1])) or
          (sat[1] > sat_link[1] or (sat[1] < -150 and sat_link[1] > 150 and sat[1] < sat_link[1]))):
        return True
    return False

def _assign_link(valid_satellites, key, key_link, sat, sat_link):
    """Assign link direction between two satellites."""
    # North branch
    if sat[0] < sat_link[0] and sat[2] is None and sat_link[3] is None:
        sat[2] = key_link
        sat_link[3] = key
    # South branch
    elif sat[0] > sat_link[0] and sat[3] is None and sat_link[2] is None:
        sat[3] = key_link
        sat_link[2] = key
    # East branch
    elif (sat[1] < sat_link[1] or (sat[1] > 150 and sat_link[1] < -150 and sat[1] > sat_link[1])) and sat[4] is None and sat_link[5] is None:
        sat[4] = key_link
        sat_link[5] = key
    # West branch
    elif (sat[1] > sat_link[1] or (sat[1] < -150 and sat_link[1] > 150 and sat[1] < sat_link[1])) and sat[5] is None and sat_link[4] is None:
        sat[5] = key_link
        sat_link[4] = key

def _apply_topology(valid_satellites):
    """Apply computed topology to actual satellite objects."""
    if constants.DEBUG:
        print("Linking phase completed. Applying...")

    for key, sat_data in valid_satellites.items():
        if sat_data is None:  # Satellite out of latitude range
            satellite = env.satellites.get(key)
            satellite.remove_link(Direction.NORTH)
            satellite.remove_link(Direction.SOUTH)
            satellite.remove_link(Direction.EAST)
            satellite.remove_link(Direction.WEST)
            continue
            
        satellite = env.satellites.get(key)
        north_link = env.satellites.get(sat_data[2]) if sat_data[2] else None
        south_link = env.satellites.get(sat_data[3]) if sat_data[3] else None
        east_link = env.satellites.get(sat_data[4]) if sat_data[4] else None
        west_link = env.satellites.get(sat_data[5]) if sat_data[5] else None

        satellite.add_link(north_link, Direction.NORTH) if north_link else satellite.remove_link(Direction.NORTH)
        satellite.add_link(south_link, Direction.SOUTH) if south_link else satellite.remove_link(Direction.SOUTH)
        satellite.add_link(east_link, Direction.EAST) if east_link else satellite.remove_link(Direction.EAST)
        satellite.add_link(west_link, Direction.WEST) if west_link else satellite.remove_link(Direction.WEST)

def _build_graph_incremental():
    """Build networkx graph with incremental updates."""
    env.main_graph = nx.Graph()
    
    # Add active satellite links
    edges_to_add = []
    for name, sat in env.satellites.items():
        for dir, link in sat._links.items():
            if link.is_active() and link.target:
                target_name = link.target.get_name()
                edge_key = (min(name, target_name), max(name, target_name))
                
                # Use cached distance if available
                if edge_key not in _distance_cache:
                    _distance_cache[edge_key] = utils.get_distance_between_satellites(sat, link.target)
                
                edges_to_add.append((
                    name,
                    target_name,
                    {
                        'weight': _distance_cache[edge_key],
                        'available_bandwidth': constants.SATELLITE_LINK_CAPACITY,
                        'link_obj': link
                    }
                ))
    
    env.main_graph.add_edges_from(edges_to_add)

    # Link to GS and closer satellites
    for gs_name, gs in env.ground_stations.items():
        closer_satellites = utils.get_closer_satellites_for_graph(env.satellites, (gs.lat, gs.lon))
        gs_edges = []
        for sat_name, sat in closer_satellites:
            distance_to_sat = utils.get_distance_between_satellite_and_gs(sat, gs)
            if distance_to_sat <= constants.SATELLITE_COVERAGE_AREA_RADIUS:
                gs_edges.append((
                    gs_name, sat_name,
                    {
                        'weight': distance_to_sat,
                        'available_bandwidth': constants.GROUND_STATION_LINK_CAPACITY
                    }
                ))
        env.main_graph.add_edges_from(gs_edges)

    num_nodes = env.main_graph.number_of_nodes()
    num_edges = env.main_graph.number_of_edges()
    #print(f"[DEBUG] Main Graph: {num_edges} Edges, {num_nodes} Nodes")
   
def log_control_traffic_message(bytes: int):
    env.control_traffic_data += bytes
