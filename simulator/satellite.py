import constants
from copy import copy
from direction import Direction
import environment as env
from flow import Flow, FlowState
from geopy import distance
from ground_station import GroundStation
from link import Link, LaserLink, RadioLink
from mapping_table import MappingTable
import math
import random
from routing_action import RoutingAction
from skyfield.api import EarthSatellite, wgs84
from strategy import Strategy
import utils

class Sat:
    def __init__(self, earth_satellite, ground_stations) -> None:
        self._earth_satellite: EarthSatellite = earth_satellite
        self._lat = None
        self._lon = None
        self._links = {}
        self._links[Direction.NORTH] = LaserLink(self) #Directional laser links
        self._links[Direction.SOUTH] = LaserLink(self) #Directional laser links
        self._links[Direction.EAST] = LaserLink(self) #Directional laser links
        self._links[Direction.WEST] = LaserLink(self) #Directional laser links
        self._gs_link = RadioLink(self) #Link to Ground Station
        self.flows: dict[int, (Flow, Link)] = {} #Dictionary that maps TUPLES of int about identifiers of Flowes and Links
        self.DEBUG_dropped_flows: list[Flow] = [] #List of Dropped Flowes
        self.mapping_table = MappingTable()
        self._ground_stations = ground_stations #Selected Ground Stations for simulation
        self.state = 0.0 #Operative state of satellite
        self.serving_gs: GroundStation = None #Served Ground Station
        self._current_round_robin_iteration = random.randint(1, 4) 
        self._is_rerouting = False #if rerouting connections


    #Verify if "other" is an instance of Sat return True else False
    def __eq__(self, other) -> bool:
        if isinstance(other, Sat):
            return self.get_name() == other.get_name()
        return False
    
    #Verify if "other" is NOT an instance of Sat return True else False
    def __ne__(self, other) -> bool:
        return not self.__eq__(other)

    #Identifies active Satellites, return True if the list of links of a Satellite is NOT empty (!= 0), so the Satellite is considered active
    def is_operational(self) -> bool:
        return len([link for link in self._links.values() if link.is_active()]) != 0

    #Manages adding links to a Satellite
    def add_link(self, sat, dir: Direction):
        link = self._links.get(dir)
        if link.target == sat: #if link already exists, avoid duplicates and return
            return
        #if constants.DEBUG:
           # print("Adding link from Satellite", self.get_name(), "to Satellite", sat.get_name(), "at time", utils.get_current_time().utc_strftime())
        self.notify_neighbor_unlink(dir) #notify link removal to neighbor
        leftovers = link.point_to_sat(sat) #stores remaining flows about link pointing to satellite
        if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_NO_LB,
                                          Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                          Strategy.POSITION_GUESSING_PROGRESSIVE_LB]:
            self._update_position() #update
        if leftovers:
            for flow in leftovers:   
                if constants.DEBUG:
                    print("[add_link] Leftover from link:", dir, "on Satellite", self.get_name(), "at time", utils.get_current_time().utc_strftime(), "flow:", flow.id, [step.get_name() for step in flow.get_steps()])
                flow.add_step(self) #open_flow-like behaviour without actually opening the flux
                flow.alias_id = self.mapping_table.add(flow.alias_id)
                flow.drop_steps_from(self) #remove flow's steps that pass through this link of the satellite
                self.drop_flow(flow, FlowState.LINK_CONGESTED) #####
                #self.open_flow(flow)

    
    #Remove a link and notify neighbor
    def remove_link(self, dir: Direction, notify_neighbor = True):
        link = self._links.get(dir) #obtain the link from dictionary _links
        ####print(f"Attempting to remove link {dir} for satellite {self.get_name()} that's active? {link.is_active()}")######
        if not(link.is_active()):  # Verifica che il link esista ed è attivo
            return
        if notify_neighbor:
            self.notify_neighbor_unlink(dir)
        #if constants.DEBUG:
        #print("Removing link from Satellite", self.get_name(), "to Satellite", self._links[dir].target.get_name(), "at time", utils.get_current_time().utc_strftime())
        #print(f"Link {dir} removed for satellite {self.get_name()}")######
        leftovers = self._links[dir].idle() #stores remaining flows
        if leftovers and self.is_operational():
            for flow in leftovers:
                if constants.DEBUG:
                    print("[remove_link] Leftover from link:", dir, "on Satellite", self.get_name(), "at time", utils.get_current_time().utc_strftime(), "flow:", flow.id, [step.get_name() for step in flow.get_steps()])
                flow.add_step(self) #open_flow-like behaviour without actually opening the flux
                flow.alias_id = self.mapping_table.add(flow.alias_id)
                flow.drop_steps_from(self)
                self.drop_flow(flow, FlowState.LINK_CONGESTED)
                #self.open_flow(flow)
        if not(self.is_operational()):
            if self.serving_gs:
                #if constants.DEBUG:
                    #print("Satellite", self.get_name(), "is serving Ground Station", self.serving_gs.get_name(), "but is no longer operational. Requesting reattachment...")
                self.serving_gs.reattach() #reconnection to Ground Station
    
    #Return name of Satellite as the last 3 digit of satellite's name ("satellite156") as 156
    def get_name(self) -> int:
        return int(self._earth_satellite.name[-3:])
    
    #Return lat
    def get_latitude(self):
        return self._lat
    
    #Return lon
    def get_longitude(self):
        return self._lon
    
    def store_flow_direction(self, flow: Flow, link: Link):
        #print(f"    Storing flow {flow.alias_id} in satellite {self.get_name()} headed to link {flow},{link if link != None else None} at time {utils.get_current_time().utc_strftime()}")
        #print("self.fluxes check", self.flows)
        if flow.alias_id not in self.flows.keys():
            self.flows[flow.alias_id] = (flow, link)
            #print(" <======= stored new into self.flows", self.flows)
        else:
            raise RuntimeError("Alias id already present in flows structure.", flow.alias_id)
        #if constants.DEBUG:
         #   print("Stored new flow", flow.id,"with alias id", flow.alias_id, "with rate", flow.rate, "on Satellite", self.get_name()) # "at time", utils.get_current_time().utc_strftime())

            
    #Return tuple (flow, link) if the flow id is stored
    def get_stored_flow_direction(self, alias_id: int) -> list[(Flow, Link)]:
        if alias_id in self.flows.keys():
            #print("+ storing")
            return self.flows[alias_id]
        return []

    #Manage drop of flows
    def drop_flow(self, flow: Flow, reason: FlowState):
        if constants.DEBUG: #debugging messages
            msg = "Flow " + str(flow.id) + " with alias id " + str(flow.alias_id) + " with rate " + str(flow.rate) + " Gbps has been dropped by Satellite " + str(self.get_name()) + " at time " + utils.get_current_time().utc_strftime() + ". "
            if reason == FlowState.SATELLITE_CONGESTED:
                msg += "Satellite is congested."
            elif reason == FlowState.LINK_CONGESTED:
                msg += "Link is congested."
            elif reason == FlowState.EXPIRED_TTL:
                msg += "TTL is 0."
            elif reason == FlowState.SATELLITE_NOT_OPERATIONAL:
                msg += "Satellite is not operational."
            else:
                raise ValueError("The reason is not expected.", reason)
            print(msg)
        
        flow.state = reason #update flow's state with reason for the drop
        self.store_flow_direction(flow, None) #flow dropped and no more connected to active link
        self.DEBUG_dropped_flows.append(flow) 
        self._ground_stations[[key for key, gs in self._ground_stations.items() if gs.lat == flow.destination[0] and gs.lon == flow.destination[1]][0]].DEBUG_get_dropped_flow(flow)

    #Update infos on neighbors
    def update_neighbors(self):
        #self._update_position() #update satellite position ###
        #self._update_gs_link() #update connection to Ground Station ###
        self._update_state() #update satellite state
        for dir, link in self._links.items(): #update for every link, dir
            if link.is_active():
                link.send_update(self.get_latitude(), self.get_longitude(), self.state, utils.get_coupled_link_direction(dir)) #params to update
                if constants.ROUTING_STRATEGY == Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB:
                    env.log_control_traffic_message(2)
                env.log_control_traffic_message(6)
    
    #Update satellite state
    def _update_state(self):
        #print("XXXXX    Updating state for Satellite", self.get_name(), "self._link.values():", self._links.values())
        #print("___ any link active?", any([link for link in self._links.values() if link.is_active()]))
        if any([link for link in self._links.values() if link.is_active()]): #check if exists an active link
            local_state = (constants.SATELLITE_LINK_CAPACITY - (sum([link.get_available_bandwidth() for link in self._links.values() if link.is_active()]) / len([link for link in self._links.values() if link.is_active()]))) / constants.SATELLITE_LINK_CAPACITY #medium available bandwidth/active links/satellite link capacity
            #print("Sum of available bandwidth on active links:", sum([link.get_available_bandwidth() for link in self._links.values() if link.is_active()]))
            #print("len of active links:", len([link for link in self._links.values() if link.is_active()]))
            #print("local state:", local_state)
            neighbor_state = sum([link.state for link in self._links.values() if link.is_active()]) / len([link for link in self._links.values() if link.is_active()]) #sum of neighbor's link state
            #print("neighbor state:", neighbor_state)
            self.state = local_state * (1 - constants.LOAD_BALANCING_WEIGHT_FACTOR) + neighbor_state * constants.LOAD_BALANCING_WEIGHT_FACTOR #real state of satellite as a mix of local state and neighbors' state
            #print("self.state:", self.state, "of SATELLITE", self.get_name())
        else:
            self.state = 0
        
        #Debug
        if constants.DEBUG:
            if self.state > 1:
                print(self.state, self.get_name())
                raise ValueError("STATE MAGGIORE DI 1")
            #if self.state > 0.1:
            #    print("Satellite State:", self.state, "sat:", self.get_name())
        
    #Update link with Ground Station
    def _update_gs_link(self):
        #print("UPDATE GS LINK method")
        gs_candidates = []
        for gs in self._ground_stations.values():
            distance_from_destination = distance.distance((self.get_latitude(), self.get_longitude()), (gs.lat, gs.lon)).km #calculate distance between 2 points using Geopy
            if distance_from_destination < constants.SATELLITE_COVERAGE_AREA_RADIUS:
                gs_candidates.append(gs) #if distance from GS's lat & lon is less then satellite's area radius appends GS to candidates
        if set(gs_candidates) != set(self._gs_link.get_attached_gs()): #if candidates GS are different from already connected GS the satellite requires an update of link with a NEW GS 
            leftovers = self._gs_link.detach_from_all() #satellite remove all GS links
            for gs in gs_candidates: #dopo aver rimosso tutti i gs link, per ogni gs attacco il link alle gs candidate
                self._gs_link.attach_to_gs(gs) #and reconnect to new candidates
            if leftovers:
                for flow in leftovers:
                    if constants.DEBUG:
                        print("[_update_gs_link] Leftover from gs_link on Satellite", self.get_name(), "at time", utils.get_current_time().utc_strftime(), "flow:", flow.id, [step.get_name() for step in flow.get_steps()])
                    flow.add_step(self) #open_flow-like behaviour without actually opening the flux
                    flow.alias_id = self.mapping_table.add(flow.alias_id)
                    flow.drop_steps_from(self)
                    self.drop_flow(flow, FlowState.LINK_CONGESTED) #otherwise drop flow
                    #self.open_flow(flow)

    #Update satellite position
    def _update_position(self):
        geocentric = self._earth_satellite.at(utils.get_current_time()) #calculate geocentric position of satellite (effective update!)
        lat, lon = wgs84.latlon_of(geocentric) #geographic coordinates conversion to standard WGS84
        self._lat = lat.degrees 
        self._lon = lon.degrees
        #GUESSING #Using these strategies requires position update
        if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_NO_LB,
                                          Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                          Strategy.POSITION_GUESSING_PROGRESSIVE_LB]:
            north_link = self._links.get(Direction.NORTH) #retrieve links
            south_link = self._links.get(Direction.SOUTH)
            east_link = self._links.get(Direction.EAST)
            west_link = self._links.get(Direction.WEST)
            #GUESSING of the position #calculate the guessing longitude delta for translations in degrees
            if east_link.is_active() or west_link.is_active():
                longitude_delta = (40075 / 2 / 6) / (40075 / 360) * math.cos(self._lat)
                if east_link.is_active(): #EAST
                    if self.get_longitude() + longitude_delta > 180:
                        east_link.lon = -180 + (self.get_longitude() + longitude_delta - 180)
                    else:
                        east_link.lon = self.get_longitude() + longitude_delta
                if west_link.is_active(): #WEST
                    if self.get_longitude() - longitude_delta < -180:
                        west_link.lon = 180 - (self.get_longitude() - longitude_delta + 180)
                    else:
                        west_link.lon = self.get_longitude() - longitude_delta
            #calculate latitude delta for translations in degrees
            if north_link.is_active() or south_link.is_active():
                latitude_delta = (40008 / 11) / (40008 / 2 / 180)
                if north_link.is_active(): #NORTH
                    if self.get_latitude() + latitude_delta > 90:
                        north_link.lat = 90 - (self.get_latitude() + latitude_delta - 90)
                    else:
                        north_link.lat = self.get_latitude() + latitude_delta
                if south_link.is_active(): #SOUTH
                    if self.get_latitude() - latitude_delta < -90:
                        south_link.lat = -90 - (self.get_latitude() - latitude_delta + 90)
                    else:
                        south_link.lat = self.get_latitude() - latitude_delta

    #Notifies unlinking to neighbor
    def notify_neighbor_unlink(self, dir: Direction):
        link = self._links.get(dir)
        if link.is_active():
            #if constants.DEBUG:
             #   print("^[UNLINK] Dropping link between", self.get_name(), "and", link.target.get_name())
            link.unlink(utils.get_coupled_link_direction(dir))
    
    #Sender of flows
    def send_flow(self, flow: Flow, link: Link, routing_decisions = None):
        if link.reserve_bandwidth(flow): #if the needed bandwidth is available return TRUE
            '''if constants.DEBUG:
                if isinstance(link, RadioLink):
                    print("Opened flow", flow.id, "to Radiolink on Satellite", self.get_name(), "with rate", flow.rate, "Gbps on link headed to", [gs.get_name() for gs in link.target]) #"at time", utils.get_current_time().utc_strftime())
                else:
                    print("Opened flow", flow.id, "to Laserlink on Satellite", self.get_name(), "with rate", flow.rate, "Gbps on link headed to", link.target.get_name()) # "at time", utils.get_current_time().utc_strftime())
            '''
            self.store_flow_direction(flow, link) #save direction
            if isinstance(link, RadioLink):
                flow.travelled_distance += utils.get_distance_between_satellite_and_gs(self, link.target[0]) #if link is a radiolink calculates the distance satellite and GS
            else:
                flow.travelled_distance += utils.get_distance_between_satellites(self, link.target) #otherwise calculates distance between satellites
            if routing_decisions != None:
                link.send_flow(flow, routing_decisions) #send centralized
            else:
                link.send_flow(flow) #then send flow
        else:
            self.drop_flow(flow, FlowState.LINK_CONGESTED) #otherwise drop it
    
    #reopen flow
    def _reopen_flow(self, flow: Flow, routing_decisions = None):#print(f"Self sat {self.get_name()} is operational?___{self.is_operational()}")
        if self.is_operational() == False:
            print("Satellite", self.get_name(), "is not operational")
            self._close_internal_flow(flow.alias_id) #if Satellite NOT operational, close and drop flow
            self.drop_flow(flow, FlowState.SATELLITE_NOT_OPERATIONAL)
        else:
            if routing_decisions == None: #Se ci sono già le decisions
                routing_decisions = self.route(flow) #triple(action, flow, link) could be more then one if there are splitted flows #otherwise if satellite is operational, calculates routing for the flow 
                #print("Routing decisions [_reopen_flow]", flow.id, "on Satellite", self.get_name(), ", Routing Decision:", routing_decisions) #print routing decisions
                self._close_internal_flow(flow.alias_id)
                if len(routing_decisions) > 1: #if more routing decisions, get and add input id 
                    for _, f, _ in routing_decisions[1:]:
                        #print("ALIAS 2", f.alias_id, "for flow", f)
                        f.alias_id = self.mapping_table.get_input_id(f.alias_id)
                        f.alias_id = self.mapping_table.add(f.alias_id)
                #print("     [MAPPING] Self mapping table DISTR _reopen_flow on", self.get_name(), "SAT :", self.mapping_table.table) #print mapping table for debug
                for action, f, link in routing_decisions:
                    if action == RoutingAction.FORWARD or action == RoutingAction.DELIVER:
                        self.send_flow(f, link) #send
                    elif action == RoutingAction.ERROR:
                        self.drop_flow(f, link) #drop
                    elif action == RoutingAction.REOPEN:
                        f.alias_id = self.mapping_table.get_input_id(f.alias_id)
                        f.drop_steps_from(self)
                        self.open_flow(f) #reopen
            else:
                #print("****Branch for centralized routing****")
                routing_centralized_decisions = []
                decision = (routing_decisions[0][0], flow, routing_decisions[0][2]) #take the first routing decision for centralized flows
                routing_centralized_decisions.append(decision)
                self._close_internal_flow(flow.alias_id)
                #print("Routing decision da usare nel satellite in _reopening_flow ", routing_centralized_decisions)
                #print("Routing decisions [_reopen_flow] centr", flow.id, "on Satellite", self.get_name(), ", Routing Decision:", routing_centralized_decisions) #print routing decisions
                
                #print("     [MAPPING] Self mapping table CENTR _reopen_flow on", self.get_name(), "SAT :", self.mapping_table.table) #print mapping table for debug
                for action, f, link in routing_centralized_decisions:
                    if action == RoutingAction.FORWARD or action == RoutingAction.DELIVER:
                        routing_decisions.pop(0)
                        #print("routing decision complete meno la prima per il nuovo satellite", routing_decisions)
                        self.send_flow(f, link, routing_decisions) #send centralized
                    elif action == RoutingAction.ERROR:
                        routing_decisions.pop(0)
                        self.drop_flow(f, link) #drop
                    elif action == RoutingAction.REOPEN:
                        f.alias_id = self.mapping_table.get_input_id(f.alias_id)
                        f.drop_steps_from(self)
                        routing_decisions.pop(0)
                        self.open_flow(f, routing_decisions) #reopen centralized


    def open_flow(self, flow: Flow, routing_decisions=None): #Manage the open of flows 
        #if constants.DEBUG:
         #   print("--- Opening flow on [sat]", flow.id, "alias_id", flow.alias_id, "on Satellite", self.get_name(), "with rate:", flow.rate, "Gbps") #"at time", utils.get_current_time().utc_strftime())
        flow.add_step(self) #flow is added to the self satellite #print("  Opening flow2", flow, "id", flow.id, "with alias_id", flow.alias_id, "on Satellite", self.get_name(), "with rate:", flow.rate, "Gbps")
        flow.alias_id = self.mapping_table.add(flow.alias_id)#update of the id, added to the mapping table
        #print(" <[MAPPING]> Self mapping table open_flow on", self.get_name(), "SAT :", self.mapping_table.table) #print mapping table for debug
        #print("°    flow.alias_id", flow.alias_id)
        if flow.ttl == 0:
            self.drop_flow(flow, FlowState.EXPIRED_TTL)
        else:
            if routing_decisions != None: #if there are some decisions pass them for forwarding
                self._reopen_flow(flow, routing_decisions)
            else:
                self._reopen_flow(flow) #print("  Opening flow4", flow, "id", flow.id, "with alias_id", flow.alias_id, "on Satellite", self.get_name(), "with rate:", flow.rate, "Gbps")

    #Manage routing decisions (START THE CORE OF ROUTING DECISIONS doing basic route then adapting to link bandwidth)
    def route(self, flow: Flow) -> list[(RoutingAction, Flow, Link)]:
        routing_decisions = self.basic_route(flow)
        routing_decisions = self.adapt_routing_decisions_to_available_link_bandwidth(flow, routing_decisions)
        return routing_decisions

    #Routing decisions for bandwidth
    def adapt_routing_decisions_to_available_link_bandwidth(self, flow: Flow, routing_decisions: list[tuple[RoutingAction, Link]]) -> list[tuple[RoutingAction, Flow, Link]]:
        #print("adapt_routing_decisions_to_available_link_bandwidth metodo")
        adapted_routing_decisions = []
        for action, link in routing_decisions:
            if action == RoutingAction.FORWARD or action == RoutingAction.DELIVER:
                available_bandwidth = link.get_available_bandwidth()
                if available_bandwidth == 0:
                    continue
                if available_bandwidth >= flow.rate:
                    adapted_routing_decisions.append((action, flow, link))
                    break
                else:
                    f, flow = flow.split(available_bandwidth)
                    adapted_routing_decisions.append((action, f, link))
            elif action == RoutingAction.ERROR:
                adapted_routing_decisions.append((action, flow, link))
                break
        else:
            adapted_routing_decisions.append((RoutingAction.ERROR, flow, FlowState.SATELLITE_CONGESTED))
            #print("flusso congestionato ADAPT")
        return adapted_routing_decisions

    #Route method
    def basic_route(self, flow: Flow, avoid: list[Link] = []) -> list[tuple[RoutingAction, Link]]: ##---- reserve_band? send_flow
        #Excludes node (next hop) from candidates to avoid Loops #definition of function get_nodes_to_be_excluded_from_next_hop_candidates to redefine it for every simulation, not execution of function
        def get_nodes_to_be_excluded_from_next_hop_candidates(flow) -> list: #get_nodes_to_be_excluded_from_next_hop_candidates PERMETTE DI VALUTARE QUALE SARA' IL PROSSIMO HOP
            if constants.LOOP_AVOIDANCE_CUTOFF == 0: #if 0 no need to avoid loops #if > 0 excludes a defined number of previously made passages by the flow
                return []
            else:
                steps = flow.get_steps() if len(flow.get_steps()) < constants.LOOP_AVOIDANCE_CUTOFF else flow.get_steps()[-constants.LOOP_AVOIDANCE_CUTOFF:] #take steps of flow if steps < CUTOFF value & if CUTOFF > 0 take only the last N steps (equal to CUTOFF) from the steps list of the current flow 
                if steps[-1] == self:
                    steps = steps[:-1] #cut steps list if the last step was the current satellite
                indices = [i+1 for i, x in enumerate(steps) if x == self] #indices in steps that corresponds to current node
                if len(steps) > 0:
                    indices.append(-1)
                return [steps[i] for i in indices] #list of excluded steps as NEXT HOP

        routing_output = list()
        #calculates distance from the target, if in the satellite's range, flow is delivered to GS destination
        distance_from_destination = distance.distance((self.get_latitude(), self.get_longitude()), flow.destination).km
        if distance_from_destination < constants.SATELLITE_COVERAGE_AREA_RADIUS:
            routing_output.append((RoutingAction.DELIVER, self._gs_link))

        #different strategies
        if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_NO_LB,
                                          Strategy.POSITION_SHARING_NO_LB]:
            nodes_to_be_excluded = get_nodes_to_be_excluded_from_next_hop_candidates(flow)

            candidates = list()
            for key, link in self._links.items():
                if link in avoid:
                    continue
                if link.is_active():
                    if link.target in nodes_to_be_excluded: #if target of the link is in "excluded nodes" set distance of link to infinite
                        dist = float("inf")
                    else:
                        dist = distance.distance((link.lat, link.lon), flow.destination).km #else calculates the real distance to destination
                    candidates.append({'distance': dist, 'dir': key}) #add candidate with distance and direction
            candidates.sort(key=lambda x: x['distance']) #sort candidates for distance, first = closest

            #if there's no candidates(no links are operational) satellite cannot be operative
            if not(candidates):
                routing_output.append((RoutingAction.ERROR, FlowState.SATELLITE_NOT_OPERATIONAL))

            #first candidate
            candidate = candidates[0]
            for r_o in routing_output: #check if there's an error, throws RuntimeError
                if r_o[0] == RoutingAction.ERROR:
                    raise RuntimeError("routing_output already contains an error action")
            #add Forward action to the Link in the specific direction
            routing_output.append((RoutingAction.FORWARD, self._links.get(candidate['dir'])))

        #other strategies for node exclusion 
        elif constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                            Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK]:
            nodes_to_be_excluded = get_nodes_to_be_excluded_from_next_hop_candidates(flow)

            candidates = list()
            for key, link in self._links.items():
                if link in avoid:
                    continue
                if link.is_active():
                    if link.target in nodes_to_be_excluded:
                        dist = float("inf")
                    else:
                        dist = distance.distance((link.lat, link.lon), flow.destination).km
                    candidates.append({'distance': dist, 'dir': key})
            candidates.sort(key=lambda x: x['distance'])

            if not(candidates):
                routing_output.append((RoutingAction.ERROR, FlowState.SATELLITE_NOT_OPERATIONAL))

            for candidate in candidates:
                for r_o in routing_output:
                    if r_o[0] == RoutingAction.ERROR:
                        raise RuntimeError("routing_output already contains an error action")
                routing_output.append((RoutingAction.FORWARD, self._links.get(candidate['dir'])))

        #other strategies for node exclusion
        elif constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                            Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                            Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB]:
            nodes_to_be_excluded = get_nodes_to_be_excluded_from_next_hop_candidates(flow)

            candidates = list()
            for key, link in self._links.items():
                if link in avoid:
                    continue
                if link.is_active():
                    if link.target in nodes_to_be_excluded:
                        dist = float("inf")
                    else:
                        dist = distance.distance((link.lat, link.lon), flow.destination).km
                    #Calculate Load Balance Score 
                    if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                                      Strategy.POSITION_SHARING_PROGRESSIVE_LB]:
                        load_balancing_score = link.get_available_bandwidth() / constants.SATELLITE_LINK_CAPACITY * 4 #scale based on 4 degrees evaluation
                    elif constants.ROUTING_STRATEGY == Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB:
                        load_balancing_score = (1 - link.state) * 4   ######GESTIONE LOAD BALANCING 
                    candidates.append({'distance': dist, 'dir': key, 'load_balancing_score': load_balancing_score})
            candidates.sort(key=lambda x: x['distance'])

            for i, candidate in enumerate(candidates):
                ordering_score = 4 - i if candidate['distance'] != float('inf') else 0  #order, closer candidate gets a higher score
                candidate['total_score'] = ordering_score + candidate['load_balancing_score'] #sum of ordering score + load balance score
            candidates.sort(key=lambda x: x['total_score'], reverse=True) 

            if not(candidates):
                routing_output.append((RoutingAction.ERROR, FlowState.SATELLITE_NOT_OPERATIONAL))

            for candidate in candidates:
                for r_o in routing_output:
                    if r_o[0] == RoutingAction.ERROR:
                        raise RuntimeError("routing_output already contains an error action")
                routing_output.append((RoutingAction.FORWARD, self._links.get(candidate['dir'])))

        elif constants.ROUTING_STRATEGY == Strategy.POSITION_AND_STATE_SHARING_TWO_HOPS:
            nodes_to_be_excluded = get_nodes_to_be_excluded_from_next_hop_candidates(flow)
            candidates = []

            for key, link in self._links.items():
                if link in avoid or not link.is_active():
                    continue

                if link.target in nodes_to_be_excluded:
                    dist = float('inf')
                else:
                    dist = distance.distance((link.lat, link.lon), flow.destination).km

                direct_lb_score = (1 - link.state) * 4
                neighbor_sat = link.target

                two_hop_links = [
                    l for l in neighbor_sat._links.values()
                    if l.target is not None and l.is_active() and l.target != self
                ]
                if two_hop_links:
                    active_links = [l for l in two_hop_links if (1 - l.state) > 0.1]
                    if active_links:
                        two_hop_avg_state = sum(1 - l.state for l in active_links) / len(active_links)
                        two_hop_lb_score = two_hop_avg_state * 4
                    else:
                        two_hop_lb_score = 0
                else:
                    two_hop_lb_score = 0

                candidates.append({
                    'distance': dist,
                    'dir': key,
                    'link': link,
                    'direct_lb_score': direct_lb_score,
                    'two_hop_lb_score': two_hop_lb_score
                })

            candidates.sort(key=lambda x: x['distance'])

            for i, candidate in enumerate(candidates):
                ordering_score = 4 - i if candidate['distance'] != float('inf') else 0
                alpha = 0.3  # o dinamico (in questo caso do maggiore enfasi ai valori di score dei 2 hop)
                lb_score = alpha * candidate['direct_lb_score'] + (1 - alpha) * candidate['two_hop_lb_score']
                delta = candidate['direct_lb_score'] - candidate['two_hop_lb_score']
                penalty = max(delta, 0)
                candidate['total_score'] = ordering_score + lb_score - penalty

            candidates.sort(key=lambda x: x['total_score'], reverse=True)

            if not candidates:
                routing_output.append((RoutingAction.ERROR, FlowState.SATELLITE_NOT_OPERATIONAL))
            for candidate in candidates:
                for r_o in routing_output:
                    if r_o[0] == RoutingAction.ERROR:
                        raise RuntimeError("routing_output already contains an error action")
                routing_output.append((RoutingAction.FORWARD, self._links.get(candidate['dir'])))

        elif constants.ROUTING_STRATEGY in [Strategy.POSITION_SHARING_COST_BALANCING]:
            nodes_to_be_excluded = get_nodes_to_be_excluded_from_next_hop_candidates(flow)

            candidates = list()
            for key, link in self._links.items():
                if link in avoid:
                    continue
                if link.is_active():
                    if link.target in nodes_to_be_excluded:
                        dist = float("inf")
                    else:
                        dist = distance.distance((link.lat, link.lon), flow.destination).km

                    # Calcolo del punteggio di bilanciamento del carico
                    if link.get_available_bandwidth() > 0:
                        load_balancing_score = link.get_available_bandwidth() / constants.SATELLITE_LINK_CAPACITY * 4
                    else:
                        load_balancing_score = 0
                    alpha_values = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]  

                    #candidates.append({'distance': dist, 'dir': key, 'costs': costs})
                    candidates.append({'distance': dist, 'dir': key, 'load_balancing_score': load_balancing_score})

            # Normalizzazione delle distanze
            finite_distances = [c['distance'] for c in candidates if c['distance'] != float('inf')]

            if finite_distances:  # Evita errori se ci sono candidati validi
                min_distance = min(finite_distances)
                max_distance = max(finite_distances)
                for candidate in candidates:
                    if candidate['distance'] != float('inf'):
                        if max_distance == min_distance:  # Evita divisione per zero
                            candidate['normalized_distance'] = 0  # Oppure un altro valore predefinito
                        else:
                            candidate['normalized_distance'] = (candidate['distance'] - min_distance) / (max_distance - min_distance)
                    else:
                        candidate['normalized_distance'] = 1  # Se infinito, assegna il valore massimo normalizzato
            else:
                # Se non ci sono distanze finite, assegna un valore predefinito a tutti i candidati
                for candidate in candidates:
                    candidate['normalized_distance'] = 1  # Oppure un altro valore predefinito

            # Calcolo del punteggio complessivo
            alpha_values = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
            for i, candidate in enumerate(candidates):
                ordering_score = 4 - i if candidate['distance'] != float('inf') else 0  # Vicinanza più alta = punteggio più alto
                for alpha in alpha_values:
                    candidate['costs_score'] = (alpha * (1 - candidate['normalized_distance'])) + \
                                            ((1 - alpha) * candidate['load_balancing_score'])

            candidates.sort(key=lambda x: x['costs_score'], reverse=True)

            if not(candidates):
                routing_output.append((RoutingAction.ERROR, FlowState.SATELLITE_NOT_OPERATIONAL))

            #print("     Print Candidates:", candidates)
            for candidate in candidates:
                for r_o in routing_output:
                    if r_o[0] == RoutingAction.ERROR:
                        raise RuntimeError("routing_output already contains an error action")
                routing_output.append((RoutingAction.FORWARD, self._links.get(candidate['dir'])))
            
        #print("  Debugging routing output:", routing_output) # DEBUG
        return routing_output

    def close_flow(self, flow: Flow): #close flows
        #print("[INFO] CLOSING flow Method with alias_id:", flow.alias_id , "on Satellite", self.get_name())
        local_ids = self.mapping_table.get_local_ids(flow.alias_id) #obtains local ids associated with flow id
        #print(f"&& local_ids are {local_ids}")
        for local_id in local_ids:
            self._close_internal_flow(local_id) #close      
            if self.mapping_table.contains_local_id(local_id):
                self.mapping_table.remove(local_id) #remove from mapping table

    #close internal flows
    def _close_internal_flow(self, alias_id: int):
        #print("[INFO] Closing INTERNAL flow with alias_id:", alias_id , "on Satellite", self.get_name()) #viene eseguito ogni volta che aggiorno la capacità del link
        flow_link_pairs = self.get_stored_flow_direction(alias_id) #obtain association between flow and link
        if flow_link_pairs:
            self.flows.pop(alias_id) #remove flow from active flows using id
            flow, link = flow_link_pairs
            
            if isinstance(link, RadioLink):
                flow.travelled_distance -= utils.get_distance_between_satellite_and_gs(self, link.target[0])#calculate distances
            elif isinstance(link, LaserLink):
                flow.travelled_distance -= utils.get_distance_between_satellites(self, link.target)
            #Link can be None when the flow is dropped on the current satellite.
            if link != None:
                #print(f"    [INFO] [SAT] Close_internal_flow id {flow.id} with alias id {flow.alias_id} on Satellite {self.get_name()}")
                link.close_flow(flow) #close
            else:
                #if constants.DEBUG:
                 #   print("Closed dropped flow", flow.id, "with alias id", flow.alias_id, "with rate", flow.rate, "Gbps on Satellite", self.get_name(), "at time", utils.get_current_time().utc_strftime())

                f = [f for f in self.DEBUG_dropped_flows if f.alias_id == flow.alias_id][0] #assume at least there is a flow and stores it in f
                self._ground_stations[[key for key, gs in self._ground_stations.items() if gs.lat == flow.destination[0] and gs.lon == flow.destination[1]][0]].DEBUG_close_dropped_flow(f) #check if there is association between destination and GS coordinates then drop the flow f
                del self.DEBUG_dropped_flows[[i for i, fl in enumerate(self.DEBUG_dropped_flows) if fl.alias_id == flow.alias_id][0]] #delete debug dropped flows if there is the same id

    #update the link informations with new params
    def update_link_info(self, lat, lon, state, dir: Direction):
        self._links.get(dir).update(lat, lon, state)

    #obtain as a list all the active links between satellites
    def get_active_links(satellites):
        active_links = []  # Lista delle connessioni attive tra i satelliti
        for sat in satellites:
            if not isinstance(sat, Sat):
                print(f"Attenzione: {sat} non è un oggetto Sat!")
            for link in sat._links.values():
                if link.is_active():
                    active_links.append((sat, link.target)) #append del parent del link e del suo target
        return active_links
    
    def extract_satellites_from_routing_decisions(self, routing_decisions: list[tuple]) -> list[str]:#extract satellite sequence starting from routing decisions
        satellites = []
        if not routing_decisions:
            return satellites  # Restituisci lista vuota se non ci sono decisioni
        # Aggiungi il `source` del primo link
        first_link = routing_decisions[0][2]  # Ottieni il primo link
        if hasattr(first_link, '_parent') and first_link._parent:
            satellites.append(first_link._parent.get_name())  # Aggiungi il nome del satellite di origine
        # Aggiungi i `target` di tutti i link
        for _, _, link in routing_decisions:
            if hasattr(link, 'target') and link.target:
                # Se il target è una lista, aggiungi tutti i nomi
                if isinstance(link.target, list):
                    for target in link.target:
                        if hasattr(target, 'get_name'):
                            satellites.append(target.get_name())
                # Se il target è un singolo oggetto
                elif hasattr(link.target, 'get_name'):
                    satellites.append(link.target.get_name())
        return satellites
