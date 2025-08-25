import constants
from direction import Direction
import environment as env
from geopy import distance
from skyfield.api import Timescale
from strategy import Strategy
import utils
import networkx as nx

main_graph = None
satellites: dict
ground_stations: dict

class PriorityQueue:
    def __init__(self):
        self.queue = []

    def put(self, priority, function, **kwargs):
        self.queue.append((priority, function, kwargs)) #add element to queue (a tuple of "priority, function, kwargs")
        self.queue.sort(key=lambda p: p[0]) #sort elements with increasing order

    #take the element with higher priority (the first one)
    def get(self):
        return self.queue.pop(0) 
    
    def is_not_empty(self):
        return True if self.queue else False
    
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
    for i in range(0, constants.SIMULATION_DURATION, constants.TOPOLOGY_UPDATE_TIME):
        env.put(i, topology_builder)
        
    if constants.ROUTING_STRATEGY in [Strategy.BASELINE_DIJKSTRA,
                                      Strategy.SOURCE_ROUTING_BY_HOP_NO_LB,
                                      Strategy.SOURCE_ROUTING_BY_LENGTH_NO_LB,
                                      Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
                                      Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                      Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING,
                                      Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK]:
        #update positions
        for sat in env.satellites.values(): 
            for i in range(0, constants.SIMULATION_DURATION, constants.SATELLITE_NEIGHBORS_UPDATE_TIME):
                env.put(i, update_satellites_position)
        #update neighbors
        for sat in env.satellites.values():
            for i in range(0, constants.SIMULATION_DURATION, constants.SATELLITE_NEIGHBORS_UPDATE_TIME):
                env.put(i, sat.update_neighbors)

    if constants.ROUTING_STRATEGY in [Strategy.POSITION_SHARING_NO_LB, 
                                      Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK, 
                                      Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                      Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
                                      Strategy.POSITION_AND_LOAD_STATE_SHARING_TWO_HOPS]:
        #update positions
        for sat in env.satellites.values(): 
            for i in range(0, constants.SIMULATION_DURATION, constants.SATELLITE_NEIGHBORS_UPDATE_TIME):
                env.put(i, update_satellites_position)
        #update neighbors
        for sat in env.satellites.values():
            for i in range(0, constants.SIMULATION_DURATION, constants.SATELLITE_NEIGHBORS_UPDATE_TIME):
                env.put(i, sat.update_neighbors)

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

    if constants.ROUTING_STRATEGY in [Strategy.SOURCE_ROUTING_BY_HOP_NO_LB,
                                      Strategy.SOURCE_ROUTING_BY_LENGTH_NO_LB,
                                      Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
                                      Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                      Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING,
                                      Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,
                                      Strategy.POSITION_GUESSING_NO_LB,
                                      Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                      Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                      Strategy.POSITION_SHARING_NO_LB,
                                      Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                                      Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                      Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
                                      Strategy.POSITION_AND_LOAD_STATE_SHARING_TWO_HOPS]:
        print("- Satellite neighbors information update scheduled each", constants.SATELLITE_NEIGHBORS_UPDATE_TIME, "seconds")

    if constants.ROUTING_STRATEGY == Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB:
        print("- Adaptive load balancing weight factor:", constants.LOAD_BALANCING_WEIGHT_FACTOR)
    
    if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_NO_LB,
                                      Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                      Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                      Strategy.POSITION_SHARING_NO_LB,
                                      Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                                      Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                      Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
                                      Strategy.POSITION_AND_LOAD_STATE_SHARING_TWO_HOPS]:
        print("- Launching Simulation on Distributed Paradigm.")

    if constants.ROUTING_STRATEGY in [Strategy.SOURCE_ROUTING_BY_HOP_NO_LB,
                                      Strategy.SOURCE_ROUTING_BY_LENGTH_NO_LB,
                                      Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
                                      Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                      Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING,
                                      Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,
                                      Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING]:
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

#updater of satellites position
def update_satellites_position():
    for sat in env.satellites.values():
        sat._update_position() #update position
        sat._update_gs_link() #update link to GS 
    for gs in env.ground_stations.values():
        gs.reattach() #reattach with GS

