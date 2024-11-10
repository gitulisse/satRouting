import charts
import constants
from gravity_model import get_traffic_matrix
from ground_station import GroundStation
import environment as env
from itertools import chain
import json
import matplotlib.pyplot as plt
from mpl_toolkits.basemap import Basemap
import numpy as np
import random
from satellite import Sat
from skyfield.api import load
from traffic_analyzer import AnalysisMetric, TrafficAnalyzer
from traffic_generator import TrafficGenerator
import utils

import sys
sys.setrecursionlimit(10000)

#Read JSONs
def read_from_json(filename):
    with open(f'{filename}.json', 'r', encoding='utf-8') as f:
        return json.load(f)

#Constellation map generated
def show_constellation_map(satellites: list[Sat], ground_stations: list[GroundStation], **kwargs):
    def draw_map(m, scale=0.2):
        # draw a shaded-relief image
        m.shadedrelief(scale=scale)
        
        # lats and longs are returned as a dictionary
        lats = m.drawparallels(np.linspace(-90, 90, 13))
        lons = m.drawmeridians(np.linspace(-180, 180, 13))

        # keys contain the plt.Line2D instances
        lat_lines = chain(*(tup[1][0] for tup in lats.items()))
        lon_lines = chain(*(tup[1][0] for tup in lons.items()))
        all_lines = chain(lat_lines, lon_lines)
        
        # cycle through these lines and set the desired style
        for line in all_lines:
            line.set(linestyle='-', alpha=0., color='w')

    plt.figure(figsize=(8, 6), edgecolor='w')
    m = Basemap(projection='cyl', resolution=None,
                llcrnrlat=-90, urcrnrlat=90,
                llcrnrlon=-180, urcrnrlon=180,)
    draw_map(m)

    for satellite in satellites:
        x = satellite.get_longitude()
        y = satellite.get_latitude()
        plt.plot(x, y, 'ok', markersize=3)
        plt.text(x, y, str(satellite.get_name()), fontsize=7)
    
    for gs in ground_stations:
        x = gs.lon
        y = gs.lat
        plt.plot(x, y, 'or', markersize=20)
        #plt.text(x - 5, y + 3, str(gs.get_name()), fontsize=9, fontweight='bold')

    if 'links' in kwargs:
        links = kwargs['links']
        for link in links:
            plt.plot([link[0].get_longitude(), link[1].get_longitude()], 
                    [link[0].get_latitude(), link[1].get_latitude()],
                    color='0.85')
    
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
                    color = c)
                old_node = node

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

#Ground Stations selected
ground_stations = {
    'TOKYO' : tokyo_gs,
    'NEW YORK' : new_york_gs,
    'DAR ES SALAAM' : dar_es_salaam_gs,
    'SAN FRANCISCO' : san_francisco_gs
}

#Obtain the Traffic Matrix
traffic_matrix = get_traffic_matrix([gs.get_name() for gs in ground_stations.values()])
print(traffic_matrix)

'''
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
print("Completed.")
'''

#Retrieve satellites info from NORAD (in realtà sono 80 satelliti)
print("Retrieving satellites...")
stations_url = "https://celestrak.org/NORAD/elements/gp.php?GROUP=iridium-NEXT&FORMAT=tle"
satellites = {int(sat.name[-3:]) : Sat(sat, ground_stations) for sat in load.tle_file(stations_url) if int(sat.name[-3:]) not in [176, 170, 175, 169, 162, 161, 105, 124, 115, 181, 178, 179, 174, 177]}
print('Loaded', len(satellites), 'satellites.')

for gs in ground_stations.values():
    gs.set_satellites(satellites)

env.satellites = satellites
env.ground_stations = ground_stations
env.prepare()

# Inizio del blocco di codice che prepara e avvia una simulazione "standard" non finalizzata allo sviluppo di grafici o
# all'analisi di metriche specifiche
traffic_generators = []

for gs in ground_stations.values():
    gs_traffic_details = traffic_matrix[gs.get_name()]
    for destination in gs_traffic_details:
        tg = TrafficGenerator(gs_traffic_details[destination], constants.SIMULATION_DURATION, source_gs=gs, destination_gs=ground_stations[destination.upper()])
        traffic_generators.append(tg)
env.start()
#Fine del blocco

# Oggetto tramite cui si analizzano metriche specifiche. In base alla metrica scelta, il flusso della simulazione può essere
# alterato (skip di ore di simulazione, riavvio della simulazione più volte, simulazione di più strategie di routing diverse, ...)
traffic_analyzer = TrafficAnalyzer(ground_stations, satellites)

# Decommenta la coppia di istruzioni in base alle metriche di cui vuoi generare dei risultati
results = traffic_analyzer.analyze(AnalysisMetric.COMPARISON_WITH_DIJKSTRA)
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

#Global map showing Ground Stations' positions
#show_constellation_map([], ground_stations.values(), links=[], paths=[])

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