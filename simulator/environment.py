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
        self.queue.append((priority, function, kwargs)) #add elemenyt to queue (a tuple of "priority, function, kwargs")
        self.queue.sort(key=lambda p: p[0]) #sort elements with increasing order

    def get(self):
        return self.queue.pop(0) #take the element with higher priority (the first one)
    
    def is_not_empty(self):
        return True if self.queue else False #check if queue is not empty
    
    def clear(self):
        self.queue.clear() #clear queue
 
actions_queue = PriorityQueue() #queue of actions to do in the environment of simulation
ready = False #variable that represent environment is stil in preparation
elapsed_time = 0 #passed time
control_traffic_data = 0 #Bytes used for traffic control

def put(time, function, **kwargs):
    env.actions_queue.put(time, function, **kwargs) #insert an action in the action_queue

#used to configure the environment before the simulation
def prepare():
    print("PREPARE(((())))) called.")
    if env.ready == True:
        raise RuntimeError("Environment is already prepared. Call prepare() just once before start().") #if environment is ready and receive another prepare() throws error
    
    print("Preparing environment...")
    #count=0
    for i in range(0, constants.SIMULATION_DURATION, constants.TOPOLOGY_UPDATE_TIME): #for all the simulation's duration with the update time as interval between step
        env.put(i, topology_builder) #put the action topology builder for update topology
        '''
        if constants.DEBUG:
            count+=1
            print(f"Topology builder {count}: lanciato")
        '''
    if constants.ROUTING_STRATEGY in [Strategy.BASELINE_DIJKSTRA,
                                      Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                      Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                      Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING,
                                      Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                      Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                      Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                      Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_COSTS_SELECTION]:
        print("entrato in centralized del Topology Builder")
        #update positions
        for sat in env.satellites.values(): 
            for i in range(0, constants.SIMULATION_DURATION, constants.SATELLITE_NEIGHBORS_UPDATE_TIME):
                env.put(i, update_satellites_position)
        #update neighbors
        for sat in env.satellites.values():
            for i in range(0, constants.SIMULATION_DURATION, constants.SATELLITE_NEIGHBORS_UPDATE_TIME):
                env.put(i, sat.update_neighbors)
        #reroute
        #for sat in env.satellites.values():
         #   for i in range(0, constants.SIMULATION_DURATION, constants.SATELLITE_NEIGHBORS_UPDATE_TIME):
          #      env.put(i, sat._reroute_all)   #è necesario??????????????????????

    #if it's used a specific strategy, add actions to update values of satellites's dictionary
    if constants.ROUTING_STRATEGY in [Strategy.POSITION_SHARING_NO_LB, 
                                      Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK, 
                                      Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                      Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
                                      Strategy.POSITION_SHARING_WITH_COSTS_SELECTION]: ####
        #update positions
        for sat in env.satellites.values(): 
            for i in range(0, constants.SIMULATION_DURATION, constants.SATELLITE_NEIGHBORS_UPDATE_TIME):
                env.put(i, update_satellites_position)
        #update neighbors
        for sat in env.satellites.values():
            for i in range(0, constants.SIMULATION_DURATION, constants.SATELLITE_NEIGHBORS_UPDATE_TIME):
                env.put(i, sat.update_neighbors)
        #reroute
        for sat in env.satellites.values():
            for i in range(0, constants.SIMULATION_DURATION, constants.SATELLITE_NEIGHBORS_UPDATE_TIME):
                env.put(i, sat._reroute_all)

    env.ready = True #set ready to True
    print("Simulation ready to run.")

