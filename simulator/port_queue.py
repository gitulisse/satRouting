from flow import Flow

class PortQueue:
    def __init__(self):
        self.queue = list[Flow]
        self.capacity = 1 #Gbps

    def enqueue(self, flow: Flow):
        self.queue.append(flow)

    def dequeue(self) -> Flow:
        return self.queue.pop(0)
    
    def is_empty(self) -> bool:
        return len(self.queue) == 0
    
    def get_length(self) -> int:
        return len(self.queue)
    
    def get_available_bandwidth(self) -> float:
        return self.capacity - sum([flow.rate for flow in self.queue])