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
#from link import Link
from strategy import Strategy
from itertools import chain

import sys
sys.setrecursionlimit(10000)

#Read JSONs
def read_from_json(filename):
    with open(f'{filename}.json', 'r', encoding='utf-8') as f:
        return json.load(f)

# Constellation map generated
def show_constellation_map(satellites: list, ground_stations: list, **kwargs):
    def draw_map(ax):
        # Add basic map features
        ax.add_feature(cfeature.LAND, color='lightgray')
        ax.add_feature(cfeature.OCEAN, color='lightblue')
        ax.add_feature(cfeature.COASTLINE, edgecolor='black')
        ax.add_feature(cfeature.BORDERS, linestyle=':')

        # Draw parallels and meridians
        parallels = np.linspace(-90, 90, 13)
        meridians = np.linspace(-180, 180, 13)

        # Add gridlines
        gridlines = ax.gridlines(draw_labels=True, linewidth=0.5, color='gray', alpha=0.7, linestyle='--')
        gridlines.xlabels_top = gridlines.ylabels_right = False

    plt.figure(figsize=(8, 6))
    ax = plt.axes(projection=ccrs.PlateCarree())

    # Draw the map with features
    draw_map(ax)

    # Plot satellites on the map
    for satellite in satellites:
        x = satellite.get_longitude()
        y = satellite.get_latitude()
        plt.plot(x, y, 'ok', markersize=3, transform=ccrs.PlateCarree())
        plt.text(x, y, str(satellite.get_name()), fontsize=7, transform=ccrs.PlateCarree())

    # Plot ground stations on the map
    for gs in ground_stations:
        x = gs.lon
        y = gs.lat
        plt.plot(x, y, 'or', markersize=10, transform=ccrs.PlateCarree())
        # plt.text(x - 5, y + 3, str(gs.get_name()), fontsize=9, fontweight='bold')

    # Plot links if provided
    if 'links' in kwargs:
        links = kwargs['links']
        for link in links:
            plt.plot([link[0].get_longitude(), link[1].get_longitude()], 
                     [link[0].get_latitude(), link[1].get_latitude()],
                     color='0.50', transform=ccrs.PlateCarree())

    # Plot paths if provided
    if 'paths' in kwargs:
        paths = kwargs['paths']
        used_c = []
        for path in paths:
            if len(used_c) == 5: 
                used_c = []
            c = random.choice([color for color in ['b', 'g', 'r', 'c', 'm'] if color not in used_c])
            used_c.append(c)
            old_node = path[0]
            for node in path[1:]:
                plt.plot([old_node.get_longitude(), node.get_longitude()], 
                         [old_node.get_latitude(), node.get_latitude()],
                         color=c, transform=ccrs.PlateCarree())
                old_node = node

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

#Ground Stations selected (removed'SAN FRANCISCO' : san_francisco_gs)
ground_stations = {
    'TOKYO' : tokyo_gs,
    'NEW YORK' : new_york_gs,
    'DAR ES SALAAM' : dar_es_salaam_gs,
    'BUENOS AIRES' : buenos_aires_gs
}

#Obtain the Traffic Matrix
traffic_matrix = get_traffic_matrix([gs.get_name() for gs in ground_stations.values()])
print("Traffic matrix print:", traffic_matrix)

'''#Preparation of the environment
countries_coordinates_df = utils.get_countries_coordinates()
countries_internet_penetration_df = utils.get_countries_internet_penetration()
countries_population_df = utils.get_countries_population()

print("Estimating ground stations workload...")
for index, coordinates in countries_coordinates_df.iterrows():
    distances = list()
    for gs in ground_stations.values():
        dist = utils.get_distance_between_earth_coordinates((coordinates['latitude'], coordinates['longitude']), (gs.lat, gs.lon))
        distances.append({'distance': dist, 'gs': gs})
    distances.sort(key=lambda x: x['distance'])
    distances[0]['gs'].add_population_to_serve(round(countries_population_df.loc[index]['IT.NET.USER.ZS'] * (countries_internet_penetration_df.loc[index]['SP.POP.TOTL'] / 100)))
print("Completed.")'''


#Retrieve satellites info from NORAD (in realtà sono 80 satelliti)
print("Retrieving satellites...")
stations_url = "https://celestrak.org/NORAD/elements/gp.php?GROUP=iridium-NEXT&FORMAT=tle"
satellites = {int(sat.name[-3:]) : Sat(sat, ground_stations) for sat in load.tle_file(stations_url) if int(sat.name[-3:]) not in [176, 170, 175, 169, 162, 161, 105, 124, 115, 181, 178, 179, 174, 177]}
print('Loaded', len(satellites), 'satellites.')

