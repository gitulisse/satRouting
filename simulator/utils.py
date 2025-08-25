import constants
from direction import Direction
import environment as env
from flow import Flow
from geopy import distance
import math
import pandas as pd
from random import randint
import random
import requests
from skyfield.api import Time, Timescale
import string
import utils
import wbgapi as wb

ts: Timescale
hour_shift = 0

#exclude specified regions
def remove_extra_regions(data: pd.DataFrame) -> pd.DataFrame:
    for iso_3 in ['AFE', 'AFR', 'AFW', 'ARB', 'BEA', 'BEC', 'BHI', 'BLA', 'BMN', 'BSS', 'CAA', 'CEA', 'CEB', 'CEU', 'CHI', 'CLA', 'CME', 'CSA', 'CSS', 'CUW', 'DEA', 'DEC', 'DLA', 'DMN', 'DNS', 'DSA', 'DSF', 'DSS', 'EAP', 'EAR', 'EAS', 'ECA', 'ECS', 'EMU', 'EUU', 'FCS', 'FXS', 'GIB', 'HIC', 'HPC', 'IBB', 'IBD', 'IBT', 'IDA', 'IDB', 'IDX', 'INX', 'LAC', 'LCN', 'LDC', 'LIC', 'LMC', 'LMY', 'LTE', 'MAF', 'MDE', 'MEA', 'MIC', 'MNA', 'NAC', 'NAF', 'NRS', 'NXS', 'OED', 'OSS', 'PRE', 'PSE', 'PSS', 'PST', 'RRS', 'SAS', 'SSA', 'SSF', 'SST', 'SXM', 'SXZ', 'TEA', 'TEC', 'TLA', 'TMN', 'TSA', 'TSS', 'TWN', 'UMC', 'WLD', 'XZN']:
        data = data.drop(iso_3, errors='ignore')
    data = data.drop('IMN', errors='ignore')
    return data

#obtain population of countries
def get_countries_population() -> pd.DataFrame:
    print("Retrieving countries population...")
    df = wb.data.DataFrame('IT.NET.USER.ZS', mrnev=1)
    df = remove_extra_regions(df)
    return df

#return population (removing specified regions)
def get_countries_internet_penetration() -> pd.DataFrame:
    print("Retrieving internet penetration for each country...")
    df = wb.data.DataFrame('SP.POP.TOTL', mrnev=1)
    df = remove_extra_regions(df)
    return df

#get coordinates of countries (ISO of 3 letters, lat, lon)
def get_countries_coordinates() -> pd.DataFrame:
    print("Retrieving countries coordinates...")
    resp = requests.get('http://api.worldbank.org/v2/country?format=json&per_page=300')
    raw = resp.json()[1]
    iso_3_codes = []
    latitudes = []
    longitudes = []
    for row in raw:
        iso_3_codes.append(row['id'])
        latitudes.append(row['latitude'])
        longitudes.append(row['longitude'])
    df = pd.DataFrame({'latitude' : latitudes, 'longitude' : longitudes}, index=iso_3_codes)
    df = remove_extra_regions(df)
    return df

#identifies the closer satellites
def get_closer_satellites(satellites, position: tuple[float, float], operational_only = True):
    distances = list()
    for key, sat in satellites.items():
        if operational_only:
            if sat.is_operational() == False:
                continue
        distances.append({'distance': (distance.distance((sat.get_latitude(), sat.get_longitude()), position).km), 'name': key})
    distances.sort(key=lambda x: x['distance']) #sort from closest
    return distances

#identifies the only one closest satellite
def get_closest_satellite_for_graph(satellites, position: tuple[float, float], operational_only=True):
    closest_satellite = None
    min_distance = float('inf')
    for key, sat in satellites.items():
        if operational_only and not sat.is_operational():
            continue
        distance_to_gs = distance.distance((sat.get_latitude(), sat.get_longitude()), position).km
        if distance_to_gs <= constants.SATELLITE_COVERAGE_AREA_RADIUS and distance_to_gs < min_distance:
            min_distance = distance_to_gs
            closest_satellite = (key, sat)
    return [closest_satellite]

