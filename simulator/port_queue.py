import constants
from flux import Flux
import sys

class PortQueue:
    def __init__(self):
        self.queue = list[Flux]
        self.capacity = 1 #Mbps

    def enqueue(self, flux: Flux):
        self.queue.append(flux)

    def dequeue(self) -> Flux:
        return self.queue.pop(0)
    
    def is_empty(self) -> bool:
        return len(self.queue) == 0
    
    def get_length(self) -> int:
        return len(self.queue)
    
    def get_available_bandwidth(self) -> float:
        return self.capacity - sum([flux.rate for flux in self.queue])