for gs in ground_stations.values():
    gs.set_satellites(satellites)

env.satellites = satellites
env.ground_stations = ground_stations
env.prepare() #prepare the environment with all necessary components
#launch 2 topology builder (for 2 runs of simulation on 20 secs duration) until "simulation ready to run"


# Start of the code block that launches the "standard" simulation not aimed at developing graphs or analyzing specific metrics
traffic_generators = []
header_builders = []

if constants.ROUTING_STRATEGY in [Strategy.BASELINE_DIJKSTRA, 
                                  Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                  Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                  Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING,
                                  Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                  Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                  Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                  Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_COSTS_SELECTION]:
    for gs in ground_stations.values():
        gs_traffic_details = traffic_matrix[gs.get_name()]
        for destination in gs_traffic_details:
            #destination = ground_stations.get(destination_name.upper())
            #print(f"HeaderBuilder from {gs.get_name()} -> {destination_name} with rate {rate} Gbps")
            hb = HeaderBuilder(gs_traffic_details[destination], constants.SIMULATION_DURATION, gss=ground_stations, source_gs=gs, destination_gs=ground_stations[destination.upper()])
            header_builders.append(hb)

if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_NO_LB,
                                  Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                  Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                  Strategy.POSITION_SHARING_NO_LB,
                                  Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                                  Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                  Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
                                  Strategy.POSITION_SHARING_WITH_COSTS_SELECTION]:
    for gs in ground_stations.values():
        gs_traffic_details = traffic_matrix[gs.get_name()]
        for destination in gs_traffic_details:
            tg = TrafficGenerator(gs_traffic_details[destination], constants.SIMULATION_DURATION, source_gs=gs, destination_gs=ground_stations[destination.upper()]) #SIMULATION_DURATION, header_builder=header_builder,
            traffic_generators.append(tg)
    '''
    if constants.DEBUG:
        print("traffic_generators LIST", traffic_generators)
    '''
env.start()
# End of block

# Oggetto (TrafficAnalyzer) tramite cui si analizzano metriche specifiche. In base alla metrica scelta, il flusso della simulazione può essere
# alterato (skip di ore di simulazione, riavvio della simulazione più volte, simulazione di più strategie di routing diverse, ...)
if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_NO_LB,
                                  Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                  Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                  Strategy.POSITION_SHARING_NO_LB,
                                  Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                                  Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                  Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
                                  Strategy.POSITION_SHARING_WITH_COSTS_SELECTION]:
    traffic_analyzer = TrafficAnalyzer(ground_stations, satellites)


# Decommenta la coppia di istruzioni in base alle metriche di cui vuoi generare dei risultati
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

# Se invece hai già i risultati salvati (tipo in un json), usa queste istruzioni per visualizzare il grafico corrispondente
# senza stare a rigenerare tutti i dati. 
#charts.show_shortest_paths_table(read_from_json("dijkstra_table"))
#charts.show_average_link_occupation_chart(read_from_json("average_link_occupation"))
#charts.show_delivered_dropped_ratio_chart(read_from_json("delivered_dropped_ratio"))
#charts.show_control_traffic_comparison_chart(read_from_json("control_traffic_comparison"))
#charts.show_weight_sensitivity_analysis_chart(read_from_json("weight_sensitivity_analysis"))
#charts.show_time_passing_simulation_chart(read_from_json("time_passing_simulation"))
#charts.show_loop_avoidance_analysis_chart()

#######################################################################################################
#Global map showing Ground Stations' positions
#show_constellation_map([], ground_stations.values(), links=[], paths=[])

#Print the GS & satellites positions
#show_constellation_map(satellites.values(), ground_stations.values(), links=[], paths=[])

#Print all the active links in the constellation (the orizontal links are painted in a weird way cause of the 2D rapresentation of the globe)
#active_links = Sat.get_active_links(satellites.values())
#show_constellation_map(satellites.values(), ground_stations.values(), links=active_links, paths=[])

#vuole gli argomenti passati come un dict
##########
#paths = traffic_analyzer.calculate_dijkstra(kwargs={'ground_stations': ground_stations, 'satellites': satellites}) #qui da sostituire poi con Header_builder
#print("PERCORSI TROVIATI PER DIJKSTRA", paths)

'''
while True:
    data = constants.drawing_queue.get()
    links = []
    for satellite in satellites.values():
        for link in satellite._links.values():
            if link.is_active():
                links.append([satellite, link.target])
    show_constellation_map(satellites.values(), ground_stations.values(), links=links, paths=data)
'''