def start():
    if env.ready == False: #if simulation isn't ready throws error
        raise RuntimeError("Environment is not ready to start. Call prepare() before start().")
    
    print("Simulation started. Configuraton:")
    print("- Routing strategy:", constants.ROUTING_STRATEGY.name)
    print("- Simulation time:", utils.get_current_time().utc_strftime()) #datetime
    print("- Duration:", constants.SIMULATION_DURATION, "seconds")
    print("- Total traffic in network:", constants.TOTAL_VOLUME_OF_TRAFFIC, "Mbps")
    print("- Involved ground stations:", len(env.ground_stations))
    print("- Topology update scheduled each", constants.TOPOLOGY_UPDATE_TIME, "seconds")

    #if the strategy requires LB print the current UPDATE_TIME
    if constants.ROUTING_STRATEGY in [Strategy.BASELINE_DIJKSTRA,
                                      Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                      Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                      Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING,
                                      Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                      Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                      Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                      Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_COSTS_SELECTION,
                                      Strategy.POSITION_SHARING_NO_LB,
                                      Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                                      Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                      Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB]:
        print("- Satellite neighbors information update scheduled each", constants.SATELLITE_NEIGHBORS_UPDATE_TIME, "seconds")

    #if POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB then print the WEIGHT_FACTOR
    if constants.ROUTING_STRATEGY == Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB:
        print("- Adaptive load balancing weight factor:", constants.LOAD_BALANCING_WEIGHT_FACTOR)
    
    if constants.ROUTING_STRATEGY in [Strategy.BASELINE_DIJKSTRA,
                                      Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                      Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                      Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING,
                                      Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                      Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                      Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                      Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_COSTS_SELECTION]:
        print("- Launching Centralized Strategy of Simulation.")
      
    #while the queue has actions then execute all actions
    while env.actions_queue.is_not_empty():

        #extract actions
        time, action, kwargs = env.actions_queue.get()
        if time != env.elapsed_time: 
            env.elapsed_time = time
            print("Simulating", time, "/", constants.SIMULATION_DURATION, "seconds")
        '''
        if constants.DEBUG:
            print("TIME: ", time ,"ACTIONS QUEUE: ", action) ###########
        '''
        #print("TIME: ", time ,"ACTIONS QUEUE: ", action, "KWARGS: ", kwargs) ###########
        #print("AZIONI", action)
        if kwargs:
            action(kwargs)
        else:
            action()
        
    print("Simulation ended.")

#reset the environment
def reset():
    print("Resetting environment...")
    env.actions_queue.clear() #clear variables and queue
    env.elapsed_time = 0
    env.control_traffic_data = 0
    update_satellites_position() #update positions of satellites

    #for all satellites remove links and reset state
    for satellite in env.satellites.values():
        satellite.remove_link(Direction.NORTH)
        satellite.remove_link(Direction.SOUTH)
        satellite.remove_link(Direction.EAST)
        satellite.remove_link(Direction.WEST)
        satellite.state = 0.0

    #for all GS close the outoging fluxes without end_time
    for gs in env.ground_stations.values():
        for flux, _, end_time in gs.outgoing_fluxes:
            if end_time == None:
                gs.close_outgoing_flux(flux) #close
        gs.outgoing_fluxes.clear() #cleare outgoing fluxes
        gs.incoming_fluxes.clear() #clear incoming fluxes
        gs.DEBUG_dropped_incoming_fluxes.clear() #clear debug dropped fluxes
    env.ready = False #set ready to False
    print("Environment reset.")

#updater of satellites position
def update_satellites_position():
    for sat in env.satellites.values():
        sat._update_position() #update position
        sat._update_gs_link() #update link to GS 
    for gs in env.ground_stations.values():
        if constants.ROUTING_STRATEGY in [Strategy.BASELINE_DIJKSTRA, #rivedere sta parte perchè non c'è il riferimento alla GS
                                            Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING,
                                            Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                            Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                            Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                            Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                            Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                            Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_COSTS_SELECTION]:
            gs.reattach()
        else:
            gs.reattach() #reattach with GS