#identifies close satellites to build the graph structure (not used in the simulation cause it's used a single connection to GS)
def get_closer_satellites_for_graph(satellites, position: tuple[float, float], operational_only = True):
    closer_satellites = []
    for key, sat in satellites.items():
        if operational_only and not sat.is_operational():
            continue
        distance_to_gs = distance.distance((sat.get_latitude(), sat.get_longitude()), position).km
        if distance_to_gs <= constants.SATELLITE_COVERAGE_AREA_RADIUS:
            closer_satellites.append({'name': key, 'satellite': sat, 'distance': distance_to_gs})
        closer_satellites.sort(key=lambda x: x['distance'])
        chosen_satellites = [(entry['name'], entry['satellite']) for entry in closer_satellites]
    return chosen_satellites

#calculate distance between satellites in km
def get_distance_between_satellites(sat1, sat2, satellites = None):
    if isinstance(sat1, int):
        sat1 = satellites.get(sat1)
    if isinstance(sat2, int):
        sat2 = satellites.get(sat2)
    return distance.distance((sat1.get_latitude(), sat1.get_longitude()), (sat2.get_latitude(), sat2.get_longitude())).km

#calculate the distance as hypotenuse from GS to satellite
def get_distance_between_satellite_and_gs(sat, gs, satellites = None, ground_stations = None):
    if isinstance(sat, int):
        sat = satellites.get(sat)
    if isinstance(gs, str):
        gs = ground_stations.get(gs.upper())
    return math.hypot(distance.distance((gs.lat, gs.lon), (sat.get_latitude(), sat.get_longitude())).km, 780)

#calculate distance of coordinates on earth
def get_distance_between_earth_coordinates(coord1, coord2):
    return distance.distance(coord1, coord2).km

#return the opposite direction passed as param
def get_coupled_link_direction(dir: Direction) -> Direction:
    if dir == Direction.NORTH:
        return Direction.SOUTH
    if dir == Direction.SOUTH:
        return Direction.NORTH
    if dir == Direction.EAST:
        return Direction.WEST
    if dir == Direction.WEST:
        return Direction.EAST
    raise ValueError("Parameter dir must be a Direction")

#calculate delay in queue
def queuing_delay(queue_size, bandwidth) -> float:
    return queue_size / bandwidth 

#calculate delay in transmission
def transmission_delay(packet_size, bandwidth) -> float:
    return packet_size / bandwidth 

#calculate signal delay propagation between two positions
def propagation_delay(position1, position2) -> float:
    return (position1 - position2).distance().km * 0.000003335640951982 #constant time of light travelling for 1 km

#get time
def get_current_time() -> Time:
    return ts.utc(2023, 10, 15, 0 + utils.hour_shift, 0, env.elapsed_time) #year/month/day/hours hours set to 00:00:00

#manage hour shift
def set_hour_shift(shift):
    utils.hour_shift = shift

#get delta between two times
def get_seconds_between(time1: Time, time2: Time) -> int:
    delta_datetime = time1.utc_datetime() - time2.utc_datetime()
    delta_seconds = delta_datetime.total_seconds()
    return abs(delta_seconds)

#add time to the simulation
def add_seconds_to_time(time: Time, seconds: int) -> Time:
    return ts.utc(time.utc[0], time.utc[1], time.utc[2] + seconds / 24 / 60 / 60, time.utc[3], time.utc[4], time.utc[5])

#calculate sleep delay
def get_sleep_delay(seconds):
    return seconds / constants.TIME_MULTIPLIER

#manage creation of flows
def create_new_flow(destination: tuple[float, float], rate: float):
    return Flow(randint(1, 1000000), rate, destination)

#generates a randomic word in lowercase
def randomword(length):
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(length))

#obtain satellites in path
def get_satellites_in_path(routing_decisions):
    satellites_in_path = []
    for action, flow, link in routing_decisions:
        if link._parent not in satellites_in_path:
            satellites_in_path.append(link._parent)
        if link.target is not None and link.target not in satellites_in_path:
            satellites_in_path.append(link.target)
    return satellites_in_path

#get ground station name by coordinates
def get_ground_station_name_by_coords(lat, lon):
    for name, gs in env.ground_stations.items():
        if gs.lat == lat and gs.lon == lon:
            return name