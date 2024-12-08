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
    def centralized_route(self, flux: Flux) -> list[(RoutingAction, Flux, Link)]:
        #print("Flux passed to method", flux)
        routing_decisions = self.basic_centralized_route(flux)
        #routing_decisions = self.adapt_routing_decisions_to_available_link_bandwidth(flux, routing_decisions)

        #########print("THE ROUTING DECISIONS:", routing_decisions)
        return routing_decisions

    def basic_centralized_route(self, flux: Flux) -> list[(RoutingAction, Flux, Link)]:
        routing_output = list() #

        if constants.ROUTING_STRATEGY == Strategy.BASELINE_DIJKSTRA:
            self.prepare_results_for_dijkstra(ground_stations=self.ground_stations)
            
            #find the shortest path for dijkstra algorithm
            dijkstra_shortest_path = self.calculate_dijkstra({
                'source': self.source,
                'destination': self.destination,
                'satellites': self.satellites
            })

            #print("SHORTEST PATH calculated and passed to basic_centralize_route", dijkstra_shortest_path)
            
            if not dijkstra_shortest_path:
                print("No valid path found for Dijkstra, returning empty routing output.")
                return routing_output
            
            #iterates on the path to build che routing_output
            for i in range(len(dijkstra_shortest_path) - 1):
                current_node = dijkstra_shortest_path[i]
                next_node = dijkstra_shortest_path[i + 1]

                #retrieve the link between a node and the next node in the path
                link = self._get_link_between_nodes(current_node, next_node, self.satellites)

                if not link:
                    print(f"Warning: No link found between {current_node} and {next_node}. Skipping.")
                    continue

                #determinates the action that must be executed
                action = RoutingAction.FORWARD

                #add the action to the decisions
                routing_output.append((action, flux, link))
                #env.put(0, self.calculate_dijkstra, source=self.source, destination=self.destination, satellites=self.satellites)
                #env.put(0, self.calculate_dijkstra, ground_stations=self.ground_stations, satellites=self.satellites)  # come output ritorna i "dijkstra_shortest_paths" esegui la simulazione con Dijkstra 
                #env.start()

            last_node = dijkstra_shortest_path[-1]
            last_link = self._get_link_to_ground_station(last_node, self.destination, self.satellites, self.ground_stations)

            action = RoutingAction.DELIVER
            routing_output.append((action, flux, last_link))

        if constants.ROUTING_STRATEGY == Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING:
            print("Starting the Kshortestdisjointpaths algorithm...")
            self.prepare_results_for_kshortestdisjointpaths(ground_stations=self.ground_stations)
            
            #disjoint_paths = self.calculate_k_disjoint_paths({'source': self.source, 'destination': self.destination, 'satellites': self.satellites})
            disjoint_paths = self.calculate_k_disjoint_paths({
                'source': self.source,
                'destination': self.destination,
                'satellites': self.satellites
            })

            if not disjoint_paths:
                #print("No valid Disjoint paths found, returning empty routing output.")
                return routing_output
            
            # Seleziona il primo percorso disgiunto per instradare il flusso
            routing_output = []

            for path_index, path in enumerate(disjoint_paths):
                print(f"Processing path {path_index + 1}: {path}")
                single_path_routing_output = []
            
                for i in range(len(path) - 2):
                    current_node = path[i]
                    next_node = path[i + 1]

                    link = self._get_link_between_nodes_or_ground_station(current_node, next_node, self.satellites, self.ground_stations)
                    if not link:
                        print(f"Warning: No link found between {current_node} and {next_node}. Skipping.")
                        continue

                    action = RoutingAction.FORWARD
                    single_path_routing_output.append((action, flux, link))

                last_node = path[-2]
                last_link = self._get_link_to_ground_station(last_node, self.destination, self.satellites, self.ground_stations)
                action = RoutingAction.DELIVER
                single_path_routing_output.append((action, flux, last_link))

                routing_output.append(single_path_routing_output)

        #print("The routing output obtained from basic_centralized_route:", routing_output)
        return routing_output #


    def calculate_k_disjoint_paths(self, kwargs):
        source: dict = kwargs['source']
        destination: dict = kwargs['destination']
        satellites: dict = kwargs['satellites']

        k = constants.K_SHORTEST_VALUE  # Number of disjoint paths required

        if source == destination:
            print(f"Source and destination are the same: {source.get_name().upper()}. No route needed.")
            return None

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
        #print(source.get_name().upper(),"-", destination.get_name().upper())
        for name, sat in satellites.items():
            for dir, link in sat._links.items():  # Itera sui link del satellite
                if link.is_active() and link.target:  # Controlla se il link è attivo e ha un target
                    g.add_edge(name, link.target.get_name(), weight=utils.get_distance_between_satellites(sat, link.target))  # Aggiungi l'arco al grafo
                    #print(f"Edge added: {name} -> {link.target.get_name()} with distance {utils.get_distance_between_satellites(sat, link.target)}")
        ###########end_satellites = self._get_candidate_end_satellites_names(satellites, (destination.lat, destination.lon)) 
        
        #connect source GS to closest satellites
        source_name = source.get_name().upper()
        g.add_node(source_name)  # Aggiungi la ground station come nodo
        closer_satellites = utils.get_closer_satellites_for_graph(satellites, (source.lat, source.lon))  # Trova i satelliti più vicini
        for sat_name, sat in closer_satellites:
            if sat_name not in satellites:
                print(f"Satellite {sat_name} non trovato nel dizionario 'satellites'")
                continue
            distance_to_sat = utils.get_distance_between_satellite_and_gs(sat, source)  # Calcola la distanza
            #print("Distanza da GS sorgente a Sat:", distance_to_sat)
            if distance_to_sat <= constants.SATELLITE_COVERAGE_AREA_RADIUS:
                g.add_edge(source_name, sat_name, weight=distance_to_sat)  # Collega la source al satellite

        #connect last satellites to destination GS
        destination_name = destination.get_name().upper()
        g.add_node(destination_name)  # Aggiungi la ground station come nodo
        closer_satellites = utils.get_closer_satellites_for_graph(satellites, (destination.lat, destination.lon))  # Trova i satelliti più vicini
        for sat_name, sat in closer_satellites:
            if sat_name not in satellites:
                print(f"Satellite {sat_name} non trovato nel dizionario 'satellites'")
                continue
            distance_to_sat = utils.get_distance_between_satellite_and_gs(sat, destination)  # Calcola la distanza
            #print("Distanza da Sat a GS destinazione:", distance_to_sat)
            if distance_to_sat <= constants.SATELLITE_COVERAGE_AREA_RADIUS:
                g.add_edge(sat_name, destination_name, weight=distance_to_sat)  # Collega il satellite alla destination

        # Debug: verifica il grafo
        #print("Nodi del grafo:", g.nodes)
        #print("Archi del grafo:", g.edges(data=True))

        #check if source & destination are inside the graph 
        if source_name not in g or destination_name not in g:
            print(f"Errore: source ({source_name}) o destination ({destination_name}) non trovati nel grafo.")
            return []

        disjoint_paths = [] #list of k paths
        try:
            paths = list(nx.node_disjoint_paths(g, source_name, destination_name)) #calculate disjoint paths in graph excluding already used nodes
            disjoint_paths.extend(paths)  #add all found paths
        except nx.NetworkXNoPath:
            print(f"No path between {source_name} and {destination_name}.")
        
        return disjoint_paths

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

    #Routing decisions for bandwidth (modificare la tupla delle routing_decisions per passarlo come parametro togliendo le info del flux)
    def adapt_routing_decisions_to_available_link_bandwidth(self, flux: Flux, routing_decisions: list[tuple[RoutingAction, Link]]) -> list[tuple[RoutingAction, Flux, Link]]:
        adapted_routing_decisions = []
        for action, link in routing_decisions:
            if action == RoutingAction.FORWARD or action == RoutingAction.DELIVER:
                available_bandwidth = link.get_available_bandwidth()
                if available_bandwidth == 0:
                    continue
                if available_bandwidth >= flux.rate:
                    adapted_routing_decisions.append((action, flux, link))
                    break
                else:
                    f, flux = flux.split(available_bandwidth)
                    adapted_routing_decisions.append((action, f, link))
                    #adapted_routing_decisions.append((RoutingAction.REOPEN, flux, None))
                    #break
            elif action == RoutingAction.ERROR:
                adapted_routing_decisions.append((action, flux, link))
                break
        else:
            adapted_routing_decisions.append((RoutingAction.ERROR, flux, FluxState.SATELLITE_CONGESTED))
        return adapted_routing_decisions

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
    
    def prepare_results_for_kshortestdisjointpaths(self, ground_stations):
        self.results = {}
        for source in ground_stations.values():
            for destination in ground_stations.values():
                if source == destination: 
                    continue
                self.results[source.get_name() + ' - ' + destination.get_name()] = { #create a key in self.result made by GSsource-GSdestination
                    'K-SHORTEST-DISJOINT-PATHS' : {} #for K-shortest disjoint paths
                }
                for strategy in self.results[source.get_name() + ' - ' + destination.get_name()].keys(): #for every strategy
                    self.results[source.get_name() + ' - ' + destination.get_name()][strategy] = {
                        'successful' : [], #store succesful routings
                        'failed' : [], #stores failed routings
                        'distance' : [] #store the travelled distances
                    }

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
        # for the links of source satellite key:direction and value:link
        for direction, link in satellite1._links.items():
            if link.target is None:  #if link as a target
                #print(f"Link with {direction} from '{node1}' has no target.")
                continue
            if link.target.get_name() == node2:  #check if target is effectively the next satellite of the shortest path
                #print(f"Link found between '{node1}' and '{node2}' with {direction}.")
                return link
        #if there is no link throws the error
        raise ValueError(f"No link exists between '{node1}' and '{node2}'.")
    
    def _get_link_to_ground_station(self, node, destination, satellites, ground_stations):
        #Debug
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

        #print(f"No active link from satellite '{node}' to ground station '{destination.get_name()}'.")
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