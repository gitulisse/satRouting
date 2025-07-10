from enum import Enum

class Strategy(Enum):
    POSITION_GUESSING_NO_LB = 1
    POSITION_GUESSING_LB_ON_SATURATED_LINK = 2
    POSITION_GUESSING_PROGRESSIVE_LB = 3

    POSITION_SHARING_NO_LB = 4
    POSITION_SHARING_LB_ON_SATURATED_LINK = 5
    POSITION_SHARING_PROGRESSIVE_LB = 6

    POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB = 7 #one hop neighbors information sharing
    POSITION_AND_LOAD_STATE_SHARING_TWO_HOPS = 8 #two hops neighbors
    
    BASELINE_DIJKSTRA = 10
    SOURCE_ROUTING_BY_HOP_NO_LB = 11 #based on length of path
    SOURCE_ROUTING_BY_LENGTH_NO_LB = 12 #based on length of path

    NODE_DISJOINT_SOURCE_ROUTING_LB = 13 #based on length for K paths (K = 4)
    EDGE_DISJOINT_SOURCE_ROUTING_LB = 14 #based on length for K paths (K = 4)

    NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK = 15 #based on link occupation of the path
    EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING = 16 #path cost selection

    