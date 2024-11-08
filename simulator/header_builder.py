import constants
import dijkstra
from flux import Flux
from link import Link
from routing_action import RoutingAction
from strategy import Strategy
import utils


class HeaderBuilder:
    def __init__(self, ground_stations: list, satellites: list):
        self.results = None
        self.ground_stations = ground_stations
        self.satellites = satellites
        
        
    #add routing method for GS
    #Route method
    def centralized_route(self, flux: Flux, avoid: list[Link] = []) -> list[tuple[RoutingAction, Link]]:
        
        # Ground stations e satelliti come punti di partenza e destinazione
        ground_stations = self.gss  # Dizionario delle ground stations
        satellites = self.satellites  # Dizionario dei satelliti disponibili

        # Risultato per il routing
        routing_output = list()

        if constants.ROUTING_STRATEGY == Strategy.BASELINE_DIJKSTRA:
            # Ciclo su ogni coppia di stazioni di partenza e arrivo
            for source in ground_stations.values():
                for destination in ground_stations.values():
                    if source == destination: continue  # Evita routing verso sé stesso

                    # Ottieni i percorsi più brevi da source a destination
                    dijkstra_shortest_paths = self._get_dijkstra_shortest_paths(satellites, source, destination)
                    #self.results[source.get_name() + ' - ' + destination.get_name()]['DIJKSTRA']['successful'].append(len(dijkstra_shortest_paths[0])) #first shortest path
                    #self.results[source.get_name() + ' - ' + destination.get_name()]['DIJKSTRA']['distance'].append(min([self._get_path_distance(dijkstra_shortest_path, source, destination, satellites) for dijkstra_shortest_path in dijkstra_shortest_paths])) #append under the key 'distance' the minimun path distance from all dijkstra_shortest_paths for each source-destination couple
                
                    # Prendi il percorso più breve ottenuto con Dijkstra
                    if dijkstra_shortest_paths:
                        shortest_path = dijkstra_shortest_paths[0]
                        
                        # Converti il percorso più breve in una lista di azioni di routing e link
                        for i in range(len(shortest_path) - 1):
                            current_node = shortest_path[i]
                            next_node = shortest_path[i + 1]
                           
                            # Identifica il link tra current_node e next_node
                            link = satellites[current_node]._links.get(next_node)
                            if link and link.is_active():
                                routing_action = RoutingAction(source, destination, flux)
                                routing_output.append((routing_action, link))
        
        return routing_output
    

    #add routing method for GS
    #Route method
    def basic_route(self, kwargs, flux: Flux, avoid: list[Link] = []) -> list[tuple[RoutingAction, Link]]:
        ground_stations: dict = kwargs['ground_stations']
        satellites: dict = kwargs['satellites'] #extract the dictionary of satellites
        
        routing_output = list()

        def get_nodes_to_be_excluded_from_next_hop_candidates(flux) -> list:
            if constants.LOOP_AVOIDANCE_CUTOFF == 0: #if 0 no need to avoid loops #if > 0 excludes a defined number of previously made passages by the flux
                return []
            else:
                #take steps of flux if steps < CUTOFF value & if CUTOFF > 0 take only the last N steps (equal to CUTOFF) from the steps list of the current flux 
                steps = flux.get_steps() if len(flux.get_steps()) < constants.LOOP_AVOIDANCE_CUTOFF else flux.get_steps()[-constants.LOOP_AVOIDANCE_CUTOFF:] 
                if steps[-1] == self: 
                    steps = steps[:-1] #cut steps list if the last step was the current satellite
                indices = [i+1 for i, x in enumerate(steps) if x == self] #indices in steps that corresponds to current node
                if len(steps) > 0:
                    indices.append(-1)
                return [steps[i] for i in indices] #list of excluded steps as NEXT HOP

        if constants.ROUTING_STRATEGY == Strategy.BASELINE_DIJKSTRA:
            for source in ground_stations.values(): #start from every source 
                for destination in ground_stations.values(): #and all related destinations
                    if source == destination: continue
                    dijkstra_shortest_paths = self._get_dijkstra_shortest_paths(satellites, source, destination) #obtain shortest paths
                    self.results[source.get_name() + ' - ' + destination.get_name()]['DIJKSTRA']['successful'].append(len(dijkstra_shortest_paths[0])) #first shortest path
                    self.results[source.get_name() + ' - ' + destination.get_name()]['DIJKSTRA']['distance'].append(min([self._get_path_distance(dijkstra_shortest_path, source, destination, satellites) for dijkstra_shortest_path in dijkstra_shortest_paths])) #append under the key 'distance' the minimun path distance from all dijkstra_shortest_paths for each source-destination couple

        if constants.ROUTING_STRATEGY == Strategy.NO_SMOOTHING_ON_BUFFER_SIZE_SOURCE_ROUTING:
            print()
        
        
        return routing_output
    

    
    #calculate shortest path between 2 GS stations with DIJKSTRA
    def sample_dijkstra(self, kwargs): #kwargs passes a single dictionary
        ground_stations: dict = kwargs['ground_stations'] #extract the dictionary of GS
        satellites: dict = kwargs['satellites'] #extract the dictionary of satellites
        for source in ground_stations.values(): #start from every source 
            for destination in ground_stations.values(): #and all related destinations
                if source == destination: continue #skip 
                dijkstra_shortest_paths = self._get_dijkstra_shortest_paths(satellites, source, destination) #obtain shortest paths
                self.results[source.get_name() + ' - ' + destination.get_name()]['DIJKSTRA']['successful'].append(len(dijkstra_shortest_paths[0])) #first shortest path
                self.results[source.get_name() + ' - ' + destination.get_name()]['DIJKSTRA']['distance'].append(min([self._get_path_distance(dijkstra_shortest_path, source, destination, satellites) for dijkstra_shortest_path in dijkstra_shortest_paths])) #append under the key 'distance' the minimun path distance from all dijkstra_shortest_paths for each source-destination couple

    #calculate all the shortest available paths
    def _get_dijkstra_shortest_paths(self, satellites, source, destination):
        
        g = dijkstra.Graph() #construct a graph for satellites

        #for every satellite item using as keys name & sat, and for every link of them check if link is active
        for name, sat in satellites.items(): 
            for link in sat._links.values(): 
                if link.is_active():
                    g.add_edge(name, link.target.get_name(), utils.get_distance_between_satellites(sat, link.target)) #add a connection from name(the current satellite) to the target
        end_satellites = self._get_candidate_end_satellites_names(satellites, (destination.lat, destination.lon)) #otherwise check for the closet satellites in the area of destination GS

        #calculate Dijkstra's shortest path
        d = dijkstra.DijkstraSPF(g, source.sat.get_name()) #initialize dijkstra algorithm on the graph starting from source

        shortest_paths = [d.get_path(end_satellite) for end_satellite in end_satellites] #list of paths, for every candidate as end_satellite calculate the shortest path from the source
        shortest_path = min(shortest_paths, key=lambda x: len(x)) #obtain the shortest path in the list shortest_paths
        shortest_paths = [path for path in shortest_paths if len(path) == len(shortest_path)] #maintain each path that is equal in length to the shortest path
        for sp in shortest_paths:
            print(f"Dijkstra's shortest path from {source.get_name()} to {destination.get_name()}: ", sp)
        print(f"Dijkstra's shortest path length from {source.get_name()} to {destination.get_name()}: ", len(shortest_paths), "x", len(shortest_path), "hops.")
        return shortest_paths

    #obtain list of closer satellites in coverage area
    def _get_candidate_end_satellites_names(self, satellites, position):
        sat_list = utils.get_closer_satellites(satellites, position) #list of closer satellites
        return [sat['name'] for sat in sat_list if sat['distance'] < constants.SATELLITE_COVERAGE_AREA_RADIUS] #list of the only satellites inside the coverage area of self