#topology builder
def topology_builder():
    update_satellites_position() #updates positions and link to GS
    print("update satellites position")
    temp_satellites = {} #create temporary dictionary for satellites
    for key, sat in env.satellites.items():
        temp_satellites[key] = [sat.get_latitude(), #populate temp_satellites with lat, lon and links
                                sat.get_longitude(), 
                                None, #Northern link
                                None, #Southern link
                                None, #Eastern link
                                None] #Western link
    
    distances = list() #list for distances with other satellites
    for key, sat in temp_satellites.items():
        if sat[0] > constants.LATITUDE_CUTOFF or sat[0] < -constants.LATITUDE_CUTOFF: #if lat>70° or lat<-70° not consider satellites for link creation
            sat[2] = None
            sat[3] = None
            sat[4] = None
            sat[5] = None
            continue
        for key_link, sat_link in temp_satellites.items(): 
            if key == key_link: #if the key of any satellite is equal to key_link don't calculate distance to itself and skip
                continue
            if sat_link[0] > constants.LATITUDE_CUTOFF or sat_link[0] < -constants.LATITUDE_CUTOFF: #if out of area of interest then skip
                continue
            dist = distance.distance((sat_link[0], sat_link[1]), (sat[0], sat[1])).km #calculate the distance between SAT_LINK e SAT (the 2 considered satellites)
            if dist > 5100: 
                continue #skip if distance is > 5100 km
            distances.append({'distance': dist, 'sat1': key, 'sat2': key_link}) #add the distance in the list "distances"
    distances.sort(key=lambda x: x['distance']) #sort with increasing order
    
    #for each distance get the information of sat (sat1) & sat_link (sat2) to be saved in temp_satellites
    for dist in distances:
        key = dist['sat1']
        sat_key = dist['sat2']
        sat = temp_satellites.get(key)
        sat_link = temp_satellites.get(sat_key)

        #check if sat & sat_link are close enough to create a link (+/- 7 degrees of longitude & +/- 173 degrees on international line of Date change)
        if sat[1] + 7 > sat_link[1] and sat[1] - 7 < sat_link[1] or sat[1] < -173 and sat_link[1] > 173 or sat[1] > 173 and sat_link[1] < -173:
            #if sat it's under sat_link & sat has no NORTHERN link and sat_link has no SOUTHERN link
            if sat[0] < sat_link[0] and sat[2] == None and sat_link[3] == None: #North branch (from source satellite creates a link towards North)
                sat[2] = sat_key #store the distance for the Northern link (towards North)
                sat_link[3] = key #store the distance for the Southern link
            elif sat[0] > sat_link[0] and sat[3] == None and sat_link[2] == None: #South branch (does same thing if but towards South)
                sat[3] = sat_key
                sat_link[2] = key
        #else check if the source satellite (sat) is at a lower longitude (so it's at EAST respect to sat_link) 
        elif (sat[1] < sat_link[1] or sat[1] > 150 and sat_link[1] < -150 and sat[1] > sat_link[1]) and sat[4] == None and sat_link[5] == None: #East branch
                sat[4] = sat_key #store the distance for the Eastern link (towards East)
                sat_link[5] = key #store the distance for the Western link
        elif (sat[1] > sat_link[1] or sat[1] < -150 and sat_link[1] > 150 and sat[1] < sat_link[1]) and sat[5] == None and sat_link[4] == None: #West branch
                sat[5] = sat_key
                sat_link[4] = key
    '''
    #debug            
    if constants.DEBUG:
        print("Linking phase completed. Applying...")
    '''

    #for every satellite update their infos and add links
    for key, sat in temp_satellites.items():
        satellite = env.satellites.get(key)
        north_link = env.satellites.get(sat[2])
        south_link = env.satellites.get(sat[3])
        east_link = env.satellites.get(sat[4])
        west_link = env.satellites.get(sat[5])

        #add the links if there is effectively a north_link else remove link because there isn't a sattellite in the north to connect with
        #print("north_link", north_link)
        satellite.add_link(north_link, Direction.NORTH) if north_link != None else satellite.remove_link(Direction.NORTH)
        satellite.add_link(south_link, Direction.SOUTH) if south_link != None else satellite.remove_link(Direction.SOUTH)
        satellite.add_link(east_link, Direction.EAST) if east_link != None else satellite.remove_link(Direction.EAST)
        satellite.add_link(west_link, Direction.WEST) if west_link != None else satellite.remove_link(Direction.WEST)

    
    #debug
    if constants.DEBUG:
        #print("DISTANZE", distances)
        print("Applied.")

#calculate the value of control_traffic_data used during the simulation
def log_control_traffic_message(bytes: int):
    env.control_traffic_data += bytes