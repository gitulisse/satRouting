import constants
import dijkstra
from enum import Enum
import environment as env
from flow import Flow
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
import networkx as nx
import random
from itertools import permutations

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

    def analyze(self, metric: AnalysisMetric): #core of the analyzer
        match metric: #switch
            case AnalysisMetric.COMPARISON_WITH_DIJKSTRA: #case 1
                simulation_duration_backup = constants.SIMULATION_DURATION #save simulation duration that determinates how much time is executed for each strategy
                constants.SIMULATION_DURATION = 1 #change duration
                self.prepare_results_for_comparison(ground_stations=self.ground_stations)

                #traffic_matrix = get_traffic_matrix([gs.get_name() for gs in self.ground_stations.values()]) #create traffic matrix using GS names
                #print(traffic_matrix)
                for strategy in [Strategy.BASELINE_DIJKSTRA,
                                  #Strategy.POSITION_GUESSING_NO_LB,
                                  #Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                  #Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                  #Strategy.POSITION_SHARING_NO_LB,
                                  #Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                                  #Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                  #Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
                                  #Strategy.POSITION_AND_STATE_SHARING_TWO_HOPS,
                                  #Strategy.POSITION_SHARING_COST_BALANCING,
                                  Strategy.SOURCE_ROUTING_NO_LB,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_ON_SATURATED_LINK,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_ON_SATURATED_LINK,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK
                                  ]:
                    constants.ROUTING_STRATEGY = strategy 
                    flows = {} #empty dictionary of flows
                    for i in range(0, simulation_duration_backup): #repeat simulation shifting hour from 0 to simulation_duration_backup with new strategies
                        utils.set_hour_shift(i)
                        env.reset()
                        env.prepare()
                        env.put(0, self.prepare_strategy_comparison, ground_stations=self.ground_stations, flows=flows)#, traffic_matrix=traffic_matrix)
                        env.put(0, self.sample_strategy_comparison, ground_stations=self.ground_stations, flows=flows)
                        env.put(0, self.end_strategy_comparison, ground_stations=self.ground_stations, flows=flows)
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
                            flows = {}
                            env.put(0, self.prepare_link_occupation_analysis, ground_stations=self.ground_stations, flows=flows, traffic_matrix=traffic_matrix) #put event prepare_link_occupation_analysis with 0 delay (executed as first) and pass as params gs, flows & traffic matrix
                            env.put(constants.SIMULATION_DURATION, self.sample_link_occupation_analysis, satellites=self.satellites, ground_stations=self.ground_stations, flows=flows) #put event that store data for  analysis at the end of simulation (constants.SIMULATION_DURATION) with params
                            env.put(constants.SIMULATION_DURATION, self.end_link_occupation_analysis, ground_stations=self.ground_stations, flows=flows) #put event end links occupation analysis with params at the end of simulation
                            env.start() #starts the simulation with the events inserted by env.put command
                utils.set_hour_shift(0)
                constants.TOTAL_VOLUME_OF_TRAFFIC = total_traffic_backup
            #case 3
            case AnalysisMetric.DELIVERED_DROPPED_RATIO: #poco senso con Centralized Route #va a rieseguire per ogni strategia ripartendo da 1 Mb e aggiungendo 1 Mb di traffico per ogni ciclio su tutte le strategie
                total_traffic_backup = constants.TOTAL_VOLUME_OF_TRAFFIC
                self.prepare_results_for_delivered_dropped_ratio()
                
                volumes = [10] ####
                for volume in volumes: ####
                #for volume in range(1, total_traffic_backup + 1, 1): #Aumenta sempre più il volume del traffico immesso in rete con range(from 1, to total_traffic_backup, with steps of 1)
                    constants.TOTAL_VOLUME_OF_TRAFFIC = volume
                    traffic_matrix = get_traffic_matrix([gs.get_name() for gs in self.ground_stations.values()])
                    print(traffic_matrix)
                    #for strategy in Strategy:
                    for strategy in [#Strategy.BASELINE_DIJKSTRA,
                                  #Strategy.POSITION_GUESSING_NO_LB,
                                  #Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                  #Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                  #Strategy.POSITION_SHARING_NO_LB,
                                  Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                                  #Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                  #Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
                                  #Strategy.POSITION_AND_STATE_SHARING_TWO_HOPS,
                                  #Strategy.POSITION_SHARING_COST_BALANCING,
                                  #Strategy.SOURCE_ROUTING_NO_LB,
                                  #Strategy.NODE_DISJOINT_SOURCE_ROUTING,
                                  #Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
                                  #Strategy.EDGE_DISJOINT_SOURCE_ROUTING,
                                  #Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                  #Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_ON_SATURATED_LINK,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_ON_SATURATED_LINK,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK
                                  ]:
                        env.reset()
                        constants.ROUTING_STRATEGY = strategy
                        env.prepare()
                        flows = {}
                        env.put(0, self.prepare_delivered_dropped_ratio, ground_stations=self.ground_stations, flows=flows, traffic_matrix=traffic_matrix)
                        env.put(constants.SIMULATION_DURATION, self.sample_delivered_dropped_ratio, ground_stations=self.ground_stations, flows=flows)
                        env.put(constants.SIMULATION_DURATION, self.end_delivered_dropped_ratio, ground_stations=self.ground_stations, flows=flows)
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
                for strategy in [Strategy.BASELINE_DIJKSTRA,
                                  Strategy.POSITION_GUESSING_NO_LB,
                                  #Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                  #Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                  Strategy.POSITION_SHARING_NO_LB,
                                  Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                                  Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                  Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
                                  Strategy.POSITION_AND_STATE_SHARING_TWO_HOPS,
                                  Strategy.POSITION_SHARING_COST_BALANCING,
                                  Strategy.SOURCE_ROUTING_NO_LB,
                                  #Strategy.NODE_DISJOINT_SOURCE_ROUTING,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
                                  #Strategy.EDGE_DISJOINT_SOURCE_ROUTING,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_ON_SATURATED_LINK,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_ON_SATURATED_LINK,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK
                                  ]:
                    constants.ROUTING_STRATEGY = strategy
                    for time in neighbors_update_times:
                        constants.SATELLITE_NEIGHBORS_UPDATE_TIME = time #each loop select a different update time
                        constants.TOPOLOGY_UPDATE_TIME = min(30, constants.SATELLITE_NEIGHBORS_UPDATE_TIME) #update topology_update time to min between 30 secs or neighbors update time
                        for i in range(0, 10): #use 10 hours range variation 
                            utils.set_hour_shift(i)
                            env.reset()
                            env.prepare()
                            flows = {}
                            env.put(0, self.prepare_control_traffic_comparison, ground_stations=self.ground_stations, flows=flows, traffic_matrix=traffic_matrix)
                            env.put(constants.SIMULATION_DURATION, self.sample_control_traffic_comparison, ground_stations=self.ground_stations, flows=flows, neighbors_update_time=time)
                            env.put(constants.SIMULATION_DURATION, self.end_control_traffic_comparison, ground_stations=self.ground_stations, flows=flows)
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
                        flows = {}
                        env.put(0, self.prepare_weight_sensitivity_analysis, ground_stations=self.ground_stations, flows=flows, traffic_matrix=traffic_matrix)
                        env.put(constants.SIMULATION_DURATION, self.sample_weight_sensitivity_analysis, satellites=self.satellites, ground_stations=self.ground_stations, flows=flows)
                        env.put(constants.SIMULATION_DURATION, self.end_weight_sensitivity_analysis, ground_stations=self.ground_stations, flows=flows)
                        env.start()
                utils.set_hour_shift(0)
                constants.ROUTING_STRATEGY = strategy_backup
            #case 6
            case AnalysisMetric.TIME_PASSING_SIMULATION: #simulation for testing strategy's behaviour during time
                strategy_backup = constants.ROUTING_STRATEGY
                traffic_matrix = get_traffic_matrix([gs.get_name() for gs in self.ground_stations.values()])
                self.prepare_results_for_time_passing_simulation()
                for strategy in [Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB]: #could use some different strategies to test them during time
                    constants.ROUTING_STRATEGY = strategy
                    flows = {}
                    env.reset()
                    env.prepare()
                    env.put(0, self.prepare_time_passing_simulation, ground_stations=self.ground_stations, flows=flows, traffic_matrix=traffic_matrix)
                    for i in range(1, constants.SIMULATION_DURATION + 1): #for each second of simulation
                        env.put(i, self.sample_time_passing_simulation, ground_stations=self.ground_stations, flows=flows) #obtain sample of gs, flows and variables
                    env.put(constants.SIMULATION_DURATION, self.end_time_passing_simulation, ground_stations=self.ground_stations, flows=flows)
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

    def prepare_results_for_comparison(self, ground_stations):
        self.results = {}
        for source in ground_stations.values():
            for destination in ground_stations.values():
                if source == destination: continue
                self.results[source.get_name() + ' - ' + destination.get_name()] = { #create a key in self.result made by GSsource-GSdestination
                    Strategy.BASELINE_DIJKSTRA.name : {},
                    #Strategy.POSITION_GUESSING_NO_LB.name : {},
                    #Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK.name : {},
                    #Strategy.POSITION_GUESSING_PROGRESSIVE_LB.name : {},
                    #Strategy.POSITION_SHARING_NO_LB.name : {},
                    #Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK.name : {},
                    #Strategy.POSITION_SHARING_PROGRESSIVE_LB.name : {},
                    #Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB.name : {},
                    #Strategy.POSITION_AND_STATE_SHARING_TWO_HOPS.name : {},
                    #Strategy.POSITION_SHARING_COST_BALANCING.name : {},
                    Strategy.SOURCE_ROUTING_NO_LB.name : {}, #key that will contain results for source routing without load balancing
                    Strategy.NODE_DISJOINT_SOURCE_ROUTING.name : {},
                    Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB.name : {},
                    Strategy.EDGE_DISJOINT_SOURCE_ROUTING.name : {},
                    Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB.name : {},
                    Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING.name : {},
                    Strategy.NODE_DISJOINT_SOURCE_ROUTING_ON_SATURATED_LINK.name : {},
                    Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK.name : {},
                    Strategy.EDGE_DISJOINT_SOURCE_ROUTING_ON_SATURATED_LINK.name : {},
                    Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK.name : {}
                }
                for strategy in self.results[source.get_name() + ' - ' + destination.get_name()].keys(): #for every strategy (even dijkstra) 
                    self.results[source.get_name() + ' - ' + destination.get_name()][strategy] = {
                        'successful' : [], #store succesful routing
                        'failed' : 0, #count all failed routings
                        'distance' : [] #store the travelled distance
                    }

    def prepare_strategy_comparison(self, kwargs): #prepare the comparison among strategies
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        #traffic_matrix = kwargs['traffic_matrix']
        # Genera tutte le coppie source-destination (GS -> GS), poi le mescola
        #all_pairs = list(permutations(ground_stations.values(), 2))
        #random.shuffle(all_pairs)
        for source in ground_stations.values():
        #for source, destination in all_pairs:
            #gs_traffic_details = traffic_matrix[source.get_name()] #for every source store in a dictionary the outgoing traffic from each source GS with destination and traffic
            #traffic_rate = gs_traffic_details[destination.get_name()]
            for destination in ground_stations.values():
            #for destination_name in gs_traffic_details: #for each destination
                #destination = ground_stations[destination_name.upper()]
                if source == destination: continue
                flow = utils.create_new_flow((destination.lat, destination.lon), 0.4) #traffic_rate) #0.5 medium, create a flow with 0.5 initial traffic rate
                flows[source.get_name() + ' - ' + destination.get_name()] = flow  #store the flow in dictionary flows as: flows = {"GS1 - GS2": <Flow object>, "GS1 - GS3": <Flow object>,...}
                if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_NO_LB,
                                    Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                    Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                    Strategy.POSITION_SHARING_NO_LB,
                                    Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                                    Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                    Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
                                    Strategy.POSITION_AND_STATE_SHARING_TWO_HOPS,
                                    Strategy.POSITION_SHARING_COST_BALANCING]:
                    source.send_flow(flow) #send flow to destination for distributed strategies
                if constants.ROUTING_STRATEGY in [Strategy.BASELINE_DIJKSTRA,
                                    Strategy.SOURCE_ROUTING_NO_LB,
                                    Strategy.NODE_DISJOINT_SOURCE_ROUTING,
                                    Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
                                    Strategy.EDGE_DISJOINT_SOURCE_ROUTING,
                                    Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                    Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING,
                                    Strategy.NODE_DISJOINT_SOURCE_ROUTING_ON_SATURATED_LINK,
                                    Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,
                                    Strategy.EDGE_DISJOINT_SOURCE_ROUTING_ON_SATURATED_LINK,
                                    Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK]:
                    #print("PARTITO CENTRALIZED ROUTING")
                    source.start_centralized_routing(flow, env.ground_stations) #send flow to destination for centralized strategies

    def sample_strategy_comparison(self, kwargs): #store perferomance data for comparison
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                if source == destination: continue
                flow = flows[source.get_name() + ' - ' + destination.get_name()] #store the flow obtained by key source-destination in the dictionary flows
                if destination.is_incoming_flow_alive(flow): #if the flow is incoming in destination
                    destination.get_flow_info(flow, until=utils.get_current_time()) #obtain flow infos until the time of the current simulation
                    print(f"Routing strategy's shortest path from {source.get_name()} to {destination.get_name()}: ", [sat.get_name() for sat in flow.paths[-1]])
                    print(f"Routing strategy's shortest path length from {source.get_name()} to {destination.get_name()}: ", len(flow.paths[-1]), "hops.")
                    self.results[source.get_name() + ' - ' + destination.get_name()][constants.ROUTING_STRATEGY.name]['successful'].append(len(flow.paths[-1])) #store length (as steps) of successful paths
                    self.results[source.get_name() + ' - ' + destination.get_name()][constants.ROUTING_STRATEGY.name]['distance'].append(flow.travelled_distance) #store the travelled distance 
                else:
                    print(f"Failed to route flow to destination from {source.get_name()} to {destination.get_name()}.") #error message
                    self.results[source.get_name() + ' - ' + destination.get_name()][constants.ROUTING_STRATEGY.name]['failed'] += 1 #increase the counter of failed strategies for the specific source-destination key

    def end_strategy_comparison(self, kwargs): #stop the comparison closing the flows
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                if source == destination: continue
                flow = flows[source.get_name() + ' - ' + destination.get_name()] #store the flow obtained by key source-destination in the dictionary flows
                source.close_outgoing_flow(flow) #close outgoing flows from source GS
        flows.clear() #after closing all active flows, the dictionary flows is cleared for future simulations
    

    #prepare the dictionary for avarage link occupation analysis
    def prepare_results_for_average_link_occupation_analysis(self):
        self.results = {}
        for s in [Strategy.POSITION_GUESSING_NO_LB,
                                  Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                  Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                  Strategy.POSITION_SHARING_NO_LB,
                                  Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                                  Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                  Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
                                  Strategy.POSITION_AND_STATE_SHARING_TWO_HOPS,
                                  Strategy.POSITION_SHARING_COST_BALANCING,
                                  Strategy.BASELINE_DIJKSTRA,
                                  Strategy.SOURCE_ROUTING_NO_LB,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_ON_SATURATED_LINK,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_ON_SATURATED_LINK,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK
                                  ]:
        #for s in Strategy:
            self.results[s.name] = {
                'average_link_occupation' : [],
                'involved_satellites' : [],
                'cumulative_dropped_data' : [],
                'volume_of_traffic' : []
            }

    def prepare_link_occupation_analysis(self, kwargs): #prepare for the link occupation analysis
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        traffic_matrix = kwargs['traffic_matrix']
        for source in ground_stations.values():
            gs_traffic_details = traffic_matrix[source.get_name()] #for every source store in a dictionary the outgoing traffic from each source GS with destination and traffic
            for destination_name in gs_traffic_details: #for each destination
                destination = ground_stations[destination_name.upper()] #store GS destinations as Upper case
                flow = utils.create_new_flow((destination.lat, destination.lon), gs_traffic_details[destination_name]) #create flow
                flows[source.get_name() + ' - ' + destination.get_name()] = flow #flow store in dictionary flows
                if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_NO_LB,
                                  Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                  Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                  Strategy.POSITION_SHARING_NO_LB,
                                  Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                                  Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                  Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
                                  Strategy.POSITION_AND_STATE_SHARING_TWO_HOPS,
                                  Strategy.POSITION_SHARING_COST_BALANCING]:
                    source.send_flow(flow) #send flow to destination for distributed strategies
                if constants.ROUTING_STRATEGY in [Strategy.BASELINE_DIJKSTRA,
                                  Strategy.SOURCE_ROUTING_NO_LB,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_ON_SATURATED_LINK,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_ON_SATURATED_LINK,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK]:
                    source.start_centralized_routing(flow, env.ground_stations) #send flow to destination for centralized strategies
                #source.send_flow(flow) #send flow

    def sample_link_occupation_analysis(self, kwargs): #analyze and store avarage link occupation
        satellites: dict = kwargs['satellites']
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        all_sats_and_link_occupations = self._get_satellites_and_link_occupations_for_links_involved_in_flow_forwarding(None, satellites) #store satellite and link occupations during the transmission
        average = statistics.mean([link_occupation for _, link_occupation in all_sats_and_link_occupations]) #calculate mean occupation of links
        involved_satellites = len(set([sat_name for sat_name, _ in all_sats_and_link_occupations])) #calculate the number of involved hops
        self.results[constants.ROUTING_STRATEGY.name]['average_link_occupation'].append(average) #store the values
        self.results[constants.ROUTING_STRATEGY.name]['involved_satellites'].append(involved_satellites)
        self.results[constants.ROUTING_STRATEGY.name]['volume_of_traffic'].append(constants.TOTAL_VOLUME_OF_TRAFFIC)
        
        dropped_data = 0
        for source in ground_stations.values(): #for every couple of source and destination
            for destination in ground_stations.values():
                flow = flows[source.get_name() + ' - ' + destination.get_name()] #retrieve a specific flow from flows using source and destination 
                dropped_data += destination.get_flow_info(flow, until = utils.get_current_time())[2] #calculate dropped data getting flow info as the [2] that corresponds to dropped data variable of the flow
        self.results[constants.ROUTING_STRATEGY.name]['cumulative_dropped_data'].append(dropped_data)
        print(f"Average link occupation: {average}. {involved_satellites} satellites involved in routing. Cumulative dropped data: {dropped_data}")

    def end_link_occupation_analysis(self, kwargs): #stops the analysis on link occupation
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flow = flows[source.get_name() + ' - ' + destination.get_name()]
                source.close_outgoing_flow(flow) #close the outgoing flows of GS

    def _get_satellites_and_link_occupations_for_links_involved_in_flow_forwarding(self, flow_id: int, satellites): #get infos about satellite and link occupation between satellites 
        all_sats_and_link_occupations = []
        for name, sat in satellites.items(): #for every satellite extract name and item (sat)
            if sat.flows.values(): #if there are flows
                for f, link in sat.flows.values(): #for every flow (f) and link in sat.flows
                    if isinstance(link, LaserLink): #if the link it's a laserlink
                        if flow_id == None or f.id == flow_id: #if Flow_id is None(there is no specified flow) we want infos about all flows on satellite OR if equal to flow_id param we want infos about that specific flow
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

    def prepare_delivered_dropped_ratio(self, kwargs): #prepare to analyze ratio between delivered and dropped data
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        traffic_matrix = kwargs['traffic_matrix']
        for source in ground_stations.values(): #for every source in GS
            gs_traffic_details = traffic_matrix[source.get_name()] #dictionary that store and access to traffic matrix info using source's name as key
            for destination_name in gs_traffic_details: #for every destination
                destination = ground_stations[destination_name.upper()]
                flow = utils.create_new_flow((destination.lat, destination.lon), gs_traffic_details[destination_name]) #create flow
                flows[source.get_name() + ' - ' + destination.get_name()] = flow
                if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_NO_LB,
                                    Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                    Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                    Strategy.POSITION_SHARING_NO_LB,
                                    Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                                    Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                    Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
                                    Strategy.POSITION_AND_STATE_SHARING_TWO_HOPS,
                                    Strategy.POSITION_SHARING_COST_BALANCING]:
                    source.send_flow(flow) #send flow to destination for distributed strategies
                if constants.ROUTING_STRATEGY in [Strategy.BASELINE_DIJKSTRA,
                                    Strategy.SOURCE_ROUTING_NO_LB,
                                    Strategy.NODE_DISJOINT_SOURCE_ROUTING,
                                    Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
                                    Strategy.EDGE_DISJOINT_SOURCE_ROUTING,
                                    Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                    Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING,
                                    Strategy.NODE_DISJOINT_SOURCE_ROUTING_ON_SATURATED_LINK,
                                    Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,
                                    Strategy.EDGE_DISJOINT_SOURCE_ROUTING_ON_SATURATED_LINK,
                                    Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK]:
                    #print("PARTITO CENTRALIZED ROUTING")
                    source.start_centralized_routing(flow, env.ground_stations) #send flow to destination for centralized strategies

    def sample_delivered_dropped_ratio(self, kwargs): #analyze and store delivered & dropped ratio
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        
        delivered_data = 0
        dropped_data = 0
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flow = flows[source.get_name() + ' - ' + destination.get_name()] #obtain the flow with selected source-destination
                _, delivered, dropped = destination.get_flow_info(flow, until = utils.get_current_time()) #total_data_sent/total_data_delivered/total_data_dropped (the first one isn't used)
                delivered_data += delivered
                dropped_data += dropped
        #store the results
        self.results[constants.ROUTING_STRATEGY.name]['delivered'].append(delivered_data)
        self.results[constants.ROUTING_STRATEGY.name]['dropped'].append(dropped_data)
        self.results[constants.ROUTING_STRATEGY.name]['volume_of_traffic'].append(constants.TOTAL_VOLUME_OF_TRAFFIC)

    def end_delivered_dropped_ratio(self, kwargs): #stops the analysis on delivered & dropped ratio
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flow = flows[source.get_name() + ' - ' + destination.get_name()]
                source.close_outgoing_flow(flow) #close outgoing flows

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

    def prepare_control_traffic_comparison(self, kwargs): #prepare to analyze a comparison of traffic
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        traffic_matrix = kwargs['traffic_matrix']
        for source in ground_stations.values():
            gs_traffic_details = traffic_matrix[source.get_name()]
            for destination_name in gs_traffic_details:
                destination = ground_stations[destination_name.upper()]
                flow = utils.create_new_flow((destination.lat, destination.lon), gs_traffic_details[destination_name]) #create flow
                flows[source.get_name() + ' - ' + destination.get_name()] = flow
                source.send_flow(flow) #send flow

    def sample_control_traffic_comparison(self, kwargs): #analyze and store traffic comparison
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        neighbors_update_time = kwargs['neighbors_update_time']
        
        delivered_data = 0
        dropped_data = 0
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flow = flows[source.get_name() + ' - ' + destination.get_name()] #obtain the flow with selected source-destination
                _, delivered, dropped = destination.get_flow_info(flow, until = utils.get_current_time()) #total_data_sent/total_data_delivered/total_data_dropped (the first one isn't used)
                delivered_data += delivered
                dropped_data += dropped
        #store the results
        self.results[constants.ROUTING_STRATEGY.name][neighbors_update_time]['delivered'].append(delivered_data)
        self.results[constants.ROUTING_STRATEGY.name][neighbors_update_time]['dropped'].append(dropped_data)
        self.results[constants.ROUTING_STRATEGY.name][neighbors_update_time]['control_traffic'].append(env.control_traffic_data)

    def end_control_traffic_comparison(self, kwargs): #stop the analysis of traffic comparison
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flow = flows[source.get_name() + ' - ' + destination.get_name()]
                source.close_outgoing_flow(flow) #close flow

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

    def prepare_weight_sensitivity_analysis(self, kwargs): #prepare to analyze the weight sensitivity
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        traffic_matrix = kwargs['traffic_matrix']
        for source in ground_stations.values():
            gs_traffic_details = traffic_matrix[source.get_name()]
            for destination_name in gs_traffic_details:
                destination = ground_stations[destination_name.upper()]
                flow = utils.create_new_flow((destination.lat, destination.lon), gs_traffic_details[destination_name]) #create flow
                flows[source.get_name() + ' - ' + destination.get_name()] = flow
                source.send_flow(flow) #send flow

    def sample_weight_sensitivity_analysis(self, kwargs): #analyze and store weight sensitivity
        satellites: dict = kwargs['satellites']
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        all_sats_and_link_occupations = self._get_satellites_and_link_occupations_for_links_involved_in_flow_forwarding(None, satellites) #store satellite and link occupation between satellites
        average = statistics.mean([link_occupation for _, link_occupation in all_sats_and_link_occupations]) #calculate mean occupation
        involved_satellites = len(set([sat_name for sat_name, _ in all_sats_and_link_occupations])) #calculate amount of involved satellite
        self.results[constants.LOAD_BALANCING_WEIGHT_FACTOR]['average_link_occupation'].append(average) #store the results
        self.results[constants.LOAD_BALANCING_WEIGHT_FACTOR]['involved_satellites'].append(involved_satellites)
        self.results[constants.LOAD_BALANCING_WEIGHT_FACTOR]['volume_of_traffic'].append(constants.TOTAL_VOLUME_OF_TRAFFIC)
        
        dropped_data = 0
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flow = flows[source.get_name() + ' - ' + destination.get_name()] #retrieve a specific flow from flows using source and destination
                dropped_data += destination.get_flow_info(flow, until = utils.get_current_time())[2] #calculate dropped data getting flow info as the [2] that corresponds to dropped data variable of the flow
        self.results[constants.LOAD_BALANCING_WEIGHT_FACTOR]['cumulative_dropped_data'].append(dropped_data) #store data under the key of load balancing weight factor
        print(f"Average link occupation: {average}. {involved_satellites} satellites involved in routing. Cumulative dropped data: {dropped_data}")

    def end_weight_sensitivity_analysis(self, kwargs): #stop analysis of weight sensitivity
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flow = flows[source.get_name() + ' - ' + destination.get_name()]
                source.close_outgoing_flow(flow) #close flow

    #prepare the dictionary to analyze the simulation during time
    def prepare_results_for_time_passing_simulation(self):
        self.results = {}
        for s in [Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB]:
            self.results[s.name] = {
                'delivered' : [],
                'dropped' : [],
                'distance' : []
            }

    def prepare_time_passing_simulation(self, kwargs): #prepare to analyze simulation on time passing
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        traffic_matrix = kwargs['traffic_matrix']
        for source in ground_stations.values():
            gs_traffic_details = traffic_matrix[source.get_name()]
            for destination_name in gs_traffic_details:
                destination = ground_stations[destination_name.upper()]
                flow = utils.create_new_flow((destination.lat, destination.lon), gs_traffic_details[destination_name])
                flows[source.get_name() + ' - ' + destination.get_name()] = flow
                source.send_flow(flow)

    def sample_time_passing_simulation(self, kwargs): #analyze and store the data from simulation during a period of time
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        
        delivered_data = 0
        dropped_data = 0
        distance_data = 0
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flow = flows[source.get_name() + ' - ' + destination.get_name()]
                _, delivered, dropped = destination.get_flow_info(flow, until = utils.get_current_time())
                delivered_data += delivered
                dropped_data += dropped
                distance_data += flow.travelled_distance
        distance_data /= len(flows) #calculate the avarage distance travelled, dividing by number of flows
        #store the results
        self.results[constants.ROUTING_STRATEGY.name]['delivered'].append(delivered_data)
        self.results[constants.ROUTING_STRATEGY.name]['dropped'].append(dropped_data)
        self.results[constants.ROUTING_STRATEGY.name]['distance'].append(distance_data)

    def end_time_passing_simulation(self, kwargs): #stop the analysis of the dimulation during time
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flow = flows[source.get_name() + ' - ' + destination.get_name()]
                source.close_outgoing_flow(flow) #close flow
    