import constants
from copy import copy
from enum import Enum
from routing_action import RoutingAction

class Flux:
    def __init__(self, id: int, rate: float, destination: tuple[float, float]):
        self.id = id
        self.rate = rate #Mbps
        self.destination = destination
        self.ttl = constants.FLUX_TTL
        self.steps = list()
        self.paths = list()
        self.alias_id = id
        self.state: FluxState = FluxState.NOT_DEFINED
        self.travelled_distance = 0 #km

    #get steps of the flux as satellite list
    def get_steps(self) -> list:
        return copy(self.steps)
    
    #add steps and reduce by 1 the TTL
    def add_step(self, sat):
        self.ttl -= 1
        self.steps.append(sat)
        #print("selfsteps added", self.steps) #self.steps costituiti dai satelliti che attraversa il flusso

    #drop steps from a specific satellite
    def drop_steps_from(self, sat):
        indices = [i for i, x in enumerate(self.steps) if x == sat] #obtain the list of indeces and satellites equal to sat
        self.steps = self.steps[:indices[-1]] #the list is cut off till the last index found, every satellite after that point is cut off
        self.ttl = constants.FLUX_TTL - len(self.steps) #recalculate the TTL subtracting the new length of steps

    #split the flux based on rate
    def split(self, rate):
        if rate >= self.rate:
            raise ValueError("The rate requested for this split is higher than the current rate of the flux.")
        else:
            splitted_flux = self.clone() #clone flux
            splitted_flux.rate = rate #new rate
            backup_flux = self.clone() #backup
            backup_flux.rate = self.rate - rate #backup rate of the flux minus current rate
            return (splitted_flux, backup_flux)

    #clone flux
    def clone(self):
        clone = Flux(self.id, self.rate, self.destination)
        clone.ttl = self.ttl
        clone.steps = copy(self.steps)
        clone.paths = copy(self.paths)
        clone.alias_id = self.alias_id
        clone.travelled_distance = self.travelled_distance
        return clone

    #check if 2 fluxes are equal
    def __eq__(self, other) -> bool:
        if isinstance(other, Flux): #if other is instance of Flux
            return self.id == other.id #True if same id
        return False
    
    #check if 2 fluxes aren't equal
    def __ne__(self, other) -> bool:
        return not self.__eq__(other)
    
    #calculate hash for a Flux (with id & destination) using hash native function of py
    def __hash__(self):
        return hash((self.id, self.destination))
    
#enumeration of different possible Flux's states
class FluxState(Enum):
    NOT_DEFINED = "not_defined"
    DELIVERED = "Delivered"
    SATELLITE_CONGESTED = "Satellite congested"
    LINK_CONGESTED = "Link congested"
    EXPIRED_TTL = "Expired TTL"
    SATELLITE_NOT_OPERATIONAL = "Satellite not operational"