#topology builder
def topology_builder():
    update_satellites_position()
    temp_satellites = {}
    for key, sat in env.satellites.items():
        temp_satellites[key] = [sat.get_latitude(),
                                sat.get_longitude(), 
                                None, #Northern link
                                None, #Southern link
                                None, #Eastern link
                                None] #Western link
    
    distances = list()
    for key, sat in temp_satellites.items():
        if sat[0] > constants.LATITUDE_CUTOFF or sat[0] < -constants.LATITUDE_CUTOFF: #if lat>70° or lat<-70° not consider satellites for link creation
            sat[2] = None
            sat[3] = None
            sat[4] = None
            sat[5] = None
            continue
        for key_link, sat_link in temp_satellites.items(): 
            if key == key_link:
                continue
            if sat_link[0] > constants.LATITUDE_CUTOFF or sat_link[0] < -constants.LATITUDE_CUTOFF: #if out of area of interest then skip
                continue
            dist = distance.distance((sat_link[0], sat_link[1]), (sat[0], sat[1])).km
            if dist > 5100: 
                continue
            distances.append({'distance': dist, 'sat1': key, 'sat2': key_link})
    distances.sort(key=lambda x: x['distance'])
    
    for dist in distances:
        key = dist['sat1']
        sat_key = dist['sat2']
        sat = temp_satellites.get(key)
        sat_link = temp_satellites.get(sat_key)

        #check if sat & sat_link are close enough to create a link (+/- 7 degrees of longitude & +/- 173 degrees on international line of Date change)
        if sat[1] + 7 > sat_link[1] and sat[1] - 7 < sat_link[1] or sat[1] < -173 and sat_link[1] > 173 or sat[1] > 173 and sat_link[1] < -173:
            if sat[0] < sat_link[0] and sat[2] == None and sat_link[3] == None: #North branch
                sat[2] = sat_key
                sat_link[3] = key
            elif sat[0] > sat_link[0] and sat[3] == None and sat_link[2] == None: #South branch
                sat[3] = sat_key
                sat_link[2] = key
        #else check if the source satellite (sat) is at a lower longitude (so it's at EAST respect to sat_link) 
        elif (sat[1] < sat_link[1] or sat[1] > 150 and sat_link[1] < -150 and sat[1] > sat_link[1]) and sat[4] == None and sat_link[5] == None: #East branch
                sat[4] = sat_key
                sat_link[5] = key
        elif (sat[1] > sat_link[1] or sat[1] < -150 and sat_link[1] > 150 and sat[1] < sat_link[1]) and sat[5] == None and sat_link[4] == None: #West branch
                sat[5] = sat_key
                sat_link[4] = key
           
    if constants.DEBUG:
        print("Linking phase completed. Applying...")

    for key, sat in temp_satellites.items():
        satellite = env.satellites.get(key)
        north_link = env.satellites.get(sat[2])
        south_link = env.satellites.get(sat[3])
        east_link = env.satellites.get(sat[4])
        west_link = env.satellites.get(sat[5])

        satellite.add_link(north_link, Direction.NORTH) if north_link != None else satellite.remove_link(Direction.NORTH)
        satellite.add_link(south_link, Direction.SOUTH) if south_link != None else satellite.remove_link(Direction.SOUTH)
        satellite.add_link(east_link, Direction.EAST) if east_link != None else satellite.remove_link(Direction.EAST)
        satellite.add_link(west_link, Direction.WEST) if west_link != None else satellite.remove_link(Direction.WEST)

    env.main_graph = nx.Graph()
    # Add active links to active satellites
    for name, sat in env.satellites.items():
        for dir, link in sat._links.items(): 
            if link.is_active() and link.target:
                env.main_graph.add_edge(
                    name,
                    link.target.get_name(), 
                    weight=utils.get_distance_between_satellites(sat, link.target), 
                    available_bandwidth=constants.SATELLITE_LINK_CAPACITY, 
                    link_obj=link
                )

    # Link to GS and closer satellites
    for gs_name, gs in env.ground_stations.items():
        closer_satellites = utils.get_closer_satellites_for_graph(env.satellites, (gs.lat, gs.lon))
        for sat_name, sat in closer_satellites:
            distance_to_sat = utils.get_distance_between_satellite_and_gs(sat, gs)
            if distance_to_sat <= constants.SATELLITE_COVERAGE_AREA_RADIUS:
                env.main_graph.add_edge(
                    gs_name, sat_name,
                    weight=distance_to_sat,
                    available_bandwidth=constants.GROUND_STATION_LINK_CAPACITY
                )

    num_nodes = env.main_graph.number_of_nodes()
    num_edges = env.main_graph.number_of_edges()
    edges_list = [f"{u} <-> {v} {data.get('available_bandwidth', 'N/A')}" for u, v, data in env.main_graph.edges(data=True)]
    #print(f"[DEBUG] Main Graph: {num_edges} Edges, {num_nodes} Nodes in graph: {edges_list}")
    
    print("Applied. Main graph successfully updated by topology_builder.")
   
def log_control_traffic_message(bytes: int):
    env.control_traffic_data += bytes