import constants
import dijkstra
from enum import Enum
import environment as env
from flux import Flux
from geopy import distance
from gravity_model import get_traffic_matrix
from ground_station import GroundStation
from itertools import groupby
import json
from link import LaserLink
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import random
from skyfield.api import Timescale
import statistics
from strategy import Strategy
import threading
import time
import utils

class AnalysisMetric(Enum): #metrics
    COMPARISON_WITH_DIJKSTRA = 1
    AVERAGE_LINK_OCCUPATION = 2
    DELIVERED_DROPPED_RATIO = 3
    CONTROL_TRAFFIC_COMPARISON = 4
    WEIGHT_SENSITIVITY_ANALYSIS = 5
    TIME_PASSING_SIMULATION = 6

class TrafficAnalyzer:
    def __init__(self, ground_stations: list, satellites: list):
        self.results = None
        self.ground_stations = ground_stations
        self.satellites = satellites

    #core of the analyzer
    def analyze(self, metric: AnalysisMetric):
        match metric: #switch

            #case 1
            case AnalysisMetric.COMPARISON_WITH_DIJKSTRA: 
                simulation_duration_backup = constants.SIMULATION_DURATION #save simulation duration that determinates how much time is executed for each strategy
                constants.SIMULATION_DURATION = 1 #change duration
                self.prepare_results_for_comparison_with_dijkstra(ground_stations=self.ground_stations)

                for i in range(0, simulation_duration_backup):
                    utils.set_hour_shift(i) #repeat simulation shifting hour from 0 to simulation_duration_backup
                    env.reset()
                    env.prepare()
                    #USE DIJKSTRA AS BASELINE
                    env.put(0, self.sample_dijkstra, ground_stations=self.ground_stations, satellites=self.satellites) #execute the simulation with dijkstra algorithm
                    env.start()
                for strategy in [Strategy.POSITION_GUESSING_NO_LB, Strategy.POSITION_SHARING_NO_LB]: #assign these strateies to ROUTIING_STRATEGY
                    constants.ROUTING_STRATEGY = strategy 
                    fluxes = {} #empty dictionary of fluxes
                    for i in range(0, simulation_duration_backup): #repeat simulation shifting hour from 0 to simulation_duration_backup with new strategies
                        utils.set_hour_shift(i)
                        env.reset()
                        env.prepare()
                        env.put(0, self.prepare_strategy_comparison, ground_stations=self.ground_stations, fluxes=fluxes)
                        env.put(0, self.sample_strategy_comparison, ground_stations=self.ground_stations, fluxes=fluxes)
                        env.put(0, self.end_strategy_comparison, ground_stations=self.ground_stations, fluxes=fluxes)
                        env.start()
                utils.set_hour_shift(0)
                constants.SIMULATION_DURATION = simulation_duration_backup

            #case 2
            case AnalysisMetric.AVERAGE_LINK_OCCUPATION:
                total_traffic_backup = constants.TOTAL_VOLUME_OF_TRAFFIC #save total traffic
                self.prepare_results_for_average_link_occupation_analysis()

                for volume in range(1, total_traffic_backup + 1, 1): #range(from 1, to total_traffic_backup, with steps of 1)
                    constants.TOTAL_VOLUME_OF_TRAFFIC = volume
                    traffic_matrix = get_traffic_matrix([gs.get_name() for gs in self.ground_stations.values()]) #create traffic matrix using GS names
                    print(traffic_matrix)
                    for strategy in Strategy:
                        for i in range(0, 10):
                            utils.set_hour_shift(i)
                            env.reset()
                            constants.ROUTING_STRATEGY = strategy
                            env.prepare()
                            fluxes = {}
                            env.put(0, self.prepare_link_occupation_analysis, ground_stations=self.ground_stations, fluxes=fluxes, traffic_matrix=traffic_matrix) #put event prepare_link_occupation_analysis with 0 delay (executed as first) and pass as params gs, fluxes & traffic matrix
                            env.put(constants.SIMULATION_DURATION, self.sample_link_occupation_analysis, satellites=self.satellites, ground_stations=self.ground_stations, fluxes=fluxes) #put event that store data for  analysis at the end of simulation (constants.SIMULATION_DURATION) with params
                            env.put(constants.SIMULATION_DURATION, self.end_link_occupation_analysis, ground_stations=self.ground_stations, fluxes=fluxes) #put event end links occupation analysis with params at the end of simulation
                            env.start() #starts the simulation with the events inserted by env.put command
                utils.set_hour_shift(0)
                constants.TOTAL_VOLUME_OF_TRAFFIC = total_traffic_backup
            
            #case 3
            case AnalysisMetric.DELIVERED_DROPPED_RATIO: #va a rieseguire per ogni strategia ripartendo da 1 Mb e aggiungendo 1 Mb di traffico per ogni ciclio su tutte le strategie
                total_traffic_backup = constants.TOTAL_VOLUME_OF_TRAFFIC
                self.prepare_results_for_delivered_dropped_ratio()

                for volume in range(1, total_traffic_backup + 1, 1): #range(from 1, to total_traffic_backup, with steps of 1)
                    constants.TOTAL_VOLUME_OF_TRAFFIC = volume
                    traffic_matrix = get_traffic_matrix([gs.get_name() for gs in self.ground_stations.values()])
                    print(traffic_matrix)
                    for strategy in Strategy:
                        env.reset()
                        constants.ROUTING_STRATEGY = strategy
                        env.prepare()
                        fluxes = {}
                        env.put(0, self.prepare_delivered_dropped_ratio, ground_stations=self.ground_stations, fluxes=fluxes, traffic_matrix=traffic_matrix)
                        env.put(constants.SIMULATION_DURATION, self.sample_delivered_dropped_ratio, ground_stations=self.ground_stations, fluxes=fluxes)
                        env.put(constants.SIMULATION_DURATION, self.end_delivered_dropped_ratio, ground_stations=self.ground_stations, fluxes=fluxes)
                        env.start()

                constants.TOTAL_VOLUME_OF_TRAFFIC = total_traffic_backup #reset total traffic volume as it will not be affected in other subsequent analysis

            #case 4
            case AnalysisMetric.CONTROL_TRAFFIC_COMPARISON:
                neighbors_update_time_backup = constants.SATELLITE_NEIGHBORS_UPDATE_TIME #save satellite neighbor update time
                topology_update_backup = constants.TOPOLOGY_UPDATE_TIME #save topology update time
                neighbors_update_times = [5, 10, 15, 20, 30, 60] #update times list in which satellites retrieve info of neighbors
                self.prepare_results_for_control_traffic_comparison(neighbors_update_times) #prepare results for each specified update time 

                traffic_matrix = get_traffic_matrix([gs.get_name() for gs in self.ground_stations.values()])
                print(traffic_matrix)
                for strategy in [Strategy.POSITION_SHARING_NO_LB,
                                 Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                                 Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                 Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB]:
                    constants.ROUTING_STRATEGY = strategy
                    for time in neighbors_update_times:
                        constants.SATELLITE_NEIGHBORS_UPDATE_TIME = time #each loop select a different update time
                        constants.TOPOLOGY_UPDATE_TIME = min(30, constants.SATELLITE_NEIGHBORS_UPDATE_TIME) #update topology_update time to min between 30 secs or neighbors update time
                        for i in range(0, 10): #use 10 hours range variation 
                            utils.set_hour_shift(i)
                            env.reset()
                            env.prepare()
                            fluxes = {}
                            env.put(0, self.prepare_control_traffic_comparison, ground_stations=self.ground_stations, fluxes=fluxes, traffic_matrix=traffic_matrix)
                            env.put(constants.SIMULATION_DURATION, self.sample_control_traffic_comparison, ground_stations=self.ground_stations, fluxes=fluxes, neighbors_update_time=time)
                            env.put(constants.SIMULATION_DURATION, self.end_control_traffic_comparison, ground_stations=self.ground_stations, fluxes=fluxes)
                            env.start()
                utils.set_hour_shift(0)
                constants.SATELLITE_NEIGHBORS_UPDATE_TIME = neighbors_update_time_backup
                constants.TOPOLOGY_UPDATE_TIME = topology_update_backup

            #case 5
            case AnalysisMetric.WEIGHT_SENSITIVITY_ANALYSIS: #analyse how change the performance selecting a different weight factor
                strategy_backup = constants.ROUTING_STRATEGY
                constants.ROUTING_STRATEGY = Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB
                weights = [0.1, 0.25, 0.37, 0.5, 0.63, 0.75, 0.9]
                self.prepare_results_for_weight_sensitivity_analysis(weights)
                traffic_matrix = get_traffic_matrix([gs.get_name() for gs in self.ground_stations.values()])
                print(traffic_matrix)
                for weight in weights:
                    constants.LOAD_BALANCING_WEIGHT_FACTOR = weight
                    for i in range(0, 10):
                        utils.set_hour_shift(i)
                        env.reset()
                        env.prepare()
                        fluxes = {}
                        env.put(0, self.prepare_weight_sensitivity_analysis, ground_stations=self.ground_stations, fluxes=fluxes, traffic_matrix=traffic_matrix)
                        env.put(constants.SIMULATION_DURATION, self.sample_weight_sensitivity_analysis, satellites=self.satellites, ground_stations=self.ground_stations, fluxes=fluxes)
                        env.put(constants.SIMULATION_DURATION, self.end_weight_sensitivity_analysis, ground_stations=self.ground_stations, fluxes=fluxes)
                        env.start()
                utils.set_hour_shift(0)
                constants.ROUTING_STRATEGY = strategy_backup

            #case 6
            case AnalysisMetric.TIME_PASSING_SIMULATION: #simulation for testing strategy's behaviour during time
                strategy_backup = constants.ROUTING_STRATEGY
                traffic_matrix = get_traffic_matrix([gs.get_name() for gs in self.ground_stations.values()])
                self.prepare_results_for_time_passing_simulation()

                #could use some different strategies to test them during time
                for strategy in [Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB]:
                    constants.ROUTING_STRATEGY = strategy
                    fluxes = {}
                    env.reset()
                    env.prepare()
                    env.put(0, self.prepare_time_passing_simulation, ground_stations=self.ground_stations, fluxes=fluxes, traffic_matrix=traffic_matrix)
                    for i in range(1, constants.SIMULATION_DURATION + 1): #for each second of simulation
                        env.put(i, self.sample_time_passing_simulation, ground_stations=self.ground_stations, fluxes=fluxes) #obtain sample of gs, fluxes and variables
                    env.put(constants.SIMULATION_DURATION, self.end_time_passing_simulation, ground_stations=self.ground_stations, fluxes=fluxes)
                    env.start()
                constants.ROUTING_STRATEGY = strategy_backup


        print(self.results)

        #if duration is longer then 60 secs cretes a random file with srtored results of simulation
        if constants.SIMULATION_DURATION >= 60:
            filename = utils.randomword(10)
            print("Storing result in file named", filename)
            with open(filename + '.json', 'w', encoding='utf-8') as f:
                json.dump(self.results, f, ensure_ascii=False, indent=4)

        return self.results


    def prepare_results_for_comparison_with_dijkstra(self, ground_stations):
        self.results = {}
        for source in ground_stations.values():
            for destination in ground_stations.values():
                if source == destination: continue
                self.results[source.get_name() + ' - ' + destination.get_name()] = { #create a key in self.result made by GSsource-GSdestination
                    'DIJKSTRA' : {}, #key that will contain results for dijkstra
                    Strategy.POSITION_GUESSING_NO_LB.name : {}, #key that will contain results for position guessing no lb
                    Strategy.POSITION_SHARING_NO_LB.name : {} #key that will contain results for  position sharing no lb
                }
                for strategy in self.results[source.get_name() + ' - ' + destination.get_name()].keys(): #for every strategy (even dijkstra) 
                    self.results[source.get_name() + ' - ' + destination.get_name()][strategy] = {
                        'successful' : [], #store succesful routing
                        'failed' : 0, #count all failed routings
                        'distance' : [] #store the travelled distance
                    }

    #calculate shortest path between 2 GS stations with DIJKSTRA
    def sample_dijkstra(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        satellites: dict = kwargs['satellites']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                if source == destination: continue
                dijkstra_shortest_paths = self._get_dijkstra_shortest_paths(satellites, source, destination)

                '''
                self.results[source.get_name() + ' - ' + destination.get_name()]['DIJKSTRA']['successful'].append(len(dijkstra_shortest_paths[0]))
                self.results[source.get_name() + ' - ' + destination.get_name()]['DIJKSTRA']['distance'].append(
                        min([self._get_path_distance(dijkstra_shortest_path, source, destination, satellites) for dijkstra_shortest_path in dijkstra_shortest_paths])
                    )
                '''
                
                # Aggiunge un controllo per verificare che dijkstra_shortest_paths non sia vuoto
                if dijkstra_shortest_paths:
                    # Se ci sono percorsi, aggiungi la lunghezza del primo percorso trovato
                    self.results[source.get_name() + ' - ' + destination.get_name()]['DIJKSTRA']['successful'].append(len(dijkstra_shortest_paths[0]))
                else:
                    # In caso contrario, gestisci il caso senza percorsi (potresti aggiungere 0, None o un messaggio)
                    print(f"Nessun percorso disponibile tra {source.get_name()} e {destination.get_name()}.")
                    self.results[source.get_name() + ' - ' + destination.get_name()]['DIJKSTRA']['successful'].append(0)  # Oppure None, in base alle esigenze
                
                if dijkstra_shortest_paths:
                    # Calcola e aggiungi la minima distanza tra i percorsi disponibili
                    self.results[source.get_name() + ' - ' + destination.get_name()]['DIJKSTRA']['distance'].append(
                        min([self._get_path_distance(dijkstra_shortest_path, source, destination, satellites) for dijkstra_shortest_path in dijkstra_shortest_paths])
                    )
                else:
                    # Gestisce il caso senza percorsi
                    print(f"Nessuna distanza calcolabile tra {source.get_name()} e {destination.get_name()}.")
                    # Puoi usare un valore placeholder come float('inf') o None, a seconda di cosa è più appropriato per la tua analisi
                    self.results[source.get_name() + ' - ' + destination.get_name()]['DIJKSTRA']['distance'].append(float('inf'))
                    #se però usiamo 'inf' quando calcola nelle charts i valori ottenuti si sballa tutto, diventa +% di variazione pari a infinito
                
                    
    #prepare the comparison among strategies
    def prepare_strategy_comparison(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        fluxes: dict = kwargs['fluxes']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                if source == destination: continue
                flux = utils.create_new_flux((destination.lat, destination.lon), 0) #create a flux with 0 initial traffic rate
                fluxes[source.get_name() + ' - ' + destination.get_name()] = flux  #store the flux in dictionary fluxes as: fluxes = {"GS1 - GS2": <Flux object>, "GS1 - GS3": <Flux object>,...}
                source.send_flux(flux) #send flux to destination

    #store perferomance data for comparison
    def sample_strategy_comparison(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        fluxes: dict = kwargs['fluxes']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                if source == destination: continue
                flux = fluxes[source.get_name() + ' - ' + destination.get_name()] #store the flux obtained by key source-destination in the dictionary fluxes
                if destination.is_incoming_flux_alive(flux): #if the flux is incoming in destination
                    destination.get_flux_info(flux, until=utils.get_current_time()) #obtain flux infos until the time of the current simulation
                    print(f"Routing strategy's shortest path from {source.get_name()} to {destination.get_name()}: ", [sat.get_name() for sat in flux.paths[-1]])
                    print(f"Routing strategy's shortest path length from {source.get_name()} to {destination.get_name()}: ", len(flux.paths[-1]), "hops.")
                    self.results[source.get_name() + ' - ' + destination.get_name()][constants.ROUTING_STRATEGY.name]['successful'].append(len(flux.paths[-1])) #store length (as steps) of successful paths
                    self.results[source.get_name() + ' - ' + destination.get_name()][constants.ROUTING_STRATEGY.name]['distance'].append(flux.travelled_distance) #store the travelled distance 
                else:
                    print(f"Failed to route flux to destination from {source.get_name()} to {destination.get_name()}.") #error message
                    self.results[source.get_name() + ' - ' + destination.get_name()][constants.ROUTING_STRATEGY.name]['failed'] += 1 #increase the counter of failed strategies for the specific source-destination key

    #stop the comparison closing the fluxes
    def end_strategy_comparison(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        fluxes: dict = kwargs['fluxes']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                if source == destination: continue
                flux = fluxes[source.get_name() + ' - ' + destination.get_name()] #store the flux obtained by key source-destination in the dictionary fluxes
                source.close_outgoing_flux(flux) #close outgoing fluxes from source GS
        fluxes.clear() #after closing all active fluxes, the dictionary fluxes is cleared for future simulations

    #obtain list of closer satellites in coverage area
    def _get_candidate_end_satellites_names(self, satellites, position): #position for destination coordinates
        sat_list = utils.get_closer_satellites(satellites, position) #list of closer satellites
        return [sat['name'] for sat in sat_list if sat['distance'] < constants.SATELLITE_COVERAGE_AREA_RADIUS] #list of the only satellites inside the coverage area of self

    #calculate the distance travelled by the flux
    def _get_path_distance(self, path: list, source, destination, satellites) -> float:
        distance = utils.get_distance_between_satellite_and_gs(path[0], source, satellites=satellites) #calculate distance between GS and the first satellite
        distance += utils.get_distance_between_satellite_and_gs(path[-1], destination, satellites=satellites) #calculate & add the distance between last satellite and GS
        older_hop = path[0] #first satellite of path

        #for every hop after the first one, calucate & add distance between satellites
        for hop in path[1:]: 
            distance += utils.get_distance_between_satellites(older_hop, hop, satellites=satellites)
            older_hop = hop
        return distance

    #calculate all the shortest available paths
    def _get_dijkstra_shortest_paths(self, satellites, source, destination):
        
        g = dijkstra.Graph() #construct a graph for satellites
        
        '''
        #debug
        for name, sat in satellites.items():
            for link in sat._links.values():
                if link.is_active():
                    # Aggiunge un arco al grafo e stampa i nodi e l’arco appena aggiunto
                    target_name = link.target.get_name()
                    distance = utils.get_distance_between_satellites(sat, link.target)
                    g.add_edge(name, target_name, distance)
                    print(f"Added edge from {name} to {target_name} with distance {distance}")
                    # Stampa i nodi individualmente
                    print(f"Node added: {name}")
                    print(f"Node added: {target_name}")
        '''
                    
        #for every satellite item using as keys name & sat, and for every link of them check if link is active
        for name, sat in satellites.items(): 
            for link in sat._links.values(): 
                if link.is_active():
                    g.add_edge(name, link.target.get_name(), utils.get_distance_between_satellites(sat, link.target)) #add a connection from name(the current satellite) to the target
        
        end_satellites = self._get_candidate_end_satellites_names(satellites, (destination.lat, destination.lon)) #otherwise check for the closet satellites in the area of destination GS

        #calculate Dijkstra's shortest path
        d = dijkstra.DijkstraSPF(g, source.sat.get_name()) #initialize dijkstra algorithm on the graph starting from source

        shortest_paths = []
        for end_satellite in end_satellites:
            try:
                path = d.get_path(end_satellite)
                if path:  # Verifica che il percorso non sia vuoto
                    shortest_paths.append(path)
            except KeyError:
                # Gestione del caso in cui il nodo di destinazione non è raggiungibile
                print(f"Nessun percorso trovato per il nodo di destinazione {end_satellite}")

        # Controlla se ci sono percorsi disponibili
        if not shortest_paths:
            print(f"Non ci sono percorsi disponibili da {source.get_name()} a {destination.get_name()}.")
            return []  # Oppure None, a seconda di come vuoi gestire l'assenza di percorsi

        # Filtra e trova il percorso più breve
        shortest_path = min(shortest_paths, key=lambda x: len(x))
        shortest_paths = [path for path in shortest_paths if len(path) == len(shortest_path)]
        
        for sp in shortest_paths:
            print(f"Dijkstra's shortest path from {source.get_name()} to {destination.get_name()}: ", sp)
        print(f"Dijkstra's shortest path length from {source.get_name()} to {destination.get_name()}: ", len(shortest_paths), "x", len(shortest_path), "hops.")
        
        return shortest_paths

    #prepare the dictionary for avarage link occupation analysis
    def prepare_results_for_average_link_occupation_analysis(self):
        self.results = {}
        for s in Strategy:
            self.results[s.name] = {
                'average_link_occupation' : [],
                'involved_satellites' : [],
                'cumulative_dropped_data' : [],
                'volume_of_traffic' : []
            }

    #prepare for the link occupation analysis
    def prepare_link_occupation_analysis(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        fluxes: dict = kwargs['fluxes']
        traffic_matrix = kwargs['traffic_matrix']
        for source in ground_stations.values():
            gs_traffic_details = traffic_matrix[source.get_name()] #for every source store in a dictionary the outgoing traffic from each source GS with destination and traffic
            for destination_name in gs_traffic_details: #for each destination
                destination = ground_stations[destination_name.upper()] #store GS destinations as Upper case
                flux = utils.create_new_flux((destination.lat, destination.lon), gs_traffic_details[destination_name]) #create flux
                fluxes[source.get_name() + ' - ' + destination.get_name()] = flux #flux store in dictionary fluxes
                source.send_flux(flux) #send flux

    #analyze and store avarage link occupation
    def sample_link_occupation_analysis(self, kwargs):
        satellites: dict = kwargs['satellites']
        ground_stations: dict = kwargs['ground_stations']
        fluxes: dict = kwargs['fluxes']
        all_sats_and_link_occupations = self._get_satellites_and_link_occupations_for_links_involved_in_flux_forwarding(None, satellites) #store satellite and link occupations during the transmission
        average = statistics.mean([link_occupation for _, link_occupation in all_sats_and_link_occupations]) #calculate mean occupation of links
        involved_satellites = len(set([sat_name for sat_name, _ in all_sats_and_link_occupations])) #calculate the number of involved hops

        #store the values
        self.results[constants.ROUTING_STRATEGY.name]['average_link_occupation'].append(average)
        self.results[constants.ROUTING_STRATEGY.name]['involved_satellites'].append(involved_satellites)
        self.results[constants.ROUTING_STRATEGY.name]['volume_of_traffic'].append(constants.TOTAL_VOLUME_OF_TRAFFIC)
        
        dropped_data = 0
        for source in ground_stations.values(): #for every couple of source and destination
            for destination in ground_stations.values():
                flux = fluxes[source.get_name() + ' - ' + destination.get_name()] #retrieve a specific flux from fluxes using source and destination 
                dropped_data += destination.get_flux_info(flux, until = utils.get_current_time())[2] #calculate dropped data getting flux info as the [2] that corresponds to dropped data variable of the flux
        self.results[constants.ROUTING_STRATEGY.name]['cumulative_dropped_data'].append(dropped_data)
        print(f"Average link occupation: {average}. {involved_satellites} satellites involved in routing. Cumulative dropped data: {dropped_data}")

    #stops the analysis on link occupation
    def end_link_occupation_analysis(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        fluxes: dict = kwargs['fluxes']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flux = fluxes[source.get_name() + ' - ' + destination.get_name()]
                source.close_outgoing_flux(flux) #close the outgoing fluxes of GS

    #get infos about satellite and link occupation between satellites 
    def _get_satellites_and_link_occupations_for_links_involved_in_flux_forwarding(self, flux_id: int, satellites):
        all_sats_and_link_occupations = []
        for name, sat in satellites.items(): #for every satellite extract name and item (sat)
            if sat.fluxes.values(): #if there are fluxes
                for f, link in sat.fluxes.values(): #for every flux (f) and link in sat.fluxes
                    if isinstance(link, LaserLink): #if the link it's a laserlink
                        if flux_id == None or f.id == flux_id: #if Flux_id is None(there is no specified flux) we want infos about all fluxes on satellite OR if equal to flux_id param we want infos about that specific flux
                            all_sats_and_link_occupations.append((name, constants.SATELLITE_LINK_CAPACITY - link.get_available_bandwidth())) #max capacity - the bandwidth still available
        return all_sats_and_link_occupations

    #prepare the dictionary for delivered dropped ratio
    def prepare_results_for_delivered_dropped_ratio(self):
        self.results = {}
        for s in Strategy:
            self.results[s.name] = {
                'delivered' : [],
                'dropped' : [],
                'volume_of_traffic' : []
            }

    #prepare to analyze ratio between delivered and dropped data
    def prepare_delivered_dropped_ratio(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        fluxes: dict = kwargs['fluxes']
        traffic_matrix = kwargs['traffic_matrix']
        for source in ground_stations.values(): #for every source in GS
            gs_traffic_details = traffic_matrix[source.get_name()] #dictionary that store and access to traffic matrix info using source's name as key
            for destination_name in gs_traffic_details: #for every destination
                destination = ground_stations[destination_name.upper()]
                flux = utils.create_new_flux((destination.lat, destination.lon), gs_traffic_details[destination_name]) #create flux
                fluxes[source.get_name() + ' - ' + destination.get_name()] = flux
                source.send_flux(flux) #send flux

    #analyze and store delivered & dropped ratio
    def sample_delivered_dropped_ratio(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        fluxes: dict = kwargs['fluxes']
        
        delivered_data = 0
        dropped_data = 0
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flux = fluxes[source.get_name() + ' - ' + destination.get_name()] #obtain the flux with selected source-destination
                _, delivered, dropped = destination.get_flux_info(flux, until = utils.get_current_time()) #total_data_sent/total_data_delivered/total_data_dropped (the first one isn't used)
                delivered_data += delivered
                dropped_data += dropped

        #store the results
        self.results[constants.ROUTING_STRATEGY.name]['delivered'].append(delivered_data)
        self.results[constants.ROUTING_STRATEGY.name]['dropped'].append(dropped_data)
        self.results[constants.ROUTING_STRATEGY.name]['volume_of_traffic'].append(constants.TOTAL_VOLUME_OF_TRAFFIC)

    #stops the analysis on delivered & dropped ratio
    def end_delivered_dropped_ratio(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        fluxes: dict = kwargs['fluxes']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flux = fluxes[source.get_name() + ' - ' + destination.get_name()]
                source.close_outgoing_flux(flux) #close outgoing fluxes

    #prepare the dictionary for control traffic comparison
    def prepare_results_for_control_traffic_comparison(self, update_times):
        self.results = {}
        for s in [Strategy.POSITION_SHARING_NO_LB,
                  Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                  Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                  Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB]:
            self.results[s.name] = {}
            for time in update_times:
                self.results[s.name][time] = {
                    'delivered' : [],
                    'dropped' : [],
                    'control_traffic' : []
                }

    #prepare to analyze a comparison of traffic
    def prepare_control_traffic_comparison(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        fluxes: dict = kwargs['fluxes']
        traffic_matrix = kwargs['traffic_matrix']
        for source in ground_stations.values():
            gs_traffic_details = traffic_matrix[source.get_name()]
            for destination_name in gs_traffic_details:
                destination = ground_stations[destination_name.upper()]
                flux = utils.create_new_flux((destination.lat, destination.lon), gs_traffic_details[destination_name]) #create flux
                fluxes[source.get_name() + ' - ' + destination.get_name()] = flux
                source.send_flux(flux) #send flux

    #analyze and store traffic comparison
    def sample_control_traffic_comparison(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        fluxes: dict = kwargs['fluxes']
        neighbors_update_time = kwargs['neighbors_update_time']
        
        delivered_data = 0
        dropped_data = 0
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flux = fluxes[source.get_name() + ' - ' + destination.get_name()] #obtain the flux with selected source-destination
                _, delivered, dropped = destination.get_flux_info(flux, until = utils.get_current_time()) #total_data_sent/total_data_delivered/total_data_dropped (the first one isn't used)
                delivered_data += delivered
                dropped_data += dropped

        #store the results
        self.results[constants.ROUTING_STRATEGY.name][neighbors_update_time]['delivered'].append(delivered_data)
        self.results[constants.ROUTING_STRATEGY.name][neighbors_update_time]['dropped'].append(dropped_data)
        self.results[constants.ROUTING_STRATEGY.name][neighbors_update_time]['control_traffic'].append(env.control_traffic_data)

    #stop the analysis of traffic comparison
    def end_control_traffic_comparison(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        fluxes: dict = kwargs['fluxes']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flux = fluxes[source.get_name() + ' - ' + destination.get_name()]
                source.close_outgoing_flux(flux) #close flux

    #prepare the dictionary to analyze weight sensitivity
    def prepare_results_for_weight_sensitivity_analysis(self, weights: list):
        self.results = {}
        for weight in weights:
            self.results[weight] = {
                'average_link_occupation' : [],
                'involved_satellites' : [],
                'cumulative_dropped_data' : [],
                'volume_of_traffic' : []
            }

    #prepare to analyze the weight sensitivity
    def prepare_weight_sensitivity_analysis(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        fluxes: dict = kwargs['fluxes']
        traffic_matrix = kwargs['traffic_matrix']
        for source in ground_stations.values():
            gs_traffic_details = traffic_matrix[source.get_name()]
            for destination_name in gs_traffic_details:
                destination = ground_stations[destination_name.upper()]
                flux = utils.create_new_flux((destination.lat, destination.lon), gs_traffic_details[destination_name]) #create flux
                fluxes[source.get_name() + ' - ' + destination.get_name()] = flux
                source.send_flux(flux) #send flux

    #analyze and store weight sensitivity
    def sample_weight_sensitivity_analysis(self, kwargs):
        satellites: dict = kwargs['satellites']
        ground_stations: dict = kwargs['ground_stations']
        fluxes: dict = kwargs['fluxes']
        all_sats_and_link_occupations = self._get_satellites_and_link_occupations_for_links_involved_in_flux_forwarding(None, satellites) #store satellite and link occupation between satellites
        average = statistics.mean([link_occupation for _, link_occupation in all_sats_and_link_occupations]) #calculate mean occupation
        involved_satellites = len(set([sat_name for sat_name, _ in all_sats_and_link_occupations])) #calculate amount of involved satellite

        #store the results
        self.results[constants.LOAD_BALANCING_WEIGHT_FACTOR]['average_link_occupation'].append(average)
        self.results[constants.LOAD_BALANCING_WEIGHT_FACTOR]['involved_satellites'].append(involved_satellites)
        self.results[constants.LOAD_BALANCING_WEIGHT_FACTOR]['volume_of_traffic'].append(constants.TOTAL_VOLUME_OF_TRAFFIC)
        
        dropped_data = 0
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flux = fluxes[source.get_name() + ' - ' + destination.get_name()] #retrieve a specific flux from fluxes using source and destination
                dropped_data += destination.get_flux_info(flux, until = utils.get_current_time())[2] #calculate dropped data getting flux info as the [2] that corresponds to dropped data variable of the flux

        self.results[constants.LOAD_BALANCING_WEIGHT_FACTOR]['cumulative_dropped_data'].append(dropped_data) #store data under the key of load balancing weight factor
        print(f"Average link occupation: {average}. {involved_satellites} satellites involved in routing. Cumulative dropped data: {dropped_data}")

    #stop analysis of weight sensitivity
    def end_weight_sensitivity_analysis(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        fluxes: dict = kwargs['fluxes']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flux = fluxes[source.get_name() + ' - ' + destination.get_name()]
                source.close_outgoing_flux(flux) #close flux

    #prepare the dictionary to analyze the simulation during time
    def prepare_results_for_time_passing_simulation(self):
        self.results = {}
        for s in [Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB]:
            self.results[s.name] = {
                'delivered' : [],
                'dropped' : [],
                'distance' : []
            }

    #prepare to analyze simulation on time passing
    def prepare_time_passing_simulation(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        fluxes: dict = kwargs['fluxes']
        traffic_matrix = kwargs['traffic_matrix']
        for source in ground_stations.values():
            gs_traffic_details = traffic_matrix[source.get_name()]
            for destination_name in gs_traffic_details:
                destination = ground_stations[destination_name.upper()]
                flux = utils.create_new_flux((destination.lat, destination.lon), gs_traffic_details[destination_name])
                fluxes[source.get_name() + ' - ' + destination.get_name()] = flux
                source.send_flux(flux)

    #analyze and store the data from simulation during a period of time
    def sample_time_passing_simulation(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        fluxes: dict = kwargs['fluxes']
        
        delivered_data = 0
        dropped_data = 0
        distance_data = 0
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flux = fluxes[source.get_name() + ' - ' + destination.get_name()]
                _, delivered, dropped = destination.get_flux_info(flux, until = utils.get_current_time())
                delivered_data += delivered
                dropped_data += dropped
                distance_data += flux.travelled_distance

        if len(fluxes) > 0:
            distance_data /= len(fluxes) #calculate the avarage distance travelled, dividing by number of fluxes

        #store the results
        self.results[constants.ROUTING_STRATEGY.name]['delivered'].append(delivered_data)
        self.results[constants.ROUTING_STRATEGY.name]['dropped'].append(dropped_data)
        self.results[constants.ROUTING_STRATEGY.name]['distance'].append(distance_data)

    #stop the analysis of the dimulation during time
    def end_time_passing_simulation(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        fluxes: dict = kwargs['fluxes']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flux = fluxes[source.get_name() + ' - ' + destination.get_name()]
                source.close_outgoing_flux(flux) #close flux