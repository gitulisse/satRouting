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

    def analyze(self, metric: AnalysisMetric):
        match metric:
            #case 1
            case AnalysisMetric.COMPARISON_WITH_DIJKSTRA:
                simulation_duration_backup = constants.SIMULATION_DURATION
                constants.SIMULATION_DURATION = 1
                self.prepare_results_for_comparison(ground_stations=self.ground_stations)
                for strategy in [Strategy.BASELINE_DIJKSTRA,
                                  #Strategy.POSITION_GUESSING_NO_LB,
                                  #Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                  #Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                  #Strategy.POSITION_SHARING_NO_LB,
                                  #Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                                  #Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                  #Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
                                  #Strategy.POSITION_AND_LOAD_STATE_SHARING_TWO_HOPS,
                                  Strategy.SOURCE_ROUTING_BY_HOP_NO_LB,
                                  Strategy.SOURCE_ROUTING_BY_LENGTH_NO_LB,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING
                                  ]:
                    constants.ROUTING_STRATEGY = strategy 
                    flows = {}
                    for i in range(0, simulation_duration_backup):
                        utils.set_hour_shift(i)
                        env.reset()
                        env.prepare()
                        env.put(0, self.prepare_strategy_comparison, ground_stations=self.ground_stations, flows=flows)
                        env.put(0, self.sample_strategy_comparison, ground_stations=self.ground_stations, flows=flows)
                        env.put(0, self.end_strategy_comparison, ground_stations=self.ground_stations, flows=flows)
                        env.start()
                utils.set_hour_shift(0)
                constants.SIMULATION_DURATION = simulation_duration_backup

            #case 2
            case AnalysisMetric.AVERAGE_LINK_OCCUPATION:
                total_traffic_backup = constants.TOTAL_VOLUME_OF_TRAFFIC
                self.prepare_results_for_average_link_occupation_analysis()

                for volume in range(1, total_traffic_backup + 1, 1): #20 range(from 1, to total_traffic_backup, with steps of 1)
                    constants.TOTAL_VOLUME_OF_TRAFFIC = volume
                    traffic_matrix = get_traffic_matrix([gs.get_name() for gs in self.ground_stations.values()])
                    print(traffic_matrix)
                    for strategy in [#Strategy.BASELINE_DIJKSTRA,
                                  #Strategy.POSITION_GUESSING_NO_LB,
                                  #Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                  #Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                  #Strategy.POSITION_SHARING_NO_LB,
                                  #Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                                  #Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                  #Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
                                  #Strategy.POSITION_AND_LOAD_STATE_SHARING_TWO_HOPS,
                                  Strategy.SOURCE_ROUTING_BY_HOP_NO_LB,
                                  Strategy.SOURCE_ROUTING_BY_LENGTH_NO_LB,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING
                                  ]:
                        for i in range(0, 10):
                            utils.set_hour_shift(i)
                            env.reset()
                            constants.ROUTING_STRATEGY = strategy
                            env.prepare()
                            flows = {}
                            env.put(0, self.prepare_link_occupation_analysis, ground_stations=self.ground_stations, flows=flows, traffic_matrix=traffic_matrix)
                            env.put(constants.SIMULATION_DURATION, self.sample_link_occupation_analysis, satellites=self.satellites, ground_stations=self.ground_stations, flows=flows)
                            env.put(constants.SIMULATION_DURATION, self.end_link_occupation_analysis, ground_stations=self.ground_stations, flows=flows)
                            env.start()
                utils.set_hour_shift(0)
                constants.TOTAL_VOLUME_OF_TRAFFIC = total_traffic_backup

            #case 3
            case AnalysisMetric.DELIVERED_DROPPED_RATIO:
                total_traffic_backup = constants.TOTAL_VOLUME_OF_TRAFFIC
                self.prepare_results_for_delivered_dropped_ratio()
                
                volumes = [10]
                for volume in volumes:
                    constants.TOTAL_VOLUME_OF_TRAFFIC = volume
                    traffic_matrix = get_traffic_matrix([gs.get_name() for gs in self.ground_stations.values()])
                    print(traffic_matrix)
                    for strategy in [#Strategy.BASELINE_DIJKSTRA,
                                  #Strategy.POSITION_GUESSING_NO_LB,
                                  #Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                  #Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                  #Strategy.POSITION_SHARING_NO_LB,
                                  Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                                  #Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                  #Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
                                  #Strategy.POSITION_AND_STATE_SHARING_TWO_HOPS,
                                  #Strategy.SOURCE_ROUTING_BY_HOP_NO_LB,
                                  #Strategy.SOURCE_ROUTING_BY_LENGTH_NO_LB,
                                  #Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
                                  #Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                  #Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING
                                  ]:
                        env.reset()
                        constants.ROUTING_STRATEGY = strategy
                        env.prepare()
                        flows = {}
                        env.put(0, self.prepare_delivered_dropped_ratio, ground_stations=self.ground_stations, flows=flows, traffic_matrix=traffic_matrix)
                        env.put(constants.SIMULATION_DURATION, self.sample_delivered_dropped_ratio, ground_stations=self.ground_stations, flows=flows)
                        env.put(constants.SIMULATION_DURATION, self.end_delivered_dropped_ratio, ground_stations=self.ground_stations, flows=flows)
                        env.start()
                constants.TOTAL_VOLUME_OF_TRAFFIC = total_traffic_backup

            #case 4
            case AnalysisMetric.CONTROL_TRAFFIC_COMPARISON:
                neighbors_update_time_backup = constants.SATELLITE_NEIGHBORS_UPDATE_TIME
                topology_update_backup = constants.TOPOLOGY_UPDATE_TIME
                neighbors_update_times = [5, 10, 15, 20, 30, 60]
                self.prepare_results_for_control_traffic_comparison(neighbors_update_times)
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
                                  Strategy.POSITION_AND_LOAD_STATE_SHARING_TWO_HOPS,
                                  Strategy.SOURCE_ROUTING_BY_HOP_NO_LB,
                                  #Strategy.SOURCE_ROUTING_BY_LENGTH_NO_LB,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING
                                  ]:
                    constants.ROUTING_STRATEGY = strategy
                    for time in neighbors_update_times:
                        constants.SATELLITE_NEIGHBORS_UPDATE_TIME = time
                        constants.TOPOLOGY_UPDATE_TIME = min(30, constants.SATELLITE_NEIGHBORS_UPDATE_TIME)
                        for i in range(0, 10):
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
            case AnalysisMetric.WEIGHT_SENSITIVITY_ANALYSIS:
                strategy_backup = constants.ROUTING_STRATEGY
                constants.ROUTING_STRATEGY = Strategy.POSITION_AND_LOAD_STATE_SHARING_TWO_HOPS
                weights = [0.1, 0.25, 0.37, 0.5, 0.63, 0.75, 0.9]
                self.prepare_results_for_weight_sensitivity_analysis(weights)
                traffic_matrix = get_traffic_matrix([gs.get_name() for gs in self.ground_stations.values()])
                print(traffic_matrix)
                for weight in weights:
                    constants.LOAD_BALANCING_WEIGHT_FACTOR = weight
                    for i in range(0, 2):
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
            case AnalysisMetric.TIME_PASSING_SIMULATION:
                strategy_backup = constants.ROUTING_STRATEGY
                traffic_matrix = get_traffic_matrix([gs.get_name() for gs in self.ground_stations.values()])
                self.prepare_results_for_time_passing_simulation()
                for strategy in [Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB]:
                    constants.ROUTING_STRATEGY = strategy
                    flows = {}
                    env.reset()
                    env.prepare()
                    env.put(0, self.prepare_time_passing_simulation, ground_stations=self.ground_stations, flows=flows, traffic_matrix=traffic_matrix)
                    for i in range(1, constants.SIMULATION_DURATION + 1):
                        env.put(i, self.sample_time_passing_simulation, ground_stations=self.ground_stations, flows=flows)
                    env.put(constants.SIMULATION_DURATION, self.end_time_passing_simulation, ground_stations=self.ground_stations, flows=flows)
                    env.start()
                constants.ROUTING_STRATEGY = strategy_backup

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
                self.results[source.get_name() + ' - ' + destination.get_name()] = {
                    Strategy.BASELINE_DIJKSTRA.name : {},
                    #Strategy.POSITION_GUESSING_NO_LB.name : {},
                    #Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK.name : {},
                    #Strategy.POSITION_GUESSING_PROGRESSIVE_LB.name : {},
                    #Strategy.POSITION_SHARING_NO_LB.name : {},
                    #Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK.name : {},
                    #Strategy.POSITION_SHARING_PROGRESSIVE_LB.name : {},
                    #Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB.name : {},
                    #Strategy.POSITION_AND_LOAD_STATE_SHARING_TWO_HOPS.name : {},
                    Strategy.SOURCE_ROUTING_BY_HOP_NO_LB.name : {},
                    Strategy.SOURCE_ROUTING_BY_LENGTH_NO_LB.name : {},
                    Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB.name : {},
                    Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB.name : {},
                    Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK.name : {},
                    Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING.name : {}
                }
                for strategy in self.results[source.get_name() + ' - ' + destination.get_name()].keys(): 
                    self.results[source.get_name() + ' - ' + destination.get_name()][strategy] = {
                        'successful' : [], #store succesful routing
                        'failed' : 0, #count all failed routings
                        'distance' : [] #store the travelled distance
                    }

    def prepare_strategy_comparison(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        #traffic_matrix = kwargs['traffic_matrix']
        #Generates all source-destination pairs (GS -> GS), then mixes them
        #all_pairs = list(permutations(ground_stations.values(), 2))
        #random.shuffle(all_pairs)
        for source in ground_stations.values():
        #for source, destination in all_pairs:
            #gs_traffic_details = traffic_matrix[source.get_name()]
            #traffic_rate = gs_traffic_details[destination.get_name()]
            for destination in ground_stations.values():
            #for destination_name in gs_traffic_details: #for each destination
                #destination = ground_stations[destination_name.upper()]
                if source == destination: continue
                flow = utils.create_new_flow((destination.lat, destination.lon), 0.4)
                flows[source.get_name() + ' - ' + destination.get_name()] = flow
                if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_NO_LB,
                                    Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                    Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                    Strategy.POSITION_SHARING_NO_LB,
                                    Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                                    Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                    Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
                                    Strategy.POSITION_AND_LOAD_STATE_SHARING_TWO_HOPS]:
                    source.send_flow(flow)
                if constants.ROUTING_STRATEGY in [Strategy.BASELINE_DIJKSTRA,
                                    Strategy.SOURCE_ROUTING_BY_HOP_NO_LB,
                                    Strategy.SOURCE_ROUTING_BY_LENGTH_NO_LB,
                                    Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
                                    Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                    Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,
                                    Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING]:
                    source.start_centralized_routing(flow, env.ground_stations)

    def sample_strategy_comparison(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                if source == destination: continue
                flow = flows[source.get_name() + ' - ' + destination.get_name()]
                if destination.is_incoming_flow_alive(flow):
                    destination.get_flow_info(flow, until=utils.get_current_time())
                    print(f"Routing strategy's shortest path from {source.get_name()} to {destination.get_name()}: ", [sat.get_name() for sat in flow.paths[-1]])
                    print(f"Routing strategy's shortest path length from {source.get_name()} to {destination.get_name()}: ", len(flow.paths[-1]), "hops.")
                    self.results[source.get_name() + ' - ' + destination.get_name()][constants.ROUTING_STRATEGY.name]['successful'].append(len(flow.paths[-1]))
                    self.results[source.get_name() + ' - ' + destination.get_name()][constants.ROUTING_STRATEGY.name]['distance'].append(flow.travelled_distance) 
                else:
                    print(f"Failed to route flow to destination from {source.get_name()} to {destination.get_name()}.")
                    self.results[source.get_name() + ' - ' + destination.get_name()][constants.ROUTING_STRATEGY.name]['failed'] += 1

    def end_strategy_comparison(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                if source == destination: continue
                flow = flows[source.get_name() + ' - ' + destination.get_name()]
                source.close_outgoing_flow(flow)
        flows.clear()
    
    def prepare_results_for_average_link_occupation_analysis(self):
        self.results = {}
        for s in [#Strategy.POSITION_GUESSING_NO_LB,
                                  #Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                  #Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                  #Strategy.POSITION_SHARING_NO_LB,
                                  #Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                                  #Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                  #Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
                                  #Strategy.POSITION_AND_LOAD_STATE_SHARING_TWO_HOPS,
                                  #Strategy.BASELINE_DIJKSTRA,
                                  Strategy.SOURCE_ROUTING_BY_HOP_NO_LB,
                                  Strategy.SOURCE_ROUTING_BY_LENGTH_NO_LB,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING
                                  ]:
            self.results[s.name] = {
                'average_link_occupation' : [],
                'involved_satellites' : [],
                'cumulative_dropped_data' : [],
                'volume_of_traffic' : []
            }

    def prepare_link_occupation_analysis(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        traffic_matrix = kwargs['traffic_matrix']
        for source in ground_stations.values():
            gs_traffic_details = traffic_matrix[source.get_name()]
            for destination_name in gs_traffic_details:
                destination = ground_stations[destination_name.upper()]
                flow = utils.create_new_flow((destination.lat, destination.lon), gs_traffic_details[destination_name])
                flows[source.get_name() + ' - ' + destination.get_name()] = flow
                if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_NO_LB,
                                  Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                  Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                  Strategy.POSITION_SHARING_NO_LB,
                                  Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                                  Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                  Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
                                  Strategy.POSITION_AND_LOAD_STATE_SHARING_TWO_HOPS]:
                    source.send_flow(flow)
                if constants.ROUTING_STRATEGY in [Strategy.BASELINE_DIJKSTRA,
                                  Strategy.SOURCE_ROUTING_BY_HOP_NO_LB,
                                  Strategy.SOURCE_ROUTING_BY_LENGTH_NO_LB,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING]:
                    source.start_centralized_routing(flow, env.ground_stations)

    def sample_link_occupation_analysis(self, kwargs):
        satellites: dict = kwargs['satellites']
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        all_sats_and_link_occupations = self._get_satellites_and_link_occupations_for_links_involved_in_flow_forwarding(None, satellites)
        average = statistics.mean([link_occupation for _, link_occupation in all_sats_and_link_occupations])
        involved_satellites = len(set([sat_name for sat_name, _ in all_sats_and_link_occupations]))
        self.results[constants.ROUTING_STRATEGY.name]['average_link_occupation'].append(average)
        self.results[constants.ROUTING_STRATEGY.name]['involved_satellites'].append(involved_satellites)
        self.results[constants.ROUTING_STRATEGY.name]['volume_of_traffic'].append(constants.TOTAL_VOLUME_OF_TRAFFIC)
        
        dropped_data = 0
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flow = flows[source.get_name() + ' - ' + destination.get_name()]
                dropped_data += destination.get_flow_info(flow, until = utils.get_current_time())[2]
        self.results[constants.ROUTING_STRATEGY.name]['cumulative_dropped_data'].append(dropped_data)
        print(f"Average link occupation: {average}. {involved_satellites} satellites involved in routing. Cumulative dropped data: {dropped_data}")

    def end_link_occupation_analysis(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flow = flows[source.get_name() + ' - ' + destination.get_name()]
                source.close_outgoing_flow(flow)

    def _get_satellites_and_link_occupations_for_links_involved_in_flow_forwarding(self, flow_id: int, satellites):
        all_sats_and_link_occupations = []
        for name, sat in satellites.items():
            if sat.flows.values():
                for f, link in sat.flows.values():
                    if isinstance(link, LaserLink):
                        if flow_id == None or f.id == flow_id:
                            all_sats_and_link_occupations.append((name, constants.SATELLITE_LINK_CAPACITY - link.get_available_bandwidth()))
        return all_sats_and_link_occupations

    def prepare_results_for_delivered_dropped_ratio(self):
        self.results = {}
        for s in [Strategy.POSITION_GUESSING_NO_LB,
                                  Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                  Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                  Strategy.POSITION_SHARING_NO_LB,
                                  Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                                  Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                  Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
                                  Strategy.POSITION_AND_LOAD_STATE_SHARING_TWO_HOPS,
                                  Strategy.BASELINE_DIJKSTRA,
                                  Strategy.SOURCE_ROUTING_BY_HOP_NO_LB,
                                  Strategy.SOURCE_ROUTING_BY_LENGTH_NO_LB,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING
                                  ]:
            self.results[s.name] = {
                'delivered' : [],
                'dropped' : [],
                'volume_of_traffic' : []
            }

    def prepare_delivered_dropped_ratio(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        traffic_matrix = kwargs['traffic_matrix']
        for source in ground_stations.values():
            gs_traffic_details = traffic_matrix[source.get_name()]
            for destination_name in gs_traffic_details:
                destination = ground_stations[destination_name.upper()]
                flow = utils.create_new_flow((destination.lat, destination.lon), gs_traffic_details[destination_name])
                flows[source.get_name() + ' - ' + destination.get_name()] = flow
                if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_NO_LB,
                                    Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                    Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                    Strategy.POSITION_SHARING_NO_LB,
                                    Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
                                    Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                    Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
                                    Strategy.POSITION_AND_LOAD_STATE_SHARING_TWO_HOPS]:
                    source.send_flow(flow)
                if constants.ROUTING_STRATEGY in [Strategy.BASELINE_DIJKSTRA,
                                    Strategy.SOURCE_ROUTING_BY_HOP_NO_LB,
                                    Strategy.SOURCE_ROUTING_BY_LENGTH_NO_LB,
                                    Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
                                    Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                    Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,
                                    Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING]:
                    source.start_centralized_routing(flow, env.ground_stations)

    def sample_delivered_dropped_ratio(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        delivered_data = 0
        dropped_data = 0
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flow = flows[source.get_name() + ' - ' + destination.get_name()]
                _, delivered, dropped = destination.get_flow_info(flow, until = utils.get_current_time())
                delivered_data += delivered
                dropped_data += dropped
        self.results[constants.ROUTING_STRATEGY.name]['delivered'].append(delivered_data)
        self.results[constants.ROUTING_STRATEGY.name]['dropped'].append(dropped_data)
        self.results[constants.ROUTING_STRATEGY.name]['volume_of_traffic'].append(constants.TOTAL_VOLUME_OF_TRAFFIC)

    def end_delivered_dropped_ratio(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flow = flows[source.get_name() + ' - ' + destination.get_name()]
                source.close_outgoing_flow(flow)

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

    def prepare_control_traffic_comparison(self, kwargs):
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

    def sample_control_traffic_comparison(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        neighbors_update_time = kwargs['neighbors_update_time']
        delivered_data = 0
        dropped_data = 0
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flow = flows[source.get_name() + ' - ' + destination.get_name()]
                _, delivered, dropped = destination.get_flow_info(flow, until = utils.get_current_time())
                delivered_data += delivered
                dropped_data += dropped
        self.results[constants.ROUTING_STRATEGY.name][neighbors_update_time]['delivered'].append(delivered_data)
        self.results[constants.ROUTING_STRATEGY.name][neighbors_update_time]['dropped'].append(dropped_data)
        self.results[constants.ROUTING_STRATEGY.name][neighbors_update_time]['control_traffic'].append(env.control_traffic_data)

    def end_control_traffic_comparison(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flow = flows[source.get_name() + ' - ' + destination.get_name()]
                source.close_outgoing_flow(flow)

    def prepare_results_for_weight_sensitivity_analysis(self, weights: list):
        self.results = {}
        for weight in weights:
            self.results[weight] = {
                'average_link_occupation' : [],
                'involved_satellites' : [],
                'cumulative_dropped_data' : [],
                'volume_of_traffic' : []
            }

    def prepare_weight_sensitivity_analysis(self, kwargs):
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

    def sample_weight_sensitivity_analysis(self, kwargs):
        satellites: dict = kwargs['satellites']
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        all_sats_and_link_occupations = self._get_satellites_and_link_occupations_for_links_involved_in_flow_forwarding(None, satellites)
        average = statistics.mean([link_occupation for _, link_occupation in all_sats_and_link_occupations])
        involved_satellites = len(set([sat_name for sat_name, _ in all_sats_and_link_occupations]))
        self.results[constants.LOAD_BALANCING_WEIGHT_FACTOR]['average_link_occupation'].append(average)
        self.results[constants.LOAD_BALANCING_WEIGHT_FACTOR]['involved_satellites'].append(involved_satellites)
        self.results[constants.LOAD_BALANCING_WEIGHT_FACTOR]['volume_of_traffic'].append(constants.TOTAL_VOLUME_OF_TRAFFIC)
        dropped_data = 0
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flow = flows[source.get_name() + ' - ' + destination.get_name()]
                dropped_data += destination.get_flow_info(flow, until = utils.get_current_time())[2]
        self.results[constants.LOAD_BALANCING_WEIGHT_FACTOR]['cumulative_dropped_data'].append(dropped_data)
        print(f"Average link occupation: {average}. {involved_satellites} satellites involved in routing. Cumulative dropped data: {dropped_data}")

    def end_weight_sensitivity_analysis(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flow = flows[source.get_name() + ' - ' + destination.get_name()]
                source.close_outgoing_flow(flow)

    def prepare_results_for_time_passing_simulation(self):
        self.results = {}
        for s in [Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB]:
            self.results[s.name] = {
                'delivered' : [],
                'dropped' : [],
                'distance' : []
            }

    def prepare_time_passing_simulation(self, kwargs):
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

    def sample_time_passing_simulation(self, kwargs):
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
        distance_data /= len(flows)
        self.results[constants.ROUTING_STRATEGY.name]['delivered'].append(delivered_data)
        self.results[constants.ROUTING_STRATEGY.name]['dropped'].append(dropped_data)
        self.results[constants.ROUTING_STRATEGY.name]['distance'].append(distance_data)

    def end_time_passing_simulation(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        flows: dict = kwargs['flows']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                flow = flows[source.get_name() + ' - ' + destination.get_name()]
                source.close_outgoing_flow(flow)
