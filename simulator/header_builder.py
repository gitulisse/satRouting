import constants
import dijkstra
from flux import Flux, FluxState
from link import Link
from routing_action import RoutingAction
from strategy import Strategy
import utils
import networkx as nx
import matplotlib.pyplot as plt
from routing_action import RoutingAction
from link import Link
from ground_station import GroundStation
from geopy import distance
from satellite import Sat
import environment as env
import random

class HeaderBuilder:
    def __init__(self, rate, duration, ground_stations, satellites, source_gs, destination_gs, **kwargs ): #rate, duration
        self.results = None
        self.ground_stations = ground_stations
        self.satellites = satellites
        self.delayed_start = kwargs['delayed_start'] if 'delayed_start' in kwargs else 0 #optional param
        self.duration = duration
        self.source = source_gs
        self.destination = destination_gs
        self.flux = Flux(random.randint(1, 1000000), rate, (self.destination.lat, self.destination.lon)) #generate the flux
        env.put(self.delayed_start, self._begin_centralized_generation) #start generating
        env.put(self.duration, self._end_centralized_generation) #stop generating

    def _begin_centralized_generation(self):
        print("Calculating shortest path in the costellation...")
        self.centralized_route(constants.ROUTING_STRATEGY)

    def _end_centralized_generation(self):
        print("Finished centralized route.")

    #Manage routing decisions (START THE CORE OF ROUTING DECISIONS doing basic route then adapting to link bandwidth)
    def centralized_route(self, flux: Flux) -> list[(RoutingAction, Flux, Link)]:
        #print("Flux passed to method", flux)
        routing_decisions = self.basic_centralized_route(flux)
        #routing_decisions = self.adapt_routing_decisions_to_available_link_bandwidth(flux, routing_decisions)
        return routing_decisions

    def basic_centralized_route(self, strategy):
        #print("start basic_centraized_route method")
        
        if strategy == Strategy.BASELINE_DIJKSTRA:
            self.prepare_results_for_dijkstra(ground_stations=self.ground_stations)
            
            env.put(0, self.calculate_dijkstra, source=self.source, destination=self.destination, satellites=self.satellites)
            #env.put(0, self.calculate_dijkstra, ground_stations=self.ground_stations, satellites=self.satellites)  # come output ritorna i "dijkstra_shortest_paths" esegui la simulazione con Dijkstra 
            #return routing_output

    def calculate_dijkstra(self, kwargs):
        source: dict = kwargs['source']
        destination: dict = kwargs['destination']
        satellites: dict = kwargs['satellites']

        if source == destination:
            print(f"Source and destination are the same: {source.get_name()}. No route needed.")
            return None

        # Calcola il percorso più breve con Dijkstra
        dijkstra_shortest_path = self._get_dijkstra_shortest_path(satellites, source, destination)

        if not dijkstra_shortest_path:
            print(f"No valid path found from {source.get_name()} to {destination.get_name()}.")
        else:
            print(f"Shortest path from {source.get_name()} to {destination.get_name()}: {dijkstra_shortest_path}")

        return dijkstra_shortest_path

    
    '''
    def calculate_dijkstra_BACKUP(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        satellites: dict = kwargs['satellites']

        for source in ground_stations.values():
            for destination in ground_stations.values():
                if source == destination:
                    continue

                # Calcola i percorsi più brevi con Dijkstra
                dijkstra_shortest_paths = self._get_dijkstra_shortest_paths(satellites, source, destination) #cambiato _get_dijkstra_shortest_path(S)
                #print("shortest paths:", dijkstra_shortest_paths)   

                # Aggiungi i risultati di successo e distanza
                self.results[source.get_name() + ' - ' + destination.get_name()]['DIJKSTRA']['successful'].append(len(dijkstra_shortest_paths[0]))
                self.results[source.get_name() + ' - ' + destination.get_name()]['DIJKSTRA']['distance'].append(min([self._get_path_distance(dijkstra_shortest_path, source, destination, satellites) for dijkstra_shortest_path in dijkstra_shortest_paths]))

        print("RESULTS stored in HeaderBuilder", self.results)
        #print("PATHS returned by the calculate_dijkstra", dijkstra_shortest_paths)
        return dijkstra_shortest_paths
    '''
    
    #calculate all the shortest available paths from SOURCE to DESTINATION
    #returning THE SHORTEST PATH with minimum distance on minimum number of hops
    def _get_dijkstra_shortest_path(self, satellites, source, destination):
        
        g = dijkstra.Graph() #construct a graph for satellites    
       
        for name, sat in satellites.items():  #for every satellite item using as keys name & sat, and for every link of them check if link is active
            for link in sat._links.values(): 
                if link.is_active():
                    g.add_edge(name, link.target.get_name(), utils.get_distance_between_satellites(sat, link.target)) #add a connection from name(the current satellite) to the target
        end_satellites = self._get_candidate_end_satellites_names(satellites, (destination.lat, destination.lon)) #otherwise check for the closet satellites in the area of destination GS

        #calculate Dijkstra's shortest path
        d = dijkstra.DijkstraSPF(g, source.sat.get_name()) #initialize dijkstra algorithm on the graph starting from source

        shortest_paths = [d.get_path(end_satellite) for end_satellite in end_satellites]

        if not shortest_paths: #if there are shortest paths (there is always a path, but it's a check for wrong construction of constellation)
            print(f"No available paths from {source.get_name()} to {destination.get_name()}.")
            return []  #or could put None as return, if necessary

        shortest_path = min(shortest_paths, key=lambda x: len(x)) #return only one of the shortest paths, not all

        shortest_paths = [path for path in shortest_paths if len(path) == len(shortest_path)] #returns all the paths with same length as the shortest

        for sp in shortest_paths:
            print(f"Dijkstra's shortest path from {source.get_name()} to {destination.get_name()}: ", sp)
        print(f"Dijkstra's shortest path length from {source.get_name()} to {destination.get_name()}: ", len(shortest_paths), "x", len(shortest_path), "hops.")
        
        #Calculates distances for all paths remained with minimum number of hops
        path_distances = [
            (path, self._get_path_distance(path, source, destination, satellites)) 
            for path in shortest_paths
        ]
        shortest_path, min_distance = min(path_distances, key=lambda x: x[1]) #order and find the path with the minimum distance

        # Print the shortest path and its distance
        print(f"The shortest path from {source.get_name()} to {destination.get_name()} in km is: {shortest_path}")
        print(f"Total distance {min_distance:.2f} km")

        return shortest_path #only the path with minimum distance on minimum number of hops
    

    #Routing decisions for bandwidth
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


