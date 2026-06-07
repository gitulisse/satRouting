import charts
import constants
from gravity_model import get_traffic_matrix
from ground_station import GroundStation
import environment as env
from itertools import chain
import json
import os
import yaml
import matplotlib.pyplot as plt
import numpy as np
import random
import requests
from satellite import Sat
from skyfield.api import load, EarthSatellite
from traffic_analyzer import AnalysisMetric, TrafficAnalyzer
from header_builder import HeaderBuilder
from traffic_generator import TrafficGenerator
import utils
from strategy import Strategy
# Avoid crashes due to unlimited recursion (it would affect stack)
import sys
sys.setrecursionlimit(10000)
#Tool to select Ground Stations by config file
def load_ground_stations(config_path=None):
    if config_path == None:
        default_data_path = os.path.join(os.path.dirname(__file__), '../data/ground_stations.yaml')
        if os.path.exists(default_data_path):
            config_path = default_data_path
    if config_path:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        stations = {}
        for name, coords in config['ground_stations'].items():
            norm_name = utils.normalize_city_name(name)
            stations[norm_name] = GroundStation(
                coords['lat'], coords['lon'], norm_name
            )
        return stations
    return {
        'TOKYO': GroundStation(35.689506, 139.6917, 'TOKYO'),
        'NEW YORK': GroundStation(40.71277778, -74.00611111, 'NEW YORK'),
        'DAR ES SALAAM': GroundStation(-6.816111, 39.280278, 'DAR ES SALAAM'),
        'BUENOS AIRES': GroundStation(-34.608333, -58.371944, 'BUENOS AIRES')
    }

