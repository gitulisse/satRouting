from enum import Enum

class RoutingAction(Enum):
    FORWARD = 1
    DELIVER = 2
    CLOSE = 3
    ERROR = 4
    REOPEN = 5