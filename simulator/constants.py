import argparse
from queue import Queue
from strategy import Strategy

#Contant values to run the application

DEBUG = True

LATITUDE_CUTOFF = 70

SATELLITE_NEIGHBORS_UPDATE_TIME = 10
TOPOLOGY_UPDATE_TIME = min(30, SATELLITE_NEIGHBORS_UPDATE_TIME)

#Value between 0 and 1 stating how much the neighbor's state should affect the overall state value of the satellite (0 = no weight on neighbors, 1 = overall state depends exclusively on neighbors' state)
LOAD_BALANCING_WEIGHT_FACTOR = 0.9

SATELLITE_COVERAGE_AREA_RADIUS = 2350 #radius in km in which the satellites can operate to cover ground areas for connections with GS
SATELLITE_LINK_CAPACITY = 1 #Gbps
GROUND_STATION_LINK_CAPACITY = 1000 #Gbps

TIME_MULTIPLIER = 1

K_SHORTEST_VALUE = 3 #constant that decides how many disjoint paths should be found by k shortest algorithm

parser = argparse.ArgumentParser(prefix_chars='-')
parser.add_argument("-s", "--strategy", type=int)
parser.add_argument("-d", "--duration", type=int)
parser.add_argument("-t", "--traffic", type=int)
args = parser.parse_args()
if args.strategy:
    ROUTING_STRATEGY = Strategy(args.strategy)
else:
    ROUTING_STRATEGY = Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK #if there is no strategy it's used Position sharing with Load Balance on saturated links

FLUX_TTL = 31
LOOP_AVOIDANCE_CUTOFF = 9 #loop avoidance

SIMULATION_DURATION = args.duration if args.duration else 60 #if there is no durantion it'll be set to 60 secs
TOTAL_VOLUME_OF_TRAFFIC = args.traffic if args.traffic else 20 #Mbps passed by user in the command else 20

drawing_queue = Queue()


'''
class NetworkParameters:
    LEO_GEO_GS_TD = 0.35 # seconds
    PACKET_SIZE = 1_500  # bytes
    SATELLITE_QUEUE_SIZE = 0 # bytes
    TOTAL_VOLUME_OF_TRAFFIC = 1_000_000_000 # bit / second
    CITIES_FILE_PATH = 'cities.yaml'
    SATELLITE_PORT_RATE = 0  # bit / second
    LINK_SWITCH_DELAY = 0.25  # seconds
    LIMIT_BYTES = True
'''