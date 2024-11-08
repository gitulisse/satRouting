from datetime import datetime, timezone
import constants
from copy import copy
from direction import Direction
import environment as env
from flux import Flux, FluxState
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

#Satellite's constructor
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
        self.fluxes: dict[int, (Flux, Link)] = {} #Dictionary that maps TUPLES of int about identifiers of Fluxes and Links
        self.DEBUG_dropped_fluxes: list[Flux] = [] #List of Dropped Fluxes
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

    #Identifies active Satellites, return True if the list of links of a Sattellite is NOT empty (!= 0), so the Satellite is considered active
    def is_operational(self) -> bool:
        return len([link for link in self._links.values() if link.is_active()]) != 0

    #Manages adding links to a Satellite
    def add_link(self, sat, dir: Direction):
        link = self._links.get(dir)
        if link.target == sat: #if link already exists, avoid duplicates and return
            return

        #debug log
        if constants.DEBUG:
            print("Adding link from Satellite", self.get_name(), "to Satellite", sat.get_name(), "at time", utils.get_current_time().utc_strftime())
        

        self.notify_neighbor_unlink(dir) #notify link removal to neighbor
        leftovers = link.point_to_sat(sat) #stores remaining fluxes about link pointing to satellite
        if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_NO_LB,
                                          Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                          Strategy.POSITION_GUESSING_PROGRESSIVE_LB]:
            self._update_position() #update

        if leftovers:
            for flux in leftovers:
                if constants.DEBUG:
                    print("Leftover from link:", dir, "on Satellite", self.get_name(), "at time", utils.get_current_time().utc_strftime(), "flux:", flux.id, [step.get_name() for step in flux.get_steps()])
                flux.drop_steps_from(self) #remove flux's steps that pass through this link of the satellite
                self.open_flux(flux)
        self._reroute_all() #rerouting
        #env.put(env.elapsed_time, self._reroute_all)
    
    #Remove a link and notify neighbor
    def remove_link(self, dir: Direction, notify_neighbor = True):
        link = self._links.get(dir) #obtain the link from dictionary _links
        if not(link.is_active()): #check if active
            return
        if notify_neighbor:
            self.notify_neighbor_unlink(dir)
        
        if constants.DEBUG:
            print("Removing link from Satellite", self.get_name(), "to Satellite", self._links[dir].target.get_name(), "at time", utils.get_current_time().utc_strftime())
        
        leftovers = self._links[dir].idle() #stores remaining fluxes
        if leftovers and self.is_operational():
            for flux in leftovers:
                if constants.DEBUG:
                    print("Leftover from link:", dir, "on Satellite", self.get_name(), "at time", utils.get_current_time().utc_strftime(), "flux:", flux.id, [step.get_name() for step in flux.get_steps()])
                flux.drop_steps_from(self)
                self.open_flux(flux)
        if not(self.is_operational()):
            if self.serving_gs:
                if constants.DEBUG:
                    print("Satellite", self.get_name(), "is serving Ground Station", self.serving_gs.get_name(), "but is no longer operational. Requesting reattachment...")
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
    
    #Store tuple (flux, link)
    def store_flux_direction(self, flux: Flux, link: Link):
        if flux.alias_id not in self.fluxes.keys(): #check if flux id is NOT stored in dict fluxes (tuples of flux and link)
            self.fluxes[flux.alias_id] = (flux, link) #add tuple
        else:
            raise RuntimeError("Alias id already present in fluxes structure.", flux.alias_id) 
        if constants.DEBUG:
            print("Stored new flux with alias id", flux.alias_id, "with rate", flux.rate, "headed to link", link if link != None else None, "on Satellite", self.get_name(), "at time", utils.get_current_time().utc_strftime())

    #Return tuple (flux, link) if the flux id is stored
    def get_stored_flux_direction(self, alias_id: int) -> list[(Flux, Link)]:
        if alias_id in self.fluxes.keys():
            return self.fluxes[alias_id]
        return []
    
    #Manage drop of fluxes
    def drop_flux(self, flux: Flux, reason: FluxState):
        if constants.DEBUG: #debugging messages
            msg = "Flux " + str(flux.id) + " with alias id " + str(flux.alias_id) + " with rate " + str(flux.rate) + " Mbps has been dropped by Satellite " + str(self.get_name()) + " at time " + utils.get_current_time().utc_strftime() + ". "
            if reason == FluxState.SATELLITE_CONGESTED:
                msg += "Satellite is congested."
            elif reason == FluxState.LINK_CONGESTED:
                msg += "Link is congested."
            elif reason == FluxState.EXPIRED_TTL:
                msg += "TTL is 0."
            elif reason == FluxState.SATELLITE_NOT_OPERATIONAL:
                msg += "Satellite is not operational."
            else:
                raise ValueError("The reason is not expected.", reason)
            print(msg)

        
        flux.state = reason #update flux's state with reason for the drop
        self.store_flux_direction(flux, None) #flux dropped and no more connected to active link
        self.DEBUG_dropped_fluxes.append(flux) 
        self._ground_stations[[key for key, gs in self._ground_stations.items() if gs.lat == flux.destination[0] and gs.lon == flux.destination[1]][0]].DEBUG_get_dropped_flux(flux)
    
    #Update infos on neighbors
    def update_neighbors(self):
        self._update_position() #update satellite position
        self._update_gs_link() #update connection to Ground Station
        self._update_state() #update satellite state
        for dir, link in self._links.items(): #update for every link, dir
            if link.is_active():
                link.send_update(self.get_latitude(), self.get_longitude(), self.state, utils.get_coupled_link_direction(dir)) #params to update
                if constants.ROUTING_STRATEGY == Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB:
                    env.log_control_traffic_message(2)
                env.log_control_traffic_message(6)
    
    #Update satellite state
    def _update_state(self):
        if any([link for link in self._links.values() if link.is_active()]): #check if exists an active link
            local_state = (constants.SATELLITE_LINK_CAPACITY - (sum([link.get_available_bandwidth() for link in self._links.values() if link.is_active()]) / len([link for link in self._links.values() if link.is_active()]))) / constants.SATELLITE_LINK_CAPACITY #medium available bandwidth/active links/satellite link capacity
            neighbor_state = sum([link.state for link in self._links.values() if link.is_active()]) / len([link for link in self._links.values() if link.is_active()]) #sum of neighbor's link state
            self.state = local_state * (1 - constants.LOAD_BALANCING_WEIGHT_FACTOR) + neighbor_state * constants.LOAD_BALANCING_WEIGHT_FACTOR #real state of satellite as a mix of local state and neighbors' state
        else:
            self.state = 0

        #Debug
        if constants.DEBUG:
            if self.state > 1:
                print(self.state, self.get_name())
                raise ValueError("STATE MAGGIORE DI 1")
            if self.state > 0.1:
                print("State:", self.state, "sat:", self.get_name())

    #Update link with Ground Station
    def _update_gs_link(self):
        gs_candidates = []
        for gs in self._ground_stations.values():
            distance_from_destination = distance.distance((self.get_latitude(), self.get_longitude()), (gs.lat, gs.lon)).km #calculate distance between 2 points using Geopy
            if distance_from_destination < constants.SATELLITE_COVERAGE_AREA_RADIUS:
                gs_candidates.append(gs) #if distance from lat & lon of GS is less then satelllite's area radius appends GS to candidates
        
        if set(gs_candidates) != set(self._gs_link.get_attached_gs()): #if candidates GS are different from already connected GS the satellite requires an update of link with a NEW GS 
            leftovers = self._gs_link.detach_from_all() #satellite remove all GS links
            for gs in gs_candidates:
                self._gs_link.attach_to_gs(gs) #and reconnect to new candidates
            if leftovers:
                for flux in leftovers:
                    #Debug
                    if constants.DEBUG:
                        print("Leftover from gs_link on Satellite", self.get_name(), "at time", utils.get_current_time().utc_strftime(), "flux:", flux.id, [step.get_name() for step in flux.get_steps()])
                    
                    flux.drop_steps_from(self) #remaining fluxes are dropped
                    self.open_flux(flux) #reopen of these fluxes for resend
            self._reroute_all() #rerouting for resend
            #env.put(env.elapsed_time, self._reroute_all)

    #Update satellite position
    def _update_position(self):
        geocentric = self._earth_satellite.at(utils.get_current_time()) #calculate geocentric position of satellite
        #print(utils.get_current_time()) ############PROVA Da CANCELLARE per check del current time
        lat, lon = wgs84.latlon_of(geocentric) #geographic coordinates conversion to standard WGS84
        self._lat = lat.degrees
        self._lon = lon.degrees

        #Using these strategies requires position update
        if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_NO_LB,
                                          Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                          Strategy.POSITION_GUESSING_PROGRESSIVE_LB]:
            north_link = self._links.get(Direction.NORTH) #effective update
            south_link = self._links.get(Direction.SOUTH)
            east_link = self._links.get(Direction.EAST)
            west_link = self._links.get(Direction.WEST)
            
            #calculate longitude delta for translations in degrees
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
            if constants.DEBUG:
                print("Dropping link between", self.get_name(), "and", link.target.get_name())
            link.unlink(utils.get_coupled_link_direction(dir))

    #Sender of fluxes
    def send_flux(self, flux: Flux, link: Link):
        if link.reserve_bandwidth(flux): #if the needed bandwidth is available return TRUE

            #Debug
            if constants.DEBUG:
                if isinstance(link, RadioLink): #if it's a radiolink (to the GS)
                    print("Opened flux", flux.id, "on Satellite", self.get_name(), "with rate", flux.rate, "Mbps on link headed to", [gs.get_name() for gs in link.target], "at time", utils.get_current_time().utc_strftime()) 
                else:
                    print("Opened flux", flux.id, "on Satellite", self.get_name(), "with rate", flux.rate, "Mbps on link headed to", link.target.get_name(), "at time", utils.get_current_time().utc_strftime())
            self.store_flux_direction(flux, link)

            if isinstance(link, RadioLink):
                flux.travelled_distance += utils.get_distance_between_satellite_and_gs(self, link.target[0]) #if link is a radiolink calculates the distance satellite and GS
            else:
                flux.travelled_distance += utils.get_distance_between_satellites(self, link.target) #otherwise calculates distance between satellites
            link.send_flux(flux) #then send flux
        else:
            self.drop_flux(flux, FluxState.LINK_CONGESTED) #otherwise drop it
    
    #IMPORTANTE
    #reopen flux
    def _reopen_flux(self, flux: Flux):
        if self.is_operational() == False:  
            self._close_internal_flux(flux.alias_id) #if Satellite NOT operational, close and drop flux
            self.drop_flux(flux, FluxState.SATELLITE_NOT_OPERATIONAL)
        else:
            #########se il satellite è operativo allora rieseguo il route dal satellite in poi
            routing_decisions = self.route(flux) #otherwise if satellite is operational, calculates routing for the flux (START THE ROUTE DECISION CORE)
            self._close_internal_flux(flux.alias_id) #close the internal flux
            if len(routing_decisions) > 1: #if more routing decisions, get and add input id 
                for _, f, _ in routing_decisions[1:]:
                    f.alias_id = self.mapping_table.get_input_id(f.alias_id)
                    f.alias_id = self.mapping_table.add(f.alias_id)
            #analyze parameters action, f, link of routing_decisions
            for action, f, link in routing_decisions: 
                if action == RoutingAction.FORWARD or action == RoutingAction.DELIVER:
                    self.send_flux(f, link) #send
                elif action == RoutingAction.ERROR:
                    self.drop_flux(f, link) #drop
                elif action == RoutingAction.REOPEN:
                    f.alias_id = self.mapping_table.get_input_id(f.alias_id)
                    f.drop_steps_from(self) 
                    self.open_flux(f) #reopen

    #Manage the open of fluxes
    def open_flux(self, flux: Flux):
        #Debug
        if constants.DEBUG:
            print("Opening flux", flux.id, "on Satellite", self.get_name(), "with rate:", flux.rate, "Mbps", "at time", utils.get_current_time().utc_strftime())
        flux.add_step(self) #flux is added to the self satellite
        flux.alias_id = self.mapping_table.add(flux.alias_id) #update of the id, added to the mapping table
        if flux.ttl == 0:
            self.drop_flux(flux, FluxState.EXPIRED_TTL)
        else:
            self._reopen_flux(flux)
    
    #Manage routing decisions (START THE CORE OF ROUTING DECISIONS doing basic route then adapting to link bandwidth)
    def route(self, flux: Flux) -> list[(RoutingAction, Flux, Link)]:

        #qui potrei fare un if(se si tratta di un una GS faccio eseguire il metodo self.centrilized route della GS, altrimenti faccio usare i metodi basic_route del satellite)
        routing_decisions = self.basic_route(flux)
        routing_decisions = self.adapt_routing_decisions_to_available_link_bandwidth(flux, routing_decisions)
        return routing_decisions

    #Simulate routing decisions for bandwidth
    def simulate_adapt_routing_decisions_to_available_link_bandwidth(self, routing_decisions: list[(Flux, list[tuple[RoutingAction, Link]])]) -> dict[int, list[tuple[RoutingAction, Flux, Link]]]:
        link_availability: dict[Link, float] = {} #create dictionary that associates links(laserlinks & radiolinks) to their max capacity 
        for link in self._links.values():
            link_availability[link] = constants.SATELLITE_LINK_CAPACITY
        link_availability[self._gs_link] = constants.GROUND_STATION_LINK_CAPACITY

        adapted_routing_decisions: dict[int, list] = {} 
        for flux, routing_decision in routing_decisions:
            adapted_routing_decision = []
            for action, link in routing_decision:
                if action == RoutingAction.FORWARD or action == RoutingAction.DELIVER: #if FORWARD or DELIVER for available bandwidth send flux or split it
                    available_bandwidth = link_availability[link] 
                    if available_bandwidth == 0:
                        continue #if 0 skip decision
                    if available_bandwidth >= flux.rate: #if there is more bandwidth of flux rate
                        adapted_routing_decision.append((action, flux, link))
                        break
                    else:
                        f, flux = flux.split(available_bandwidth)
                        adapted_routing_decision.append((action, f, link))
                elif action == RoutingAction.ERROR: #if ERROR
                    adapted_routing_decision.append((action, flux, link))
                    break
            else:
                adapted_routing_decision.append((RoutingAction.ERROR, flux, FluxState.SATELLITE_CONGESTED)) #if there is not a possible/viable decision, ERROR satellite congested 
            adapted_routing_decisions[flux.alias_id] = adapted_routing_decision
            if adapted_routing_decision[0][0] != RoutingAction.ERROR: #if decision is NOT an ERROR
                link_availability[adapted_routing_decision[0][2]] -= adapted_routing_decision[0][1].rate #update link availability (minus used one by the flux)
        return adapted_routing_decisions #dictionary of decisions

    #Routing decisions for bandwidth
    def adapt_routing_decisions_to_available_link_bandwidth(self, flux: Flux, routing_decisions: list[tuple[RoutingAction, Link]]) -> list[tuple[RoutingAction, Flux, Link]]:
        adapted_routing_decisions = []
        for action, link in routing_decisions:
            if action == RoutingAction.FORWARD or action == RoutingAction.DELIVER:
                available_bandwidth = link.get_available_bandwidth()
                if available_bandwidth == 0:
                    continue
                if available_bandwidth >= flux.rate:
                    adapted_routing_decisions.append((action, flux, link))
                    break
                else:
                    f, flux = flux.split(available_bandwidth)
                    adapted_routing_decisions.append((action, f, link))
                    #adapted_routing_decisions.append((RoutingAction.REOPEN, flux, None))
                    #break
            elif action == RoutingAction.ERROR:
                adapted_routing_decisions.append((action, flux, link))
                break
        else:
            adapted_routing_decisions.append((RoutingAction.ERROR, flux, FluxState.SATELLITE_CONGESTED))
        return adapted_routing_decisions

    #Route method
    def basic_route(self, flux: Flux, avoid: list[Link] = []) -> list[tuple[RoutingAction, Link]]:
        
        #definition of function get_nodes_to_be_excluded_from_next_hop_candidates to redefine it for every simulation, not execution of function
        #Excludes node (next hop) from candidates to avoid Loops
        def get_nodes_to_be_excluded_from_next_hop_candidates(flux) -> list: #get_nodes_to_be_excluded_from_next_hop_candidates PERMETTE DI VALUTARE QUALE SARA' IL PROSSIMO HOP
            if constants.LOOP_AVOIDANCE_CUTOFF == 0: #if 0 no need to avoid loops #if > 0 excludes a defined number of previously made passages by the flux
                return []
            else:
                #take steps of flux if steps < CUTOFF value & if CUTOFF > 0 take only the last N steps (equal to CUTOFF) from the steps list of the current flux 
                steps = flux.get_steps() if len(flux.get_steps()) < constants.LOOP_AVOIDANCE_CUTOFF else flux.get_steps()[-constants.LOOP_AVOIDANCE_CUTOFF:] 
                if steps[-1] == self: 
                    steps = steps[:-1] #cut steps list if the last step was the current satellite
                indices = [i+1 for i, x in enumerate(steps) if x == self] #indices in steps that corresponds to current node
                if len(steps) > 0:
                    indices.append(-1)
                return [steps[i] for i in indices] #list of excluded steps as NEXT HOP
        
        routing_output = list()

        #calculates distance from the target, if in the satellite's range, flux is delivered to GS destination
        distance_from_destination = distance.distance((self.get_latitude(), self.get_longitude()), flux.destination).km
        if distance_from_destination < constants.SATELLITE_COVERAGE_AREA_RADIUS:
            routing_output.append((RoutingAction.DELIVER, self._gs_link))


        #different strategies
        if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_NO_LB,
                                          Strategy.POSITION_SHARING_NO_LB]:
            nodes_to_be_excluded = get_nodes_to_be_excluded_from_next_hop_candidates(flux)

            candidates = list()
            for key, link in self._links.items():
                if link in avoid:
                    continue
                if link.is_active():
                    if link.target in nodes_to_be_excluded: #if target of the link is in "excluded nodes" set distance of link to infinite
                        dist = float("inf")
                    else:
                        dist = distance.distance((link.lat, link.lon), flux.destination).km #else calculates the real distance to destination
                        #if dist > distance.distance((self.get_latitude(), self.get_longitude()), flux.destination).km:
                        #    dist = float('inf')
                    candidates.append({'distance': dist, 'dir': key}) #add candidate with distance and direction
            candidates.sort(key=lambda x: x['distance']) #sort candidates for distance, first = closest

            #if there's no candidates(no links are operational) satellite cannot be operative
            if not(candidates):
                routing_output.append((RoutingAction.ERROR, FluxState.SATELLITE_NOT_OPERATIONAL))

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
            nodes_to_be_excluded = get_nodes_to_be_excluded_from_next_hop_candidates(flux)

            candidates = list()
            for key, link in self._links.items():
                if link in avoid:
                    continue
                if link.is_active():
                    if link.target in nodes_to_be_excluded:
                        dist = float("inf")
                    else:
                        dist = distance.distance((link.lat, link.lon), flux.destination).km
                        #if dist > distance.distance((self.get_latitude(), self.get_longitude()), flux.destination).km:
                        #    dist = float('inf')
                    candidates.append({'distance': dist, 'dir': key})
            candidates.sort(key=lambda x: x['distance'])

            if not(candidates):
                routing_output.append((RoutingAction.ERROR, FluxState.SATELLITE_NOT_OPERATIONAL))

            for candidate in candidates:
                for r_o in routing_output:
                    if r_o[0] == RoutingAction.ERROR:
                        raise RuntimeError("routing_output already contains an error action")
                routing_output.append((RoutingAction.FORWARD, self._links.get(candidate['dir'])))

        #other strategies for node exclusion
        elif constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                            Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                            Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB]:
            nodes_to_be_excluded = get_nodes_to_be_excluded_from_next_hop_candidates(flux) 

            candidates = list()
            for key, link in self._links.items():
                if link in avoid:
                    continue
                if link.is_active():
                    if link.target in nodes_to_be_excluded:
                        dist = float("inf")
                    else:
                        dist = distance.distance((link.lat, link.lon), flux.destination).km
                        #if dist > distance.distance((self.get_latitude(), self.get_longitude()), flux.destination).km:
                        #    dist = float('inf')

                    #Calculate Load Balance Score 
                    if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                                      Strategy.POSITION_SHARING_PROGRESSIVE_LB]:
                        load_balancing_score = link.get_available_bandwidth() / constants.SATELLITE_LINK_CAPACITY * 4 #scale based on 4 degrees evaluation
                    elif constants.ROUTING_STRATEGY == Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB:
                        load_balancing_score = (1 - link.state) * 4

                    candidates.append({'distance': dist, 'dir': key, 'load_balancing_score': load_balancing_score})
            candidates.sort(key=lambda x: x['distance'])

            for i, candidate in enumerate(candidates):
                ordering_score = 4 - i if candidate['distance'] != float('inf') else 0  #order, closer candidate gets a higher score
                candidate['total_score'] = ordering_score + candidate['load_balancing_score'] #sum of ordering score + load balance score
            candidates.sort(key=lambda x: x['total_score'], reverse=True) 

            if not(candidates):
                routing_output.append((RoutingAction.ERROR, FluxState.SATELLITE_NOT_OPERATIONAL)) 

            for candidate in candidates:
                for r_o in routing_output:
                    if r_o[0] == RoutingAction.ERROR:
                        raise RuntimeError("routing_output already contains an error action")
                routing_output.append((RoutingAction.FORWARD, self._links.get(candidate['dir'])))
        '''
        #new strategy
        elif constants.ROUTING_STRATEGY == Strategy.BASELINE_DIJKSTRA:
            ground_stations: dict = kwargs['ground_stations']
            satellites: dict = kwargs['satellites'] #extract the dictionary of satellites
            print("Started DIJKSTRA")
            for source in ground_stations.values(): #start from every source 
                for destination in ground_stations.values(): #and all related destinations
                    if source == destination: continue
                    dijkstra_shortest_paths = self._get_dijkstra_shortest_paths(satellites, source, destination) #obtain shortest paths
                    self.results[source.get_name() + ' - ' + destination.get_name()]['DIJKSTRA']['successful'].append(len(dijkstra_shortest_paths[0])) #first shortest path
                    #append under the key 'distance' the minimun path distance from all dijkstra_shortest_paths for each source-destination couple
                    self.results[source.get_name() + ' - ' + destination.get_name()]['DIJKSTRA']['distance'].append(min([self._get_path_distance(dijkstra_shortest_path, source, destination, satellites) for dijkstra_shortest_path in dijkstra_shortest_paths]))

        #new strategy
        elif constants.ROUTING_STRATEGY == Strategy.NO_SMOOTHING_ON_BUFFER_SIZE_SOURCE_ROUTING:
            print("Started NO SMOOTHING ON BUFFER")
        
        for element in routing_output[:1]:
          print("CIAO COME VA", element ) #print element for each single line
        '''

        #print(routing_output) #AGGIUNTO PER DEBUGGARE

        return routing_output
    
    #Rerouting all
    def _reroute_all(self):
        if self._is_rerouting: #if satellite already rerouting, avoid double rerouting
            return
        self._is_rerouting = True #otherwise set attribute to True

        if self.fluxes.keys(): #if there are active fluxes
            #Debug
            if constants.DEBUG:
                print("Rerouting traffic from satellite", self.get_name())


            fluxes_copy = [] #to keep fluxes
            pointer = 0
            basic_route_decisions = []
            for flux, _ in self.fluxes.values():
                basic_route_decisions.append((flux, [(action, link) for action, link in self.basic_route(flux.clone())])) #add tuples (flux, [action, link]) based on basic_route on a copy of flux
            simulation = self.simulate_adapt_routing_decisions_to_available_link_bandwidth(basic_route_decisions) #simulation on available bandwidth
            
            while pointer < len(self.fluxes.values()): #until there's a flux that is managed, at least one
                flux, link = list(self.fluxes.values())[pointer] #extract flux & link, accessing through a pointer as index
                flux_simulation = simulation.get(flux.alias_id) #get ids from simulation
                
                #check if flux_simulation exists & from first flux take third element([0][2]) must be different from current link
                #and check if flux_simulation[0][2] not instance of FluxState and link exists
                if flux_simulation and flux_simulation[0][2] != link and not(isinstance(flux_simulation[0][2], FluxState) and link == None): 
                    #debug
                    if constants.DEBUG:
                        print("Flux", flux.id, "with alias id", flux.alias_id, "is being rerouted from link", link, "to link", flux_simulation[0][2], "on Satellite", self.get_name(), "at time:", utils.get_current_time().utc_strftime())
                    
                    fluxes_copy.append(flux.clone()) #add copy of the flux
                    input_id = self.mapping_table.remove(flux.alias_id) #assign the id value to input_id and remove id of current flux from table
                    self._close_internal_flux(flux.alias_id) #close internal flux
                    fluxes_copy[-1].alias_id = input_id #give that id stored to the cloned flux
                else:
                    pointer += 1
            for flux in fluxes_copy:
                flux.drop_steps_from(self)
                self.open_flux(flux)
        self._is_rerouting = False

    #check if there is a difference between routing_decisions list and stored decisions
    def check_for_routing_decisions_differences(self, routing_decisions: list[(RoutingAction, Flux, Link)]) -> bool:
        for action, flux, link in routing_decisions:
            if action == RoutingAction.FORWARD or action == RoutingAction.DELIVER or action == RoutingAction.ERROR:
                stored_flux, stored_link = self.get_stored_flux_direction(flux.alias_id)
                if stored_flux.rate == flux.rate and stored_link == link:
                    break
                else:
                    return True
        return False

    #close fluxes
    def close_flux(self, flux: Flux):
        local_ids = self.mapping_table.get_local_ids(flux.alias_id) #obtains local ids associated with flux id

        for local_id in local_ids:
            self._close_internal_flux(local_id) #close      
            if self.mapping_table.contains_local_id(local_id):
                self.mapping_table.remove(local_id) #remove from mapping table
        
        #self._reroute_all()
        #env.put(env.elapsed_time, self._reroute_all)

    #close internal fluxes
    def _close_internal_flux(self, alias_id: int):
        flux_link_pairs = self.get_stored_flux_direction(alias_id) #obtain association between flux and link
        if flux_link_pairs:
            self.fluxes.pop(alias_id) #remove flux from active fluxes using id
            flux, link = flux_link_pairs
            #calculate distances
            if isinstance(link, RadioLink):
                flux.travelled_distance -= utils.get_distance_between_satellite_and_gs(self, link.target[0])
            elif isinstance(link, LaserLink):
                flux.travelled_distance -= utils.get_distance_between_satellites(self, link.target)
            #Link can be None when the flux is dropped on the current satellite.
            if link != None:
                link.close_flux(flux) #close
            else:
                #debug
                if constants.DEBUG:
                    print("Closed dropped flux", flux.id, "with alias id", flux.alias_id, "with rate", flux.rate, "Mbps on Satellite", self.get_name(), "at time", utils.get_current_time().utc_strftime())
                f = [f for f in self.DEBUG_dropped_fluxes if f.alias_id == flux.alias_id][0] #assume at least there is a flux and stores it in f
                self._ground_stations[[key for key, gs in self._ground_stations.items() if gs.lat == flux.destination[0] and gs.lon == flux.destination[1]][0]].DEBUG_close_dropped_flux(f) #check if there is association between destination and GS coordinates then drop the flux f
                del self.DEBUG_dropped_fluxes[[i for i, fl in enumerate(self.DEBUG_dropped_fluxes) if fl.alias_id == flux.alias_id][0]] #delete debug dropped fluxes if there is the same id

    #update the link informations with new params
    def update_link_info(self, lat, lon, state, dir: Direction):
        self._links.get(dir).update(lat, lon, state)
        #self._reroute_all()
        #env.put(env.elapsed_time, self._reroute_all)