def main():
    # easiest definition i can think of, timescale is a standardized way to handle time in satellite simulations,
    #  and it's used by the skyfield library to compute satellite positions and events. By defining it here,
    #  we ensure that all parts of the code that need to work with time can use the same timescale object, 
    # which helps maintain consistency across the simulation.
    utils.ts = load.timescale()

    """  #GroundStations coordinates
    san_francisco_gs = GroundStation(37.77750000, -122.41638889, 'San Francisco')
    canberra_gs = GroundStation(-35.3, 149.133333, 'Canberra')
    punta_arenas_gs = GroundStation(-53.166667, -70.933333, 'Punta Arenas')
    milan_gs = GroundStation(45.466944, 9.19, 'Milan')
    tokyo_gs = GroundStation(35.689506, 139.6917, 'Tokyo')
    dar_es_salaam_gs = GroundStation(-6.816111, 39.280278, 'Dar Es Salaam')
    cape_town_gs = GroundStation(-33.9264, 18.4227, 'Cape Town')
    pretoria_gs = GroundStation(-25.74611111, 28.18805556, 'Pretoria')
    cairo_gs = GroundStation(30.04444444, 31.23583333, 'Cairo')
    stockholm_gs = GroundStation(59.32944444, 18.06861111, 'Stockholm')
    jeddah_gs = GroundStation(21.54333333, 39.17277778, 'Jeddah')
    new_york_gs = GroundStation(40.71277778, -74.00611111, 'New York')
    buenos_aires_gs = GroundStation(-34.608333, -58.371944, 'Buenos Aires')
    oslo_gs = GroundStation(59.913333, 10.738889, 'Oslo') """

    #Ground Stations selected for the simulation
    ground_stations = load_ground_stations(constants.GS_CONFIG_PATH) 
    """{
        'TOKYO' : tokyo_gs,
        'NEW YORK' : new_york_gs,
        'DAR ES SALAAM' : dar_es_salaam_gs,
        'BUENOS AIRES' : buenos_aires_gs
    }"""

    #Obtain the Traffic Matrix: Traffic matrix is a fundamental component in network simulations,
    #  as it defines the communication demand between different ground stations. 
    # By calling get_traffic_matrix with the list of ground station names, 
    # we can generate a traffic matrix that specifies how much data each ground station
    #  wants to send to every other ground station. 
    # This matrix will be used later in the simulation to create traffic generators and 
    # header builders that simulate the actual data transmission between the ground stations 
    # through the satellite network.
    traffic_matrix = get_traffic_matrix([gs.get_name() for gs in ground_stations.values()])
    print("Traffic matrix print:", traffic_matrix)
    print("SAT FORMAT:", constants.SAT_FORMAT)
    # 🛰 SATELLITE LOADING & CACHING LOGIC
    print("Retrieving satellites...")
    satellites = {}
    # Legacy excluded satellites that caused issues in previous runs
    EXCLUDED = {176, 170, 175, 169, 162, 161, 105, 124, 115, 181, 178, 179, 174, 177}

    if constants.SAT_FORMAT == 0:
        # TLE Format (Traditional Iridium approach)
        local_path = os.path.join(os.path.dirname(__file__), "../data/iridium.tle")
        stations_url = "https://celestrak.org/NORAD/elements/gp.php?GROUP=iridium-NEXT&FORMAT=tle"
        
        if constants.SATELLITE_FILE_PATH:
            local_path = constants.SATELLITE_FILE_PATH
            print(f"Using custom TLE file: {local_path}")
        
        # Check cache/download
        if not os.path.exists(local_path) or not utils.is_cache_fresh(local_path):
            if utils.is_online():
                print("Downloading fresh TLE data from Celestrak...")
                try:
                    resp = requests.get(stations_url, timeout=30)
                    with open(local_path, 'wb') as f:
                        f.write(resp.content)
                except Exception as e:
                    print(f"Download failed ({e}), attempting to use stale cache.")
            else:
                print("Offline mode: using cached TLE data.")

        try:
            tle_data = load.tle_file(local_path)
            satellites = {sat.model.satnum : Sat(sat, ground_stations) 
                         for sat in tle_data}
        except Exception as e:
            print(f"[CRITICAL] Failed to load TLE: {e}")
            sys.exit(1)

    else:
        # JSON/OMM Format (Modern OneWeb/Starlink approach)
        local_path = os.path.join(os.path.dirname(__file__), "../data/oneweb.json")
        stations_url = "https://celestrak.org/NORAD/elements/gp.php?GROUP=oneweb&FORMAT=JSON"
        
        if constants.SATELLITE_FILE_PATH:
            local_path = constants.SATELLITE_FILE_PATH
            print(f"Using custom JSON file: {local_path}")

        if not os.path.exists(local_path) or not utils.is_cache_fresh(local_path):
            if utils.is_online():
                print("Downloading fresh OMM data from Celestrak...")
                try:
                    stations_json = requests.get(stations_url, headers={'User-Agent': 'Satellite-Routing-Simulator/1.0'}, timeout=30).json()
                    with open(local_path, 'w', encoding='utf-8') as f:
                        json.dump(stations_json, f, indent=4)
                except Exception as e:
                    print(f"Download failed ({e}), attempting to use stale cache.")
            else:
                print("Offline mode: using cached OMM data.")

        stations_json = utils.read_from_json(local_path)
        if stations_json is None:
            print("[CRITICAL] Failed to load OMM data.")
            sys.exit(1)

        for jsat in stations_json:
            satnum = int(jsat["NORAD_CAT_ID"])
            essential = ["EPOCH", "MEAN_MOTION", "ECCENTRICITY", "INCLINATION"]
            if all(jsat.get(field) is not None for field in essential):
                sat = EarthSatellite.from_omm(utils.ts, jsat)
                if satnum not in EXCLUDED:
                    satellites[satnum] = Sat(sat, ground_stations)
            else:
                EXCLUDED.add(satnum)

    print(f'Loaded {len(satellites)} satellites.')
    for gs in ground_stations.values():
        gs.set_satellites(satellites)

    env.satellites = satellites
    env.ground_stations = ground_stations
    
    # Initialize positions before visualization
    env.update_satellites_position()
    
    if not constants.ANALYZE and not constants.PLOT:
        charts.show_constellation_map(env.satellites.values(), env.ground_stations.values(), links=[], paths=[])

    env.prepare()

    # Standard Simulation Execution (only if not in Plot or Analyze mode)
    if not constants.ANALYZE and not constants.PLOT:
        traffic_generators = []
        header_builders = []

        if constants.ROUTING_STRATEGY in constants.SOURCE_STRATEGIES:
            for gs in ground_stations.values():
                gs_norm = utils.normalize_city_name(gs.get_name())
                gs_traffic_details = None
                for city_name, details in traffic_matrix.items():
                    if utils.normalize_city_name(city_name) == gs_norm:
                        gs_traffic_details = details
                        break

                if gs_traffic_details:
                    for destination, rate in gs_traffic_details.items():
                        dest_norm = utils.normalize_city_name(destination)
                        dest_gs = ground_stations.get(dest_norm)
                        if dest_gs:
                            hb = HeaderBuilder(rate, constants.SIMULATION_DURATION, gss=ground_stations, source_gs=gs, destination_gs=dest_gs)
                            header_builders.append(hb)

        if constants.ROUTING_STRATEGY in constants.DISTRIBUTED_STRATEGIES:
            for gs in ground_stations.values():
                gs_norm = utils.normalize_city_name(gs.get_name())
                gs_traffic_details = None
                for city_name, details in traffic_matrix.items():
                    if utils.normalize_city_name(city_name) == gs_norm:
                        gs_traffic_details = details
                        break

                if gs_traffic_details:
                    for destination, rate in gs_traffic_details.items():
                        dest_norm = utils.normalize_city_name(destination)
                        dest_gs = ground_stations.get(dest_norm)
                        if dest_gs:
                            tg = TrafficGenerator(rate, constants.SIMULATION_DURATION, source_gs=gs, destination_gs=dest_gs)
                            traffic_generators.append(tg)
        env.start()

    # Analysis and Plotting Router
    if constants.ANALYZE or constants.PLOT:
        traffic_analyzer = TrafficAnalyzer(ground_stations, satellites)
        
        # Map string argument to AnalysisMetric enum
        metric_map = {
            'dijkstra': AnalysisMetric.COMPARISON_WITH_DIJKSTRA,
            'link_occupation': AnalysisMetric.AVERAGE_LINK_OCCUPATION,
            'delivery_ratio': AnalysisMetric.DELIVERED_DROPPED_RATIO,
            'control_traffic': AnalysisMetric.CONTROL_TRAFFIC_COMPARISON,
            'weight_sensitivity': AnalysisMetric.WEIGHT_SENSITIVITY_ANALYSIS,
            'time_passing': AnalysisMetric.TIME_PASSING_SIMULATION
        }
        
        metric = metric_map.get(constants.ANALYZE)
        
        if constants.PLOT:
            # Load from JSON and Plot
            print(f"Loading results from {constants.PLOT}...")
            results = utils.read_from_json(constants.PLOT)
        elif metric:
            # Run Analysis and Plot
            print(f"Running analysis for metric: {constants.ANALYZE}...")
            results = traffic_analyzer.analyze(metric)
        else:
            print("Error: Please specify a valid analysis metric using --analyze")
            return

        # Display the appropriate chart
        if constants.ANALYZE == 'dijkstra':
            charts.show_shortest_paths_table(results)
        elif constants.ANALYZE == 'link_occupation':
            charts.show_average_link_occupation_chart(results)
        elif constants.ANALYZE == 'delivery_ratio':
            charts.show_delivered_dropped_ratio_chart(results)
        elif constants.ANALYZE == 'control_traffic':
            charts.show_control_traffic_comparison_chart(results)
        elif constants.ANALYZE == 'weight_sensitivity':
            charts.show_weight_sensitivity_analysis_chart(results)
        elif constants.ANALYZE == 'time_passing':
            charts.show_time_passing_simulation_chart(results)

if __name__ == "__main__":
    main()
    