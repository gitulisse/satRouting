import constants
from direction import Direction
from flux import Flux
from ground_station import GroundStation
import utils
from strategy import Strategy

class Link:
    def __init__(self, parent_sat, capacity):
        self._parent = parent_sat
        self.target = None
        self.fluxes: dict[int, Flux] = {}
        self.capacity = capacity #Mbps

    #set attribute target
    def _set_target(self, target):
        self.target = target

    #check if Link is active (if it has a target)
    def is_active(self) -> bool:
        return self.target != None
    
    #calculate remaining available bandwidth
    def get_available_bandwidth(self) -> float:
        return self.capacity - sum([flux.rate for flux in self.fluxes.values()])
    
    #manage sending flux on link in centralized route
    def send_centralized_flux(self, flux: Flux, routing_decisions):
        if flux.alias_id not in self.fluxes.keys():  # Check if alias_id is reserved
            raise RuntimeError("Resources need to be reserved before sending flux " + str(flux.id) + " with alias id " + str(flux.alias_id))
        if isinstance(self.target, list): # Handle the case where target is a list
            #print("target is a list", self.target)
            for target in self.target:
                #print("target is", target.get_name())
                target.open_flux(flux.clone())
        else:
            self.target.open_centralized_flux(flux.clone(), routing_decisions) # Standard case: single target

    #send fluxes 
    def send_flux(self, flux: Flux):
        if flux.alias_id not in self.fluxes.keys(): #if alias_id isn't in fluxes keys raise error
            raise RuntimeError("Resources needs to be reserved before sending flux " + str(flux.id) + " with alias id " + str(flux.alias_id))
        self.target.open_flux(flux.clone()) #cloned flux sent to target

    #close fluxes
    def close_flux(self, flux: Flux):
        self.fluxes.pop(flux.alias_id) #remove flux id
        '''
        if constants.DEBUG:
            print("Closed flux", flux.id, "with alias id", flux.alias_id, "on Satellite", self._parent.get_name(), "headed to", self.target.get_name(), "with rate", flux.rate, "Mbps at time", utils.get_current_time().utc_strftime())
        '''
        self.target.close_flux(flux.clone()) #cloned flux sent to target will be closed by the target

    def reserve_centralized_bandwidth(self, flux: Flux) -> bool:
        self.fluxes[flux.alias_id] = flux #store flux in fluxes using alias_id as key
        '''
        #debug
        if constants.DEBUG:
            print("Reserved", flux.rate, "Mb for flux", flux.id, "with alias id", flux.alias_id, "at time", utils.get_current_time().utc_strftime())
        '''
        return True

    #manage reservation of bandwidth for a specified Flux
    def reserve_bandwidth(self, flux: Flux) -> bool:
        if self.get_available_bandwidth() >= flux.rate: 
            self.fluxes[flux.alias_id] = flux #store flux in fluxes using alias_id as key
            '''
            #debug
            if constants.DEBUG:
                print("Reserved", flux.rate, "Mb for flux", flux.id, "with alias id", flux.alias_id, "at time", utils.get_current_time().utc_strftime())
            '''
            return True
        else:
            '''
            #debug
            if constants.DEBUG:
                print("Failed to reserve", flux.rate, "Mb for flux", flux.id, "with alias id", flux.alias_id, "at time", utils.get_current_time().utc_strftime())
            '''
            return False

