import constants
from geopy import distance
from flux import Flux, FluxState
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


class GroundStation:
    def __init__(self, lat, lon, name, keep_log: bool = True) -> None:
        self.lat = lat
        self.lon = lon
        self.sat = None
        self.serving_population = 0
        self.name = name
        self.satellites = None
        self.gss = None
        self.outgoing_fluxes: list[Flux, Time, Time] = [] #Flusso, tempo di inizio invio e tempo di fine invio
        self.incoming_fluxes: list[Flux, Time, Time] = [] #Flusso, tempo di inizio ricezione e tempo di fine ricezione
        self.DEBUG_dropped_incoming_fluxes: list[(Flux, Time, Time)] = [] #Flusso, tempo di inizio ricezione, tempo di fine ricezione e causa drop
        self.keep_log = keep_log
        self.results = None
        self._graph = None
        self._auxiliary_graph = None
        self.excluded_links = []
        self.link_utilization = {}  #dictionary that maps link to its utilization
        self.destination = None
        self._is_rerouting = False #if rerouting connections
        self.undeliverable_flows = [] #flows that generates errors in routing


    def split_flux_by_min_available_bandwidth(self, selected_path, flux: Flux):
        # Determina la minima capacità disponibile sul percorso
        min_available_bandwidth = float('inf')

        for i in range(len(selected_path) - 1):
            current_node = selected_path[i]
            next_node = selected_path[i + 1]
            link = self._get_link_between_nodes_or_ground_station(current_node, next_node, self.satellites, self.gss)
            if link:
                available_bw = link.get_available_bandwidth()
                min_available_bandwidth = min(min_available_bandwidth, available_bw)
            else:
                raise RuntimeError(f"No link found between {current_node} and {next_node}")

        # Controlla la capacità del collegamento finale (verso la GS)
        last_node = selected_path[-1]
        last_link = self._get_link_to_ground_station(last_node, self.destination, self.satellites, self.gss)
        if last_link:
            min_available_bandwidth = min(min_available_bandwidth, last_link.get_available_bandwidth())
        else:
            raise RuntimeError(f"No link found from last node {last_node} to destination")

        # Esegui lo split solo se necessario
        if min_available_bandwidth < flux.rate:
            print(f"[INFO] Splitting flux {flux.id}: original rate {flux.rate} Gbps, minimum bandwidth on path is {min_available_bandwidth} Gbps")
            splitted_flux, remaining_flux = flux.split(min_available_bandwidth)
            return splitted_flux, remaining_flux
        else:
            print(f"[INFO] No splitting needed for flux {flux.id}: sufficient bandwidth ({min_available_bandwidth} Gbps)")
            return flux, None


    def _reroute_all(self):
        if self._is_rerouting:
            return
        
        self._is_rerouting = True

        fluxes_copy = []
        # itera sui flussi in uscita (attivi) dalla Ground Station
        for flux, start_time, end_time in self.outgoing_fluxes:
            if end_time is None:  # Solo se il flusso è attivo
                routing_decisions = self.basic_centralized_route(flux.clone())

                if not routing_decisions:
                    print(f"[ERROR] No available paths found for flux {flux.id} during reroute. Adding to undeliverable flows.")
                    self.undeliverable_flows.append(flux)
                    self.close_outgoing_flux(flux)
                    continue  # passa al flusso successivo
                
                adapted_routing_decisions = [(action, link) for action, flux, link in routing_decisions]
                simulation = self.sat.simulate_adapt_routing_decisions_to_available_link_bandwidth(adapted_routing_decisions)

                flux_simulation = simulation.get(flux.alias_id)

                if flux_simulation and flux_simulation[0][2] != self.sat:
                    print(f"[INFO] Flux {flux.id} is being rerouted from {self.sat.get_name()} to {flux_simulation[0][2]}.")
                    flux_clone = flux.clone()
                    input_id = self.mapping_table.remove(flux.alias_id)
                    self.close_outgoing_flux(flux)  # chiudi il flusso attuale
                    flux_clone.alias_id = input_id
                    flux_clone.drop_steps_from(self)
                    self.open_flux(flux_clone)
                else:
                    print(f"[WARNING] Flux {flux.id} cannot be rerouted. Adding to undeliverable_flows.")
                    self.undeliverable_flows.append(flux.clone())
                    self.close_outgoing_flux(flux)

        self._is_rerouting = False



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

    def start_centralized_routing(self, flux: Flux, ground_stations):
        #print("Starting centralized routing Used flux", flux) 
        self.gss = ground_stations
        flux.source = self
        routing_decisions = self.centralized_route(flux)
        #print("* Routing decisions trovate:", routing_decisions)
        if not routing_decisions:
            if flux not in self.undeliverable_flows:
                print(f"[ERROR]: No routing decisions found for flux {flux.id}. Adding to undeliverable flows.")
                self.undeliverable_flows.append(flux)
            else:
                print(f"[INFO]: Flux {flux.id} is already listed as undeliverable.")
            return

        flux_destination = flux.get_ground_station_by_coordinates(flux.destination[0], flux.destination[1], self.gss.values())
        print(f">>>> Processing now {flux} Flux ID: {flux.id}, Alias ID: {flux.alias_id} from {self.get_name().upper()} to {flux_destination.get_name().upper()} rate {flux.rate} Gbps")
        self.send_centralized_flux(flux, routing_decisions) #send the flux to the source GS

    #Manage routing decisions (START THE CORE OF ROUTING DECISIONS doing basic route then adapting to link bandwidth)
    def centralized_route(self, flux: Flux): #print("Flux passed to method", flux)
        #print(f"--------------------------------------------------------DEBUG: flux = {flux}, type = {type(flux)}")
        routing_decisions = self.basic_centralized_route(flux)
        #routing_decisions = self.adapt_routing_decisions_to_available_link_bandwidth(flux, routing_decisions) ###non necessario, è presente nei metodi con LB
        #print("THE ROUTING DECISIONS:", routing_decisions)
        return routing_decisions

    def basic_centralized_route(self, flux: Flux):
        routing_output = list() #
        #print(f"DEBUG: flux = {flux}, type = {type(flux)}")
        #print(f"DEBUG: flux.destination = {flux.destination[0]}, {flux.destination[1]}")
        self.destination = flux.get_ground_station_by_coordinates(flux.destination[0], flux.destination[1], self.gss.values())

        if constants.ROUTING_STRATEGY == Strategy.BASELINE_DIJKSTRA:
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
                routing_output.append((action, flux, link)) #add the action to the decisions
                #env.put(0, self.calculate_dijkstra, source=self.source, destination=self.destination, satellites=self.satellites)
                #env.put(0, self.calculate_dijkstra, ground_stations=self.gss, satellites=self.satellites)  # come output ritorna i "dijkstra_shortest_paths" esegui la simulazione con Dijkstra 
                #env.start()
            last_node = dijkstra_shortest_path[-1][0] if isinstance(dijkstra_shortest_path[-1], list) else dijkstra_shortest_path[-1]
            last_link = self._get_link_to_ground_station(last_node, self.destination, self.satellites, self.gss)
            action = RoutingAction.DELIVER
            routing_output.append((action, flux, last_link))
            print("ROUTING 1______", routing_output)
            routing_output = self.adapt_routing_with_single_split(flux, routing_output) #walkthrough simulation of passage
            print("ROUTING 2______", routing_output)

        elif constants.ROUTING_STRATEGY in [Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                            Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB]:
            #self.prepare_results_for_disjointpaths(ground_stations=self.gss)
            disjoint_paths = self.calculate_k_disjoint_paths({
                'source': self,
                'destination': self.destination,
                'satellites': self.satellites,
                'flux': flux
            })
            #for path_index, path in enumerate(disjoint_paths): #Debug
            #    print(f"Processing path {path_index + 1}: {path}")
            if not disjoint_paths:
                #print("No valid Disjoint paths found, returning empty routing output.")
                return routing_output
            probabilities = self.calculate_path_weights_kshortest_disjoint(self._graph, disjoint_paths) #calculate probabilities based on weights of k disjoint paths
            selected_path = self.select_path_with_probabilities(disjoint_paths, probabilities) #select path based on probabilities
            routing_output = self.process_routing_output(selected_path, flux)  #process the output for routing
            #print("ROUTING 1______", routing_output)
            if constants.ROUTING_STRATEGY == Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING:
                routing_output = self.adapt_routing_with_single_split(flux, routing_output)
            if constants.ROUTING_STRATEGY == Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB:
                routing_output = self.adapt_routing_decisions_to_available_link_bandwidth(flux, routing_output) ################ adapt
            #print("ROUTING ******", routing_output)
        
        elif constants.ROUTING_STRATEGY in [Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING,
                                            Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_LB]:
            #self.prepare_results_for_disjointpaths(ground_stations=self.gss)
            disjoint_paths = self.calculate_k_disjoint_paths({
                'source': self,
                'destination': self.destination,
                'satellites': self.satellites,
                'flux': flux
            })
            #for path_index, path in enumerate(disjoint_paths): #Debug
            #    print(f"Processing path {path_index + 1}: {path}")
            if not disjoint_paths:
                #print("No valid Disjoint paths found, returning empty routing output.")
                return routing_output
            probabilities = self.calculate_path_weights_kshortest_disjoint(self._graph, disjoint_paths) #calculate probabilities based on weights of k disjoint paths
            selected_path = self.select_path_with_probabilities(disjoint_paths, probabilities) #select path based on probabilities
            routing_output = self.process_routing_output(selected_path, flux) #process the output for routing
            if constants.ROUTING_STRATEGY == Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING:
                routing_output = self.adapt_routing_with_single_split(flux, routing_output)
            if constants.ROUTING_STRATEGY == Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_LB:
                routing_output = self.adapt_routing_decisions_to_available_link_bandwidth(flux, routing_output) ################ adapt

        elif constants.ROUTING_STRATEGY == Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_COSTS_SELECTION:
            #self.prepare_results_for_disjointpaths(ground_stations=self.gss)
            disjoint_paths = self.calculate_k_disjoint_paths({
                'source': self,
                'destination': self.destination,
                'satellites': self.satellites,
                'flux': flux
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
                routing_output = self.process_routing_output(selected_path, flux) #process the output for routing  

        elif constants.ROUTING_STRATEGY in [Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                            Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB]:
            #self.prepare_results_for_disjointpaths(ground_stations=self.gss)
            disjoint_paths = self.calculate_k_disjoint_paths({
                'source': self,
                'destination': self.destination,
                'satellites': self.satellites,
                'flux': flux
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
            if constants.ROUTING_STRATEGY == Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING:
                routing_output = self.adapt_routing_with_single_split(flux, routing_output)
            if constants.ROUTING_STRATEGY == Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB:
                routing_output = self.adapt_routing_decisions_to_available_link_bandwidth(flux, routing_output)
        #print("The routing output obtained from basic_centralized_route:", routing_output)
        return routing_output #

    '''
    def adapt_routing_decisions_to_available_link_bandwidth(self, flux: Flux, routing_decisions):
        adapted_routing_decisions = []
        remaining_flux = flux.clone()
        # Trova la banda minima disponibile lungo il percorso selezionato
        min_available_bw = float('inf')
        for action, _, link in routing_decisions:
            available_bw = link.get_available_bandwidth()
            if available_bw < min_available_bw:
                min_available_bw = available_bw
        print(f"[DEBUG] Min available bandwidth along path: {min_available_bw} Gbps")
        # Adatta il flusso alla minima banda disponibile
        if remaining_flux.rate > min_available_bw:
            splitted_flux, remaining_flux = remaining_flux.split(min_available_bw)
            print(f"[INFO] Flux {flux.id} split: instradato {splitted_flux.rate} Gbps, rimasto {remaining_flux.rate} Gbps")
        else:
            splitted_flux = remaining_flux
            remaining_flux = None
            print(f"[INFO] Flux {flux.id} fully routed: {splitted_flux.rate} Gbps")
        # Riserva effettivamente la banda lungo il percorso
        for action, _, link in routing_decisions:
            reserved = link.reserve_bandwidth(splitted_flux)
            target_name = link.target[0].get_name() if isinstance(link.target, list) else link.target.get_name()
            if reserved:
                adapted_routing_decisions.append((action, splitted_flux, link))
                print(f"[SUCCESS] Reserved bandwidth {splitted_flux.rate} Gbps on link {link._parent.get_name()} -> {target_name}")
            else:
                print(f"[ERROR] Failed to reserve bandwidth on link {link._parent.get_name()} -> {link.target.get_name()}")
                self.undeliverable_flows.append(splitted_flux)
                adapted_routing_decisions.append((RoutingAction.ERROR, splitted_flux, None))
                break
        # Se c'è un flusso residuo, inseriscilo negli undeliverable_flows
        if remaining_flux:
            self.undeliverable_flows.append(remaining_flux)
            print(f"[WARNING] Flux {remaining_flux.id} (residual) added to undeliverable flows.")

        print("Check undeliverable flows and their rates:")
        for flow in self.undeliverable_flows:
            print(f"Flow ID: {flow.id}, Rate: {flow.rate}")
        return adapted_routing_decisions

    '''

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


    #adaptive method used only for LB mstrategies
    def adapt_routing_decisions_to_available_link_bandwidth(self, flux: Flux, routing_decisions):
        adapted_routing_decisions = []
        #####print("flux param:", flux)
        #print("routing decisions param:", routing_decisions)
        remaining_flux = flux.clone()
        #####print("remaining flux clone:", remaining_flux)
        support_routing_decisions = routing_decisions.copy() #same as routing_decisions, perfect copy
        #print("support routing decisions clone:", support_routing_decisions)
        reached_node = None  # Inizializzazione esplicita
        ####print("SELF DESTINATION", self.destination.get_name().upper())
        for i, (action, flux, link) in enumerate(routing_decisions):
            if not remaining_flux:
                break  # Flusso completamente instradato
            if not reached_node:
                if isinstance(link.target, list):
                    if link.target:  # Lista non vuota
                        reached_node = link.target[0].get_name()
                    else:
                        print(f"Warning: Link {link} target is an empty list.")
                else:
                    reached_node = link.target.get_name()

            if action in [RoutingAction.FORWARD, RoutingAction.DELIVER]:
                available_bandwidth = link.get_available_bandwidth()
                print(f"ADAPT ROUTING: LINK {link} has available BANDWIDTH: {available_bandwidth} for {flux} with flux rate {flux.rate} ")

                if available_bandwidth > 0:
                    if available_bandwidth >= remaining_flux.rate:  # Tutto il flusso può passare
                        print("Enough bandwidth for flux")
                        adapted_routing_decisions.append((action, remaining_flux, link))
                        if isinstance(link.target, list):
                            if link.target:
                                reached_node = link.target[0].get_name()
                        else:
                            reached_node = link.target.get_name()
                        link.reserve_bandwidth(remaining_flux)   #controllare le reserve bandwidth
                        self.check_path_for_splitted_flux( #usato per il remain flux
                            remaining_flux,
                            support_routing_decisions[i + 1:],
                            adapted_routing_decisions
                        )
                        #print(f"Found decisions for REMAINED SUBFLUX: {adapted_routing_decisions}")
                        remaining_flux.rate = 0  # Tutto il flusso è stato consumato
                        break
                    else:
                        print("Not enough bandwidth for flux, proceed to splitting...")# Solo una parte del flusso passa
                        splitted_flux, remaining_flux_to_route = remaining_flux.split(available_bandwidth)
                        adapted_routing_decisions.append((action, splitted_flux, link))
                        #print(f"link PARENT {link._parent.get_name()} & link TARGET {link.target.get_name()}")
                        print(f"SPLITTED_FLUX created {splitted_flux} and REMAINING_FLUX_TO_ROUTE {remaining_flux_to_route}")
                        reached_node = link._parent.get_name()

                        link.reserve_bandwidth(splitted_flux) #fare attenzione ai reserved bandwidth
                        self.check_path_for_splitted_flux(
                            splitted_flux,
                            support_routing_decisions[i + 1:],
                            adapted_routing_decisions
                        )
                        #print(f"Found decisions for SPLITTED FLUX and subfluxes: {adapted_routing_decisions}")
                        remaining_flux = remaining_flux_to_route
                        excluded_link = (link._parent.get_name(), link.target.get_name())
                        if excluded_link not in self.excluded_links:
                            self.excluded_links.append(excluded_link)
                        break
                else:
                    print(f"Link {link} is fully saturated. No flux can pass.")
                    excluded_link = (link._parent.get_name(), link.target.get_name())
                    if excluded_link not in self.excluded_links:
                        self.excluded_links.append(excluded_link)
                    reached_node = link._parent.get_name()

            else:
                adapted_routing_decisions.append((action, remaining_flux, link))

        # Se il nodo raggiunto è la destinazione, interrompi il calcolo
        if reached_node == self.destination.get_name().upper():
            print(f"Reached destination: {reached_node}. Stopping recursion.")
            adapted_routing_decisions.append((action, remaining_flux, link)) #
            link.reserve_bandwidth(remaining_flux) #
            return adapted_routing_decisions

        # Verifica finale di reached_node
        if remaining_flux and remaining_flux.rate > 0:
            if not reached_node:
                print("ATTENTION: reached_node was not set during routing decision adaptation; attempting fallback.")
                print(f"adapted routing decisions dopo IL NO REACHED_NODE {adapted_routing_decisions}")
                if adapted_routing_decisions:
                    last_action, _, last_link = adapted_routing_decisions[-1]
                    if last_action in [RoutingAction.FORWARD, RoutingAction.DELIVER]:
                        if isinstance(last_link.target, list):
                            if last_link.target:
                                reached_node = last_link.target[0].get_name()
                        else:
                            reached_node = last_link.target.get_name()
                if not reached_node:
                    adapted_routing_decisions.append((RoutingAction.ERROR, remaining_flux, None))
                    remaining_flux = None #remaing flux becomes None cause it's lost and cannot be delivered
                    return adapted_routing_decisions
        
            # Calcolo dei nuovi percorsi
            print(f"EXCLUDED LINKS {len(self.excluded_links)} for decisions: {self.excluded_links}")
            new_routing_decisions_remaining_flux = self.calculate_path_with_exclusions(remaining_flux, reached_node, g_auxiliary=self._auxiliary_graph)
            #print("NEW routing decisions calculated path with exclusions", new_routing_decisions_remaining_flux)
            adapted_decisions_remaining_flux = self.adapt_routing_decisions_to_available_link_bandwidth(remaining_flux, new_routing_decisions_remaining_flux)
            #print("ADAPTED NEW routing decisions", adapted_decisions_remaining_flux)
            if adapted_decisions_remaining_flux:
                adapted_routing_decisions.append(adapted_decisions_remaining_flux)
            else:
                 # Controlla che il flusso non sia già negli undeliverable_flows
                if remaining_flux not in self.undeliverable_flows:
                    print(f"[ERROR]: Flux {remaining_flux.id} cannot be routed. Adding to undeliverable flows.")
                    self.undeliverable_flows.append(remaining_flux)
                else:
                    print(f"[INFO]: Flux {remaining_flux.id} already listed as undeliverable.")
                adapted_routing_decisions.append((RoutingAction.ERROR, remaining_flux, None))
                #self.undeliverable_flows.append(remaining_flux)
                remaining_flux = None


        print("Check undeliverable flows and their rates:")
        for flow in self.undeliverable_flows:
            print(f"Flow ID: {flow.id}, Rate: {flow.rate}")
        #print("----FLUSSI NON INSTRADABILI:", self.undeliverable_flows)
        #print("ADAPTED ROUTING DECISIONS:", adapted_routing_decisions)
        return adapted_routing_decisions


    def adapt_routing_with_single_split(self, flux: Flux, routing_decisions: list):
        adapted_routing_decisions = []
        remaining_flux = flux.clone()
        support_routing_decisions = routing_decisions.copy()
        #print(">>>>>>>>>>>routing decisions da adattare alla rete", routing_decisions)
        for i, (action, flux, link) in enumerate(routing_decisions):
            if action in [RoutingAction.FORWARD, RoutingAction.DELIVER]:
                available_bandwidth = link.get_available_bandwidth()
                target_name = (link.target[0].get_name() 
                                if isinstance(link.target, list) and link.target 
                                else link.target.get_name())
                print(f"ADAPT ROUTING single split: Link {link._parent.get_name()} - {target_name} has available BANDWIDTH: {available_bandwidth} for {flux} with rate {flux.rate} ")

                if available_bandwidth > 0:
                    if available_bandwidth >= remaining_flux.rate:  # Tutto il flusso può passare
                        #print("# Enough bandwidth for flux")
                        success = link.reserve_bandwidth(remaining_flux)  # Prova a riservare la banda
                        if not success:  # Se non è riuscito a riservare la banda
                            print(f"Error: Could not reserve bandwidth for flux {remaining_flux} on link {link}.")
                            adapted_routing_decisions.append((RoutingAction.ERROR, remaining_flux, None))
                            self.undeliverable_flows.append(remaining_flux)
                        else:
                            adapted_routing_decisions.append((action, remaining_flux, link))  # Solo se la banda è stata riservata con successo
                        
                        print(f"Link {link._parent.get_name()} - {target_name} has updated bandwidth {link.get_available_bandwidth()} after reserving {remaining_flux} with rate {remaining_flux.rate}")
                        self.check_path_for_splitted_flux_simple( #usato per il remaining flux
                            remaining_flux,
                            support_routing_decisions[i + 1:], #i+1 cause the first link bandwidth is already stored
                            adapted_routing_decisions
                        )
                        break
                        #inserire un check del remaining_flux e forse drop_flux
                    else:
                        # Se il flusso supera la banda disponibile, lo dividiamo
                        splitted_flux, undelivered_flux = flux.split(available_bandwidth)
                        adapted_routing_decisions.append((action, splitted_flux, link))
                        #print(f"# NOT Enough bandwidth for splitted_flux {splitted_flux} with rate {splitted_flux.rate}")
                        link.reserve_bandwidth(splitted_flux)
                        print(f"Link {link._parent.get_name()} - {target_name} has updated bandwidth {link.get_available_bandwidth()} after reserving {splitted_flux} with rate {splitted_flux.rate}")
                        self.check_path_for_splitted_flux_simple( #usato per il remaining flux
                            splitted_flux,
                            support_routing_decisions[i + 1:],
                            adapted_routing_decisions
                        )
                        # Aggiungiamo il flusso non instradabile alla lista
                        self.undeliverable_flows.append((undelivered_flux))
                        break
                else:
                    print(f"Link {link} is fully saturated. No flux can pass.")
            else:
                adapted_routing_decisions.append((action, flux, link)) #other actions unaltered
        
        print("Check undeliverable flows and their rates:")
        for flow in self.undeliverable_flows:
            print(f"Flow ID: {flow.id}, Rate: {flow.rate}")
        return adapted_routing_decisions

    def check_path_for_splitted_flux_simple(self, splitted_flux: Flux, support_routing_decisions, adapted_routing_decisions):
        for j, (inner_action, inner_flux, inner_link) in enumerate(support_routing_decisions):
            #print(f">>> Checking path for splitted flux {splitted_flux.id} with rate {splitted_flux.rate} <<<")
            decisions_copy = support_routing_decisions.copy()
            decisions_copy[j] = (inner_action, splitted_flux, inner_link)

            if inner_action in [RoutingAction.FORWARD, RoutingAction.DELIVER]:
                available_bandwidth = inner_link.get_available_bandwidth()
                target_name = (inner_link.target[0].get_name() 
                                if isinstance(inner_link.target, list) and inner_link.target 
                                else inner_link.target.get_name())
                
                if available_bandwidth >= splitted_flux.rate:
                    inner_link.reserve_bandwidth(splitted_flux)
                    adapted_routing_decisions.append((inner_action, splitted_flux, inner_link))

                    available_bandwidth = inner_link.get_available_bandwidth() #debug

                    #print(f"### Attempting to forward splitted flux {splitted_flux.id} with rate {splitted_flux.rate} ###")
                    print(f"Inner_link with Updated bandwidth {available_bandwidth} for link {inner_link._parent.get_name()} - {target_name}") #debug if available_bandwidth is zero or less then start is correct
                    if isinstance(inner_link.target, list):
                        target_node = inner_link.target[0].get_name()
                    else:    
                        target_node = inner_link.target.get_name()

                    if inner_action == RoutingAction.DELIVER:
                        print(f"[SUCCESS]: Splitted flux {splitted_flux} reached destination {target_node}!")
        return adapted_routing_decisions  # Termina la ricerca; lo splitted_flux non viene instradato


    def check_path_for_splitted_flux(self, splitted_flux: Flux, support_routing_decisions, adapted_routing_decisions):
        for j, (inner_action, inner_flux, inner_link) in enumerate(support_routing_decisions):
            
            decisions_copy = support_routing_decisions.copy()
            decisions_copy[j] = (inner_action, splitted_flux, inner_link)
            
            if inner_action in [RoutingAction.FORWARD, RoutingAction.DELIVER]:
                available_bandwidth = inner_link.get_available_bandwidth()
                target_name = (inner_link.target[0].get_name() 
                                if isinstance(inner_link.target, list) and inner_link.target 
                                else inner_link.target.get_name())
                print(f"Inner_link split {inner_link._parent.get_name()} - {target_name} with available_bandwidth {available_bandwidth}")
                
                if available_bandwidth == 0:
                    print(f"Skipping saturated link {inner_link}.")
                    excluded_link = (inner_link._parent.get_name(), inner_link.target.get_name())
                    if excluded_link not in self.excluded_links:
                        self.excluded_links.append(excluded_link)
                    continue
                
                if available_bandwidth >= splitted_flux.rate:
                    if available_bandwidth == splitted_flux.rate:
                        excluded_link = (inner_link._parent.get_name(), inner_link.target.get_name())
                        if excluded_link not in self.excluded_links:
                            self.excluded_links.append(excluded_link)
                    inner_link.reserve_bandwidth(splitted_flux)
                    adapted_routing_decisions.append((inner_action, splitted_flux, inner_link))

                    if isinstance(inner_link.target, list):
                        target_node = inner_link.target[0].get_name()
                    else:    
                        target_node = inner_link.target.get_name()

                    if inner_action == RoutingAction.DELIVER:
                        print(f"[SUCCESS]: Splitted flux {splitted_flux} reached destination {target_node}!")
                    
                else:
                    new_splitted_flux, remaining_flux = splitted_flux.split(available_bandwidth)
                    print(f"new splitted flux created in check_path_splitted_flux {new_splitted_flux} and remaining flux {remaining_flux}")
                    
                    if new_splitted_flux.rate > 0:
                        inner_link.reserve_bandwidth(new_splitted_flux)
                        adapted_routing_decisions.append((inner_action, new_splitted_flux, inner_link))
                    
                    if remaining_flux.rate > 0:
                        excluded_link = (inner_link._parent.get_name(), inner_link.target.get_name())
                        if excluded_link not in self.excluded_links:
                            self.excluded_links.append(excluded_link)
                        self.check_path_for_splitted_flux(
                            remaining_flux,
                            decisions_copy[j + 1:], 
                            adapted_routing_decisions
                        )
                        break
        return adapted_routing_decisions

    
    def calculate_path_with_exclusions(self, remaining_flux: Flux, reached_node, g_auxiliary):
        if reached_node is None:
            raise ValueError("Reached_node was not set before calling calculate_path_with_exclusions")
        disjoint_paths = []
        #g_auxiliary = self._graph.copy()  # Grafo ausiliario per calcolo

        # Rimuovi i link esclusi
        for u, v in self.excluded_links:
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

        closer_satellites = utils.get_closer_satellites_for_graph(self.satellites, (source.lat, source.lon))  # Trova i satelliti più vicini
        for sat_name, sat in closer_satellites:
            if sat_name not in self.satellites:
                print(f"Satellite {sat_name} non trovato nel dizionario 'satellites'")
                continue
            distance_to_sat = utils.get_distance_between_satellite_and_gs(sat, source)  # Calcola la distanza
            #print("Distanza da GS sorgente a Sat:", distance_to_sat)
            if distance_to_sat <= constants.SATELLITE_COVERAGE_AREA_RADIUS:
                source_satellites.append(sat_name)

        closer_satellites = utils.get_closer_satellites_for_graph(self.satellites, (destination.lat, destination.lon))
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
                    print(f"No Node disjoint path for {constants.ROUTING_STRATEGY} between {source_satellite} and {dst_sat}.")

            # Se non ci sono percorsi, prova un nodo sorgente alternativo
            if not disjoint_paths and len(source_satellites) > 1:
                print("Attempting to switch to an alternative source satellite...")
                for alternate_satellite in source_satellites:
                    if alternate_satellite != source_satellite:
                        print(f"Trying alternative source satellite: {alternate_satellite}")
                        try:
                            disjoint_paths = []
                            for dst_sat in destination_satellites:
                                paths = list(nx.node_disjoint_paths(g_auxiliary, alternate_satellite, dst_sat))
                                disjoint_paths.extend(paths)
                            if disjoint_paths:  # Se troviamo percorsi validi, aggiorna il nodo sorgente
                                source_satellite = alternate_satellite
                                break
                        except nx.NetworkXNoPath:
                            print(f"No paths found for alternate source satellite: {alternate_satellite}.")


            #self.print_paths(disjoint_paths, "Node disjoint paths")
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
            self.print_paths(disjoint_paths, "Edge disjoint paths")
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
            self.print_paths(disjoint_paths, "Length shortest node disjoint paths")
            if disjoint_paths:
                probabilities = self.calculate_path_weights_length_shortest_node_disjoint(g_auxiliary, disjoint_paths)
                selected_path = self.select_path_with_probabilities(disjoint_paths, probabilities)

        if selected_path is None:  # Se nessun percorso è stato trovato
            print(f"No valid path could be selected for {self.get_name()} to {self.destination.get_name()}.")
            reached_node = None
            return []

        #print(f"Selected path: {selected_path}")
        return self.process_routing_output(selected_path, remaining_flux)

    def print_graph_edges(self, graph, label):
        edges_list = [f"{edge[0]} -> {edge[1]}" for edge in graph.edges(data=True)]
        total_edges = len(edges_list)
        print(f"    Edges in {label} (total: {total_edges})")

    def print_paths(self, paths, label):
        print(f"{label}:")
        for path in paths:
            print(f"  Path: {list(zip(path[:-1], path[1:]))}")

    def process_routing_output(self, selected_path, flux):
        processed_output = []
        print(f"Processing selected path: {selected_path}") #select first disjoint path for routing flux
        if len(selected_path) == 1:
            single_node = selected_path[0]
            # Verifica se esiste un collegamento per consegna diretta al GS
            last_link = self._get_link_to_ground_station(single_node, self.destination, self.satellites, self.gss)
            if last_link:
                action = RoutingAction.DELIVER
                processed_output.append((action, flux, last_link))
            else:
                print(f"Warning: No link found to deliver flux from single node {single_node} to destination.")
            return processed_output

        for i in range(len(selected_path) - 1):
            current_node = selected_path[i]
            next_node = selected_path[i + 1]
            link = self._get_link_between_nodes_or_ground_station(current_node, next_node, self.satellites, self.gss)
            if not link:
                print(f"Warning: No link found between {current_node} and {next_node}. Skipping.")
                continue
            action = RoutingAction.FORWARD
            processed_output.append((action, flux, link))
        last_node = selected_path[-1] #manage last node for delivery to GS
        last_link = self._get_link_to_ground_station(last_node, self.destination, self.satellites, self.gss)
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
        flux: Flux = kwargs['flux']  # aggiunto flux
        k = constants.K_SHORTEST_VALUE  # Numero massimo di percorsi disgiunti richiesti

        print(f"Routing calculation from <<<{source.get_name().upper()} - {destination.get_name().upper()}>>>")
        k_disjoint_paths = self._get_k_disjoint_paths(satellites, source, destination)

        if not k_disjoint_paths:  # Controllo corretto se nessun percorso è disponibile
            print(f"[WARNING] Nessun percorso disponibile per il flusso {flux.id}")
            self.undeliverable_flows.append(flux)  # Aggiungi il flusso non instradabile
            return []  # Restituisci immediatamente una lista vuota

        k_disjoint_paths = k_disjoint_paths[:k] 
        #print(f"Shortest disjoint paths from {source.get_name().upper()} to {destination.get_name().upper()}: {k_disjoint_paths}")
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
            if distance_to_sat <= constants.SATELLITE_COVERAGE_AREA_RADIUS:
                source_satellites.append(sat_name)
                source_name = source.get_name().upper()
                g.add_edge(source_name, sat_name, weight=distance_to_sat)  # Collega la source al satellite
        #print("source satellites:", source_satellites)
        closer_satellites = utils.get_closer_satellites_for_graph(satellites, (destination.lat, destination.lon))  # Trova i satelliti più vicini
        for sat_name, sat in closer_satellites:
            if sat_name not in satellites:
                print(f"Satellite {sat_name} non trovato nel dizionario 'satellites'")
                continue
            distance_to_sat = utils.get_distance_between_satellite_and_gs(sat, destination)  # Calcola la distanza
            if distance_to_sat <= constants.SATELLITE_COVERAGE_AREA_RADIUS:
                destination_satellites.append(sat_name)
                destination_name = destination.get_name().upper()
                g.add_edge(sat_name, destination_name, weight=distance_to_sat)  # Collega il satellite alla destination
        #print("destination satellites", destination_satellites)

        # Rimuovi gli archi con banda disponibile pari a 0
        edges_to_remove = [(u, v) for u, v, data in g.edges(data=True) if data.get('available_bandwidth', 0) <= 0]
        for u, v in edges_to_remove:
            g.remove_edge(u, v)
        #print("Nodi del grafo:", g.nodes)
        #print("Archi del grafo:", g.edges(data=True))
        #print("Satelliti vicini alla sorgente:", source_satellites)# Debug: Satelliti vicini alla sorgente
        #print("Satelliti vicini alla destinazione:", destination_satellites)# Debug: Satelliti vicini alla destinazione
        self._graph = g #store the graph for successive use
        self._auxiliary_graph = self._graph.copy()

        disjoint_paths = [] #list of k paths
        if constants.ROUTING_STRATEGY in [Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                          Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB]:
            if source == destination:
                #print(f"Source and destination are the same: {source.get_name().upper()}. No route needed.")
                closer_sats=utils.get_closer_satellites(satellites, (self.lat, self.lon), False)
                disjoint_paths.append([closer_sats[0]['name']])
                return disjoint_paths
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
            if source == destination:
                #print(f"Source and destination are the same: {source.get_name().upper()}. No route needed.")
                closer_sats=utils.get_closer_satellites(satellites, (self.lat, self.lon), False)
                disjoint_paths.append([closer_sats[0]['name']])
                return disjoint_paths
            for src_sat in source_satellites:
                for dst_sat in destination_satellites:
                    try:
                        paths = list(nx.edge_disjoint_paths(g, src_sat, dst_sat)) #calculate disjoint paths in graph excluding already used nodes
                        disjoint_paths.extend(paths)  #add all found paths
                    except nx.NetworkXNoPath:
                        print(f"No Edge disjoint path for {constants.ROUTING_STRATEGY} between {src_sat} and {dst_sat}.")

        elif constants.ROUTING_STRATEGY in [Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                            Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB]:
            if source == destination:
                #print(f"Source and destination are the same: {source.get_name().upper()}. No route needed.")
                closer_sats=utils.get_closer_satellites(satellites, (self.lat, self.lon), False)
                disjoint_paths.append([closer_sats[0]['name']])
                return disjoint_paths
            for src_sat in source_satellites:
                for dst_sat in destination_satellites:
                    try:
                        paths = list(nx.node_disjoint_paths(g, src_sat, dst_sat)) #calculate disjoint paths in graph excluding already used nodes
                        disjoint_paths.extend(paths)  #add all found paths
                    except nx.NetworkXNoPath:
                        print(f"No Node disjoint path for {constants.ROUTING_STRATEGY} between {src_sat} and {dst_sat}.")
        #print("Percorsi generati da _get_k_disjoint_paths:", disjoint_paths)
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
        from link import LaserLink
        path_weights = []
        for path in disjoint_paths:
            if len(path) == 1:
                #print(f"Single bounce node: {path}. Probability 1.0.")
                return [1.0]

            weight = 0
            for i in range(len(path) - 1):
                current_node = path[i]
                next_node = path[i + 1]
                link_key = (current_node, next_node)

                # Verifica che il collegamento esista nel grafo e abbia un peso
                if 'weight' not in graph[current_node][next_node]:
                    raise KeyError(f"Il collegamento tra {current_node} e {next_node} non ha un peso definito.")
                
                base_weight = graph[current_node][next_node]['weight'] #obtain the link's weight in graph as length
                #print("base weight:", base_weight)
                utilization = self.link_utilization.get(link_key, 0) #add factor of link occupation. If value doesn't exists, self.link_utilization returns 0

                link = self._get_link_between_nodes(current_node, next_node, self.satellites)
                if isinstance(link, LaserLink):
                    max_capacity = constants.SATELLITE_LINK_CAPACITY  #Default for LaserLink
                else:
                    max_capacity = constants.GROUND_STATION_LINK_CAPACITY  # Default for RadioLink

                if max_capacity <= 0:
                    raise ValueError(f"La capacità massima del link tra {current_node} e {next_node} è invalida: {max_capacity}")

                penalty = (utilization / max_capacity)  #normalize utilization on maximum capacity (link load/link)
                weight += base_weight * (1 + penalty)  #penalty for more occupied links
                # Log di debug
                '''
                print(f"Path: {path}, Current Node: {current_node}, Next Node: {next_node}, "
                    f"Base Weight: {base_weight}, Utilization: {utilization}, "
                    f"Max Capacity: {max_capacity}, Penalty: {penalty}")
                ''' 
            path_weights.append(weight)
            # Controlla che i pesi non siano vuoti
            if not path_weights:
                raise ValueError("Nessun peso calcolato per i percorsi disgiunti.")
        total_weight = sum(path_weights) #sum all weights for normalization
        #print(f"total of weights {total_weight}")
        # Verifica che il peso totale non sia zero
        if total_weight == 0:
            raise ValueError("Il peso totale calcolato è zero. Controlla i pesi dei percorsi o i dati del grafo.")
        # Gestisci il caso in cui c'è un solo percorso disponibile
        if len(path_weights) == 1:
            probabilities = [1.0]  # Unico percorso ha probabilità 1
        else:
            probabilities = [1 - (w / total_weight) for w in path_weights] #lightest paths have higher probabilities
        #print(f"Weights' list over total weight {path_weights} / {total_weight} ")
        #print(f"Probabilities' list {probabilities}")
        return probabilities

    def calculate_path_weights_length_shortest_node_disjoint(self, graph, paths):
        sum_weights = sum([path_weight(graph, p, weight="weight") for p in paths])
        if sum_weights == 0:
            return 0 
        total_path_weights = sum([1 - (path_weight(graph, path, weight="weight") / sum([path_weight(graph, p, weight="weight") for p in paths])) for path in paths]) #total weights as length of paths
        weights = [(1 - (path_weight(graph, path, weight="weight") / sum([path_weight(graph, p, weight="weight") for p in paths]))) / total_path_weights for path in paths] #normalized weights
        return weights

    #select path based on probabilities
    def select_path_with_probabilities(self, paths, probabilities): 
        if len(paths) == 1:
            return paths[0]
        selected_path = random.choices(population=paths, weights=probabilities)[0]
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
        #print(f"Available ground stations: {list(self.gss.keys())}")
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
        if isinstance(ground_stations, list):
            ground_stations = {gs.name: gs for gs in ground_stations}
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

    def reattach(self):
        distances = utils.get_closer_satellites(self.satellites, (self.lat, self.lon), False)
        new_sat = self.satellites.get(distances[0]['name'])
        #if constants.DEBUG:
         #   if new_sat != self.sat:
        #print("Attaching Ground Station", self.get_name(), "to Satellite", new_sat.get_name(), "at time", utils.get_current_time().utc_strftime())
        self.attach_to_sat(new_sat)

    #connect GS to satellite
    def attach_to_sat(self, sat):
        #print("attach_to_sat", sat.get_name())
        #print("OUTGOING FLUXES ----", self.outgoing_fluxes)
        if sat != self.sat: #check if connected satellite is different from the current satellite (connected to GS) as param
            backup_fluxes = [] #copy of fluxes
            #DEBUG
            #print("outgoing_fluxes in attach_to_sat", self.outgoing_fluxes)
        
            for outgoing_flux, _, end_time in self.outgoing_fluxes: #for the outgoing fluxes check that end_time is None to copy them
                if end_time == None:
                    backup_fluxes.append(outgoing_flux)
                    self.close_outgoing_flux(outgoing_flux) #close
            if self.sat != None: 
                self.sat.serving_gs = None #change attribute serving_gs of current satellite to None
            self.sat = sat #change of satellite that is serving the GS
            self.sat.serving_gs = self #connect to GS
            # Itera su ogni flusso nella lista `backup_fluxes`
            #print("Backup_fluxes attach to sat", backup_fluxes)
            for flux in backup_fluxes:
                print(f"Fluxes to send {flux} ID: {flux.id}, Alias ID: {flux.alias_id} with rate {flux.rate} Gbps. Destination {flux.destination}")
            for backup_flux in backup_fluxes: 
                if constants.ROUTING_STRATEGY in [Strategy.BASELINE_DIJKSTRA, 
                                  Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                  Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                  Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING,
                                  Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                  Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                  Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                  Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_COSTS_SELECTION]:
                    print(f"-> Backup flux Centr print {backup_flux} id {backup_flux.id} alias {backup_flux.alias_id} rate {backup_flux.rate} destination {backup_flux.destination}")
                    #print("stampa le self.GSS Stations", self.gss)
                    self.destination = backup_flux.get_ground_station_by_coordinates(backup_flux.destination[0], backup_flux.destination[1], self.gss.values())
                    print("destination of backup flux", self.destination.get_name().upper())
                    self.start_centralized_routing(backup_flux, self.gss) #send the flux to the source GS Routing 
                else:
                    print(f"-> Backup flux Distrib print {backup_flux} id {backup_flux.id} alias {backup_flux.alias_id} rate {backup_flux.rate} destination {backup_flux.destination}")
                    self.send_flux(backup_flux) #send copied fluxes 

    #get name
    def get_name(self) -> str:
        return self.name


    #sender of fluxes from GS to connected satellite
    def send_centralized_flux(self, flux: Flux, routing_decisions):
        #routing_decisions = self.flatten_to_separate_lists(routing_decisions)
        routing_decisions = self.extract_separated_decision_lists(routing_decisions)
        
        print("* Send Centralized DECISIONS", routing_decisions)
        self.outgoing_fluxes.append((flux, utils.get_current_time(), None)) #print("!!!!!!!!!!!!!!!send outgoing_fluxes", self.outgoing_fluxes)
        #if constants.DEBUG:
        #print(" OPENING FLUX on GS -centralized-", flux, "id", flux.id, "with alias id", flux.alias_id, "from", self.get_name(), "to", self.destination.get_name() , "with rate", flux.rate, "at time", utils.get_current_time().utc_strftime())
        flux.travelled_distance += utils.get_distance_between_satellite_and_gs(self.sat, self) #distance from source GS to first satellite #print("flux travelled distance to first Sat", flux.travelled_distance) #####print("satellites in path",utils.get_satellites_in_path(routing_decisions),"flux steps", flux.get_steps() ) #debug print
        
        if not isinstance(routing_decisions[0], list):
            routing_decisions = [routing_decisions]
        
        for routing_sequence in routing_decisions:
            for decision in routing_sequence:
                action, flux, link = decision
                if action == RoutingAction.ERROR:
                    print(f"[ERROR] Cannot route flux {flux.id}")
                    continue
                # Apri il flusso usando direttamente il flux già presente nella decisione
                print("***********************decision", decision)
                self.sat.open_centralized_flux(flux.clone(), [decision])
        #self.sat.open_centralized_flux(flux.clone(), routing_decisions)
 
    #sender of fluxes from GS to connected satellite
    def send_flux(self, flux: Flux):
        self.outgoing_fluxes.append((flux, utils.get_current_time(), None)) #add an outgoing flux with current time, None is the time of termination of the flux
        #if constants.DEBUG:
         #   print(" OPENING FLUX on GS -distributed-", flux.id, "with alias id", flux.alias_id, "from", self.get_name(), "with rate", flux.rate, "at time", utils.get_current_time().utc_strftime())
        flux.travelled_distance += utils.get_distance_between_satellite_and_gs(self.sat, self)
        self.sat.open_flux(flux.clone())

    #close the outgoing flux
    def close_outgoing_flux(self, flux: Flux):
        print("Backup_fluxes in closed OUT", self.outgoing_fluxes)
        print("Backup_fluxes in closed INCOMING", self.incoming_fluxes)
        print("Backup_fluxes in closed DEBUG_DROPPED", self.DEBUG_dropped_incoming_fluxes)
        print("Backup_fluxes in closed UNDELIVERABLE", self.undeliverable_flows)
        if self.keep_log:
            for i, (outgoing_flux, start_time, end_time) in enumerate(self.outgoing_fluxes):
                print("CONTROLLO PARAMETRI flux",flux, "out_flux",outgoing_flux, "flux.alias_id", flux.alias_id, "outgoing_flux.alias_id", outgoing_flux.alias_id, "flux.rate", flux.rate, "outgoing_flux.rate", outgoing_flux.rate, "end_time", end_time)
                if flux == outgoing_flux and flux.alias_id == outgoing_flux.alias_id and flux.rate == outgoing_flux.rate and end_time == None:
                    self.outgoing_fluxes[i] = (outgoing_flux, start_time, utils.get_current_time())
                    print("outgoing_fluxes at i index", self.outgoing_fluxes[i])
                    #outgoing_flux.travelled_distance -= utils.get_distance_between_satellite_and_gs(self.sat, self)
                    outgoing_flux.travelled_distance = 0                    
                    if constants.DEBUG:
                        print("Closed outgoing flux", flux.id, "with alias id", flux.alias_id, "with rate", flux.rate, "at time", utils.get_current_time().utc_strftime())
                    break
        else:
            while self.outgoing_fluxes.__contains__(flux):
                self.outgoing_fluxes.remove(flux)
        self.sat.close_flux(flux.clone())
        print("Backup_fluxes in closed OUT2", self.outgoing_fluxes)
        print("Backup_fluxes in closed INCOMING2", self.incoming_fluxes)
        print("Backup_fluxes in closed DEBUG_DROPPED2", self.DEBUG_dropped_incoming_fluxes)
        print("Backup_fluxes in closed UNDELIVERABLE2", self.undeliverable_flows)

    def open_flux(self, flux: Flux): #apre il flux se è alla ground station di destinazione allora copia gli step in path e diventano il percorso attuato
        #print("flux destination", flux.destination)
        #print("self.lat and self.lon", self.lat, self.lon)
        if flux.destination[0] == self.lat and flux.destination[1] == self.lon:
            flux.paths.append(flux.get_steps())
            flux.state = FluxState.DELIVERED
            self.incoming_fluxes.append((flux, utils.get_current_time(), None))
            print("Flux", flux.id, "with rate", flux.rate, "Gbps has reached its destination!", "at time", utils.get_current_time().utc_strftime())
            print("Steps:", [step.get_name() for step in flux.get_steps()])
        else:
            self._discard_flux(flux)
        
    def _discard_flux(self, flux: Flux):
        #print("discard") #Eliminare 
        if constants.DEBUG:
            print("Flux with id", flux.id, "has been discarded on gs", self.get_name())

    def close_flux(self, flux: Flux):
        if self.keep_log:
            for i, (incoming_flux, start_time, end_time) in enumerate(self.incoming_fluxes):
                if flux == incoming_flux and flux.alias_id == incoming_flux.alias_id and flux.rate == incoming_flux.rate and end_time == None:
                    self.incoming_fluxes[i] = (incoming_flux, start_time, utils.get_current_time())
                    '''
                    if constants.DEBUG:
                        print("Closed incoming flux", flux.id, "with alias id", flux.alias_id, "from", self.get_name(), "with rate", flux.rate, "at time", utils.get_current_time().utc_strftime())
                    '''
                    break
        else:
            while self.incoming_fluxes.__contains__(flux):
                self.incoming_fluxes.remove(flux)

    def is_incoming_flux_alive(self, flux: Flux):
        for incoming_flux, _, end_time in self.incoming_fluxes:
            if flux == incoming_flux:
                if end_time == None:
                    return True
        return False

    def get_flux_info(self, flux: Flux, until: Time, precision: int = 0) -> tuple[float, float, float]:
        total_data_received = 0
        total_data_sent = 0
        total_data_dropped = 0
        flux.paths = []
        sum_travelled_distance = 0 #km
        incoming_fluxes_count = 0
        for incoming_flux, start_time, end_time in self.incoming_fluxes:
            if flux == incoming_flux:
                if end_time == None or until - end_time < 0:
                    end_time = until
                active_time_in_seconds = utils.get_seconds_between(start_time, end_time)
                if active_time_in_seconds >= precision:
                    total_data_received += active_time_in_seconds * incoming_flux.rate
                    flux.paths.append(incoming_flux.get_steps())
                    sum_travelled_distance += incoming_flux.travelled_distance
                    incoming_fluxes_count += 1 
                    '''
                    #debug 
                    if constants.DEBUG:
                        print(total_data_received, utils.get_seconds_between(start_time, end_time) * incoming_flux.rate, "incoming for", utils.get_seconds_between(start_time, end_time), "from", start_time.utc_strftime(), "to", end_time.utc_strftime(), "at rate", incoming_flux.rate, "with alias id", incoming_flux.alias_id)
                        print([sat.get_name() for sat in incoming_flux.get_steps()])
                    '''
        if incoming_fluxes_count > 0:
            flux.travelled_distance = sum_travelled_distance / incoming_fluxes_count
            if constants.DEBUG or not(constants.DEBUG):
                print("Average distance travelled by flux", flux.id, "in kms:", flux.travelled_distance)
        for outgoing_flux, start_time, end_time in self.outgoing_fluxes:
            if flux == outgoing_flux:
                if end_time == None or until - end_time < 0:
                    end_time = until
                active_time_in_seconds = utils.get_seconds_between(start_time, end_time)
                if active_time_in_seconds >= precision:
                    total_data_sent += active_time_in_seconds * outgoing_flux.rate
        for dropped_flux, start_time, end_time in self.DEBUG_dropped_incoming_fluxes:
            if flux == dropped_flux:
                if end_time == None or until - end_time < 0:
                    end_time = until
                active_time_in_seconds = utils.get_seconds_between(start_time, end_time)
                if active_time_in_seconds >= precision:
                    total_data_dropped += active_time_in_seconds * dropped_flux.rate
                    #Escluso in modo tale da memorizzare solo i path a buon fine nel flux
                    #flux.paths.append(dropped_flux.get_steps())
                    '''
                    if constants.DEBUG:
                        print(total_data_dropped, utils.get_seconds_between(start_time, end_time) * dropped_flux.rate, "dropped for", utils.get_seconds_between(start_time, end_time), "from", start_time.utc_strftime(), "to", end_time.utc_strftime(), "at rate", dropped_flux.rate, "with alias id", dropped_flux.alias_id, "reason", dropped_flux.state)
                        print([sat.get_name() for sat in dropped_flux.get_steps()])
                    '''
        # Stampa tutti i percorsi del flusso
        #print("\nPercorsi per il flusso", flux.id, ":")
        #for idx, path in enumerate(flux.paths):
         #   print(f"Path {idx + 1}: {[sat.get_name() for sat in path]}")
        return (total_data_sent, total_data_received, total_data_dropped)
        
    def DEBUG_get_dropped_flux(self, flux: Flux):
        flux.paths.append(flux.get_steps())
        self.DEBUG_dropped_incoming_fluxes.append((flux, utils.get_current_time(), None))
        '''
        if constants.DEBUG:
            print("Logged opening of dropped flux", flux.id, "with rate", flux.rate, "Gbps at time", utils.get_current_time().utc_strftime())
            print("Steps:", [step.get_name() for step in flux.get_steps()])
        '''
  
    def DEBUG_close_dropped_flux(self, flux: Flux):
        if self.keep_log:
            for i, (dropped_flux, start_time, end_time) in enumerate(self.DEBUG_dropped_incoming_fluxes):
                if flux == dropped_flux and flux.alias_id == dropped_flux.alias_id and flux.rate == dropped_flux.rate and end_time == None:
                    self.DEBUG_dropped_incoming_fluxes[i] = (dropped_flux, start_time, utils.get_current_time())
                    '''
                    if constants.DEBUG:
                        print("Logged closing of dropped flux", flux.id, "with rate", flux.rate, "Gbps at time", utils.get_current_time().utc_strftime())
                        print("Steps:", [step.get_name() for step in flux.get_steps()])
                    '''
                    break
        else:
            while self.DEBUG_dropped_incoming_fluxes.__contains__(flux):
                self.DEBUG_dropped_incoming_fluxes.remove(flux)

