import constants
from direction import Direction
import environment as env
from geopy import distance
from skyfield.api import Timescale
from strategy import Strategy
import utils

satellites: dict
ground_stations: dict

class PriorityQueue:
    def __init__(self):
        self.queue = []

    def put(self, priority, function, **kwargs):
        self.queue.append((priority, function, kwargs))
        self.queue.sort(key=lambda p: p[0])

    def get(self):
        return self.queue.pop(0)
    
    def is_not_empty(self):
        return True if self.queue else False
    
    def clear(self):
        self.queue.clear()

actions_queue = PriorityQueue()
ready = False
elapsed_time = 0
control_traffic_data = 0 #Bytes

def put(time, function, **kwargs):
    env.actions_queue.put(time, function, **kwargs)

def prepare():
    if env.ready == True:
        raise RuntimeError("Environment is already prepared. Call prepare() kust once before start().")
    
    print("Preparing environment...")
    for i in range(0, constants.SIMULATION_DURATION, constants.TOPOLOGY_UPDATE_TIME):
        env.put(i, topology_builder)

    if constants.ROUTING_STRATEGY in [Strategy.POSITION_SHARING_NO_LB, 
                                      Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK, 
                                      Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                      Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB]:
        for sat in env.satellites.values():
            for i in range(0, constants.SIMULATION_DURATION, constants.SATELLITE_NEIGHBORS_UPDATE_TIME):
                env.put(i, update_satellites_position)
        for sat in env.satellites.values():
            for i in range(0, constants.SIMULATION_DURATION, constants.SATELLITE_NEIGHBORS_UPDATE_TIME):
                env.put(i, sat.update_neighbors)
        for sat in env.satellites.values():
            for i in range(0, constants.SIMULATION_DURATION, constants.SATELLITE_NEIGHBORS_UPDATE_TIME):
                env.put(i, sat._reroute_all)

    env.ready = True
    print("Simulation ready to run.")

def start():
    if env.ready == False:
        raise RuntimeError("Environment is not ready to start. Call prepare() before start().")
    
    print("Simulation started. Configuraton:")
    print("- Routing strategy:", constants.ROUTING_STRATEGY.name)
    print("- Simulation time:", utils.get_current_time().utc_strftime())
    print("- Duration:", constants.SIMULATION_DURATION, "seconds")
    print("- Total traffic in network:", constants.TOTAL_VOLUME_OF_TRAFFIC, "Mbps")
    print("- Involved ground stations:", len(env.ground_stations))
    print("- Topology update scheduled each", constants.TOPOLOGY_UPDATE_TIME, "seconds")
    if constants.ROUTING_STRATEGY in [Strategy.POSITION_SHARING_NO_LB,
                                      Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                                      Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                      Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB]:
        print("- Satellite neighbors information update scheduled each", constants.SATELLITE_NEIGHBORS_UPDATE_TIME, "seconds")
    if constants.ROUTING_STRATEGY == Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB:
        print("- Adaptive load balancing weight factor:", constants.LOAD_BALANCING_WEIGHT_FACTOR)
    
    while env.actions_queue.is_not_empty():
        time, action, kwargs = env.actions_queue.get()
        if time != env.elapsed_time:
            env.elapsed_time = time
            print("Simulating", time, "/", constants.SIMULATION_DURATION, "seconds")
        if kwargs:
            action(kwargs)
        else:
            action()

    print("Simulation ended.")

def reset():
    print("Resetting environment...")
    env.actions_queue.clear()
    env.elapsed_time = 0
    env.control_traffic_data = 0
    update_satellites_position()
    for satellite in env.satellites.values():
        satellite.remove_link(Direction.NORTH)
        satellite.remove_link(Direction.SOUTH)
        satellite.remove_link(Direction.EAST)
        satellite.remove_link(Direction.WEST)
        satellite.state = 0.0
    for gs in env.ground_stations.values():
        for flux, _, end_time in gs.outgoing_fluxes:
            if end_time == None:
                gs.close_outgoing_flux(flux)
        gs.outgoing_fluxes.clear()
        gs.incoming_fluxes.clear()
        gs.DEBUG_dropped_incoming_fluxes.clear()    
    env.ready = False
    print("Environment reset.")

def update_satellites_position():
    for sat in env.satellites.values():
        sat._update_position()
        sat._update_gs_link()
    for gs in env.ground_stations.values():
        gs.reattach()

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
        if sat[0] > constants.LATITUDE_CUTOFF or sat[0] < -constants.LATITUDE_CUTOFF:
            sat[2] = None
            sat[3] = None
            sat[4] = None
            sat[5] = None
            continue
        for key_link, sat_link in temp_satellites.items():
            if key == key_link:
                continue
            if sat_link[0] > constants.LATITUDE_CUTOFF or sat_link[0] < -constants.LATITUDE_CUTOFF:
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

        if sat[1] + 7 > sat_link[1] and sat[1] - 7 < sat_link[1] or sat[1] < -173 and sat_link[1] > 173 or sat[1] > 173 and sat_link[1] < -173:
            if sat[0] < sat_link[0] and sat[2] == None and sat_link[3] == None: #North branch
                sat[2] = sat_key
                sat_link[3] = key
            elif sat[0] > sat_link[0] and sat[3] == None and sat_link[2] == None: #South branch
                sat[3] = sat_key
                sat_link[2] = key
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

    if constants.DEBUG:
        print("Applied.")

def log_control_traffic_message(bytes: int):
    env.control_traffic_data += bytes