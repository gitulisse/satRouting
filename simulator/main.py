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
import cartopy.crs as ccrs
import cartopy.feature as cfeature
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
from itertools import chain
# Avoid crashes due to unlimited recursion (it would affect stack)
import sys
sys.setrecursionlimit(10000)
#A tool to select Ground Stations by config file
def load_ground_stations(config_path=None):
    if config_path:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        stations = {}
        for name, coords in config['ground_stations'].items():
            stations[name.upper()] = GroundStation(
                coords['lat'], coords['lon'], name
            )
        return stations
    return {
        'TOKYO': GroundStation(35.689506, 139.6917, 'Tokyo'),
        'NEW YORK': GroundStation(40.71277778, -74.00611111, 'New York'),
        'DAR ES SALAAM': GroundStation(-6.816111, 39.280278, 'Dar Es Salaam'),
        'BUENOS AIRES': GroundStation(-34.608333, -58.371944, 'Buenos Aires')
    }
#Read JSONs
def read_from_json(filename):
    with open(f'{filename}.json', 'r', encoding='utf-8') as f:
        return json.load(f)

# Constellation map generation
def show_constellation_map(satellites: list, ground_stations: list, **kwargs):
    def draw_map(ax):
        ax.add_feature(cfeature.LAND, color='lightgray')
        ax.add_feature(cfeature.OCEAN, color='lightblue')
        ax.add_feature(cfeature.COASTLINE, edgecolor='black')
        ax.add_feature(cfeature.BORDERS, linestyle=':')
        gridlines = ax.gridlines(draw_labels=True, linewidth=0.5, color='gray', alpha=0.7, linestyle='--')
        gridlines.xlabels_top = gridlines.ylabels_right = False
    plt.figure(figsize=(8, 6))
    ax = plt.axes(projection=ccrs.PlateCarree())
    ax.set_global()
    ax.set_extent([-180, 180, -90, 90], crs=ccrs.PlateCarree())

    draw_map(ax)

    for gs in ground_stations:
        x = gs.lon
        y = gs.lat
        plt.plot(x, y, 'or', markersize=10, transform=ccrs.PlateCarree())
        plt.text(x - 5, y + 3, str(gs.get_name()), fontsize=9, fontweight='bold', color='red', transform=ccrs.PlateCarree())

    plt.title("Constellation Map")
    plt.show()

def main():
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

    #Obtain the Traffic Matrix
    traffic_matrix = get_traffic_matrix([gs.get_name() for gs in ground_stations.values()])
    print("Traffic matrix print:", traffic_matrix)
    print("SAT FORMAT:", constants.SAT_FORMAT)
    if constants.SAT_FORMAT == 0 : 
        #Retrieve satellites info from NORAD
        print("Retrieving satellites...")
        stations_url = "https://celestrak.org/NORAD/elements/gp.php?GROUP=iridium-NEXT&FORMAT=tle"
        satellites = {int(sat.name[-3:]) : Sat(sat, ground_stations) for sat in load.tle_file(stations_url) if int(sat.name[-3:]) not in [176, 170, 175, 169, 162, 161, 105, 124, 115, 181, 178, 179, 174, 177]}
        print('Loaded', len(satellites), 'satellites.')
        for gs in ground_stations.values():
            gs.set_satellites(satellites)

        env.satellites = satellites
        env.ground_stations = ground_stations
        env.prepare()
    else :
        #Retrieve satellites info from NORAD
        print("Retrieving satellites...")
        
        # Check if using local file (for --input 2 with --sat-file)
        if constants.SAT_FORMAT == 2 and constants.SATELLITE_FILE_PATH:
            # Load from local file
            local_file = constants.SATELLITE_FILE_PATH
            
            if not os.path.exists(local_file):
                print(f"[ERROR] Local satellite file not found: {local_file}")
                print("Please provide a valid path with --sat-file")
                exit(1)
            
            print(f"Loading satellites from local file: {local_file}")
            with open(local_file, 'r', encoding='utf-8') as f:
                try:
                    stations_json = json.load(f)
                except:
                    print("WARNING: loading failed, main.py at line 134")
            EXCLUDED = {}
            print(f"Loaded {len(stations_json)} satellites from file")
            
        elif constants.SAT_FORMAT == 1 :
            # OneWeb from Celestrak API
            #for testing purposes i've left here, the commented celestrack site
            #stations_url = "https://celestrak.org/NORAD/elements/gp.php?GROUP=iridium-NEXT&FORMAT=JSON"
            stations_url = "https://celestrak.org/NORAD/elements/gp.php?GROUP=oneweb&FORMAT=JSON"
            EXCLUDED = {176, 170, 175, 169, 162, 161, 105, 124, 115, 181, 178, 179, 174, 177}
            try:
                stations_json = requests.get(stations_url, headers={'User-Agent': 'Satellite-Routing-Simulator/1.0'}, timeout=30).json()
            except:
                print("WARNING: failed to load IRIDIUM from celestrak,main.py line 146")
                sys.exit(1)
        else :
            # Custom OMM from URL (interactive). Do not use if on ssh
            stations_url = input("Inserisci il link JSON della tua rete in formato OMM:")
            EXCLUDED = {}
            stations_json = requests.get(stations_url, headers={'User-Agent': 'Satellite-Routing-Simulator/1.0'}, timeout=30).json()

        satellites = {}

        for jsat in stations_json:
            satnum = int(jsat["NORAD_CAT_ID"])
            essential = ["EPOCH", "MEAN_MOTION", "ECCENTRICITY", "INCLINATION"]
            missing = [field for field in essential if field not in jsat or jsat[field] is None]
            if missing:
                print("Missing orbital fields for", jsat["OBJECT_NAME"], missing)
                EXCLUDED.add(satnum)
                continue
            sat = EarthSatellite.from_omm(utils.ts, jsat)
            if satnum not in EXCLUDED:
                satellites[satnum] = Sat(sat, ground_stations)
                print('Loaded', len(satellites), 'satellites.')
        for gs in ground_stations.values():
            gs.set_satellites(satellites)


        env.satellites = satellites
        env.ground_stations = ground_stations
        env.prepare()

    # Standard Simulation Execution (only if not in Plot or Analyze mode)
    if not constants.ANALYZE and not constants.PLOT:
        traffic_generators = []
        header_builders = []

        if constants.ROUTING_STRATEGY in constants.SOURCE_STRATEGIES:
            for gs in ground_stations.values():
                gs_traffic_details = traffic_matrix[gs.get_name()]
                for destination in gs_traffic_details:
                    hb = HeaderBuilder(gs_traffic_details[destination], constants.SIMULATION_DURATION, gss=ground_stations, source_gs=gs, destination_gs=ground_stations[destination.upper()])
                    header_builders.append(hb)

        if constants.ROUTING_STRATEGY in constants.DISTRIBUTED_STRATEGIES:
            for gs in ground_stations.values():
                gs_traffic_details = traffic_matrix[gs.get_name()]
                for destination in gs_traffic_details:
                    tg = TrafficGenerator(gs_traffic_details[destination], constants.SIMULATION_DURATION, source_gs=gs, destination_gs=ground_stations[destination.upper()])
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
            results = read_from_json(constants.PLOT)
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

    ### Map Visualization (Optional) ###
    # show_constellation_map(satellites.values(), ground_stations.values(), links=[], paths=[])
if __name__ == "__main__":
    main()