#Laserlink between satellites
class LaserLink(Link):
    def __init__(self, parent_sat):
        super().__init__(parent_sat, constants.SATELLITE_LINK_CAPACITY)
        self.lat = None
        self.lon = None
        self.state = None

    #maintain trace of the leftover fluxes & redirect the LaserLink
    def point_to_sat(self, sat) -> list[Flux]:
        leftovers = [] #residual fluxes
        #print(f"Fluxes: {self.fluxes}")
        while len(self.fluxes.values()) > 0: #if there are fluxes
            print("Fluxes in point_to_sat", self.fluxes)##########
            flux = list(self.fluxes.values())[0] #take first value of fluxes
            print(f"first flux is.. {flux} id {flux.id} alias_id {flux.alias_id}")##########
            if constants.ROUTING_STRATEGY in [Strategy.BASELINE_DIJKSTRA, 
                                  Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                  Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                  Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING,
                                  Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                  Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                  Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                  Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_COSTS_SELECTION]:
                leftovers.append(flux.clone())
                print(f"parent sat {self._parent.get_name()} CENTRALIZED leftovers list: {leftovers}")
                print(f"mapping table of the parent sat {self._parent.mapping_table.table}")
                input_id = self._parent.mapping_table.remove(flux.alias_id) #remove flux id from parent mapping table & save it as input_id
                print(f"input:id: {input_id}")
                self._parent._close_internal_flux(flux.alias_id) #close the flux internal to parent satellite
                leftovers[-1].alias_id = input_id #set the input of the last inserted flux in leftovers
            else:
                leftovers.append(flux.clone()) #add this flux to leftovers
                print(f"DISTRIBUTED leftovers list: {leftovers}")
                input_id = self._parent.mapping_table.remove(flux.alias_id) #remove flux id from parent mapping table & save it as input_id
                print(f"input:id: {input_id}")
                self._parent._close_internal_flux(flux.alias_id) #close the flux internal to parent satellite
                leftovers[-1].alias_id = input_id #set the input of the last inserted flux in leftovers
            
        self.lat = sat.get_latitude() #lat
        self.lon = sat.get_longitude() #lon
        self.state = 0.0 #state
        self._set_target(sat) #set new target satellite
        return leftovers 
    
    #put link in idle state
    def idle(self) -> list[Flux]:
        print(f"Link {self._parent.get_name()} -> {self.target.get_name()} going idle with fluxes: {self.fluxes}")##########
        leftovers = []
        while len(self.fluxes.values()) > 0:
            flux = list(self.fluxes.values())[0]
            if constants.ROUTING_STRATEGY in [Strategy.BASELINE_DIJKSTRA,
                                    Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                    Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                    Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING,
                                    Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                    Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                    Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                    Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_COSTS_SELECTION]:
                print(f"IDLE Alias id {flux.alias_id} on parent Mapping Table {self._parent.mapping_table.table}")

                if flux.alias_id not in self._parent.mapping_table.table:
                    print(f"Skipping invalid alias_id -centralized-: {flux.alias_id}")
                    return
                
                leftovers.append(flux.clone())
                input_id = self._parent.mapping_table.remove(flux.alias_id)
                self._parent._close_internal_flux(flux.alias_id)
                leftovers[-1].alias_id = input_id

            else:

                if flux.alias_id not in self._parent.mapping_table.table:
                    print(f"Skipping invalid alias_id -distributed-: {flux.alias_id}")
                    return
                
                leftovers.append(flux.clone())
                input_id = self._parent.mapping_table.remove(flux.alias_id)
                self._parent._close_internal_flux(flux.alias_id)
                leftovers[-1].alias_id = input_id

        self._set_target(None)
        self.lat = None
        self.lon = None
        self.state = None
        return leftovers
    
    #update coordinates and state
    def update(self, lat, lon, state):
        self.lat = lat
        self.lon = lon
        self.state = state

    #send the update to a target(if active)
    def send_update(self, lat, lon, state, dir: Direction):
        if self.is_active():
            self.target.update_link_info(lat, lon, state, dir)

    #remove the link of a target with the specified direction(dir)
    def unlink(self, dir: Direction):
        if self.is_active():
            self.target.remove_link(dir, False)

#RadioLink between Ground Station and satellite
class RadioLink(Link):
    def __init__(self, parent_sat):
        super().__init__(parent_sat, constants.GROUND_STATION_LINK_CAPACITY)
        self.target: list[GroundStation] = []  #maybe a list as target for radiolink can be trivial

    #attach link to GS
    def attach_to_gs(self, gs):
        if not(self.target.__contains__(gs)): #if the GS isn't already in the target list of the link
            self.target.append(gs) #add to list

    #disconnect link from GS
    def detach_from_all(self):
        leftovers = [] #residual fluxes
        while len(self.fluxes.values()) > 0: #if there are fluxes
            flux = list(self.fluxes.values())[0] #take first value of fluxes
            leftovers.append(flux.clone()) #add cloned flux to leftovers
            input_id = self._parent.mapping_table.remove(flux.alias_id) #remove id from parent table and store id value in input_id
            self._parent._close_internal_flux(flux.alias_id) #close internal flux in parent
            leftovers[-1].alias_id = input_id #set the input of the last inserted flux in leftovers
        for gs in self.target: 
            self.target.remove(gs) #every GS in self.target is removed
        return leftovers

    #get the self.target list of GS connected to RadioLink
    def get_attached_gs(self) -> list[GroundStation]:
        return self.target
    '''
    #sender for centralized flux
    def send_centralized_flux(self, flux: Flux):
        if flux.alias_id not in self.fluxes.keys(): #if id isn't among the keys of fluxes return error
            raise RuntimeError("Resources needs to be reserved before sending flux " + str(flux.id) + " with alias id " + str(flux.alias_id))
        for gs in self.target:
            gs.open_flux(flux.clone())
    '''
    #send flux
    def send_flux(self, flux: Flux):
        if flux.alias_id not in self.fluxes.keys(): #if id isn't among the keys of fluxes return error
            raise RuntimeError("Resources needs to be reserved before sending flux " + str(flux.id) + " with alias id " + str(flux.alias_id))
        for gs in self.target:
            gs.open_flux(flux.clone())

    #close flux
    def close_flux(self, flux: Flux):
        self.fluxes.pop(flux.alias_id) #remove flux using id
        for gs in self.target:
            '''
            #debug
            if constants.DEBUG:
                print("Closed flux", flux.id, "with alias id", flux.alias_id, "on Satellite", self._parent.get_name(), "headed to", gs.get_name(), "with rate", flux.rate, "Mbps at time", utils.get_current_time().utc_strftime())
            '''
            gs.close_flux(flux.clone()) #every GS in self.target close the flux
            