import constants
from copy import copy
from enum import Enum

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

    def get_steps(self) -> list:
        return copy(self.steps)
    
    def add_step(self, sat):
        self.ttl -= 1
        self.steps.append(sat)

    def drop_steps_from(self, sat):
        indices = [i for i, x in enumerate(self.steps) if x == sat]
        self.steps = self.steps[:indices[-1]]
        self.ttl = constants.FLUX_TTL - len(self.steps)

    def split(self, rate):
        if rate >= self.rate:
            raise ValueError("The rate requested for this split is higher than the current rate of the flux.")
        else:
            splitted_flux = self.clone()
            splitted_flux.rate = rate
            backup_flux = self.clone()
            backup_flux.rate = self.rate - rate
            return (splitted_flux, backup_flux)

    def clone(self):
        clone = Flux(self.id, self.rate, self.destination)
        clone.ttl = self.ttl
        clone.steps = copy(self.steps)
        clone.paths = copy(self.paths)
        clone.alias_id = self.alias_id
        clone.travelled_distance = self.travelled_distance
        return clone

    def __eq__(self, other) -> bool:
        if isinstance(other, Flux):
            return self.id == other.id
        return False
    
    def __ne__(self, other) -> bool:
        return not self.__eq__(other)
    
    def __hash__(self):
        return hash((self.id, self.destination))
    

class FluxState(Enum):
    NOT_DEFINED = "not_defined"
    DELIVERED = "Delivered"
    SATELLITE_CONGESTED = "Satellite congested"
    LINK_CONGESTED = "Link congested"
    EXPIRED_TTL = "Expired TTL"
    SATELLITE_NOT_OPERATIONAL = "Satellite not operational"