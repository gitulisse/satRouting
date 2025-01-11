import constants
from direction import Direction
from flux import Flux
from ground_station import GroundStation
import utils

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
            flux = list(self.fluxes.values())[0] #take first value of fluxes
            #print(f"first flux is.. {flux}")
            leftovers.append(flux.clone()) #add this flux to leftovers
            #print(f"leftovers list: {leftovers}")
            input_id = self._parent.mapping_table.remove(flux.alias_id) #remove flux id from parent mapping table & save it as input_id
            #print(f"input:id: {input_id}")
            self._parent._close_internal_flux(flux.alias_id) #close the flux internal to parent satellite
            leftovers[-1].alias_id = input_id #set the input of the last inserted flux in leftovers
            
        self.lat = sat.get_latitude() #lat
        self.lon = sat.get_longitude() #lon
        self.state = 0.0 #state
        self._set_target(sat) #set new target satellite
        return leftovers 
    
    #manage idle state for the links
    def idle(self) -> list[Flux]:
        print(f"Link {self} going idle with fluxes: {self.fluxes}")##########
        leftovers = []
        while len(self.fluxes.values()) > 0:
            flux = list(self.fluxes.values())[0]
            if flux.alias_id not in self._parent.mapping_table.table:
                print(f"Skipping invalid alias_id: {flux.alias_id}")
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
            