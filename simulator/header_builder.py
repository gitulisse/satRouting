import constants
import dijkstra
from flux import Flux
from link import Link
from routing_action import RoutingAction
from strategy import Strategy
import utils
import networkx as nx
import matplotlib.pyplot as plt
from routing_action import RoutingAction
from link import Link, LaserLink, RadioLink
from ground_station import GroundStation
from geopy import distance
from satellite import Sat

class HeaderBuilder:
    def __init__(self, ground_stations: list, satellites: list):
        self.results = None
        self.ground_stations = ground_stations
        self.satellites = satellites
    
    #Manage routing decisions (START THE CORE OF ROUTING DECISIONS doing basic route then adapting to link bandwidth)
    def centralized_route(self, flux: Flux) -> list[(RoutingAction, Flux, Link)]:

        routing_decisions = self.basic_centralized_route(flux)
        routing_decisions = self.adapt_routing_decisions_to_available_link_bandwidth(flux, routing_decisions)
        return routing_decisions

    def basic_centralized_route(self, flux: Flux, avoid: list[Link] = []) -> list[tuple[RoutingAction, Link]]:
        routing_output = list()

        #calculates distance from the target, if in the satellite's range, flux is delivered to GS destination
        distance_from_destination = distance.distance((GroundStation.get_latitudeGS(), GroundStation.get_longitudeGS()), flux.destination).km
        if distance_from_destination < constants.SATELLITE_COVERAGE_AREA_RADIUS:
            routing_output.append((RoutingAction.DELIVER, Sat._gs_link))

        print("centralizzato")

        return routing_output

    def prepare_results_for_dijkstra(self, ground_stations):
        self.results = {}
        for source in ground_stations.values():
            for destination in ground_stations.values():
                if source == destination: continue
                self.results[source.get_name() + ' - ' + destination.get_name()] = { #create a key in self.result made by GSsource-GSdestination
                    'DIJKSTRA' : {}
                }

    #calculate shortest path between 2 GS stations with DIJKSTRA
    def sample_dijkstra(self, kwargs):
        ground_stations: dict = kwargs['ground_stations']
        satellites: dict = kwargs['satellites']
        for source in ground_stations.values():
            for destination in ground_stations.values():
                if source == destination: continue
                dijkstra_shortest_paths = self._get_dijkstra_shortest_paths(satellites, source, destination)

                if dijkstra_shortest_paths:
                    self.results[source.get_name() + ' - ' + destination.get_name()]['DIJKSTRA']['successful'].append(len(dijkstra_shortest_paths[0]))
                else:
                    # In caso contrario, gestisci il caso senza percorsi (potresti aggiungere 0, None o un messaggio)
                    print(f"Nessun percorso disponibile tra {source.get_name()} e {destination.get_name()}.")
                    self.results[source.get_name() + ' - ' + destination.get_name()]['DIJKSTRA']['successful'].append(0)
                
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
                
    #calculate all the shortest available paths
    def _get_dijkstra_shortest_paths(self, satellites, source, destination):
        g = dijkstra.Graph() #construct a graph for satellites 
        #for every satellite item using as keys name & sat, and for every link of them check if link is active
        for name, sat in satellites.items(): 
            for link in sat._links.values(): 
                if link.is_active():
                    g.add_edge(name, link.target.get_name(), utils.get_distance_between_satellites(sat, link.target)) #add a connection from name(the current satellite) to the target
        end_satellites = self._get_candidate_end_satellites_names(satellites, (destination.lat, destination.lon)) #otherwise check for the closet satellites in the area of destination GS

        d = dijkstra.DijkstraSPF(g, source.sat.get_name()) #calculate Dijkstra's shortest path,initialize dijkstra algorithm on the graph starting from source
        shortest_paths = []
        for end_satellite in end_satellites:
            path = d.get_path(end_satellite)
            if path: # Verifica che il percorso non sia vuoto
                shortest_paths.append(path)

        if not shortest_paths: # Controlla se ci sono percorsi disponibili
            print(f"Non ci sono percorsi disponibili da {source.get_name()} a {destination.get_name()}.")
            return []  # Oppure None, a seconda di come vuoi gestire l'assenza di percorsi

        shortest_path = min(shortest_paths, key=lambda x: len(x))
        #debug
        print(shortest_path)

        shortest_paths = [path for path in shortest_paths if len(path) == len(shortest_path)]

        return shortest_paths



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
    def centralized_route(self, kwargs, flux: Flux, avoid: list[Link] = []) -> list[tuple[RoutingAction, Link]]:
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

