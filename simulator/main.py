import charts
import constants
from gravity_model import get_traffic_matrix
from ground_station import GroundStation
import environment as env
from itertools import chain
import json
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import numpy as np
import random
from satellite import Sat
from skyfield.api import load
from traffic_analyzer import AnalysisMetric, TrafficAnalyzer
from header_builder import HeaderBuilder
from traffic_generator import TrafficGenerator
import utils
from strategy import Strategy
from itertools import chain

import sys
sys.setrecursionlimit(10000)

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


utils.ts = load.timescale()

#GroundStations coordinates
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
oslo_gs = GroundStation(59.913333, 10.738889, 'Oslo')

#Ground Stations selected for the simulation
ground_stations = {
    'TOKYO' : tokyo_gs,
    'NEW YORK' : new_york_gs,
    'DAR ES SALAAM' : dar_es_salaam_gs,
    'BUENOS AIRES' : buenos_aires_gs
}

#Obtain the Traffic Matrix
traffic_matrix = get_traffic_matrix([gs.get_name() for gs in ground_stations.values()])
print("Traffic matrix print:", traffic_matrix)

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

# Start of the code block that launches the standard simulation
traffic_generators = []
header_builders = []

if constants.ROUTING_STRATEGY in [Strategy.BASELINE_DIJKSTRA,
                                  Strategy.SOURCE_ROUTING_BY_HOP_NO_LB,
                                  Strategy.SOURCE_ROUTING_BY_LENGTH_NO_LB,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING]:
    for gs in ground_stations.values():
        gs_traffic_details = traffic_matrix[gs.get_name()]
        for destination in gs_traffic_details:
            hb = HeaderBuilder(gs_traffic_details[destination], constants.SIMULATION_DURATION, gss=ground_stations, source_gs=gs, destination_gs=ground_stations[destination.upper()])
            header_builders.append(hb)

if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_NO_LB,
                                  Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                  Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                  Strategy.POSITION_SHARING_NO_LB,
                                  Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                                  Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                  Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
                                  Strategy.POSITION_AND_LOAD_STATE_SHARING_TWO_HOPS]:
    for gs in ground_stations.values():
        gs_traffic_details = traffic_matrix[gs.get_name()]
        for destination in gs_traffic_details:
            tg = TrafficGenerator(gs_traffic_details[destination], constants.SIMULATION_DURATION, source_gs=gs, destination_gs=ground_stations[destination.upper()])
            traffic_generators.append(tg)
env.start()
# End of block

# Object (TrafficAnalyzer) used to analyze specific metrics. Depending on the selected metric, the simulation flow can be
# altered (skipping simulation hours, restarting the simulation multiple times, simulating multiple different routing strategies, ...)

traffic_analyzer = TrafficAnalyzer(ground_stations, satellites)

# Uncomment the pair of instructions based on the metrics you want to generate results for.
#results = traffic_analyzer.analyze(AnalysisMetric.COMPARISON_WITH_DIJKSTRA)
#charts.show_shortest_paths_table(results)
#results = traffic_analyzer.analyze(AnalysisMetric.AVERAGE_LINK_OCCUPATION)
#charts.show_average_link_occupation_chart(results)
#results = traffic_analyzer.analyze(AnalysisMetric.DELIVERED_DROPPED_RATIO)
#charts.show_delivered_dropped_ratio_chart(results)
#results = traffic_analyzer.analyze(AnalysisMetric.CONTROL_TRAFFIC_COMPARISON)
#charts.show_control_traffic_comparison_chart(results)
#results = traffic_analyzer.analyze(AnalysisMetric.WEIGHT_SENSITIVITY_ANALYSIS)
#charts.show_weight_sensitivity_analysis_chart(results)
#results = traffic_analyzer.analyze(AnalysisMetric.TIME_PASSING_SIMULATION)
#charts.show_time_passing_simulation_chart(results)

# If you already have the results saved (e.g., in a json), use these instructions to display the corresponding chart
# without having to regenerate all the data.
#charts.show_shortest_paths_table(read_from_json("comparison_with_dijkstra_source_routing_results"))
#charts.show_average_link_occupation_chart(read_from_json("average_link_occupation_decentralized_results"))
#charts.show_delivered_dropped_ratio_chart(read_from_json("delivered_and_dropped_ratio_decentralized_results"))
#charts.show_control_traffic_comparison_chart(read_from_json("control_traffic_comparison"))
#charts.show_weight_sensitivity_analysis_chart(read_from_json("weight_sensitivity_analysis"))
#charts.show_time_passing_simulation_chart(read_from_json("time_passing_simulation"))
#charts.show_loop_avoidance_analysis_chart()

### Map ###
#Global map showing Ground Stations' positions
#show_constellation_map([], ground_stations.values(), links=[], paths=[])

#Print the GS & satellites positions
#show_constellation_map(satellites.values(), ground_stations.values(), links=[], paths=[])
