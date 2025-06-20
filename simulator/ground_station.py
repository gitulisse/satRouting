import constants
from geopy import distance
from flow import Flow, FlowState
import math
from skyfield.api import Time, Timescale
from routing_action import RoutingAction
from strategy import Strategy
import utils
import dijkstra
#from link import Link, LaserLink, RadioLink
import networkx as nx
import matplotlib.pyplot as plt
import environment as env
import random
from networkx.classes.function import path_weight
from mapping_table import MappingTable
from itertools import chain
import copy

class GroundStation:
    def __init__(self, lat, lon, name, keep_log: bool = True) -> None:
        self.lat = lat
        self.lon = lon
        self.sat = None
        self.serving_population = 0
        self.name = name
        self.satellites = None
        self.gss = None
        self.outgoing_flows: list[Flow, Time, Time] = [] #Flusso, tempo di inizio invio e tempo di fine invio
        self.incoming_flows: list[Flow, Time, Time] = [] #Flusso, tempo di inizio ricezione e tempo di fine ricezione
        self.DEBUG_dropped_incoming_flows: list[(Flow, Time, Time)] = [] #Flusso, tempo di inizio ricezione, tempo di fine ricezione e causa drop
        self.keep_log = keep_log
        self.results = None
        self._graph = None
        self._auxiliary_graph = None
        self.excluded_links = []
        self.link_utilization = {}  #dictionary that maps link to its utilization
        self.destination = None
        self.DEBUG_dropped_flows: list[Flow] = []

    #set satellite
    def set_satellites(self, satellites):
        self.satellites = satellites

    #set GS
    def set_ground_stations(self, ground_stations: dict):
        self.gss = ground_stations
    
    #get latitude of GS
    def get_latitudeGS(self):
        return self.lat
    
    #get longitude of GS
    def get_longitudeGS(self):
        return self.lon
    
    #set serving population
    def add_population_to_serve(self, amount: int):
        self.serving_population += amount

    #connect GS to satellite
    def attach_to_sat(self, sat):
        if sat != self.sat: #check if connected satellite is different from the current satellite (connected to GS) as param
            backup_flows = [] #copy of flows
            for outgoing_flow, _, end_time in self.outgoing_flows: #for the outgoing flows check that end_time is None to copy them
                if end_time == None:
                    backup_flows.append(outgoing_flow)
                    self.close_outgoing_flow(outgoing_flow) #close
            if self.sat != None: 
                self.sat.serving_gs = None #change attribute serving_gs of current satellite to None
            self.sat = sat #change of satellite that is serving the GS
            self.sat.serving_gs = self #connect to GS
            #for flow in backup_flows:
             #   print(f"Flowes to send {flow} ID: {flow.id}, Alias ID: {flow.alias_id} with rate {flow.rate} Gbps. Destination {flow.destination}")
            '''for backup_flow in backup_flows: 
                if constants.ROUTING_STRATEGY in [#Strategy.BASELINE_DIJKSTRA, 
                                  Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                  Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                  Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING,
                                  Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                  Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                  Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                  Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_COSTS_SELECTION]:
                    print(f"-> Backup flow Centr print {backup_flow} id {backup_flow.id} alias {backup_flow.alias_id} rate {backup_flow.rate} destination {backup_flow.destination}")
                    self.drop_flow(backup_flow, FlowState.SATELLITE_CONGESTED) #send the flow to the source GS Routing
                    #self.start_centralized_routing(backup_flow, self.gss) #send the flow to the source GS Routing 
                else:
                    print(f"-> Backup flow Distrib print {backup_flow} id {backup_flow.id} alias {backup_flow.alias_id} rate {backup_flow.rate} destination {backup_flow.destination}")
                    self.send_flow(backup_flow) #send copied flows '''

    #get name
    def get_name(self) -> str:
        return self.name

    #sender of flows from GS to connected satellite
    def send_flow(self, flow: Flow, routing_decisions=None): #optional parameter routing_decisions
        self.outgoing_flows.append((flow, utils.get_current_time(), None)) #add an outgoing flow with current time, None is the time of termination of the flow
        if constants.DEBUG:
            print("----- [OPENING FLOW] on GS", flow, "with ID", flow.id, "alias_ID", flow.alias_id, "from", self.get_name().upper(), "with Rate", flow.rate)# "at time", utils.get_current_time().utc_strftime())
        flow.travelled_distance += utils.get_distance_between_satellite_and_gs(self.sat, self)
        if routing_decisions != None:
            self.sat.open_flow(flow.clone(), routing_decisions) #Port Forwarding branch
        else:
            self.sat.open_flow(flow.clone())

    def close_outgoing_flow(self, flow: Flow):#close the outgoing flow
        if self.keep_log:
            #print(">-< SELF.outgoing_flows", self.outgoing_flows)
            for i, (outgoing_flow, start_time, end_time) in enumerate(self.outgoing_flows):
                if flow == outgoing_flow and flow.alias_id == outgoing_flow.alias_id and flow.rate == outgoing_flow.rate and end_time == None:
                    
                    #if constants.DEBUG:
                     #   for listed_flow in self.outgoing_flows:
                      #      print("SELF.outgoing_flows id", listed_flow[0].id,"and alias_id", listed_flow[0].alias_id)

                    self.outgoing_flows[i] = (outgoing_flow, start_time, utils.get_current_time())
                    #print("outgoing_flows at i index", self.outgoing_flows[i])
                    #outgoing_flow.travelled_distance -= utils.get_distance_between_satellite_and_gs(self.sat, self)
                    outgoing_flow.travelled_distance = 0                    
                    #if constants.DEBUG:
                     #   print("Closed outgoing flow", flow.id, "with alias id", flow.alias_id, "with rate", flow.rate, "at time", utils.get_current_time().utc_strftime())
                    break
        else:
            while self.outgoing_flows.__contains__(flow):
                self.outgoing_flows.remove(flow)
        self.sat.close_flow(flow.clone())

    #metodo di arrivo alla destinazione
    def open_flow(self, flow: Flow): #apre il flow se è alla ground station di destinazione allora copia gli step in path e diventano il percorso attuato
        if flow.destination[0] == self.lat and flow.destination[1] == self.lon:
            flow.paths.append(flow.get_steps())
            flow.state = FlowState.DELIVERED
            self.incoming_flows.append((flow, utils.get_current_time(), None))
            print("----- [DELIVERED FLOW]", flow, "ID", flow.id, "with rate", flow.rate, "Gbps has reached its destination!")# "at time", utils.get_current_time().utc_strftime())
            print("#     Steps obtained:", [step.get_name() for step in flow.get_steps()])
        else:
            self._discard_flow(flow)

    def _discard_flow(self, flow: Flow):
        if constants.DEBUG:
            print("Flow with id", flow.id, "has been discarded on gs", self.get_name())

    def close_flow(self, flow: Flow):
        if self.keep_log:
            for i, (incoming_flow, start_time, end_time) in enumerate(self.incoming_flows):
                if flow == incoming_flow and flow.alias_id == incoming_flow.alias_id and flow.rate == incoming_flow.rate and end_time == None:
                    self.incoming_flows[i] = (incoming_flow, start_time, utils.get_current_time())
                    #if constants.DEBUG:
                     #   print("Closed incoming flow", flow.id, "with alias id", flow.alias_id, "from", self.get_name(), "with rate", flow.rate, "at time", utils.get_current_time().utc_strftime())
                    break
        else:
            while self.incoming_flows.__contains__(flow):
                self.incoming_flows.remove(flow)

    def is_incoming_flow_alive(self, flow: Flow):
        for incoming_flow, _, end_time in self.incoming_flows:
            if flow == incoming_flow:
                if end_time == None:
                    return True
        return False

    def get_flow_info(self, flow: Flow, until: Time, precision: int = 0) -> tuple[float, float, float]:
        total_data_received = 0
        total_data_sent = 0
        total_data_dropped = 0
        flow.paths = []
        sum_travelled_distance = 0 #km
        incoming_flows_count = 0
        for incoming_flow, start_time, end_time in self.incoming_flows:
            if flow == incoming_flow:
                if end_time == None or until - end_time < 0:
                    end_time = until
                active_time_in_seconds = utils.get_seconds_between(start_time, end_time)
                if active_time_in_seconds >= precision:
                    total_data_received += active_time_in_seconds * incoming_flow.rate
                    flow.paths.append(incoming_flow.get_steps())
                    sum_travelled_distance += incoming_flow.travelled_distance
                    incoming_flows_count += 1 
                    #debug 
                    #if constants.DEBUG:
                     #   print("!total received", total_data_received, utils.get_seconds_between(start_time, end_time) * incoming_flow.rate, "incoming for", utils.get_seconds_between(start_time, end_time), "from", start_time.utc_strftime(), "to", end_time.utc_strftime(), "at rate", incoming_flow.rate, "with alias id", incoming_flow.alias_id)
                      #  print("incoming_flow steps...sat", [sat.get_name() for sat in incoming_flow.get_steps()])
        if incoming_flows_count > 0:
            flow.travelled_distance = sum_travelled_distance / incoming_flows_count
            #if constants.DEBUG or not(constants.DEBUG):
            #    print("Average distance travelled by flow", flow.id, "in kms:", flow.travelled_distance)
        for outgoing_flow, start_time, end_time in self.outgoing_flows:
            if flow == outgoing_flow:
                if end_time == None or until - end_time < 0:
                    end_time = until
                active_time_in_seconds = utils.get_seconds_between(start_time, end_time)
                if active_time_in_seconds >= precision:
                    total_data_sent += active_time_in_seconds * outgoing_flow.rate
        for dropped_flow, start_time, end_time in self.DEBUG_dropped_incoming_flows:
            if flow == dropped_flow:
                if end_time == None or until - end_time < 0:
                    end_time = until
                active_time_in_seconds = utils.get_seconds_between(start_time, end_time)
                if active_time_in_seconds >= precision:
                    total_data_dropped += active_time_in_seconds * dropped_flow.rate
                    #Escluso in modo tale da memorizzare solo i path a buon fine nel flow
                    #flow.paths.append(dropped_flow.get_steps())
                    '''
                    if constants.DEBUG:
                        print(total_data_dropped, utils.get_seconds_between(start_time, end_time) * dropped_flow.rate, "dropped for", utils.get_seconds_between(start_time, end_time), "from", start_time.utc_strftime(), "to", end_time.utc_strftime(), "at rate", dropped_flow.rate, "with alias id", dropped_flow.alias_id, "reason", dropped_flow.state)
                        print([sat.get_name() for sat in dropped_flow.get_steps()])
                    '''
        # Stampa tutti i percorsi del flusso
        #print("\nPercorsi per il flusso", flow.id, ":")
        #for idx, path in enumerate(flow.paths):
         #   print(f"Path {idx + 1}: {[sat.get_name() for sat in path]}")
        return (total_data_sent, total_data_received, total_data_dropped)
        
    def DEBUG_get_dropped_flow(self, flow: Flow):
        flow.paths.append(flow.get_steps())
        self.DEBUG_dropped_incoming_flows.append((flow, utils.get_current_time(), None))
        #if constants.DEBUG:
         #   print("Logged opening of dropped flow", flow.id, "with rate", flow.rate, "Mbps at time", utils.get_current_time().utc_strftime())
          #  print("Steps:", [step.get_name() for step in flow.get_steps()])
  
    def DEBUG_close_dropped_flow(self, flow: Flow):
        if self.keep_log:
            for i, (dropped_flow, start_time, end_time) in enumerate(self.DEBUG_dropped_incoming_flows):
                if flow == dropped_flow and flow.alias_id == dropped_flow.alias_id and flow.rate == dropped_flow.rate and end_time == None:
                    self.DEBUG_dropped_incoming_flows[i] = (dropped_flow, start_time, utils.get_current_time())
                    #if constants.DEBUG:
                     #   print("Logged closing of dropped flux", flow.id, "with rate", flow.rate, "Mbps at time", utils.get_current_time().utc_strftime())
                      #  print("Steps in DEBUG_close_dropped_flow:", [step.get_name() for step in flow.get_steps()])
                    break
        else:
            while self.DEBUG_dropped_incoming_flows.__contains__(flow):
                self.DEBUG_dropped_incoming_flows.remove(flow)

    def reattach(self):
        distances = utils.get_closer_satellites(self.satellites, (self.lat, self.lon), False)
        new_sat = self.satellites.get(distances[0]['name'])
        #if constants.DEBUG:
         #   if new_sat != self.sat:
        #print("Attaching Ground Station", self.get_name(), "to Satellite", new_sat.get_name(), "at time", utils.get_current_time().utc_strftime())
        self.attach_to_sat(new_sat)


    #starting point of centralized routing
    def start_centralized_routing(self, flow: Flow, ground_stations):
        self.gss = ground_stations
        flow.source = self
        routing_decisions = self.centralized_route(flow)
        
        if not routing_decisions:
            return 

        routing_decisions = self.extract_separated_decision_lists(routing_decisions) #decisioni annidate estratte

        routing_decisions = [
                sublist for sublist in routing_decisions
                if all(action != RoutingAction.ERROR for action, _, _ in sublist)
            ]
        
        #print(f"> Cleaned Routing decisions for flow at start_centralized_routing {routing_decisions}")
        #self.reset_all_links_capacity(self.satellites.values())
       
        for decision in routing_decisions: #ora che ho tutte le liste di tutti i flussi voglio inviare i singoli flussi con le loro decisioni sulla rete, uno alla volta
            action, partial_flow, link = decision[0]
            #print(f"  +++++      Sending flow {partial_flow} id {partial_flow.id} alias_id {partial_flow.alias_id} rate {partial_flow.rate} to satellite {self.sat.get_name()}")
            #print(f"  +++++      Sending with decisions: {decision}")
            self.send_flow(partial_flow, decision) #send the flow to the source GS

    def centralized_route(self, flow: Flow): 
        routing_decisions = self.basic_centralized_route(flow)
        return routing_decisions

    def basic_centralized_route(self, flow: Flow):
        routing_output = list()
        self.destination = flow.get_ground_station_by_coordinates(flow.destination[0], flow.destination[1], self.gss.values())

        '''if constants.ROUTING_STRATEGY == Strategy.BASELINE_DIJKSTRA:
            #self.prepare_results_for_dijkstra(ground_stations=self.gss)
            dijkstra_shortest_path = self.calculate_dijkstra({'source': self,'destination': self.destination,'satellites': self.satellites})

            if not dijkstra_shortest_path:
                #print("No valid path found for Dijkstra, returning empty routing output.")
                return routing_output
            
            for i in range(len(dijkstra_shortest_path) - 1): #iterates on the path to build che routing_output
                current_node = dijkstra_shortest_path[i]
                next_node = dijkstra_shortest_path[i + 1]
                link = self._get_link_between_nodes(current_node, next_node, self.satellites) #retrieve the link between a node and the next node in the path
                if not link:
                    print(f"Warning: No link found between {current_node} and {next_node}. Skipping.")
                    continue
                action = RoutingAction.FORWARD #determinates the action that must be executed
                routing_output.append((action, flow, link)) #add the action to the decisions
            last_node = dijkstra_shortest_path[-1][0] if isinstance(dijkstra_shortest_path[-1], list) else dijkstra_shortest_path[-1]
            last_link = self._get_link_to_ground_station(last_node, self.destination, self.satellites, self.gss)
            action = RoutingAction.DELIVER
            routing_output.append((action, flow, last_link))
            routing_output = self.adapt_routing_with_single_split(flow, routing_output) #walkthrough simulation of passage
        '''
        if constants.ROUTING_STRATEGY in [Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                            Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB]:

            disjoint_paths = self.calculate_k_disjoint_paths({
                'source': self,
                'destination': self.destination,
                'satellites': self.satellites,
                'flow': flow
            })
            #print("Disjoint paths trovati da CALCULATE K DISJOINT PATHS", disjoint_paths)
            if not disjoint_paths:
                #print("No valid Disjoint paths found, returning empty routing output.")
                return routing_output
            
            probabilities = self.calculate_path_weights_kshortest_disjoint(self._graph, disjoint_paths) #calculate probabilities based on weights of k disjoint paths
            selected_path = self.select_path_with_probabilities(disjoint_paths, probabilities) #select path based on probabilities
            routing_output = self.process_routing_output(selected_path, flow)  #process the output for routing

            #print(f"basic centralized method - routing output {routing_output}")

            #print("ROUTING 1______", routing_output)
            if constants.ROUTING_STRATEGY == Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING:
                routing_output = self.adapt_routing_with_single_split(flow, routing_output)
            if constants.ROUTING_STRATEGY == Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB:
                routing_output = self.adapt_routing_decisions_to_available_link_bandwidth(flow, routing_output) ################ adapt
            #print("ROUTING ******", routing_output)
        
        elif constants.ROUTING_STRATEGY in [Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING,
                                            Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_LB]:

            disjoint_paths = self.calculate_k_disjoint_paths({
                'source': self,
                'destination': self.destination,
                'satellites': self.satellites,
                'flow': flow
            })
            #for path_index, path in enumerate(disjoint_paths): #Debug
            #    print(f"Processing path {path_index + 1}: {path}")
            if not disjoint_paths:
                #print("No valid Disjoint paths found, returning empty routing output.")
                return routing_output
            probabilities = self.calculate_path_weights_kshortest_disjoint(self._graph, disjoint_paths) #calculate probabilities based on weights of k disjoint paths
            selected_path = self.select_path_with_probabilities(disjoint_paths, probabilities) #select path based on probabilities
            routing_output = self.process_routing_output(selected_path, flow) #process the output for routing
            if constants.ROUTING_STRATEGY == Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING:
                routing_output = self.adapt_routing_with_single_split(flow, routing_output)
            if constants.ROUTING_STRATEGY == Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_LB:
                routing_output = self.adapt_routing_decisions_to_available_link_bandwidth(flow, routing_output) ################ adapt

        elif constants.ROUTING_STRATEGY == Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_COSTS_SELECTION:

            disjoint_paths = self.calculate_k_disjoint_paths({
                'source': self,
                'destination': self.destination,
                'satellites': self.satellites,
                'flow': flow
            })
            #Debug
            #for path_index, path in enumerate(disjoint_paths):
            #    print(f"Processing path {path_index + 1}: {path}")
            if not disjoint_paths:
                #print("No valid Disjoint paths found, returning empty routing output.")
                return routing_output
            alpha_values = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
            for alpha in alpha_values:
                costs = self.calculate_path_costs(self._graph, disjoint_paths, self.link_utilization, alpha) #calculate the costs of k paths
                selected_path = self.select_path_based_on_costs(disjoint_paths, costs) #select the path based on the previous costs
                routing_output = self.process_routing_output(selected_path, flow) #process the output for routing  

        elif constants.ROUTING_STRATEGY in [Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                            Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB]:

            disjoint_paths = self.calculate_k_disjoint_paths({
                'source': self,
                'destination': self.destination,
                'satellites': self.satellites,
                'flow': flow
            })

            if not disjoint_paths:
                return routing_output
            probabilities = self.calculate_path_weights_length_shortest_node_disjoint(self._graph, disjoint_paths) #calculate probabilities based on length of k paths
            selected_path = self.select_path_with_probabilities(disjoint_paths, probabilities) #select path based on probabilities
            routing_output = self.process_routing_output(selected_path, flow) #process the output for routing
            if constants.ROUTING_STRATEGY == Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING:
                routing_output = self.adapt_routing_with_single_split(flow, routing_output)
            if constants.ROUTING_STRATEGY == Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB:
                routing_output = self.adapt_routing_decisions_to_available_link_bandwidth(flow, routing_output)
        #print("The routing output obtained from basic_centralized_route:", routing_output)
        return routing_output #RoutingAction, Flow, Link

    def extract_separated_decision_lists(self, nested_decisions):
        separated_lists = []
        while nested_decisions:
            current_list = []
            while nested_decisions and not isinstance(nested_decisions[0], list):
                current_list.append(nested_decisions.pop(0))
            if current_list:
                separated_lists.append(current_list)
            if nested_decisions and isinstance(nested_decisions[0], list):
                nested_decisions = nested_decisions.pop(0)
        return separated_lists

    #adaptive method used only for LB strategies
    def adapt_routing_decisions_to_available_link_bandwidth(self, flow: Flow, routing_decisions):
        if len(routing_decisions) == 1: # if there is only one decision
            #print("Skipping adaptation.") #no need to check link capacity in this simulation but should be added in real world scenario
            return routing_decisions 

        adapted_routing_decisions = [] #nuove decisioni adattate alla rete
        remaining_flow = flow.clone()
        initial_flow_rate = remaining_flow.rate
        reached_node = None  # Inizializzazione esplicita
        
        # Estrai i link del percorso
        path_links = [link for action, _, link in routing_decisions if action in [RoutingAction.FORWARD, RoutingAction.DELIVER]]
        if path_links:
            min_available_bw = min(link.get_available_bandwidth() for link in path_links)
            print(f"[INFO] Minimum available bandwidth is {min_available_bw} among Links of Selected Path")

        for i, (action, flow, link) in enumerate(routing_decisions):
            if not reached_node: #inizializza il primo reached node del percorso
                print(" !!! Reached node not set yet.")
                if isinstance(link.target, list): #il primo reached node sarà il secondo nodo, target del primo link
                    if link.target:  
                        reached_node = link.target[0].get_name()
                    else:
                        print(f"Warning: Link {link} target is an empty list.")
                else:
                    reached_node = link.target.get_name()
            
            if action in [RoutingAction.FORWARD, RoutingAction.DELIVER]:
                available_bandwidth = link.get_available_bandwidth()

                if available_bandwidth > 0:
                    if min_available_bw >= remaining_flow.rate:  # Cambiata la condizione "available_bandwidth >= remaining_flow.rate:"
                        print(f"[DEBUG] Enough bandwidth equal to {min_available_bw} for flow rate {remaining_flow.rate}")
                    
                        #DEBUG
                        link_paths = [f"{link._parent.get_name()} - {', '.join(t.get_name() for t in link.target) if isinstance(link.target, list) else link.target.get_name()}" for _, _, link in routing_decisions]
                        #print(f"[DEBUG] Routing path on enough bandwidth: {link_paths}") #shows human-readable path
                        print(f"Checking path of splitted flow... first link {link._parent.get_name()} - {link.target.get_name()} with available bandwidth {link.get_available_bandwidth()}")
                        adapted_routing_decisions.append((action, flow, link)) #remaining_flow
                        if isinstance(link.target, list):
                            if link.target:
                                reached_node = link.target[0].get_name()
                        else:
                            reached_node = link.target.get_name()

                        self.check_path_for_splitted_flow( #usato per il remain flow
                            flow, #remaining_flow
                            routing_decisions[i + 1:], #support_routing_decisions
                            adapted_routing_decisions
                        )
                        
                        remaining_flow.rate = 0 # Tutto il flusso è stato consumato
                        break

                    else:
                        # Flow splitting logic, solo una parte del flusso passa
                        splitted_flow, remaining_flow_to_route = remaining_flow.split(min_available_bw) #sfruttando la Min bandwidth di tutto il percorso #splitted flow è il flusso che può passare, remaining flow to route è il flusso che non può passare
                        print("[DEBUG] Not enough bandwidth, proceed to splitting...")
                        print(f"[DEBUG] Created Splitted_flow with rate {splitted_flow.rate} and Remaining_flow_to_route with rate {remaining_flow_to_route.rate}")
                        #print(f"Splitted_flow {splitted_flow} Rate {splitted_flow.rate} and Remaining_flow_to_route {remaining_flow_to_route} Rate {remaining_flow_to_route.rate}")
                        print(f"Checking path of splitted flow... first link {link._parent.get_name()} - {link.target.get_name()} with available_bandwidth {link.get_available_bandwidth()}")
                        adapted_routing_decisions.append((action, splitted_flow, link))
                        reached_node = link._parent.get_name()

                        self.check_path_for_splitted_flow(
                            splitted_flow,
                            routing_decisions[i + 1:], #support_routing_decisions
                            adapted_routing_decisions
                        )
                        remaining_flow = remaining_flow_to_route
                        excluded_link = (link._parent.get_name(), link.target.get_name())
                        if excluded_link not in self.excluded_links:
                            self.excluded_links.append(excluded_link)
                        break
                else:
                    print(f"Link {link} is fully saturated. No flow can pass.")
                    excluded_link = (link._parent.get_name(), link.target.get_name())
                    if excluded_link not in self.excluded_links:
                        self.excluded_links.append(excluded_link)
                    reached_node = link._parent.get_name()
            else:
                adapted_routing_decisions.append((action, remaining_flow, link))

        if isinstance(reached_node, str):
            reached_node = reached_node.upper()

        # Se il nodo raggiunto è la destinazione, interrompi il calcolo
        if reached_node == self.destination.get_name().upper():
            print(f"Reached destination: {reached_node}. Stopping recursion.")
            remaining_flow.rate = initial_flow_rate #reimposta il valore al rate originale
            adapted_routing_decisions.append((action, remaining_flow, link)) #
            #print("reserve 2")
            #link.reserve_bandwidth(remaining_flow) #
            #print("Decisions to destination", adapted_routing_decisions)
            return adapted_routing_decisions

        # Verifica finale di reached_node
        if remaining_flow and remaining_flow.rate > 0:
            if not reached_node:
                print("[ADAPT] ATTENTION: reached_node was not set during routing decision adaptation; attempting fallback.")
                print(f"[ADAPT] Adapted routing decisions after no reach_node {adapted_routing_decisions}")
                if adapted_routing_decisions:
                    last_action, _, last_link = adapted_routing_decisions[-1]
                    if last_action in [RoutingAction.FORWARD, RoutingAction.DELIVER]:
                        if isinstance(last_link.target, list):
                            if last_link.target:
                                reached_node = last_link.target[0].get_name()
                        else:
                            reached_node = last_link.target.get_name()
                if not reached_node:
                    adapted_routing_decisions.append((RoutingAction.ERROR, remaining_flow, None))
                    remaining_flow = None #remaing flow becomes None cause it's lost and cannot be delivered
                    return adapted_routing_decisions
       
            # Calcolo dei nuovi percorsi
            #print(f"EXCLUDED LINKS {len(self.excluded_links)} for decisions: {self.excluded_links}")
            #num_nodes = self._auxiliary_graph.number_of_nodes()
            #num_edges = self._auxiliary_graph.number_of_edges()
            #edges_list = [f"{u} <-> {v} ({data.get('available_bandwidth', 'N/A')})" for u, v, data in self._auxiliary_graph.edges(data=True)] #, W: {data.get('weight', 'N/A'):.2f}
            #print(f"self.AUXILIARY before calculatepathwitheclusions AUXILIARY Graph Simplified List  of {num_edges} Edges, {num_nodes} Nodes in g graph: {edges_list}")

            new_routing_decisions_remaining_flow = self.calculate_path_with_exclusions(remaining_flow, reached_node, g_auxiliary=self._auxiliary_graph)
            #print("NEW routing decisions calculated path with exclusions for flow", remaining_flow ,":", new_routing_decisions_remaining_flow)
            adapted_decisions_remaining_flow = self.adapt_routing_decisions_to_available_link_bandwidth(remaining_flow, new_routing_decisions_remaining_flow) #RICORSIONE
            #print("ADAPTED NEW routing decisions", adapted_decisions_remaining_flow)
            if adapted_decisions_remaining_flow:
                adapted_routing_decisions.append(adapted_decisions_remaining_flow)
            else:
                adapted_routing_decisions.append((RoutingAction.ERROR, remaining_flow, None))
                remaining_flow = None
        #print("ADAPTED ROUTING DECISIONS:", adapted_routing_decisions)
        return adapted_routing_decisions

    #method for NO LB strategies
    def adapt_routing_with_single_split(self, flow: Flow, routing_decisions: list):
        if len(routing_decisions) == 1: # if there is only one decision
            #print("Skipping adaptation.") #no need to check link capacity in this simulation but should be added in real world scenario
            return routing_decisions 
        
        adapted_routing_decisions = []
        remaining_flow = flow.clone()
        initial_flow_rate = remaining_flow.rate
        reached_node = None  # Inizializzazione esplicita

        # Estrai i link del percorso
        path_links = [link for action, _, link in routing_decisions if action in [RoutingAction.FORWARD, RoutingAction.DELIVER]]
        if path_links:
            min_available_bw = min(link.get_available_bandwidth() for link in path_links)
            print(f"[INFO] Minimum available bandwidth is {min_available_bw} among Links of Single Selected Single Path") #print(f"Links in path: {path_links}")

        for i, (action, flow, link) in enumerate(routing_decisions): 
            if not remaining_flow:
                print("No remaining flow to route.")
                break  # Flusso completamente instradato
            if not reached_node: #inizializza il primo reached node del percorso
                #print("Reached node not set yet.")
                if isinstance(link.target, list): #il primo reached node sarà il secondo nodo, target del primo link
                    if link.target:  
                        reached_node = link.target[0].get_name()
                    else:
                        print(f"Warning: Link {link} target is an empty list.")
                else:
                    reached_node = link.target.get_name()

            if action in [RoutingAction.FORWARD, RoutingAction.DELIVER]:
                available_bandwidth = link.get_available_bandwidth()
                
                if available_bandwidth > 0:
                    if min_available_bw >= remaining_flow.rate:  # Cambiata la condizione "available_bandwidth >= remaining_flow.rate:"
                        print(f"[DEBUG] Enough bandwidth equal to {min_available_bw} for flow rate {remaining_flow.rate}")
                    
                        #DEBUG
                        link_paths = [f"{link._parent.get_name()} - {', '.join(t.get_name() for t in link.target) if isinstance(link.target, list) else link.target.get_name()}" for _, _, link in routing_decisions]
                        #print(f"[DEBUG] Routing path on enough bandwidth: {link_paths}") #shows human-readable path
                        print(f"Checking path of single splitted flow... first link {link._parent.get_name()} - {link.target.get_name()} with available bandwidth {link.get_available_bandwidth()}")
                        adapted_routing_decisions.append((action, flow, link)) #remaining_flow
                        if isinstance(link.target, list):
                            if link.target:
                                reached_node = link.target[0].get_name()
                        else:
                            reached_node = link.target.get_name()

                        self.check_path_for_splitted_flow_simple(
                            flow,
                            routing_decisions[i + 1:],
                            adapted_routing_decisions
                        )

                        remaining_flow.rate = 0 # Tutto il flusso è stato consumato
                        break  # Flusso interamente instradato, possiamo interrompere qui
                    
                    else:
                        # Flow splitting logic for single routing
                        splitted_flow, undeliverable_flow = remaining_flow.split(min_available_bw)
                        print("[DEBUG] Not enough bandwidth, proceed to splitting...")
                        print(f"[DEBUG] Created Splitted_flow with rate {splitted_flow.rate} and Remaining_flow_to_route with rate {undeliverable_flow.rate}")
                        #print(f"Splitted_flow {splitted_flow} Rate {splitted_flow.rate} and Remaining_flow_to_route {remaining_flow_to_route} Rate {remaining_flow_to_route.rate}")
                        print(f"Checking path of single splitted flow... first link {link._parent.get_name()} - {link.target.get_name()} with available_bandwidth {link.get_available_bandwidth()}")
                        adapted_routing_decisions.append((action, splitted_flow, link))
                        reached_node = link._parent.get_name()

                        self.check_path_for_splitted_flow_simple(
                            splitted_flow,
                            routing_decisions[i + 1:],
                            adapted_routing_decisions
                        )
                        remaining_flow = undeliverable_flow
                        excluded_link = (link._parent.get_name(), link.target.get_name())
                        if excluded_link not in self.excluded_links:
                            self.excluded_links.append(excluded_link)
                        break
                else:
                    print(f"Link {link} is fully saturated. No flow can pass.")
                    excluded_link = (link._parent.get_name(), link.target.get_name())
                    if excluded_link not in self.excluded_links:
                        self.excluded_links.append(excluded_link)
                    reached_node = link._parent.get_name()
            else:
                adapted_routing_decisions.append((action, remaining_flow, link))

        '''if remaining_flow and remaining_flow.rate > 0:
            #print("[DEBUG] Undeliverable flow with rate", remaining_flow.rate, "after single split adaptation." )
            flow.add_step(self) #open_flow-like behaviour without actually opening the flux
            #flow.alias_id = self.mapping_table.add(flow.alias_id)
            flow.drop_steps_from(self) #remove flow's steps that pass through this link of the satellite
            self.drop_flow(flow, FlowState.LINK_CONGESTED) '''

        return adapted_routing_decisions

    def check_path_for_splitted_flow_simple(self, flow: Flow, support_routing_decisions, adapted_routing_decisions):
        for j, (inner_action, inner_flow, inner_link) in enumerate(support_routing_decisions):
            decisions_copy = support_routing_decisions.copy()
            decisions_copy[j] = (inner_action, flow, inner_link)

            if inner_action in [RoutingAction.FORWARD, RoutingAction.DELIVER]:
                available_bandwidth = inner_link.get_available_bandwidth()

                if isinstance(inner_link.target, list):
                    expected_destination = utils.get_ground_station_name_by_coords(flow.destination[0], flow.destination[1])
                    ##print(f"Expected Destination -> {expected_destination}")
                    # Cerca nella lista dei target l'oggetto che corrisponde al nome
                    confirmed_destination = [destination for destination in inner_link.target if hasattr(destination, 'get_name') and destination.get_name().upper() == expected_destination]
                    confirmed_destination_node = utils.get_ground_station_name_by_coords(confirmed_destination[0].lat, confirmed_destination[0].lon)
                    ##print(f"Confirmed Destination -> {confirmed_destination_node}")
                    target_name = confirmed_destination_node
                else:
                    target_name = inner_link.target.get_name()

                print(f"Checking path of splitted flow... link {inner_link._parent.get_name()} - {target_name} with available_bandwidth {available_bandwidth}")
                
                #banda superiore o uguale al rate di flusso
                if available_bandwidth >= flow.rate:
                    if available_bandwidth == flow.rate:
                        excluded_link = (inner_link._parent.get_name(), inner_link.target.get_name())
                        if excluded_link not in self.excluded_links:
                            self.excluded_links.append(excluded_link)

                    if isinstance(inner_link.target, list):
                        adapted_routing_decisions.append((inner_action, flow, inner_link))
                        target_node = confirmed_destination_node #inner_link.target[0].get_name()
                    else:  
                        adapted_routing_decisions.append((inner_action, flow, inner_link))  
                        target_node = inner_link.target.get_name()

                    if inner_action == RoutingAction.DELIVER:                        
                        expected_destination = utils.get_ground_station_name_by_coords(flow.destination[0], flow.destination[1]) #lat #lon
                        
                        '''if target_node.upper() == expected_destination:
                            print(f"[SUCCESSFUL]: Splitted flow {flow} rate {flow.rate} reached destination {target_node.upper()}!")
                        else:
                            print(f"[WARNING]: Flow delivered to {target_node.upper()}, but expected {expected_destination}. Not considered successful.")
                            '''
                else: #banda inferiore al rate del flusso
                    new_splitted_flow, remaining_flow = flow.split(available_bandwidth)
                    print(f"NEW  splitted flow created in check_path_for_splitted_flow_simple {new_splitted_flow} rate {new_splitted_flow.rate} and remaining flow {remaining_flow} rate {remaining_flow.rate}")
                    
                    if new_splitted_flow.rate > 0:
                        inner_link.reserve_bandwidth(new_splitted_flow)
                        adapted_routing_decisions.append((inner_action, new_splitted_flow, inner_link))

                    if remaining_flow.rate > 0:
                        excluded_link = (inner_link._parent.get_name(), inner_link.target.get_name())
                        if excluded_link not in self.excluded_links:
                           self.excluded_links.append(excluded_link)
                        #print("[DEBUG] Undeliverable flow with rate", remaining_flow.rate, "after single split adaptation." )
                        flow.add_step(self) #open_flow-like behaviour without actually opening the flux
                        #flow.alias_id = self.mapping_table.add(flow.alias_id)
                        flow.drop_steps_from(self) #remove flow's steps that pass through this link of the satellite
                        self.drop_flow(flow, FlowState.LINK_CONGESTED) 
        
        return adapted_routing_decisions  # Termina la ricerca; il flow non viene instradato

    def check_path_for_splitted_flow(self, flow: Flow, support_routing_decisions, adapted_routing_decisions):
        for j, (inner_action, inner_flow, inner_link) in enumerate(support_routing_decisions):
            decisions_copy = support_routing_decisions.copy()
            decisions_copy[j] = (inner_action, flow, inner_link)

            if inner_action in [RoutingAction.FORWARD, RoutingAction.DELIVER]:
                available_bandwidth = inner_link.get_available_bandwidth()

                if isinstance(inner_link.target, list):
                    expected_destination = utils.get_ground_station_name_by_coords(flow.destination[0], flow.destination[1])
                    ##print(f"Expected Destination -> {expected_destination}")
                    # Cerca nella lista dei target l'oggetto che corrisponde al nome
                    confirmed_destination = [destination for destination in inner_link.target if hasattr(destination, 'get_name') and destination.get_name().upper() == expected_destination]
                    confirmed_destination_node = utils.get_ground_station_name_by_coords(confirmed_destination[0].lat, confirmed_destination[0].lon)
                    ##print(f"Confirmed Destination -> {confirmed_destination_node}")
                    target_name = confirmed_destination_node
                else:
                    target_name = inner_link.target.get_name()

                print(f"Checking path of splitted flow... link {inner_link._parent.get_name()} - {target_name} with available_bandwidth {available_bandwidth}")
                
                #banda superiore o uguale al rate di flusso
                if available_bandwidth >= flow.rate:
                    if available_bandwidth == flow.rate:
                        excluded_link = (inner_link._parent.get_name(), inner_link.target.get_name())
                        if excluded_link not in self.excluded_links:
                            self.excluded_links.append(excluded_link)

                    if isinstance(inner_link.target, list):
                        adapted_routing_decisions.append((inner_action, flow, inner_link))
                        target_node = confirmed_destination_node #inner_link.target[0].get_name()
                    else:  
                        adapted_routing_decisions.append((inner_action, flow, inner_link))  
                        target_node = inner_link.target.get_name()

                    if inner_action == RoutingAction.DELIVER:                        
                        expected_destination = utils.get_ground_station_name_by_coords(flow.destination[0], flow.destination[1]) #lat #lon
                        
                        '''if target_node.upper() == expected_destination:
                            print(f"[SUCCESSFUL]: Splitted flow {flow} rate {flow.rate} reached destination {target_node.upper()}!")
                        else:
                            print(f"[WARNING]: Flow delivered to {target_node.upper()}, but expected {expected_destination}. Not considered successful.")
                            '''

                else: #banda inferiore al rate del flusso
                    new_splitted_flow, remaining_flow = flow.split(available_bandwidth)
                    print(f"NEW  splitted flow created in check_path_for_splitted_flow {new_splitted_flow} rate {new_splitted_flow.rate} and remaining flow {remaining_flow} rate {remaining_flow.rate}")
                    
                    if new_splitted_flow.rate > 0:
                        inner_link.reserve_bandwidth(new_splitted_flow)
                        adapted_routing_decisions.append((inner_action, new_splitted_flow, inner_link))
                    
                    if remaining_flow.rate > 0: #controllare questa parte logica
                        excluded_link = (inner_link._parent.get_name(), inner_link.target.get_name())
                        if excluded_link not in self.excluded_links:
                           self.excluded_links.append(excluded_link)

                        self.check_path_for_splitted_flow(
                            remaining_flow,
                            decisions_copy[j + 1:], 
                            adapted_routing_decisions
                        )
                        break
                
        return adapted_routing_decisions

    def calculate_path_with_exclusions(self, remaining_flow: Flow, reached_node, g_auxiliary):
        '''num_nodes = self._auxiliary_graph.number_of_nodes()
        num_edges = self._auxiliary_graph.number_of_edges()
        edges_list = [f"{u} <-> {v} ({data.get('available_bandwidth', 'N/A')})" for u, v, data in self._auxiliary_graph.edges(data=True)] #, W: {data.get('weight', 'N/A'):.2f}
        print(f"g_auxiliary FIRST in calculate_path_with_exclusions of {num_edges} Edges, {num_nodes} Nodes in g graph: {edges_list}")
        print(f"g_auxiliary FIRST: {g_auxiliary.nodes}")'''

        if reached_node is None:
            raise ValueError("Reached_node was not set before calling calculate_path_with_exclusions")
        disjoint_paths = []

        #g_auxiliary = env.main_graph.copy() # Grafo ausiliario per calcolo delle esclusioni

        num_nodes = self._auxiliary_graph.number_of_nodes()
        num_edges = self._auxiliary_graph.number_of_edges()
        edges_list = [f"{u} <-> {v} ({data.get('available_bandwidth', 'N/A')})" for u, v, data in self._auxiliary_graph.edges(data=True)] #, W: {data.get('weight', 'N/A'):.2f}
        #print(f"g_auxiliary AFTER in calculate_path_with_exclusions of {num_edges} Edges, {num_nodes} Nodes in g graph: {edges_list}")
        #print(f"g_auxiliary AFTER: {g_auxiliary.nodes}")

        for u, v in self.excluded_links: # Rimuovi i link esclusi
            if g_auxiliary.has_edge(u, v):
                g_auxiliary.remove_edge(u, v)

        #####self.print_graph_edges(self._graph, "Original graph")
        #####self.print_graph_edges(g_auxiliary, "Auxiliary graph (after exclusions)")
        if not g_auxiliary.edges:
            raise ValueError("All links are saturated or excluded. No valid path can be calculated.")
        
        if isinstance(reached_node, str):  # Verifica se reached_node è una stringa
            source_satellite = reached_node.upper()
        else:
            source_satellite = reached_node
        destination = self.destination
        source = self
        destination_name = self.destination.get_name().upper()
        destination_satellites = []
        source_satellites = []

        closer_satellites = utils.get_closest_satellite_for_graph(self.satellites, (source.lat, source.lon))  # Trova i satelliti più vicini
        for sat_name, sat in closer_satellites:
            if sat_name not in self.satellites:
                print(f"Satellite {sat_name} non trovato nel dizionario 'satellites'")
                continue
            distance_to_sat = utils.get_distance_between_satellite_and_gs(sat, source)
            if distance_to_sat <= constants.SATELLITE_COVERAGE_AREA_RADIUS:
                source_satellites.append(sat_name)

        closer_satellites = utils.get_closest_satellite_for_graph(self.satellites, (destination.lat, destination.lon))
        for sat_name, sat in closer_satellites:
            if sat_name not in self.satellites:
                print(f"Satellite {sat_name} non trovato nel dizionario 'satellites'")
                continue
            distance_to_sat = utils.get_distance_between_satellite_and_gs(sat, destination)
            if distance_to_sat <= constants.SATELLITE_COVERAGE_AREA_RADIUS:
                destination_satellites.append(sat_name)

        selected_path = None  # Inizializza la variabile per prevenire l'errore
        #print("Nodes in g_auxiliary:", g_auxiliary.nodes)

        if constants.ROUTING_STRATEGY == Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB:
            #print(f"starting node is {source_satellite}")
            for dst_sat in destination_satellites:
                #print(f"dst_sat {dst_sat} in destination_satellites: {destination_satellites}")#debug
                # Ensure destination node exists
                if dst_sat not in g_auxiliary:
                    raise ValueError(f"Destination node {dst_sat} not found in graph!")
                try:
                    paths = list(nx.node_disjoint_paths(g_auxiliary, source_satellite, dst_sat))
                    disjoint_paths.extend(paths)
                except nx.NetworkXNoPath:
                    #if remaining_flow not in self.DEBUG_dropped_flows:
                        #modifica
                        #self.drop_flow(remaining_flow, FlowState.SATELLITE_CONGESTED)  # Store the flow that cannot be routed
                        #self.DEBUG_dropped_flows.append(remaining_flow)
                    print(f"[DROP] No Node disjoint path for Remained flow {remaining_flow} rate {remaining_flow.rate} between {source_satellite} and {dst_sat}.")

            if disjoint_paths:
                probabilities = self.calculate_path_weights_kshortest_disjoint(g_auxiliary, disjoint_paths)
                selected_path = self.select_path_with_probabilities(disjoint_paths, probabilities)
        
        elif constants.ROUTING_STRATEGY == Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_LB:
            for dst_sat in destination_satellites:
                try:
                    paths = list(nx.edge_disjoint_paths(g_auxiliary, source_satellite, dst_sat))
                    disjoint_paths.extend(paths)
                except nx.NetworkXNoPath:
                    print(f"No Edge disjoint path for {constants.ROUTING_STRATEGY} between {source_satellite} and {dst_sat}.")
            #self.print_paths(disjoint_paths, "Edge disjoint paths")
            if disjoint_paths:
                probabilities = self.calculate_path_weights_kshortest_disjoint(g_auxiliary, disjoint_paths)
                selected_path = self.select_path_with_probabilities(disjoint_paths, probabilities)

        elif constants.ROUTING_STRATEGY == Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB:
            for dst_sat in destination_satellites:
                try:
                    paths = list(nx.node_disjoint_paths(g_auxiliary, source_satellite, dst_sat))
                    disjoint_paths.extend(paths)
                except nx.NetworkXNoPath:
                    print(f"No Node disjoint path for {constants.ROUTING_STRATEGY} between {source_satellite} and {dst_sat}.")
            #self.print_paths(disjoint_paths, "Length shortest node disjoint paths")
            if disjoint_paths:
                probabilities = self.calculate_path_weights_length_shortest_node_disjoint(g_auxiliary, disjoint_paths)
                selected_path = self.select_path_with_probabilities(disjoint_paths, probabilities)

        if selected_path is None:  # Se nessun percorso è stato trovato
            print(f"DROPPED FLOW STORED while calculate path exclusions, No valid path for {remaining_flow} rate {remaining_flow.rate} from {self.get_name()} to {self.destination.get_name()}.")
            
            #print(f"DEBUG DROPPED FLOWS: {self.DEBUG_dropped_flows}")
            self.outgoing_flows.append((remaining_flow, utils.get_current_time(), None))
            remaining_flow.travelled_distance = 0

            self.drop_flow(remaining_flow, FlowState.SATELLITE_CONGESTED) #dropping the flow if no path is found
            
            reached_node = None
            return []

        #print(f"Selected path: {selected_path}")
        return self.process_routing_output(selected_path, remaining_flow)

    def print_graph_edges(self, graph, label):
        edges_list = [f"{edge[0]} -> {edge[1]}" for edge in graph.edges(data=True)]
        total_edges = len(edges_list)
        print(f"    Edges in {label} (total: {total_edges})")

    def print_paths(self, paths, label):
        print(f"{label}:")
        for path in paths:
            print(f"  Path: {list(zip(path[:-1], path[1:]))}")

    def process_routing_output(self, selected_path, flow):
        processed_output = []
        print(f">>> Processing Selected Path: {selected_path}")  # stampa per debug
        
        # Caso in cui il path abbia un solo nodo (es tokyo-tokyo)
        if len(selected_path) == 1:
            single_node = selected_path[0]
            # Verifica se esiste un collegamento diretto al GS
            last_link = self._get_link_to_ground_station(single_node, self.destination, self.satellites, self.gss)
            if last_link:
                processed_output.append((RoutingAction.DELIVER, flow, last_link))
            else:
                print(f"[ERROR]: No direct link from {single_node} to destination GS {self.destination.get_name()}.")
                return []
            return processed_output

        # Caso generale con più satelliti nel path
        for i in range(len(selected_path) - 1):
            current_node = selected_path[i]
            next_node = selected_path[i + 1]
            link = self._get_link_between_nodes_or_ground_station(current_node, next_node, self.satellites, self.gss)
            if not link:
                print(f"[WARNING]: No link found between {current_node} and {next_node}. Skipping.")
                continue
            processed_output.append((RoutingAction.FORWARD, flow, link))

        # Controllo finale 
        last_node = selected_path[-1]
        if (self.destination not in self.satellites[last_node]._gs_link.get_attached_gs()):
            print(f"[ERROR] Satellite {last_node} is not directly connected to GS {self.destination.get_name()}. Excluding and recalculating.")
            self.excluded_links.append((selected_path[-2], last_node))
            # Ricalcola un percorso alternativo
            return self.calculate_path_with_exclusions(flow, selected_path[0], self._auxiliary_graph)

        #print("Destination while processing output",  self.destination.get_name())
        # Se tutto va bene, procedi con il link finale
        last_link = self._get_link_to_ground_station(last_node, self.destination, self.satellites, self.gss)

        if last_link:
            #print("[INFO]: Final link to GS found.")
            processed_output.append((RoutingAction.DELIVER, flow, last_link))
        else:
            print(f"[ERROR]: No final link to GS from satellite {last_node} found. Path discarded.")
            return []

        return processed_output

    def calculate_k_disjoint_paths(self, kwargs):
        source: dict = kwargs['source']
        destination: dict = kwargs['destination']
        satellites: dict = kwargs['satellites']
        flow: Flow = kwargs['flow']  # aggiunto flow
        if constants.ROUTING_STRATEGY in [Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                        Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING,
                                        Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING]:
            k = constants.K_SHORTEST_VALUE # Numero massimo di percorsi disgiunti consentiti
        if constants.ROUTING_STRATEGY in [Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                  Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                  Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                  Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_COSTS_SELECTION]:
            k = constants.K_SHORTEST_VALUE_LB  # Numero massimo di percorsi disgiunti richiesti
        
        k_disjoint_paths = self._get_k_disjoint_paths(satellites, source, destination)
        
        print("> Calculated K Paths:", k_disjoint_paths)
        if not k_disjoint_paths:  # Controllo corretto se nessun percorso è disponibile
            print(f"[WARNING] No available path for flow {flow.id} with rate {flow.rate} Gbps")
            self.outgoing_flows.append((flow, utils.get_current_time(), None))
            self.drop_flow(flow, FlowState.SATELLITE_CONGESTED)
            return []  # Restituisci immediatamente una lista vuota
        k_disjoint_paths = k_disjoint_paths[:k] # Limita il numero di percorsi disgiunti a k
        return k_disjoint_paths
 
    def _get_k_disjoint_paths(self, satellites, source, destination):
        print("Starting Main Graph", env.main_graph)
        num_nodes = env.main_graph.number_of_nodes()
        num_edges = env.main_graph.number_of_edges()
        edges_list = [f"{u} <-> {v} {data.get('available_bandwidth', 'N/A')}" for u, v, data in env.main_graph.edges(data=True)] #, W: {data.get('weight', 'N/A'):.2f}"
        #print(f"[DEBUG] _get_k_disjoint Main Graph: {num_edges} Edges, {num_nodes} Nodes in graph: {edges_list}")
        source_satellite = []
        destination_satellite = []
        num_nodes1 = env.main_graph.number_of_nodes()
        num_edges1 = env.main_graph.number_of_edges()
        edges_list1 = [f"{u} <-> {v} ({data.get('available_bandwidth', 'N/A')})" for u, v, data in env.main_graph.edges(data=True)] #, W: {data.get('weight', 'N/A'):.2f}
        ###print(f"MAIN GRAPH _get_k_disjoint_paths Simplified List of {num_edges1} Edges, {num_nodes1} Nodes in g graph: {edges_list1}")
        closer_satellites = utils.get_closest_satellite_for_graph(satellites, (source.lat, source.lon))#trova satellite più vicino a sorgente #modifica nel trovare il satellite più vicino alla SORGENTE!
        for sat_name, sat in closer_satellites:
            if sat_name not in satellites:
                print(f"Satellite {sat_name} not found in dictionary 'satellites'")
                continue
            distance_to_sat = utils.get_distance_between_satellite_and_gs(sat, source)  # Calcola la distanza #print("Distanza da GS sorgente a Sat:", distance_to_sat)     
            if distance_to_sat <= constants.SATELLITE_COVERAGE_AREA_RADIUS:
                source_satellite.append(sat_name)
        closer_satellites = utils.get_closest_satellite_for_graph(satellites, (destination.lat, destination.lon))#trova satellite più vicino a destinazione #modifica nel trovare il satellite più vicino alla DESTINAZIONE!
        for sat_name, sat in closer_satellites:
            if sat_name not in satellites:
                print(f"Satellite {sat_name} not found in dictionary 'satellites'")
                continue
            distance_to_sat = utils.get_distance_between_satellite_and_gs(sat, destination)  # Calcola la distanza #print("Distanza da Sat a GS destinazione:", distance_to_sat) 
            if distance_to_sat <= constants.SATELLITE_COVERAGE_AREA_RADIUS:
                destination_satellite.append(sat_name)
        
        print("> Source satellite", source_satellite)
        print("> Destination satellite", destination_satellite)
        valid_source_sats = [sat for sat in source_satellite if sat in env.main_graph]#check validation of nodes
        valid_destination_sats = [sat for sat in destination_satellite if sat in env.main_graph]
        # Rimuovi gli archi con banda disponibile pari a 0
        edges_to_remove = [(u, v) for u, v, data in env.main_graph.edges(data=True) if data.get('available_bandwidth', 0) == 0] #graph.edges...
        print(f"[DEBUG] Removing {len(edges_to_remove)} edges: {edges_to_remove}")
        for u, v in edges_to_remove:
            env.main_graph.remove_edge(u, v)
        self._graph = env.main_graph.copy()
        self._auxiliary_graph = env.main_graph.copy()
        for gs_name in env.ground_stations.keys():
            if gs_name in env.main_graph:
                self._auxiliary_graph.remove_node(gs_name)
        num_nodes = self._auxiliary_graph.number_of_nodes()
        num_edges = self._auxiliary_graph.number_of_edges()
        edges_list = [f"{u} <-> {v} ({data.get('available_bandwidth', 'N/A')})" for u, v, data in self._auxiliary_graph.edges(data=True)] #, W: {data.get('weight', 'N/A'):.2f}
        ##print(f"AUXILIARY _get_k_disjoint AUXILIARY Graph Simplified List  of {num_edges} Edges, {num_nodes} Nodes in g graph: {edges_list}")

        disjoint_paths = [] #list of k paths
        if constants.ROUTING_STRATEGY in [Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                          Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB]:
            if source == destination:
                print(f"Source and destination are the same: {source.get_name().upper()}. No route needed.")
                closer_sats=utils.get_closer_satellites(satellites, (self.lat, self.lon), False)
                disjoint_paths = []
                disjoint_paths.append([closer_sats[0]['name']])
                return disjoint_paths
            for src_sat in source_satellite: #in case there are more than one source and destination satellites (for a more complex algorithm)
                for dst_sat in destination_satellite:
                    if src_sat not in valid_source_sats:
                        print(f"[ERROR] Source satellites missing from graph!")
                        return []
                    if dst_sat not in valid_destination_sats:
                        print(f"[ERROR] Destination satellites missing from graph!")
                        return []
                    try:
                        paths = list(nx.node_disjoint_paths(self._auxiliary_graph, src_sat, dst_sat)) #### #calculate disjoint paths in graph excluding already used nodes
                        disjoint_paths.extend(paths)  #add all found paths
                    except nx.NetworkXNoPath:
                        print(f"No Node disjoint path for {constants.ROUTING_STRATEGY} between {src_sat} and {dst_sat}.")

        elif constants.ROUTING_STRATEGY in [Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING,
                                            Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                            Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_COSTS_SELECTION]:
            if source == destination:
                print(f"Source and destination are the same: {source.get_name().upper()}. No route needed.")
                closer_sats=utils.get_closer_satellites(satellites, (self.lat, self.lon), False)
                disjoint_paths = []
                disjoint_paths.append([closer_sats[0]['name']])
                return disjoint_paths
            for src_sat in source_satellite:
                for dst_sat in destination_satellite:
                    if src_sat not in valid_source_sats:
                        print(f"[ERROR] Source satellites missing from graph!")
                        return []
                    if dst_sat not in valid_destination_sats:
                        print(f"[ERROR] Destination satellites missing from graph!")
                        return []
                    try:
                        paths = list(nx.edge_disjoint_paths(self._auxiliary_graph, src_sat, dst_sat)) #### #calculate disjoint paths in graph excluding already used nodes
                        disjoint_paths.extend(paths)  #add all found paths
                    except nx.NetworkXNoPath:
                        print(f"No Edge disjoint path for {constants.ROUTING_STRATEGY} between {src_sat} and {dst_sat}.")

        elif constants.ROUTING_STRATEGY in [Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                            Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB]:
            if source == destination:
                print(f"Source and destination are the same: {source.get_name().upper()}. No route needed.")
                closer_sats=utils.get_closer_satellites(satellites, (self.lat, self.lon), False)
                disjoint_paths = []
                disjoint_paths.append([closer_sats[0]['name']])
                return disjoint_paths
            for src_sat in source_satellite:
                for dst_sat in destination_satellite:
                    if src_sat not in valid_source_sats:
                        print(f"[ERROR] Source satellites missing from graph!")
                        return []
                    if dst_sat not in valid_destination_sats:
                        print(f"[ERROR] Destination satellites missing from graph!")
                        return []
                    try:
                        paths = list(nx.node_disjoint_paths(self._auxiliary_graph, src_sat, dst_sat)) #calculate disjoint paths in graph excluding already used nodes
                        disjoint_paths.extend(paths)  #add all found paths
                    except nx.NetworkXNoPath:
                        print(f"No Node disjoint path for {constants.ROUTING_STRATEGY} between {src_sat} and {dst_sat}.")       

        '''num_nodes = self._auxiliary_graph.number_of_nodes()
        num_edges = self._auxiliary_graph.number_of_edges()
        edges_list = [f"{u} <-> {v} ({data.get('available_bandwidth', 'N/A')})" for u, v, data in self._auxiliary_graph.edges(data=True)] #, W: {data.get('weight', 'N/A'):.2f}
        print(f"AUXILIARY Graph Simplified List  of {num_edges} Edges, {num_nodes} Nodes in g graph: {edges_list}")'''
        #print("Percorsi generati da _get_k_disjoint_paths:", disjoint_paths)
        ### dopo le modifiche aggiorniamo il grafo
        #env.main_graph = g.copy() #store the graph for successive use
        return disjoint_paths
   

    def calculate_path_costs(self, graph, paths, link_utilization, alpha): #sistemare questi valori...bisogna testare tutte le combinazioni di ALPHA e 1-ALPHA(quindi togliendo direttamente beta)
        lengths = [path_weight(graph, path, weight="weight") for path in paths] #calculate normalized lengths of paths
        min_length = min(lengths)
        max_length = max(lengths)
        normalized_lengths = []
        for length in lengths:
            if max_length == min_length:
                #print("All paths have the same length. Normalization is trivial.")
                normalized_length = 0  # O scegli un valore significativo per il contesto
            else:
                normalized_length = (length - min_length) / (max_length - min_length)
            normalized_lengths.append(normalized_length)
        
        costs = []
        for path, normalized_length in zip(paths, normalized_lengths): #calculate costs for each path
            if len(path) == 1:  # Se il percorso ha un solo nodo, non ha link
                costs.append(0) 
            else:
                link_occupation = sum(
                    link_utilization.get((path[i], path[i+1]), 0) for i in range(len(path) - 1)
                ) / (len(path) - 1)  #avarage occupation of link
                cost = (alpha * normalized_length) + ((1 - alpha) * link_occupation)
                costs.append(cost)
        return costs

    def select_path_based_on_costs(self, paths, costs):
        total_cost = sum(costs) 
        if total_cost == 0:
            return paths[0]
        probabilities = [1 - (cost / total_cost) for cost in costs]  # Percorsi con costi bassi hanno maggiore probabilità, conversione dei costi in probabilità
        selected_path = random.choices(population=paths, weights=probabilities, k=1)[0]
        return selected_path

    def calculate_path_weights_kshortest_disjoint(self, graph, disjoint_paths):
        #print(f"°°°°°    DISJOINT PATHS: {disjoint_paths}")
        from link import LaserLink
        path_weights = []
        for path in disjoint_paths:
            if len(path) == 1:
                return [1.0]# Se il percorso ha un solo nodo, ha probabilità 100%
            weight = 0
            for i in range(len(path) - 1):
                current_node = path[i]
                next_node = path[i + 1]
                # Controllo esistenza arco e peso
                if not graph.has_edge(current_node, next_node) or 'weight' not in graph[current_node][next_node]:
                    raise KeyError(f"Link tra {current_node} e {next_node} assente o senza peso.")
                base_weight = graph[current_node][next_node]['weight']
                link_key = (current_node, next_node)
                utilization = self.link_utilization.get(link_key, 0)
                link = self._get_link_between_nodes(current_node, next_node, self.satellites)
                # Determina capacità massima in base al tipo di link
                max_capacity = (
                    constants.SATELLITE_LINK_CAPACITY if isinstance(link, LaserLink)
                    else constants.GROUND_STATION_LINK_CAPACITY
                )
                if max_capacity <= 0:
                    raise ValueError(f"Capacità massima non valida per il link {current_node}-{next_node}: {max_capacity}")
                penalty = utilization / max_capacity
                weight += base_weight * (1 + penalty)
            path_weights.append(weight)

        if not path_weights:
            raise ValueError("Lista pesi vuota, nessun percorso valido.")

        total_weight = sum(path_weights)

        if total_weight == 0:
            raise ValueError("Somma totale dei pesi nulla, impossibile calcolare probabilità.")

        # Inverti i pesi (meno peso = più probabilità)
        inverted_weights = [1 / w for w in path_weights]

        total_inverted_weights = sum(inverted_weights)
        probabilities = [iw / total_inverted_weights for iw in inverted_weights]

        return probabilities

    def calculate_path_weights_length_shortest_node_disjoint(self, graph, paths):
        # Calcola i pesi dei path
        path_costs = [path_weight(graph, p, weight="weight") for p in paths]
        sum_weights = sum(path_costs)

        # Caso degenerato: tutti i pesi 0 o lista vuota
        if sum_weights == 0 or len(paths) == 0:
            return [1.0 / len(paths)] * len(paths) if paths else []

        # Calcola i pesi inversi (1 - costo_relativo)
        inverse_weights = [1 - (c / sum_weights) for c in path_costs]
        total_inverse_weight = sum(inverse_weights)

        # Caso degenerato anche qui
        if total_inverse_weight == 0:
            return [1.0 / len(paths)] * len(paths)

        # Normalizza i pesi
        return [w / total_inverse_weight for w in inverse_weights]

    def select_path_with_probabilities(self, paths, probabilities): 
        if not paths:
            raise ValueError("La lista dei percorsi è vuota, impossibile selezionare un percorso.")
        if len(paths) == 1:
            # Solo un percorso disponibile, selezionalo direttamente
            return paths[0]
        if len(paths) != len(probabilities):
            raise ValueError("Il numero di percorsi e probabilità non coincide.")
        # Scelta casuale ponderata dal vettore delle probabilità
        selected_path = random.choices(population=paths, weights=probabilities, k=1)[0]
        return selected_path


    #obtain list of closer satellites in coverage area
    def _get_candidate_end_satellites_names(self, satellites, position): #position for destination coordinates
        sat_list = utils.get_closer_satellites(satellites, position) #list of closer satellites
        return [sat['name'] for sat in sat_list if sat['distance'] < constants.SATELLITE_COVERAGE_AREA_RADIUS] #list of the only satellites inside the coverage area of self

    #calculate the distance travelled by the flow
    def _get_path_distance(self, path: list, source, destination, satellites) -> float:
        distance = utils.get_distance_between_satellite_and_gs(path[0], source, satellites=satellites) #calculate distance between GS and the first satellite
        distance += utils.get_distance_between_satellite_and_gs(path[-1], destination, satellites=satellites) #calculate & add the distance between last satellite and GS
        older_hop = path[0] #first satellite of path

        #for every hop after the first one, calucate & add distance between satellites
        for hop in path[1:]: 
            distance += utils.get_distance_between_satellites(older_hop, hop, satellites=satellites)
            older_hop = hop
        return distance

    #found the link between two nodes of the path
    def _get_link_between_nodes(self, node1, node2, satellites):        
        if node1 not in satellites:
            raise ValueError(f"Node1 '{node1}' not found in satellites.")
        if node2 not in satellites:
            raise ValueError(f"Node2 '{node2}' not found in satellites.")
        satellite1 = satellites[node1] #source satellite
        '''
        #Debug
        if constants.DEBUG:
            print(f" Satellite '{node1}' has links: {satellite1._links}")
        '''
        for direction, link in satellite1._links.items(): #for the links of source satellite key:direction and value:link
            if link.target is None:  #if link as a target
                #print(f"Link with {direction} from '{node1}' has no target.")
                continue
            if link.target.get_name() == node2:  #check if target is effectively the next satellite of the shortest path
                #print(f"Link found between '{node1}' and '{node2}' with {direction}.")
                return link
        raise ValueError(f"No link exists between '{node1}' and '{node2}'.") #if there is no link throws the error
    
    def _get_link_to_ground_station(self, node, destination, satellites, ground_stations):
        #print("Destination:", destination.get_name())
        #print("Ground Stations:", ground_stations)
        #print("Node:", node)
        #print("Satellites:", satellites)
        if node not in satellites:
            raise ValueError(f"Last Node '{node}' not found in satellites.")
        if destination not in ground_stations.values():
            raise ValueError(f"Destination '{destination}' not found in ground stations.")
        
        destination_name = destination.get_name().upper()  # get_name (es TOKYO) from the value of gs in dictionary
        if destination_name not in ground_stations:
            raise ValueError(f"Destination '{destination_name}' not found in ground stations.")

        last_satellite = satellites[node]
        #print(f"last_satellite: {last_satellite.get_name()}")
        destination_gs = ground_stations[destination_name]
        #print(f"destination_gs: {destination_gs.get_name()}")
        attached_gs_list = last_satellite._gs_link.get_attached_gs()
        #print("Attached GS list:", [gs.get_name() for gs in attached_gs_list])
        if destination_gs not in attached_gs_list:
            raise ValueError(f"Ground station '{destination_gs}' not attached to satellite '{last_satellite}'.")
        
        '''print("...........last_satellite._gs_link:", last_satellite._gs_link.target)
        target_names = [t.get_name() if hasattr(t, "get_name") else str(t) for t in last_satellite._gs_link.target] #targets of Radiolinks are always lists
        print(f"last_satellite._gs_link: {last_satellite._gs_link} is {last_satellite._gs_link._parent.get_name()} - {target_names}")'''

        return last_satellite._gs_link #è corretto il _gs_link ma ha due target di arrivo #quindi corretto passare questo gs_link ma bisogna scegliere il target corretto

    def _get_link_between_nodes_or_ground_station(self, node1, node2, satellites, ground_stations):
        #print("Ground stations keys:", ground_stations.keys())
        #print("Ground stations values:", ground_stations.values())
        #print("Node1:", node1)
        #print("Node2:", node2)
        if node2 in ground_stations.keys(): #from satellite to GS case
            node2 = ground_stations[node2]
            #print(f"Recupero link tra satellite '{node1}' e ground station '{node2.get_name()}'.")
            return self._get_link_to_ground_station(node1, node2, satellites, ground_stations)
        if node1 in ground_stations.keys(): #from GS to satellite case
            node1 = ground_stations[node1]
            #print(f"Recupero link tra ground station '{node1.get_name()}' e satellite '{node2}'.")
            return self._get_link_to_ground_station(node2, node1, satellites, ground_stations)
        #print(f"Recupero link tra satellite '{node1}' e satellite '{node2}'.")
        return self._get_link_between_nodes(node1, node2, satellites) #two satellites case


    def calculate_dijkstra(self, kwargs):
        source: dict = kwargs['source']
        destination: dict = kwargs['destination']
        satellites: dict = kwargs['satellites']

        #Calculates the shortest path with Dijkstra's algorithm
        dijkstra_shortest_path = self._get_dijkstra_shortest_path(satellites, source, destination)
        #if not dijkstra_shortest_path:
         #   print(f"No valid path found from {source.get_name()} to {destination.get_name()}.")
        #else:
         #   print(f"Shortest path from {source.get_name()} to {destination.get_name()}: {dijkstra_shortest_path}")
        return dijkstra_shortest_path
    
    #calculates all the shortest available paths from SOURCE to DESTINATION returning THE SHORTEST PATH with minimum distance on minimum number of hops
    def _get_dijkstra_shortest_path(self, satellites, source, destination):
        g = dijkstra.Graph() #construct a graph for satellites
        for name, sat in satellites.items():
            for dir, link in sat._links.items():  # Itera sui link del satellite
                if link.is_active() and link.target:  # Controlla se il link è attivo e ha un target
                    g.add_edge(name, link.target.get_name(), utils.get_distance_between_satellites(sat, link.target))  # Aggiungi l'arco al grafo
                    #print(f"Edge added: {name} -> {link.target.get_name()} with distance {utils.get_distance_between_satellites(sat, link.target)}")
        end_satellites = self._get_candidate_end_satellites_names(satellites, (destination.lat, destination.lon)) #otherwise check for the closet satellites in the area of destination GS

        d = dijkstra.DijkstraSPF(g, source.sat.get_name()) #calculate Dijkstra's shortest path, initialize dijkstra algorithm on the graph starting from source
        if source == destination:
            #print(f"Source and destination are the same: {source.get_name().upper()}. No route needed.")
            closer_sats=utils.get_closer_satellites(satellites, (self.lat, self.lon), False)
            shortest_paths = []
            shortest_paths.append([closer_sats[0]['name']])
            path_distances = [(path, self._get_path_distance(path, source, destination, satellites)) for path in shortest_paths]
            shortest_path, min_distance = min(path_distances, key=lambda x: x[1])
            print(f"The shortest path from {source.get_name()} to {destination.get_name()} for a total distance of {min_distance:.2f} km is: {shortest_path}")
            return shortest_path

        shortest_paths = [d.get_path(end_satellite) for end_satellite in end_satellites]
        if not shortest_paths: #if there are shortest paths (there is always a path, but it's a check for wrong construction of constellation)
            print(f"No available paths from {source.get_name()} to {destination.get_name()}.")
            return []  #or could put None as return, if necessary

        shortest_path = min(shortest_paths, key=lambda x: len(x)) #return only one of the shortest paths, not all
        shortest_paths = [path for path in shortest_paths if len(path) == len(shortest_path)] #returns all the paths with same length as the shortest
        #for sp in shortest_paths:
         #   print(f"Dijkstra's shortest path from {source.get_name()} to {destination.get_name()}: ", sp)
        #print(f"Dijkstra's shortest path length from {source.get_name()} to {destination.get_name()}: ", len(shortest_paths), "x", len(shortest_path), "hops.")
        '''
        #debugging for links
        if constants.DEBUG:
            for name, sat in env.satellites.items():
                active_links = [
                    (dir.name, link.target.get_name())  # Ottieni la direzione e il nome del satellite target
                    for dir, link in sat._links.items() if link.is_active()
                ]
                print(f"Check for links of Satellite {name} links: {active_links}")
        '''
        #Calculates distances for all paths remained with minimum number of hops
        path_distances = [(path, self._get_path_distance(path, source, destination, satellites)) for path in shortest_paths]
        shortest_path, min_distance = min(path_distances, key=lambda x: x[1]) #order and find the path with the minimum distance
        # Print the shortest path and its distance
        print(f"The shortest path from {source.get_name()} to {destination.get_name()} for a total distance of {min_distance:.2f} km is: {shortest_path}")
        # Saving results
        #self.results[source.get_name() + ' - ' + destination.get_name()]['DIJKSTRA']['successful'].append(len(shortest_path))
        #self.results[source.get_name() + ' - ' + destination.get_name()]['DIJKSTRA']['distance'].append(min_distance)
        return shortest_path #only the path with minimum distance on minimum number of hops

    def extract_separated_decision_lists(self, nested_decisions):
        separated_lists = []

        while nested_decisions:
            current_list = []
            while nested_decisions and not isinstance(nested_decisions[0], list):
                current_list.append(nested_decisions.pop(0))

            if current_list:
                separated_lists.append(current_list)

            if nested_decisions and isinstance(nested_decisions[0], list):
                nested_decisions = nested_decisions.pop(0)
        return separated_lists

    def drop_flow(self, flow: Flow, reason: FlowState):
        if constants.DEBUG: #debugging messages
            msg = "Flow " + str(flow.id) + " with alias id " + str(flow.alias_id) + " with rate " + str(flow.rate) + " Gbps has been dropped by Satellite " + str(self.get_name()) + " at time " + utils.get_current_time().utc_strftime() + ". "
            if reason == FlowState.SATELLITE_CONGESTED:
                msg += "Satellite is congested."
            elif reason == FlowState.LINK_CONGESTED:
                msg += "Link is congested."
            elif reason == FlowState.EXPIRED_TTL:
                msg += "TTL is 0."
            elif reason == FlowState.SATELLITE_NOT_OPERATIONAL:
                msg += "Satellite is not operational."
            else:
                raise ValueError("The reason is not expected.", reason)
            #print(msg)
        
        flow.state = reason #update flow's state with reason for the drop
        #self.store_flow_direction(flow, None) #flow dropped and no more connected to active link

        self.DEBUG_dropped_flows.append(flow) 
        self.gss[[key for key, gs in self.gss.items() if gs.lat == flow.destination[0] and gs.lon == flow.destination[1]][0]].DEBUG_get_dropped_flow(flow)
        #self.gss in sostituzione di self.ground_stations
