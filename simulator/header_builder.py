import constants
import dijkstra
from flux import Flux, FluxState
from link import Link, LaserLink, RadioLink
from routing_action import RoutingAction
from strategy import Strategy
import utils
import networkx as nx
import matplotlib.pyplot as plt
from routing_action import RoutingAction
from ground_station import GroundStation
from geopy import distance
import environment as env
import random
import constants
from itertools import islice
from networkx.algorithms.flow import build_residual_network
from networkx.algorithms.connectivity import (
    build_auxiliary_node_connectivity,
    build_auxiliary_edge_connectivity,
)
from typing import Dict, List, Tuple, Self
from networkx.classes.function import path_weight

class HeaderBuilder:
    def __init__(self, rate, duration, ground_stations, satellites, source_gs, destination_gs, **kwargs ):
        self.results = None
        self.ground_stations = ground_stations
        self.satellites = satellites
        self.delayed_start = kwargs['delayed_start'] if 'delayed_start' in kwargs else 0 #optional param
        self.duration = duration
        self.source = source_gs
        self.destination = destination_gs
        self._graph = None 
        self.link_utilization = {}  #dictionary that maps link to its utilization
        self.flux = Flux(random.randint(1, 1000000), rate, (self.destination.lat, self.destination.lon)) #generate the flux
        env.put(self.delayed_start, self._begin_centralized_generation) #start generating
        env.put(self.duration, self._end_centralized_generation) #stop generating

    def _begin_centralized_generation(self):
        #print("Calculating shortest path in the costellation...")
        self.centralized_route(self.flux)
        #self.source.start_deliver_flux(self.flux) ################## modificare correttamente il percorso dei sender/deliver usati

    def _end_centralized_generation(self):
        print("Finished centralized route.")

    #Manage routing decisions (START THE CORE OF ROUTING DECISIONS doing basic route then adapting to link bandwidth)
    def centralized_route(self, flux: Flux) -> list[(RoutingAction, Flux, Link)]: #print("Flux passed to method", flux)
        routing_decisions = self.basic_centralized_route(flux)
        #routing_decisions = self.adapt_routing_decisions_to_available_link_bandwidth(flux, routing_decisions)
        print("THE ROUTING DECISIONS:", routing_decisions)
        return routing_decisions

    def basic_centralized_route(self, flux: Flux) -> list[(RoutingAction, Flux, Link)]:
        routing_output = list() #

        if constants.ROUTING_STRATEGY == Strategy.BASELINE_DIJKSTRA:
            self.prepare_results_for_dijkstra(ground_stations=self.ground_stations)
            dijkstra_shortest_path = self.calculate_dijkstra({
                'source': self.source,
                'destination': self.destination,
                'satellites': self.satellites
            })
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
                routing_output.append((action, flux, link)) #add the action to the decisions
                #env.put(0, self.calculate_dijkstra, source=self.source, destination=self.destination, satellites=self.satellites)
                #env.put(0, self.calculate_dijkstra, ground_stations=self.ground_stations, satellites=self.satellites)  # come output ritorna i "dijkstra_shortest_paths" esegui la simulazione con Dijkstra 
                #env.start()
            last_node = dijkstra_shortest_path[-1]
            last_link = self._get_link_to_ground_station(last_node, self.destination, self.satellites, self.ground_stations)
            action = RoutingAction.DELIVER
            routing_output.append((action, flux, last_link))

        elif constants.ROUTING_STRATEGY in [Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                            Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB]:
            self.prepare_results_for_disjointpaths(ground_stations=self.ground_stations)
            disjoint_paths = self.calculate_k_disjoint_paths({
                'source': self.source,
                'destination': self.destination,
                'satellites': self.satellites
            })
            #for path_index, path in enumerate(disjoint_paths): #Debug
            #    print(f"Processing path {path_index + 1}: {path}")
            if not disjoint_paths:
                #print("No valid Disjoint paths found, returning empty routing output.")
                return routing_output
            probabilities = self.calculate_path_weights_kshortest_disjoint(self._graph, disjoint_paths) #calculate probabilities based on weights of k disjoint paths
            selected_path = self.select_path_with_probabilities(disjoint_paths, probabilities) #select path based on probabilities
            routing_output = self.process_routing_output(selected_path, flux)  #process the output for routing
            if constants.ROUTING_STRATEGY == Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB:
                routing_output = self.adapt_routing_decisions_to_available_link_bandwidth(flux, routing_output) ################ adapt
        
        elif constants.ROUTING_STRATEGY in [Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING,
                                            Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_LB]:
            self.prepare_results_for_disjointpaths(ground_stations=self.ground_stations)
            disjoint_paths = self.calculate_k_disjoint_paths({
                'source': self.source,
                'destination': self.destination,
                'satellites': self.satellites
            })
            #for path_index, path in enumerate(disjoint_paths): #Debug
            #    print(f"Processing path {path_index + 1}: {path}")
            if not disjoint_paths:
                #print("No valid Disjoint paths found, returning empty routing output.")
                return routing_output
            probabilities = self.calculate_path_weights_kshortest_disjoint(self._graph, disjoint_paths) #calculate probabilities based on weights of k disjoint paths
            selected_path = self.select_path_with_probabilities(disjoint_paths, probabilities) #select path based on probabilities
            routing_output = self.process_routing_output(selected_path, flux) #process the output for routing
            if constants.ROUTING_STRATEGY == Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_LB:
                routing_output = self.adapt_routing_decisions_to_available_link_bandwidth(flux, routing_output) ################ adapt

        elif constants.ROUTING_STRATEGY == Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_COSTS_SELECTION:
            self.prepare_results_for_disjointpaths(ground_stations=self.ground_stations)
            disjoint_paths = self.calculate_k_disjoint_paths({
                'source': self.source,
                'destination': self.destination,
                'satellites': self.satellites
            })
            #Debug
            #for path_index, path in enumerate(disjoint_paths):
            #    print(f"Processing path {path_index + 1}: {path}")
            if not disjoint_paths:
                #print("No valid Disjoint paths found, returning empty routing output.")
                return routing_output
            costs = self.calculate_path_costs(self._graph, disjoint_paths) #calculate the costs of k paths
            selected_path = self.select_path_based_on_costs(disjoint_paths, costs) #select the path based on the previous costs
            routing_output = self.process_routing_output(selected_path, flux) #process the output for routing  

        elif constants.ROUTING_STRATEGY in [Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                            Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB]:
            self.prepare_results_for_disjointpaths(ground_stations=self.ground_stations)
            disjoint_paths = self.calculate_k_disjoint_paths({
                'source': self.source,
                'destination': self.destination,
                'satellites': self.satellites
            })
            #Debug
            #for path_index, path in enumerate(disjoint_paths):
            #    print(f"Processing path {path_index + 1}: {path}")
            if not disjoint_paths:
                #print("No valid Disjoint paths found, returning empty routing output.")
                return routing_output
            probabilities = self.calculate_path_weights_length_shortest_node_disjoint(self._graph, disjoint_paths) #calculate probabilities based on length of k paths
            selected_path = self.select_path_with_probabilities(disjoint_paths, probabilities) #select path based on probabilities
            routing_output = self.process_routing_output(selected_path, flux) #process the output for routing
            if constants.ROUTING_STRATEGY == Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB:
                routing_output = self.adapt_routing_decisions_to_available_link_bandwidth(flux, routing_output) ################ adapt

        
        #print("The routing output obtained from basic_centralized_route:", routing_output)
        return routing_output #
    
    def calculate_k_disjoint_paths_remaining_flux(self, kwargs):
        source: dict = kwargs['source']
        destination: dict = kwargs['destination']
        satellites: dict = kwargs['satellites']
        k = constants.K_SHORTEST_VALUE  # Number of disjoint paths required
        
        k_disjoint_paths = self._get_k_disjoint_paths(satellites, source, destination)
        '''
        if not k_disjoint_paths:
            print(f"No valid path found from {source.get_name().upper()} to {destination.get_name().upper()}.")
        else:
            print(f"Shortest node disjoint paths from {source.get_name().upper()} to {destination.get_name().upper()}: {k_disjoint_paths}")
        '''
        return k_disjoint_paths
    
    def adapt_routing_decisions_to_available_link_bandwidth(self, flux: Flux, routing_decisions: list[tuple[RoutingAction, Flux, Link]]
    ) -> list[tuple[RoutingAction, Flux, Link]]:
        adapted_routing_decisions = []
        remaining_flux = flux.clone()
        excluded_links = []  # Tracciatore dei link saturi
        support_routing_decisions = routing_decisions.copy()

        while remaining_flux:  # Continua finché c'è del flusso residuo da instradare
            for i, (action, flux, link) in enumerate(routing_decisions):
                if not remaining_flux:
                    break  # Flusso completamente instradato

                if action in [RoutingAction.FORWARD, RoutingAction.DELIVER]:
                    available_bandwidth = link.get_available_bandwidth()
                    print(f"Debug: Link {link} has available bandwidth: {available_bandwidth}")

                    if available_bandwidth > 0:
                        if available_bandwidth >= remaining_flux.rate:  # Tutto il flusso può passare
                            adapted_routing_decisions.append((action, remaining_flux, link))
                            link.reserve_bandwidth(remaining_flux)
                            remaining_flux = None
                        else:
                            # Solo una parte del flusso passa
                            splitted_flux, remaining_flux_to_route = remaining_flux.split(available_bandwidth)
                            reached_node = link.target.get_name()
                            link.reserve_bandwidth(splitted_flux)
                            self.check_path_for_splitted_flux(
                                splitted_flux,
                                support_routing_decisions[i:],
                                adapted_routing_decisions
                            )
                            remaining_flux = remaining_flux_to_route
                            excluded_links.append((link._parent.get_name(), link.target.get_name()))
                            break
                    else:
                        print(f"Link {link} is fully saturated. No flux can pass.")
                        excluded_links.append((link._parent.get_name(), link.target.get_name()))
                else:
                    adapted_routing_decisions.append((action, remaining_flux, link))

            if remaining_flux:
                new_routing_decisions = self.calculate_path_with_exclusions(remaining_flux, excluded_links, reached_node)
                if new_routing_decisions:
                    routing_decisions = new_routing_decisions  # Aggiorna il routing per il prossimo ciclo
                else:
                    adapted_routing_decisions.append((RoutingAction.ERROR, remaining_flux, None))
                    remaining_flux = None

        print("ADAPTED ROUTING DECISIONS:", adapted_routing_decisions)
        return adapted_routing_decisions


    def check_path_for_splitted_flux(self, splitted_flux: Flux, support_routing_decisions: list[tuple[RoutingAction, Flux, Link]], 
        adapted_routing_decisions: list[tuple[RoutingAction, Flux, Link]],
    ):
        for j, (inner_action, inner_flux, inner_link) in enumerate(support_routing_decisions):
            # Aggiorna il flusso nelle routing decisions di supporto
            decision_copy = support_routing_decisions.copy()
            decision_copy[j] = (inner_action, splitted_flux, inner_link)
            print(f"  Updated inner decision at index {j}: {decision_copy[j]}")

            if inner_action in [RoutingAction.FORWARD, RoutingAction.DELIVER]:
                available_bandwidth = inner_link.get_available_bandwidth()
                if available_bandwidth >= splitted_flux.rate:
                    inner_link.reserve_bandwidth(splitted_flux)
                    adapted_routing_decisions.append((inner_action, splitted_flux, inner_link))
                else:
                    new_splitted_flux, remaining_flux = splitted_flux.split(available_bandwidth)
                    inner_link.reserve_bandwidth(new_splitted_flux)
                    adapted_routing_decisions.append((inner_action, new_splitted_flux, inner_link))
                    if remaining_flux.rate > 0:  # Condizione per fermare la ricorsione
                        self.check_path_for_splitted_flux(
                            remaining_flux, decision_copy[j + 1:], adapted_routing_decisions
                        )
                    break
    
    def calculate_path_with_exclusions(self, remaining_flux: Flux, excluded_links: list[tuple[str, str]], reached_node) -> list[tuple[RoutingAction, Flux, Link]]:
        disjoint_paths = []
        g_auxiliary = self._graph.copy()  # Grafo ausiliario per calcolo
        for u, v in excluded_links:  # Rimuovi i link esclusi
            if g_auxiliary.has_edge(u, v):
                g_auxiliary.remove_edge(u, v)

        print("Nodes of Original graph:", list(g_auxiliary.nodes))
        source_satellite = reached_node
        destination = self.destination
        destination_name = self.destination.get_name().upper()
        destination_satellites = []

        closer_satellites = utils.get_closer_satellites_for_graph(self.satellites, (destination.lat, destination.lon))  # Trova i satelliti più vicini
        for sat_name, sat in closer_satellites:
            if sat_name not in self.satellites:
                print(f"Satellite {sat_name} non trovato nel dizionario 'satellites'")
                continue
            distance_to_sat = utils.get_distance_between_satellite_and_gs(sat, destination)  # Calcola la distanza
            #print("Distanza da Sat a GS destinazione:", distance_to_sat)
            if distance_to_sat <= constants.SATELLITE_COVERAGE_AREA_RADIUS:
                destination_satellites.append(sat_name)
                #g_auxiliary.add_edge(sat_name, destination_name, weight=distance_to_sat)  # Collega il satellite alla destination
        ###print("destination satellites", destination_satellites)

        print("DEBUG: Checking nodes in g_auxiliary...")
        print("Nodes in Auxiliary graph:", list(g_auxiliary.nodes))
        print("Source satellite node:", reached_node)
        print("Destination node:", destination_name)

        #if destination_name not in g_auxiliary.nodes:
         #   print(f"ERROR: Destination node {self.destination.get_name()} is not in the graph!")

        if constants.ROUTING_STRATEGY == Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB:
            for dst_sat in destination_satellites:
                    try:
                        paths = list(nx.node_disjoint_paths(g_auxiliary, source_satellite, dst_sat)) #calculate disjoint paths in graph excluding already used nodes
                        disjoint_paths.extend(paths)  #add all found paths
                    except nx.NetworkXNoPath:
                        print(f"No Node disjoint path for {constants.ROUTING_STRATEGY} between {source_satellite} and {dst_sat}.")
            probabilities = self.calculate_path_weights_kshortest_disjoint(g_auxiliary, disjoint_paths) #calculate probabilities based on weights of k disjoint paths
            selected_path = self.select_path_with_probabilities(disjoint_paths, probabilities) #select path based on probabilities
            routing_output = self.process_routing_output(selected_path, remaining_flux)
        elif constants.ROUTING_STRATEGY == Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_LB:
            for dst_sat in destination_satellites:
                    try:
                        paths = list(nx.edge_disjoint_paths(g_auxiliary, source_satellite, dst_sat)) #calculate disjoint paths in graph excluding already used nodes
                        disjoint_paths.extend(paths)  #add all found paths
                    except nx.NetworkXNoPath:
                        print(f"No Edge disjoint path for {constants.ROUTING_STRATEGY} between {source_satellite} and {dst_sat}.")
            probabilities = self.calculate_path_weights_kshortest_disjoint(g_auxiliary, disjoint_paths) #calculate probabilities based on weights of k disjoint paths
            selected_path = self.select_path_with_probabilities(disjoint_paths, probabilities) #select path based on probabilities
            routing_output = self.process_routing_output(selected_path, remaining_flux) #process the output for routing
        elif constants.ROUTING_STRATEGY == Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB:
            for dst_sat in destination_satellites:
                try:
                    paths = list(nx.node_disjoint_paths(g_auxiliary, source_satellite, dst_sat)) #calculate disjoint paths in graph excluding already used nodes
                    disjoint_paths.extend(paths)  #add all found paths
                except nx.NetworkXNoPath:
                    print(f"No Node disjoint path for {constants.ROUTING_STRATEGY} between {source_satellite} and {dst_sat}.")
            probabilities = self.calculate_path_weights_length_shortest_node_disjoint(g_auxiliary, disjoint_paths) #calculate probabilities based on length of k paths
            selected_path = self.select_path_with_probabilities(disjoint_paths, probabilities) #select path based on probabilities
            routing_output = self.process_routing_output(selected_path, remaining_flux) #process the output for routing
        return routing_output

    def process_routing_output(self, selected_path, flux):
        processed_output = []
        print(f"Processing selected path: {selected_path}") #select first disjoint path for routing flux
        for i in range(len(selected_path) - 1):
            current_node = selected_path[i]
            next_node = selected_path[i + 1]
            link = self._get_link_between_nodes_or_ground_station(current_node, next_node, self.satellites, self.ground_stations)
            if not link:
                print(f"Warning: No link found between {current_node} and {next_node}. Skipping.")
                continue
            action = RoutingAction.FORWARD
            processed_output.append((action, flux, link))
        last_node = selected_path[-1] #manage last node for delivery to GS
        last_link = self._get_link_to_ground_station(last_node, self.destination, self.satellites, self.ground_stations)
        if last_link:
            action = RoutingAction.DELIVER
            processed_output.append((action, flux, last_link))
        else:
            print(f"Warning: No link found to deliver flux from node {last_node} to destination.")
        return processed_output

    def calculate_k_disjoint_paths(self, kwargs):
        source: dict = kwargs['source']
        destination: dict = kwargs['destination']
        satellites: dict = kwargs['satellites']
        k = constants.K_SHORTEST_VALUE  # Number of disjoint paths required
        if source == destination:
            print(f"Source and destination are the same: {source.get_name().upper()}. No route needed.")
            return None
        print(f"Routing calculation from {source.get_name().upper()} - {destination.get_name().upper()}")
        k_disjoint_paths = self._get_k_disjoint_paths(satellites, source, destination)
        '''
        if not k_disjoint_paths:
            print(f"No valid path found from {source.get_name().upper()} to {destination.get_name().upper()}.")
        else:
            print(f"Shortest node disjoint paths from {source.get_name().upper()} to {destination.get_name().upper()}: {k_disjoint_paths}")
        '''
        return k_disjoint_paths
    
    def _get_k_disjoint_paths(self, satellites, source, destination):
        g= nx.DiGraph()
        source_satellites = []
        destination_satellites = []
        #print(source.get_name().upper(),"-", destination.get_name().upper())
        for name, sat in satellites.items():
            for dir, link in sat._links.items():  # Itera sui link del satellite
                if link.is_active() and link.target:  # Controlla se il link è attivo e ha un target
                    g.add_edge(name, link.target.get_name(), weight=utils.get_distance_between_satellites(sat, link.target), available_bandwidth=link.get_available_bandwidth())  # Aggiungi l'arco al grafo
                    #print(f"Edge added: {name} -> {link.target.get_name()} with distance {utils.get_distance_between_satellites(sat, link.target)}")
        #end_satellites = self._get_candidate_end_satellites_names(satellites, (destination.lat, destination.lon)) 
        
        closer_satellites = utils.get_closer_satellites_for_graph(satellites, (source.lat, source.lon))  # Trova i satelliti più vicini
        for sat_name, sat in closer_satellites:
            if sat_name not in satellites:
                print(f"Satellite {sat_name} non trovato nel dizionario 'satellites'")
                continue
            distance_to_sat = utils.get_distance_between_satellite_and_gs(sat, source)  # Calcola la distanza
            #print("Distanza da GS sorgente a Sat:", distance_to_sat)
            if distance_to_sat <= constants.SATELLITE_COVERAGE_AREA_RADIUS:
                source_satellites.append(sat_name)
                #g.add_edge(source_name, sat_name, weight=distance_to_sat)  # Collega la source al satellite
        ###print("source satellites:", source_satellites)

        closer_satellites = utils.get_closer_satellites_for_graph(satellites, (destination.lat, destination.lon))  # Trova i satelliti più vicini
        for sat_name, sat in closer_satellites:
            if sat_name not in satellites:
                print(f"Satellite {sat_name} non trovato nel dizionario 'satellites'")
                continue
            distance_to_sat = utils.get_distance_between_satellite_and_gs(sat, destination)  # Calcola la distanza
            #print("Distanza da Sat a GS destinazione:", distance_to_sat)
            if distance_to_sat <= constants.SATELLITE_COVERAGE_AREA_RADIUS:
                destination_satellites.append(sat_name)
                #g.add_edge(sat_name, destination_name, weight=distance_to_sat)  # Collega il satellite alla destination
        ###print("destination satellites", destination_satellites)

        for name, sat in satellites.items():
            for dir, link in sat._links.items():
                if link.is_active() and link.target:
                   self.link_utilization[(name, link.target.get_name())] = 0  #link utilization starts with 0 values
        # Debug: verifica il grafo
        #print("Nodi del grafo:", g.nodes)
        #print("Archi del grafo:", g.edges(data=True))
        self._graph = g #store the graph for successive use
        '''
        #Debug
        print("Struttura del grafo con disponibilità di banda:")
        for source, target, data in self._graph.edges(data=True):
            print(f"Link: {source} -> {target}")
            print(f"  Distanza: {data['weight']}")
            if 'available_bandwidth' in data:
                print(f"  Banda disponibile: {data['available_bandwidth']} Mbps")
            else:
                print("  Banda disponibile: Non definita")
        '''
        disjoint_paths = [] #list of k paths
        if constants.ROUTING_STRATEGY in [Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                          Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB]:
            for src_sat in source_satellites:
                for dst_sat in destination_satellites:
                    try:
                        paths = list(nx.node_disjoint_paths(g, src_sat, dst_sat)) #calculate disjoint paths in graph excluding already used nodes
                        disjoint_paths.extend(paths)  #add all found paths
                    except nx.NetworkXNoPath:
                        print(f"No Node disjoint path for {constants.ROUTING_STRATEGY} between {src_sat} and {dst_sat}.")

        elif constants.ROUTING_STRATEGY in [Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING,
                                            Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                            Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_COSTS_SELECTION]:
            for src_sat in source_satellites:
                for dst_sat in destination_satellites:
                    try:
                        paths = list(nx.edge_disjoint_paths(g, src_sat, dst_sat)) #calculate disjoint paths in graph excluding already used nodes
                        disjoint_paths.extend(paths)  #add all found paths
                    except nx.NetworkXNoPath:
                        print(f"No Edge disjoint path for {constants.ROUTING_STRATEGY} between {src_sat} and {dst_sat}.")

        elif constants.ROUTING_STRATEGY in [Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                            Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB]:
            for src_sat in source_satellites:
                for dst_sat in destination_satellites:
                    try:
                        paths = list(nx.node_disjoint_paths(g, src_sat, dst_sat)) #calculate disjoint paths in graph excluding already used nodes
                        disjoint_paths.extend(paths)  #add all found paths
                    except nx.NetworkXNoPath:
                        print(f"No Node disjoint path for {constants.ROUTING_STRATEGY} between {src_sat} and {dst_sat}.")
        return disjoint_paths
    
    def calculate_path_costs(graph, paths, link_utilization, alpha=0.5, beta=0.5): #sistemare questi valori...bisogna testare tutte le combinazioni di ALPHA e 1-ALPHA(quindi togliendo direttamente beta)
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
            link_occupation = sum(
                link_utilization.get((path[i], path[i+1]), 0) for i in range(len(path) - 1)
            ) / (len(path) - 1)  #avarage occupation of link
            cost = alpha * normalized_length + beta * link_occupation
            costs.append(cost)
        return costs

    def select_path_based_on_costs(paths, costs):
        total_cost = sum(costs) 
        probabilities = [1 - (cost / total_cost) for cost in costs]  # Percorsi con costi bassi hanno maggiore probabilità, conversione dei costi in probabilità
        selected_path = random.choices(population=paths, weights=probabilities, k=1)[0]
        return selected_path

    def calculate_path_weights_kshortest_disjoint(self, graph, disjoint_paths):
        path_weights = []
        for path in disjoint_paths:
            weight = 0
            for i in range(len(path) - 1):
                current_node = path[i]
                next_node = path[i + 1]
                link_key = (current_node, next_node)
                base_weight = graph[current_node][next_node]['weight'] #obtain the link's weight in graph as length
                #print("base weight:", base_weight)
                utilization = self.link_utilization.get(link_key, 0) #add factor of link occupation. If value doesn't exists, self.link_utilization returns 0
                ##########fare un CHECK sulla utilization
                link = self._get_link_between_nodes(current_node, next_node, self.satellites)
                if isinstance(link, LaserLink):
                    max_capacity = constants.SATELLITE_LINK_CAPACITY  #Default for LaserLink
                else:
                    max_capacity = constants.GROUND_STATION_LINK_CAPACITY  # Default for RadioLink
                penalty = (utilization / max_capacity)  #normalize utilization on maximum capacity (link load/link)
                weight += base_weight * (1 + penalty)  #penalty for more occupied links
            path_weights.append(weight)
        total_weight = sum(path_weights) #sum all weights for normalization
        probabilities = [1 - (w / total_weight) for w in path_weights] #lightest paths have higher probabilities
        return probabilities

    def calculate_path_weights_length_shortest_node_disjoint(self, graph, paths):
        total_path_weights = sum([1 - (path_weight(graph, path, weight="weight") / sum([path_weight(graph, p, weight="weight") for p in paths])) for path in paths]) #total weights as length of paths
        weights = [(1 - (path_weight(graph, path, weight="weight") / sum([path_weight(graph, p, weight="weight") for p in paths]))) / total_path_weights for path in paths] #normalized weights
        return weights

    #select path based on probabilities
    def select_path_with_probabilities(self, paths, probabilities): 
        selected_path = random.choices(population=paths, weights=probabilities, k=1)[0]
        return selected_path

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
        #print("Destination:", destination)
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
        destination_gs = ground_stations[destination_name]
        attached_gs_list = last_satellite._gs_link.get_attached_gs()
        if destination_gs not in attached_gs_list:
            raise ValueError(f"Ground station '{destination_gs}' not attached to satellite '{last_satellite}'.")
        #print(f"Last satellite in path: {last_satellite}")
        #print(f"Destination ground station: {destination_gs}")
        #print(f"Checking links between {last_satellite} and ground station...")
        #print(f"Available satellites: {list(self.satellites.keys())}")
        #print(f"Available ground stations: {list(self.ground_stations.keys())}")
        # Controlla il collegamento radio verso la stazione di terra
        #if satellite._gs_link.is_active():
         #   print(f"Found active radio link from satellite '{node}' to ground station '{destination.get_name()}'.")
           # return satellite._gs_link
        return last_satellite._gs_link

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

    def prepare_results_for_dijkstra(self, ground_stations):
        self.results = {}
        for source in ground_stations.values():
            for destination in ground_stations.values():
                if source == destination: 
                    continue
                self.results[source.get_name() + ' - ' + destination.get_name()] = { #create a key in self.result made by GSsource-GSdestination
                    'DIJKSTRA' : {} #for Dijkstra
                }
                for strategy in self.results[source.get_name() + ' - ' + destination.get_name()].keys(): #for every strategy
                    self.results[source.get_name() + ' - ' + destination.get_name()][strategy] = {
                        'successful' : [], #store succesful routing
                        'failed' : 0, #count all failed routings that are 0 for Dijkstra
                        'distance' : [] #store the travelled distance
                    }
    
    def prepare_results_for_disjointpaths(self, ground_stations):
        self.results = {}
        for source in ground_stations.values():
            for destination in ground_stations.values():
                if source == destination: 
                    continue
                if constants.ROUTING_STRATEGY == Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING:
                    self.results[source.get_name() + ' - ' + destination.get_name()] = { #create a key in self.result made by GSsource-GSdestination
                        'K-SHORTEST-NODE-DISJOINT-PATHS' : {} #for K-shortest disjoint paths
                    }
                elif constants.ROUTING_STRATEGY == Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB:
                    self.results[source.get_name() + ' - ' + destination.get_name()] = {
                        'K-SHORTEST-NODE-DISJOINT-PATHS-WITH-LOAD-BALANCING' : {}
                    }
                elif constants.ROUTING_STRATEGY == Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING:
                    self.results[source.get_name() + ' - ' + destination.get_name()] = {
                        'K-SHORTEST-EDGE-DISJOINT-PATHS' : {}
                    }
                elif constants.ROUTING_STRATEGY == Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_LB:
                    self.results[source.get_name() + ' - ' + destination.get_name()] = {
                        'K-SHORTEST-EDGE-DISJOINT-PATHS-WITH-LOAD-BALANCING' : {}
                    }
                elif constants.ROUTING_STRATEGY == Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING:
                    self.results[source.get_name() + ' - ' + destination.get_name()] = {
                        'LENGTH-SHORTEST-NODE-DISJOINT-PATHS' : {}
                    }
                elif constants.ROUTING_STRATEGY == Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB:
                    self.results[source.get_name() + ' - ' + destination.get_name()] = {
                        'LENGTH-SHORTEST-NODE-DISJOINT-PATHS-WITH-LOAD-BALANCING' : {}
                    }
                elif constants.ROUTING_STRATEGY == Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_COSTS_SELECTION:
                    self.results[source.get_name() + ' - ' + destination.get_name()] = {
                        'CALCULATION-WITH-COSTS-SELECTION' : {} #cambiare il nome della strategia
                    }

                for strategy in self.results[source.get_name() + ' - ' + destination.get_name()].keys(): #for every strategy
                    self.results[source.get_name() + ' - ' + destination.get_name()][strategy] = {
                        'successful' : [], #store succesful routings
                        'failed' : [], #stores failed routings
                        'distance' : [] #store the travelled distances
                    }

    def calculate_dijkstra(self, kwargs):
        source: dict = kwargs['source']
        destination: dict = kwargs['destination']
        satellites: dict = kwargs['satellites']

        if source == destination:
            print(f"Source and destination are the same: {source.get_name()}. No route needed.")
            return None
        #Calculates the shortest path with Dijkstra's algorithm
        dijkstra_shortest_path = self._get_dijkstra_shortest_path(satellites, source, destination)
        if not dijkstra_shortest_path:
            print(f"No valid path found from {source.get_name()} to {destination.get_name()}.")
        else:
            print(f"Shortest path from {source.get_name()} to {destination.get_name()}: {dijkstra_shortest_path}")
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

        shortest_paths = [d.get_path(end_satellite) for end_satellite in end_satellites]
        if not shortest_paths: #if there are shortest paths (there is always a path, but it's a check for wrong construction of constellation)
            print(f"No available paths from {source.get_name()} to {destination.get_name()}.")
            return []  #or could put None as return, if necessary

        shortest_path = min(shortest_paths, key=lambda x: len(x)) #return only one of the shortest paths, not all
        shortest_paths = [path for path in shortest_paths if len(path) == len(shortest_path)] #returns all the paths with same length as the shortest
        for sp in shortest_paths:
            print(f"Dijkstra's shortest path from {source.get_name()} to {destination.get_name()}: ", sp)
        print(f"Dijkstra's shortest path length from {source.get_name()} to {destination.get_name()}: ", len(shortest_paths), "x", len(shortest_path), "hops.")
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
        print(f"The shortest path from {source.get_name()} to {destination.get_name()} in km is: {shortest_path}")
        print(f"Total distance {min_distance:.2f} km")
        # Saving results
        #self.results[source.get_name() + ' - ' + destination.get_name()]['DIJKSTRA']['successful'].append(len(shortest_path))
        #self.results[source.get_name() + ' - ' + destination.get_name()]['DIJKSTRA']['distance'].append(min_distance)
        return shortest_path #only the path with minimum distance on minimum number of hops

    def _get_alternate_paths(self, source, target):
        """
        Trova percorsi alternativi tra due nodi nel grafo.
        """
        try:
            paths = list(nx.all_shortest_paths(self._graph, source=source, target=target, weight='weight'))
            return paths
        except nx.NetworkXNoPath:
            print(f"No alternate paths found between {source} and {target}.")
            return []

    def _is_path_feasible(self, path, flux):
        """
        Verifica se un percorso alternativo ha sufficiente larghezza di banda disponibile.
        """
        for i in range(len(path) - 1):
            link_key = (path[i], path[i + 1])
            current_utilization = self.link_utilization.get(link_key, 0)
            max_capacity = constants.SATELLITE_LINK_CAPACITY if isinstance(self.satellites[path[i]]._links.get(path[i + 1]), LaserLink) else constants.GROUND_STATION_LINK_CAPACITY
            
            if flux.rate > (max_capacity - current_utilization):
                return False  # Il percorso non è utilizzabile
        return True

    def _build_routing_decisions_from_path(self, path, flux):
        """
        Costruisce le decisioni di routing per un percorso specifico.
        """
        routing_decisions = []
        for i in range(len(path) - 1):
            source = path[i]
            target = path[i + 1]
            link = self._get_link_between_nodes(source, target, self.satellites)
            if link:
                action = RoutingAction.FORWARD
                routing_decisions.append((action, flux, link))
        return routing_decisions
