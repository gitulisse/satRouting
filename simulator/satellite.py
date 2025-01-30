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
from header_builder import HeaderBuilder as hb

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

    #Identifies active Satellites, return True if the list of links of a Satellite is NOT empty (!= 0), so the Satellite is considered active
    def is_operational(self) -> bool:
        return len([link for link in self._links.values() if link.is_active()]) != 0

    #Manages adding links to a Satellite
    def add_link(self, sat, dir: Direction):
        link = self._links.get(dir)
        if link.target == sat: #if link already exists, avoid duplicates and return
            return
        #debug log
        #if constants.DEBUG:
           # print("Adding link from Satellite", self.get_name(), "to Satellite", sat.get_name(), "at time", utils.get_current_time().utc_strftime())
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
        ####print(f"Attempting to remove link {dir} for satellite {self.get_name()} that's active? {link.is_active()}")######
        if not(link.is_active()):  # Verifica che il link esista ed è attivo
            return
        if notify_neighbor:
            self.notify_neighbor_unlink(dir)
        
        #if constants.DEBUG:
        print("Removing link from Satellite", self.get_name(), "to Satellite", self._links[dir].target.get_name(), "at time", utils.get_current_time().utc_strftime())
        print(f"Link {dir} removed for satellite {self.get_name()}")######
        leftovers = self._links[dir].idle() #stores remaining fluxes
        if leftovers and self.is_operational():
            for flux in leftovers:
                #if constants.DEBUG:
                #print("Leftover from link:", dir, "on Satellite", self.get_name(), "at time", utils.get_current_time().utc_strftime(), "flux:", flux.id, [step.get_name() for step in flux.get_steps()])
                flux.drop_steps_from(self)
                self.open_flux(flux)
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
    
    #Store tuple (flux, link)
    def store_flux_direction(self, flux: Flux, link: Link):
        if flux.alias_id not in self.fluxes.keys(): #check if flux id is NOT stored in dict fluxes (tuples of flux and link)
            self.fluxes[flux.alias_id] = (flux, link) #add tuple
        else:
            _, existing_link = self.fluxes[flux.alias_id]
            if existing_link is None:  # Flusso era "dropped"
                #print(f"Flux {flux.alias_id} is already dropped; no action taken.")
                return  # Non fare nulla se il link esistente è None
            else:  # Flusso già attivo, errore
                raise RuntimeError("Alias id already present in fluxes structure.", flux.alias_id)
        '''
        if constants.DEBUG:
            print("Stored new flux with alias id", flux.alias_id, "with rate", flux.rate, "headed to link", link if link != None else None, "on Satellite", self.get_name(), "at time", utils.get_current_time().utc_strftime())
        '''
            
    #Return tuple (flux, link) if the flux id is stored
    def get_stored_flux_direction(self, alias_id: int) -> list[(Flux, Link)]:
        if alias_id in self.fluxes.keys():
            return self.fluxes[alias_id]
        return []
    
    #Manage drop of fluxes
    def drop_flux(self, flux: Flux, reason: FluxState):
        if constants.DEBUG: #debugging messages
            msg = "Flux " + str(flux) + " id " + str(flux.id) + " with alias id " + str(flux.alias_id) + " with rate " + str(flux.rate) + " Mbps has been dropped by Satellite " + str(self.get_name()) + " at time " + utils.get_current_time().utc_strftime() + ". "
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
        #print(f"SONO PRESENTI self.fluxes in satellite {self.get_name()}: {self.fluxes}")
        flux.state = reason #update flux's state with reason for the drop
        self.store_flux_direction(flux, None) #flux dropped and no more connected to active link
        self.DEBUG_dropped_fluxes.append(flux) 
        ############print(f"DEBUG_dropped_fluxes in satellite: {self.DEBUG_dropped_fluxes}")
        self._ground_stations[[key for key, gs in self._ground_stations.items() if gs.lat == flux.destination[0] and gs.lon == flux.destination[1]][0]].DEBUG_get_dropped_flux(flux)
 
    #Update infos on neighbors
    def update_neighbors(self):
        #self._update_position() #update satellite position ###
        self._update_gs_link() #update connection to Ground Station ###
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
        '''
        #Debug
        if constants.DEBUG:
            if self.state > 1:
                print(self.state, self.get_name())
                raise ValueError("STATE MAGGIORE DI 1")
            if self.state > 0.1:
                print("State:", self.state, "sat:", self.get_name())
        '''
    #Update link with Ground Station
    def _update_gs_link(self):
        #print("UPDATE GS LINK")
        gs_candidates = []
        for gs in self._ground_stations.values():
            distance_from_destination = distance.distance((self.get_latitude(), self.get_longitude()), (gs.lat, gs.lon)).km #calculate distance between 2 points using Geopy
            if distance_from_destination < constants.SATELLITE_COVERAGE_AREA_RADIUS:
                gs_candidates.append(gs) #if distance from GS's lat & lon is less then satelllite's area radius appends GS to candidates
        
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
        geocentric = self._earth_satellite.at(utils.get_current_time()) #calculate geocentric position of satellite (effective update!)
        lat, lon = wgs84.latlon_of(geocentric) #geographic coordinates conversion to standard WGS84
        self._lat = lat.degrees 
        self._lon = lon.degrees

        #Using these strategies requires position update
        #GUESSING
        if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_NO_LB,
                                          Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                          Strategy.POSITION_GUESSING_PROGRESSIVE_LB]:
            north_link = self._links.get(Direction.NORTH) #retrieve links
            south_link = self._links.get(Direction.SOUTH)
            east_link = self._links.get(Direction.EAST)
            west_link = self._links.get(Direction.WEST)
            
            #GUESSING of the position
            #calculate the guessing longitude delta for translations in degrees
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
            '''
            if constants.DEBUG:
                print("Dropping link between", self.get_name(), "and", link.target.get_name())
            '''
            link.unlink(utils.get_coupled_link_direction(dir))
    
    #Sender of centralized fluxes
    def send_centralized_flux(self, flux: Flux, link: Link, routing_decisions: list):
        if link.reserve_centralized_bandwidth(flux): #sistemata: la bandwidth viene già riservata durante il calcolo del percorso, quindi NON va riservata nuovamente
            '''
            #Debug
            if constants.DEBUG:
                if isinstance(link, RadioLink): #if it's a radiolink (to the GS)
                    print("Opened flux", flux.id, "on Satellite", self.get_name(), "with rate", flux.rate, "Mbps on link headed to", [gs.get_name() for gs in link.target], "at time", utils.get_current_time().utc_strftime()) 
                else:
                    print("Opened flux", flux.id, "on Satellite", self.get_name(), "with rate", flux.rate, "Mbps on link headed to", link.target.get_name(), "at time", utils.get_current_time().utc_strftime())
            '''
            self.store_flux_direction(flux, link) #save direction
            if isinstance(link, RadioLink):
                flux.travelled_distance += utils.get_distance_between_satellite_and_gs(self, link.target[0]) #if link is a radiolink calculates the distance satellite and GS
            else:
                flux.travelled_distance += utils.get_distance_between_satellites(self, link.target) #otherwise calculates distance between satellites
            link.send_centralized_flux(flux, routing_decisions) #then send flux
        else:
            self.drop_flux(flux, FluxState.LINK_CONGESTED) #otherwise drop it
    
    #Sender of fluxes
    def send_flux(self, flux: Flux, link: Link):
        if link.reserve_bandwidth(flux): #if the needed bandwidth is available return TRUE
            '''
            #Debug
            if constants.DEBUG:
                if isinstance(link, RadioLink): #if it's a radiolink (to the GS)
                    print("Opened flux", flux.id, "on Satellite", self.get_name(), "with rate", flux.rate, "Mbps on link headed to", [gs.get_name() for gs in link.target], "at time", utils.get_current_time().utc_strftime()) 
                else:
                    print("Opened flux", flux.id, "on Satellite", self.get_name(), "with rate", flux.rate, "Mbps on link headed to", link.target.get_name(), "at time", utils.get_current_time().utc_strftime())
            '''
            self.store_flux_direction(flux, link) #save direction
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
        #print("  REopening flux", flux, "id", flux.id, "with alias_id", flux.alias_id, "on Satellite", self.get_name(), "with rate:", flux.rate, "Mbps", "at time", utils.get_current_time().utc_strftime())
        if self.is_operational() == False:
            self._close_internal_flux(flux.alias_id) #if Satellite NOT operational, close and drop flux
            self.drop_flux(flux, FluxState.SATELLITE_NOT_OPERATIONAL)
        else:
            #########se il satellite è operativo allora rieseguo il route dal satellite in poi
            routing_decisions = self.route(flux) #otherwise if satellite is operational, calculates routing for the flux (START THE ROUTE DECISION CORE)
            #if constants.DEBUG:
             #   print("Distributed decisions:", routing_decisions)
            self._close_internal_flux(flux.alias_id)
            #print("ALIAS 1", flux.alias_id, "for flux", flux) ####close the internal flux
            #print("         routing_decisions REOPEN FLUX", routing_decisions)
            if len(routing_decisions) > 1: #if more routing decisions, get and add input id 
                #print("-----decisions", routing_decisions, "selezionato ->>", routing_decisions[1:])
                for _, f, _ in routing_decisions[1:]:
                    print("FLUSSO UTILIZZATO", f, "id", f.id, "alias_id", f.alias_id)
                    #print("ALIAS 2", f.alias_id, "for flux", f)
                    #print("f", f)
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
 
    def _reopen_centralized_flux(self, flux: Flux, routing_decisions: list):
        #print("  REopening flux", flux, "id", flux.id, "with alias_id", flux.alias_id, "on Satellite", self.get_name(), "with rate:", flux.rate, "Mbps", "at time", utils.get_current_time().utc_strftime())
        if self.is_operational() == False:
            self._close_internal_flux(flux.alias_id) #if Satellite NOT operational, close and drop flux
            self.drop_flux(flux, FluxState.SATELLITE_NOT_OPERATIONAL)
        else:
            #print(" reopen centralized flux") #qui prendere il percorso già prefissato e inviare
            self._close_internal_flux(flux.alias_id) #close the internal flux
            #print("ALIAS 1", flux.alias_id, "for flux", flux)
            #print("         routing_decisions REOPEN FLUX", routing_decisions)
            #if len(routing_decisions) > 1: #if more routing decisions, get and add input id 
                #routing_centralized_decisions = routing_decisions[0] 
            routing_centralized_decisions = []
            routing_centralized_decisions.append(routing_decisions[0])
            '''
                print("  INTERNAL routing_decisions REOPEN FLUX", routing_decisions, "<<prima decisione>>", routing_centralized_decisions)
                action, f, link = routing_centralized_decisions #estraendo una tupla non sfrutto il ciclo for ma estraggo direttamente i valori
                print("FLUSSO UTILIZZATO", f, "id", f.id, "alias_id", f.alias_id)
                print("ALIAS 2", f.alias_id, "for flux", f)
                #print("f", f) 
                if self.mapping_table.contains_input_id(f.alias_id): 
                    f.alias_id = self.mapping_table.get_input_id(f.alias_id) #debugging printing looking for local_id
                f.alias_id = self.mapping_table.add(f.alias_id)
            '''
            #analyze parameters action, f, link of routing_decisions
            #for action, f, link in routing_decisions:
            for action, f, link in routing_centralized_decisions:
                if action == RoutingAction.FORWARD or action == RoutingAction.DELIVER:
                    #print(f"-DELIVER OR FORWARD flux- {f}")
                    routing_decisions.pop(0)
                    self.send_centralized_flux(f, link, routing_decisions) #send
                elif action == RoutingAction.ERROR:
                    print(f"-ERROR flux- {f}")
                    routing_decisions.pop(0)
                    self.drop_flux(f, link) #drop
                elif action == RoutingAction.REOPEN: #non necessario nel centralized
                    print(f"-REOPEN flux- {f}")
                    f.alias_id = self.mapping_table.get_input_id(f.alias_id)
                    f.drop_steps_from(self)
                    routing_decisions.pop(0)
                    self.open_centralized_flux(f, routing_decisions) #reopen centralized


    #Manage dispatch of the flux
    def open_centralized_flux(self, flux: Flux, routing_decisions: list):
        #sats = self.extract_satellites_from_routing_decisions(routing_decisions)
        #print("SATELLITES on routing decisions", sats)
        #print("  Opening flux1 on Sat", flux, "id", flux.id, "with alias_id", flux.alias_id, "on Satellite", self.get_name(), "with rate:", flux.rate, "Mbps") #, "at time", utils.get_current_time().utc_strftime())
        flux.add_step(self) #flux is added to the self satellite
        #print("  Opening flux2", flux, "id", flux.id, "with alias_id", flux.alias_id, "on Satellite", self.get_name(), "with rate:", flux.rate, "Mbps") #, "at time", utils.get_current_time().utc_strftime())
        #here the table starts as empty
        flux.alias_id = self.mapping_table.add(flux.alias_id) #update of the id, added to the mapping table
        print(f"***TABLE*** for sat {self.get_name()} : {self.mapping_table.table}")
        #print("  Opening flux3", flux, "id", flux.id, "with alias_id", flux.alias_id, "on Satellite", self.get_name(), "with rate:", flux.rate, "Mbps") #, "at time", utils.get_current_time().utc_strftime()) #qui cambia quindi prima di questo metodo tiro fuori il flux
        if flux.ttl == 0:
            self.drop_flux(flux, FluxState.EXPIRED_TTL)
        else:
            self._reopen_centralized_flux(flux, routing_decisions)
            print("  Opening flux4", flux, "id", flux.id, "with alias_id", flux.alias_id, "on Satellite", self.get_name(), "with rate:", flux.rate, "Mbps") #, "at time", utils.get_current_time().utc_strftime())
    
    def open_flux(self, flux: Flux): #Manage the open of fluxes #qui il flux è GIA CLONATO
        #if constants.DEBUG:
         #   print("  Opening flux1 on Sat", flux, "id", flux.id, "with alias_id", flux.alias_id, "on Satellite", self.get_name(), "with rate:", flux.rate, "Mbps", "at time", utils.get_current_time().utc_strftime())
        flux.add_step(self) #flux is added to the self satellite
        #print("  Opening flux2", flux, "id", flux.id, "with alias_id", flux.alias_id, "on Satellite", self.get_name(), "with rate:", flux.rate, "Mbps")
        #print("***TABLE****", self.mapping_table.table) print(f"***TABLE*** for sat {self.get_name()} : {self.mapping_table.table}")
        flux.alias_id = self.mapping_table.add(flux.alias_id)#update of the id, added to the mapping table
        #print("  Opening flux3", flux, "id", flux.id, "with alias_id", flux.alias_id, "on Satellite", self.get_name(), "with rate:", flux.rate, "Mbps")
        #print("Current Mapping Table:") #
        #for in_id, out_id in self.mapping_table.table: #
         #   print(f"Input ID: {in_id}, Output ID: {out_id}") #
        if flux.ttl == 0:
            self.drop_flux(flux, FluxState.EXPIRED_TTL)
        else:
            self._reopen_flux(flux)
            ##############print("  Opening flux4", flux, "id", flux.id, "with alias_id", flux.alias_id, "on Satellite", self.get_name(), "with rate:", flux.rate, "Mbps")

    #Manage routing decisions (START THE CORE OF ROUTING DECISIONS doing basic route then adapting to link bandwidth)
    def route(self, flux: Flux) -> list[(RoutingAction, Flux, Link)]:

        routing_decisions = self.basic_route(flux)
        #print("     ###Basic Route results", routing_decisions)
        routing_decisions = self.adapt_routing_decisions_to_available_link_bandwidth(flux, routing_decisions)
        #print("    #########Adapted Route results", routing_decisions)
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
                        load_balancing_score = (1 - link.state) * 4   ######GESTIONE LOAD BALANCING 
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

        elif constants.ROUTING_STRATEGY in [Strategy.POSITION_SHARING_WITH_COSTS_SELECTION]:
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
                routing_output.append((RoutingAction.ERROR, FluxState.SATELLITE_NOT_OPERATIONAL))

            print("     Candidates:", candidates)
            for candidate in candidates:
                for r_o in routing_output:
                    if r_o[0] == RoutingAction.ERROR:
                        raise RuntimeError("routing_output already contains an error action")
                routing_output.append((RoutingAction.FORWARD, self._links.get(candidate['dir'])))
        #print("  Debugging routing output:", routing_output) # DEBUG
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
            if constants.ROUTING_STRATEGY in [Strategy.BASELINE_DIJKSTRA,
                                    Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                    Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                    Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING,
                                    Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                    Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                    Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                    Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_COSTS_SELECTION]:
                for flux, _ in self.fluxes.values():
                    print("reroute all centralized")
                    basic_route_decisions.append((flux, [(action, link) for action, link in self.basic_centralized_route(flux.clone())]))
                    ##########################    #BASIC CENTRALIZED ROUTE da sistemare sopra
            else:
                for flux, _ in self.fluxes.values():
                    ###########print("reroute all distributed")
                    basic_route_decisions.append((flux, [(action, link) for action, link in self.basic_route(flux.clone())])) #add tuples (flux, [action, link]) based on basic_route on a copy of flux
                    ###########print("REROUTE ALL - BASIC ROUTE DECISIONS", basic_route_decisions)

            #print(f"Into VALUES of Flux {flux} BASIC ROUTE DECISIONS {basic_route_decisions}")
            simulation = self.simulate_adapt_routing_decisions_to_available_link_bandwidth(basic_route_decisions) #simulation on available bandwidth
            #print("SIMULATION", simulation)#################

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
                    ########################print("INVECE QUI 22")
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
        #print(f"local_ids are {local_ids}")
        for local_id in local_ids:
            self._close_internal_flux(local_id) #close      
            if self.mapping_table.contains_local_id(local_id):
                #############print("INVECE QUI")
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
                '''
                #debug
                if constants.DEBUG:
                    print("Closed dropped flux", flux.id, "with alias id", flux.alias_id, "with rate", flux.rate, "Mbps on Satellite", self.get_name(), "at time", utils.get_current_time().utc_strftime())
                '''
                f = [f for f in self.DEBUG_dropped_fluxes if f.alias_id == flux.alias_id][0] #assume at least there is a flux and stores it in f
                self._ground_stations[[key for key, gs in self._ground_stations.items() if gs.lat == flux.destination[0] and gs.lon == flux.destination[1]][0]].DEBUG_close_dropped_flux(f) #check if there is association between destination and GS coordinates then drop the flux f
                del self.DEBUG_dropped_fluxes[[i for i, fl in enumerate(self.DEBUG_dropped_fluxes) if fl.alias_id == flux.alias_id][0]] #delete debug dropped fluxes if there is the same id

    #update the link informations with new params
    def update_link_info(self, lat, lon, state, dir: Direction):
        self._links.get(dir).update(lat, lon, state)
        #self._reroute_all()
        #env.put(env.elapsed_time, self._reroute_all)

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
    
    #extract satellite sequence starting from routing decisions
    def extract_satellites_from_routing_decisions(self, routing_decisions: list[tuple]) -> list[str]:
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
