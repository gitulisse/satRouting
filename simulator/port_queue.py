import constants
from flow import Flow
import sys

class PortQueue:
    def __init__(self):
        self.queue = list[Flow]
        self.capacity = 1 #Gbps

    #add a flow
    def enqueue(self, flow: Flow):
        self.queue.append(flow)

    #remove a flow
    def dequeue(self) -> Flow:
        return self.queue.pop(0)
    
    #check if queue (list of flowes) is empty, return bool
    def is_empty(self) -> bool:
        return len(self.queue) == 0
    
    #lenght of queue
    def get_length(self) -> int:
        return len(self.queue)
    
    #calculate available bandwidth
    def get_available_bandwidth(self) -> float:
        return self.capacity - sum([flow.rate for flow in self.queue]) #max capacity of the port minus the sum of all the flowes rate saved as a the list