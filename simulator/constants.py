import argparse
from queue import Queue
from strategy import Strategy

#Constants values to run the application
DEBUG = False

LATITUDE_CUTOFF = 70

SATELLITE_NEIGHBORS_UPDATE_TIME = 10
TOPOLOGY_UPDATE_TIME = min(30, SATELLITE_NEIGHBORS_UPDATE_TIME)

#Value between 0 and 1 stating how much the neighbor's state should affect the overall state value of the satellite (0 = no weight on neighbors, 1 = overall state depends exclusively on neighbors' state)
LOAD_BALANCING_WEIGHT_FACTOR = 0.75

SATELLITE_COVERAGE_AREA_RADIUS = 2350 #radius in km in which the satellites can operate to cover ground areas for connections with GS
SATELLITE_LINK_CAPACITY = 1 #Gbps
GROUND_STATION_LINK_CAPACITY = 1000 #Gbps

TIME_MULTIPLIER = 1

K_SHORTEST_VALUE = 1 #constant k value for shortest path algorithm without load balancing
K_SHORTEST_VALUE_LB = 4 #constant that decides how many disjoint paths should be found by k shortest algorithm with load balancing


parser = argparse.ArgumentParser(prefix_chars='-')
parser.add_argument("-s", "--strategy", type=int)
parser.add_argument("-d", "--duration", type=int)
parser.add_argument("-t", "--traffic", type=int)
parser.add_argument("-i", "--input", type=int, choices=[0, 1], help="Satellite data format (0=TLE, 1=JSON/OMM)")
parser.add_argument("--gs-config", type=str, help="Path to ground stations YAML config")
parser.add_argument("--sat-file", type=str, help="Optional: Path to local satellite file (overrides auto-cache)")
parser.add_argument("--analyze", type=str, choices=['dijkstra', 'link_occupation', 'delivery_ratio', 'control_traffic', 'weight_sensitivity', 'time_passing'], help="Run a specific analysis metric")
parser.add_argument("--plot", type=str, help="Path to a JSON file to plot without re-running the analysis")
args = parser.parse_args()
GS_CONFIG_PATH = args.gs_config if args.gs_config else None

ANALYZE = args.analyze
PLOT = args.plot

SAT_FORMAT = args.input if args.input is not None else 1 # Default to JSON/OneWeb
if args.strategy:
    ROUTING_STRATEGY = Strategy(args.strategy)
else:
    ROUTING_STRATEGY = Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK #if there is no strategy it's used Position Sharing with Load Balance on Saturated Links

FLOW_TTL = 31
LOOP_AVOIDANCE_CUTOFF = 9 #loop avoidance value

SIMULATION_DURATION = args.duration if args.duration else 60 #if there is no durantion it'll be set to 60 secs
TOTAL_VOLUME_OF_TRAFFIC = args.traffic if args.traffic else 10 #Gbps passed by user in the command else 20

# Local satellite file path (for --input 2 with local file)
SATELLITE_FILE_PATH = args.sat_file if args.sat_file else None
SOURCE_STRATEGIES = [
    Strategy.BASELINE_DIJKSTRA,
    Strategy.SOURCE_ROUTING_BY_HOP_NO_LB,
    Strategy.SOURCE_ROUTING_BY_LENGTH_NO_LB,
    Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
    Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
    Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING,
    Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,

]
SOURCE_STRATEGIES_EXCEPT_DIJKSTRA = [
    Strategy.SOURCE_ROUTING_BY_HOP_NO_LB,
    Strategy.SOURCE_ROUTING_BY_LENGTH_NO_LB,
    Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
    Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
    Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING,
    Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,

]
DISTRIBUTED_STRATEGIES = [
    Strategy.POSITION_GUESSING_NO_LB,
    Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
    Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
    Strategy.POSITION_SHARING_NO_LB,
    Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
    Strategy.POSITION_SHARING_PROGRESSIVE_LB,
    Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
    Strategy.POSITION_AND_LOAD_STATE_SHARING_TWO_HOPS

]
ACTIVE_STRATEGIES =  DISTRIBUTED_STRATEGIES + SOURCE_STRATEGIES

drawing_queue = Queue()

