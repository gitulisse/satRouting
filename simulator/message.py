import constants
import sys

class Message:
    def __init__(self, destination_lat, destination_lon, message, is_link_update: bool = False) -> None:
        self.lat = destination_lat
        self.lon = destination_lon
        self.message = message
        self.is_link_update = is_link_update
        self._steps = list()
        self.total_time = 0.0
        self.last_step = None
        self.delivered = None
        self.ttl = 32

    def add_step(self, sat):
        self._steps.append(sat)

    def get_steps(self) -> list:
        return self._steps

    def __sizeof__(self) -> int:
        return sys.getsizeof(self.lat) + sys.getsizeof(self.lon) + sys.getsizeof(self.message) + sys.getsizeof(self.is_link_update)