import constants
from flux import Flux
import sys

class PortQueue:
    def __init__(self):
        self.queue = list[Flux]
        self.capacity = 1 #Gbps

    #add a flux
    def enqueue(self, flux: Flux):
        self.queue.append(flux)

    #remove a flux
    def dequeue(self) -> Flux:
        return self.queue.pop(0)
    
    #check if queue (list of fluxes) is empty, return bool
    def is_empty(self) -> bool:
        return len(self.queue) == 0
    
    #lenght of queue
    def get_length(self) -> int:
        return len(self.queue)
    
    #calculate available bandwidth
    def get_available_bandwidth(self) -> float:
        return self.capacity - sum([flux.rate for flux in self.queue]) #max capacity of the port minus the sum of all the fluxes rate saved as a the list