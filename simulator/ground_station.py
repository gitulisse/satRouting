import constants
from geopy import distance
from flow import Flow, FlowState
from skyfield.api import Time, Timescale
from routing_action import RoutingAction
from strategy import Strategy
import utils
import networkx as nx
import matplotlib.pyplot as plt
import environment as env
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
        self.outgoing_flows: list[Flow, Time, Time] = [] #Flow, Start time, End time
        self.incoming_flows: list[Flow, Time, Time] = [] #Flow, Start time, End time
        self.DEBUG_dropped_incoming_flows: list[(Flow, Time, Time)] = [] #Flow, Start time, End time
        self.results = None
        self._graph = None
        self._auxiliary_graph = None
        self.detected_paths = []
        self.excluded_links = []
        self.link_utilization = {}
        self.destination = None
        self.DEBUG_dropped_flows: list[Flow] = []
        self.keep_log = keep_log

    def set_satellites(self, satellites):
        self.satellites = satellites

    def set_ground_stations(self, ground_stations: dict):
        self.gss = ground_stations
    
    def get_latitudeGS(self):
        return self.lat
    
    def get_longitudeGS(self):
        return self.lon
    
    def add_population_to_serve(self, amount: int):
        self.serving_population += amount

    #connect GS to satellite
    def attach_to_sat(self, sat):
        if sat != self.sat:
            backup_flows = []
            for outgoing_flow, _, end_time in self.outgoing_flows:
                if end_time == None:
                    backup_flows.append(outgoing_flow)
                    self.close_outgoing_flow(outgoing_flow)
            if self.sat != None: 
                self.sat.serving_gs = None
            self.sat = sat
            self.sat.serving_gs = self

    def get_name(self) -> str:
        return self.name

    #sender of flows from GS to connected satellite
    def send_flow(self, flow: Flow, routing_decisions=None): #optional parameter routing_decisions
        self.outgoing_flows.append((flow, utils.get_current_time(), None))
        if constants.DEBUG:
            print("----- [OPENING FLOW] on GS", flow, "with ID", flow.id, "alias_ID", flow.alias_id, "from", self.get_name().upper(), "with Rate", flow.rate)
        flow.travelled_distance += utils.get_distance_between_satellite_and_gs(self.sat, self)
        if routing_decisions != None:
            self.sat.open_flow(flow.clone(), routing_decisions) #Port Forwarding branch
        else:
            self.sat.open_flow(flow.clone())

    #close the outgoing flows
    def close_outgoing_flow(self, flow: Flow):
        if self.keep_log:
            for i, (outgoing_flow, start_time, end_time) in enumerate(self.outgoing_flows):
                if flow == outgoing_flow and flow.alias_id == outgoing_flow.alias_id and flow.rate == outgoing_flow.rate and end_time == None:
                    self.outgoing_flows[i] = (outgoing_flow, start_time, utils.get_current_time())
                    outgoing_flow.travelled_distance = 0
                    #if constants.DEBUG:
                        #print("Closed outgoing flow", flow.id, "with alias id", flow.alias_id, "with rate", flow.rate, "at time", utils.get_current_time().utc_strftime())
                    break
        else:
            while self.outgoing_flows.__contains__(flow):
                self.outgoing_flows.remove(flow)
        self.sat.close_flow(flow.clone())

    def close_remaining_flows(self):
        def remove_ongoing(flows):
            cleaned = []
            for f in flows:
                if isinstance(f, tuple):
                    flow, start, end = f
                    if end is None or (isinstance(end, str) and end.upper() == "ONGOING"):
                        continue
                    cleaned.append((flow, start, end))
                else:
                    end = getattr(f, "end", None)
                    if end is None or (isinstance(end, str) and str(end).upper() == "ONGOING"):
                        continue
                    cleaned.append(f)
            return cleaned
        self.outgoing_flows = remove_ongoing(self.outgoing_flows)
        self.incoming_flows = remove_ongoing(self.incoming_flows)
        self.DEBUG_dropped_incoming_flows = remove_ongoing(self.DEBUG_dropped_incoming_flows)
        self.DEBUG_dropped_flows = remove_ongoing(self.DEBUG_dropped_flows)

    #open flow at destination GS
    def open_flow(self, flow: Flow):
        if flow.destination[0] == self.lat and flow.destination[1] == self.lon:
            flow.paths.append(flow.get_steps())
            flow.state = FlowState.DELIVERED
            self.incoming_flows.append((flow, utils.get_current_time(), None))
            if constants.DEBUG:
                print("----- [DELIVERED FLOW]", flow, "ID", flow.id, "with rate", flow.rate, "Gbps has reached its destination!")
                print("#     Steps obtained:", [step.get_name() for step in flow.get_steps()])
        else:
            self._discard_flow(flow)

    def _discard_flow(self, flow: Flow):
        if constants.DEBUG:
            print("Flow with id", flow.id, "has been discarded on GS", self.get_name())

    #close incoming flow
    def close_flow(self, flow: Flow):
        if self.keep_log:
            for i, (incoming_flow, start_time, end_time) in enumerate(self.incoming_flows):
                if flow == incoming_flow and flow.alias_id == incoming_flow.alias_id and flow.rate == incoming_flow.rate and end_time == None:
                    self.incoming_flows[i] = (incoming_flow, start_time, utils.get_current_time())
                    #if constants.DEBUG:
                        #print("Closed incoming flow", flow.id, "with alias id", flow.alias_id, "from", self.get_name(), "with rate", flow.rate, "at time", utils.get_current_time().utc_strftime())
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
                    #if constants.DEBUG:
                        #print("Total Received", total_data_received, utils.get_seconds_between(start_time, end_time) * incoming_flow.rate, "incoming for", utils.get_seconds_between(start_time, end_time), "from", start_time.utc_strftime(), "to", end_time.utc_strftime(), "at rate", incoming_flow.rate, "with alias id", incoming_flow.alias_id)
                        #print("incoming_flow steps...sat", [sat.get_name() for sat in incoming_flow.get_steps()])
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
                    #if constants.DEBUG:
                        #print(total_data_dropped, utils.get_seconds_between(start_time, end_time) * dropped_flow.rate, "dropped for", utils.get_seconds_between(start_time, end_time), "from", start_time.utc_strftime(), "to", end_time.utc_strftime(), "at rate", dropped_flow.rate, "with alias id", dropped_flow.alias_id, "reason", dropped_flow.state)
                        #print([sat.get_name() for sat in dropped_flow.get_steps()])
        return (total_data_sent, total_data_received, total_data_dropped)
        
    def DEBUG_get_dropped_flow(self, flow: Flow):
        flow.paths.append(flow.get_steps())
        self.DEBUG_dropped_incoming_flows.append((flow, utils.get_current_time(), None))
        #if constants.DEBUG:
            #print("Logged opening of dropped flow", flow.id, "with rate", flow.rate, "Mbps at time", utils.get_current_time().utc_strftime())
            #print("Steps:", [step.get_name() for step in flow.get_steps()])
  
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
        if constants.DEBUG:
            if new_sat != self.sat:
                print("Attaching Ground Station", self.get_name(), "to Satellite", new_sat.get_name(), "at time", utils.get_current_time().utc_strftime())
        self.attach_to_sat(new_sat)

    #starting point of source routing paradigm
    def start_centralized_routing(self, flow: Flow, ground_stations):
        self.gss = ground_stations
        flow.source = self
        self.outgoing_flows.append((flow, utils.get_current_time(), None))
        routing_decisions = self.centralized_route(flow)
        if not routing_decisions:
            return
        routing_decisions = self.extract_separated_decision_lists(routing_decisions) #nested decisions extracted
    
        for decision in routing_decisions:
            action, partial_flow, link = decision[0]
            if constants.DEBUG:
                print(f"  +++++      Sending flow {partial_flow} id {partial_flow.id} alias_id {partial_flow.alias_id} rate {partial_flow.rate} to satellite {self.sat.get_name()}")
                print(f"  +++++      Sending with decisions: {decision}")
            self.send_flow(partial_flow, decision)

    def centralized_route(self, flow: Flow):
        routing_decisions = self.basic_centralized_route(flow)
        return routing_decisions
    
    def basic_centralized_route(self, flow: Flow):
        self.detected_paths.clear()
        routing_output = list()
        self.destination = flow.get_ground_station_by_coordinates(flow.destination[0], flow.destination[1], self.gss.values())

        if constants.ROUTING_STRATEGY == Strategy.BASELINE_DIJKSTRA:
            dijkstra_shortest_path = self.calculate_k_disjoint_paths({
                'source': self,
                'destination': self.destination,
                'satellites': self.satellites,
                'flow': flow
            })
            if not dijkstra_shortest_path:
                return routing_output
            print("Dijkstra shortest path found:", dijkstra_shortest_path)

            selected_path = dijkstra_shortest_path[0]
            routing_output = self.process_routing_output_no_lb(selected_path, flow)
            routing_output = self.adapt_routing_with_single_split(flow, routing_output)


        elif constants.ROUTING_STRATEGY in [Strategy.SOURCE_ROUTING_BY_HOP_NO_LB, Strategy.SOURCE_ROUTING_BY_LENGTH_NO_LB]:
            disjoint_paths = self.calculate_k_disjoint_paths({
                'source': self,
                'destination': self.destination,
                'satellites': self.satellites,
                'flow': flow
            })
            if not disjoint_paths:
                return routing_output
            
            self.detected_paths = disjoint_paths #ranked_paths
            selected_path = self.detected_paths[0]
            del self.detected_paths[0]
            routing_output = self.process_routing_output_no_lb(selected_path, flow)
            routing_output = self.adapt_routing_with_single_split(flow, routing_output)
            
        elif constants.ROUTING_STRATEGY in [Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB]:
            disjoint_paths = self.calculate_k_disjoint_paths({
                'source': self,
                'destination': self.destination,
                'satellites': self.satellites,
                'flow': flow
            })
            if not disjoint_paths:
                return routing_output
            
            self.detected_paths = disjoint_paths #ranked_paths
            selected_path = self.detected_paths[0]
            routing_output = self.process_routing_output(selected_path, flow)
            del self.detected_paths[0]
            if constants.ROUTING_STRATEGY == Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB:
                routing_output = self.adapt_routing_decisions_to_available_link_bandwidth(flow, routing_output)
        
        elif constants.ROUTING_STRATEGY in [Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB]:
            disjoint_paths = self.calculate_k_disjoint_paths({
                'source': self,
                'destination': self.destination,
                'satellites': self.satellites,
                'flow': flow
            })
            if not disjoint_paths:
                return routing_output
            
            self.detected_paths = disjoint_paths #ranked_paths
            selected_path = self.detected_paths[0]
            routing_output = self.process_routing_output(selected_path, flow)
            del self.detected_paths[0]
            if constants.ROUTING_STRATEGY == Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB:
                routing_output = self.adapt_routing_decisions_to_available_link_bandwidth(flow, routing_output)

        elif constants.ROUTING_STRATEGY in [Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK]:
            disjoint_paths = self.calculate_k_disjoint_paths({
                'source': self,
                'destination': self.destination,
                'satellites': self.satellites,
                'flow': flow
            })
            if not disjoint_paths:
                return routing_output
            
            self.detected_paths = disjoint_paths #ranked_paths
            selected_path = self.detected_paths[0]
            routing_output = self.process_routing_output(selected_path, flow)
            del self.detected_paths[0]
            if constants.ROUTING_STRATEGY == Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK:
                routing_output = self.adapt_routing_decisions_to_available_link_bandwidth(flow, routing_output)

        elif constants.ROUTING_STRATEGY == Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING:
            disjoint_paths = self.calculate_k_disjoint_paths({
                'source': self,
                'destination': self.destination,
                'satellites': self.satellites,
                'flow': flow
            })
            if not disjoint_paths:
                return routing_output
            print("disjoint paths for cost balancing", disjoint_paths)
            alpha = 0.25
            self.detected_paths = disjoint_paths #ranked_paths
            path_cost_pairs = self.calculate_path_costs(self._graph, self.detected_paths, alpha) 
            selected_path = path_cost_pairs[0][0]
            del self.detected_paths[0]
            routing_output = self.process_routing_output(selected_path, flow)
            if constants.ROUTING_STRATEGY == Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING:
                routing_output = self.adapt_routing_decisions_to_available_link_bandwidth(flow, routing_output)

        return routing_output #RoutingAction, Flow, Link

    #manage nested decisions
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

    #adaptive method for LB strategies
    def adapt_routing_decisions_to_available_link_bandwidth(self, flow: Flow, routing_decisions):
        if len(routing_decisions) == 1:
            return routing_decisions 
        adapted_routing_decisions = [] 
        remaining_flow = flow.clone()
        initial_flow_rate = remaining_flow.rate
        reached_node = None
    
        path_links = [link for action, _, link in routing_decisions if action in [RoutingAction.FORWARD, RoutingAction.DELIVER]]
        if path_links:
            min_available_bw = min(link.get_available_bandwidth() for link in path_links)
            print(f"[INFO] Minimum available bandwidth is {min_available_bw} among Links of Selected Path")

        for i, (action, flow, link) in enumerate(routing_decisions):
            if not reached_node:
                if isinstance(link.target, list):
                    if link.target:  
                        reached_node = link.target[0].get_name()
                    else:
                        print(f"Warning: Link {link} target is an empty list.")
                else:
                    reached_node = link.target.get_name()
            
            if action in [RoutingAction.FORWARD, RoutingAction.DELIVER]:
                available_bandwidth = link.get_available_bandwidth()

                if available_bandwidth > 0:
                    if min_available_bw >= remaining_flow.rate:
                        print(f"[DEBUG] ENOUGH BANDWIDTH equal to {min_available_bw} for flow rate {remaining_flow.rate}")
                    
                        #link_paths = [f"{link._parent.get_name()} - {', '.join(t.get_name() for t in link.target) if isinstance(link.target, list) else link.target.get_name()}" for _, _, link in routing_decisions]
                        #print(f"[DEBUG] Routing path on enough bandwidth: {link_paths}") #shows human-readable path
                        print(f"Checking path of splitted flow... first link {link._parent.get_name()} - {link.target.get_name()} with available bandwidth {link.get_available_bandwidth()}")
                        adapted_routing_decisions.append((action, flow, link)) #remaining_flow
                        if isinstance(link.target, list):
                            if link.target:
                                reached_node = link.target[0].get_name()
                        else:
                            reached_node = link.target.get_name()

                        self.check_path_for_splitted_flow(
                            flow,
                            routing_decisions[i + 1:],
                            adapted_routing_decisions
                        )
                        
                        remaining_flow.rate = 0 #full flow consumed
                        break

                    else:
                        # Flow splitting logic
                        splitted_flow, remaining_flow_to_route = remaining_flow.split(min_available_bw)
                        print("[DEBUG] NOT ENOUGH BANDWIDTH, proceed to splitting...")
                        print(f"[DEBUG] Created Splitted_flow with rate {splitted_flow.rate} and Remaining_flow_to_route with rate {remaining_flow_to_route.rate}")
                        #print(f"Splitted_flow {splitted_flow} Rate {splitted_flow.rate} and Remaining_flow_to_route {remaining_flow_to_route} Rate {remaining_flow_to_route.rate}")
                        print(f"Checking path of splitted flow... first link {link._parent.get_name()} - {link.target.get_name()} with available_bandwidth {link.get_available_bandwidth()}")
                        adapted_routing_decisions.append((action, splitted_flow, link))
                        reached_node = link._parent.get_name()

                        self.check_path_for_splitted_flow(
                            splitted_flow,
                            routing_decisions[i + 1:],
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
        if reached_node == self.destination.get_name().upper():
            print(f"Reached destination: {reached_node}. Stopping recursion.")
            remaining_flow.rate = initial_flow_rate
            adapted_routing_decisions.append((action, remaining_flow, link)) 
            return adapted_routing_decisions
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
                    print("[INFO] Appending ERROR for flow", remaining_flow, "with rate", remaining_flow.rate)
                    adapted_routing_decisions.append((RoutingAction.ERROR, remaining_flow, FlowState.SATELLITE_CONGESTED))
                    remaining_flow = None
                    return adapted_routing_decisions

            new_routing_decisions_remaining_flow = self.calculate_path_with_exclusions(remaining_flow, reached_node, g_auxiliary=self._auxiliary_graph)
            #print("New routing decisions calculated path with exclusions for flow", remaining_flow ,":", new_routing_decisions_remaining_flow)
            adapted_decisions_remaining_flow = self.adapt_routing_decisions_to_available_link_bandwidth(remaining_flow, new_routing_decisions_remaining_flow)
            #print("New adapted routing decisions", adapted_decisions_remaining_flow)
            if adapted_decisions_remaining_flow:
                adapted_routing_decisions.append(adapted_decisions_remaining_flow)
            else:
                adapted_routing_decisions.append((RoutingAction.ERROR, remaining_flow, None))
                remaining_flow = None
        return adapted_routing_decisions

    #adaptive method for strategies without LB
    def adapt_routing_with_single_split(self, flow: Flow, routing_decisions: list):
        if len(routing_decisions) == 1:
            return routing_decisions 
        adapted_routing_decisions = []
        remaining_flow = flow.clone()
        initial_flow_rate = remaining_flow.rate
        reached_node = None
        path_links = [link for action, _, link in routing_decisions if action in [RoutingAction.FORWARD, RoutingAction.DELIVER]]
        if path_links:
            min_available_bw = min(link.get_available_bandwidth() for link in path_links)
            print(f"[INFO] Minimum available bandwidth is {min_available_bw} among Links of Single Selected Single Path")
        for i, (action, flow, link) in enumerate(routing_decisions): 
            if not remaining_flow:
                print("No remaining flow to route.")
                break
            if not reached_node:
                if isinstance(link.target, list):
                    if link.target:  
                        reached_node = link.target[0].get_name()
                    else:
                        print(f"Warning: Link {link} target is an empty list.")
                else:
                    reached_node = link.target.get_name()

            if action in [RoutingAction.FORWARD, RoutingAction.DELIVER]:
                available_bandwidth = link.get_available_bandwidth()
                if available_bandwidth > 0:
                    if min_available_bw >= flow.rate:
                        print(f"[DEBUG] ENOUGH BANDWIDTH equal to {min_available_bw} for flow rate {remaining_flow.rate}")
                        #link_paths = [f"{link._parent.get_name()} - {', '.join(t.get_name() for t in link.target) if isinstance(link.target, list) else link.target.get_name()}" for _, _, link in routing_decisions]
                        #print(f"[DEBUG] Routing path on enough bandwidth: {link_paths}") #shows human-readable path
                        print(f"Checking path of single splitted flow... first link {link._parent.get_name()} - {link.target.get_name()} with available bandwidth {link.get_available_bandwidth()}")
                        adapted_routing_decisions.append((action, flow, link))
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

                        remaining_flow.rate = 0 #full flow consumed
                        break
                    else:
                        # Flow splitting logic for single split routing
                        splitted_flow, undeliverable_flow = remaining_flow.split(min_available_bw)
                        print("[DEBUG] NOT ENOUGH BANDWIDTH, proceed to splitting...")
                        print(f"[DEBUG] Created Splitted_flow with rate {splitted_flow.rate} and Undeliverable_flow with rate {undeliverable_flow.rate}")
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
                        adapted_routing_decisions.append([(RoutingAction.ERROR, remaining_flow, FlowState.LINK_CONGESTED)])
                        break
                else:
                    print(f"Link {link} is fully saturated. No flow can pass.")
                    excluded_link = (link._parent.get_name(), link.target.get_name())
                    if excluded_link not in self.excluded_links:
                        self.excluded_links.append(excluded_link)
                    reached_node = link._parent.get_name()
            else:
                adapted_routing_decisions.append((action, remaining_flow, link))

        return adapted_routing_decisions

    def check_path_for_splitted_flow_simple(self, flow: Flow, support_routing_decisions, adapted_routing_decisions):
        for j, (inner_action, inner_flow, inner_link) in enumerate(support_routing_decisions):
            decisions_copy = support_routing_decisions.copy()
            decisions_copy[j] = (inner_action, flow, inner_link)

            if inner_action in [RoutingAction.FORWARD, RoutingAction.DELIVER]:
                available_bandwidth = inner_link.get_available_bandwidth()
                if isinstance(inner_link.target, list):
                    expected_destination = utils.get_ground_station_name_by_coords(flow.destination[0], flow.destination[1])
                    confirmed_destination = [destination for destination in inner_link.target if hasattr(destination, 'get_name') and destination.get_name().upper() == expected_destination]
                    confirmed_destination_node = utils.get_ground_station_name_by_coords(confirmed_destination[0].lat, confirmed_destination[0].lon)
                    target_name = confirmed_destination_node
                else:
                    target_name = inner_link.target.get_name()

                print(f"Checking path of splitted flow... link {inner_link._parent.get_name()} - {target_name} with available_bandwidth {available_bandwidth}")
                
                if available_bandwidth >= flow.rate:
                    if available_bandwidth == flow.rate:
                        excluded_link = (inner_link._parent.get_name(), inner_link.target.get_name())
                        if excluded_link not in self.excluded_links:
                            self.excluded_links.append(excluded_link)
                    if isinstance(inner_link.target, list):
                        adapted_routing_decisions.append((inner_action, flow, inner_link))
                        target_node = confirmed_destination_node
                    else:  
                        adapted_routing_decisions.append((inner_action, flow, inner_link))  
                        target_node = inner_link.target.get_name()
                    if inner_action == RoutingAction.DELIVER:                        
                        expected_destination = utils.get_ground_station_name_by_coords(flow.destination[0], flow.destination[1]) #lat #lon
                else:
                    new_splitted_flow, remaining_flow = flow.split(available_bandwidth)
                    print(f"New  splitted flow created in check_path_for_splitted_flow_simple {new_splitted_flow} rate {new_splitted_flow.rate} and remaining flow {remaining_flow} rate {remaining_flow.rate}")
                    if new_splitted_flow.rate > 0:
                        adapted_routing_decisions.append((inner_action, new_splitted_flow, inner_link))
                    if remaining_flow.rate > 0:
                        adapted_routing_decisions.append((RoutingAction.ERROR, remaining_flow, FlowState.LINK_CONGESTED))
        return adapted_routing_decisions

    def check_path_for_splitted_flow(self, flow: Flow, support_routing_decisions, adapted_routing_decisions):
        for j, (inner_action, inner_flow, inner_link) in enumerate(support_routing_decisions):
            decisions_copy = support_routing_decisions.copy()
            decisions_copy[j] = (inner_action, flow, inner_link)
            if inner_action in [RoutingAction.FORWARD, RoutingAction.DELIVER]:
                available_bandwidth = inner_link.get_available_bandwidth()
                if isinstance(inner_link.target, list):
                    expected_destination = utils.get_ground_station_name_by_coords(flow.destination[0], flow.destination[1])
                    confirmed_destination = [destination for destination in inner_link.target if hasattr(destination, 'get_name') and destination.get_name().upper() == expected_destination]
                    confirmed_destination_node = utils.get_ground_station_name_by_coords(confirmed_destination[0].lat, confirmed_destination[0].lon)
                    target_name = confirmed_destination_node
                else:
                    target_name = inner_link.target.get_name()

                print(f"Checking path of splitted flow... link {inner_link._parent.get_name()} - {target_name} with available_bandwidth {available_bandwidth}")
                
                if available_bandwidth >= flow.rate:
                    if available_bandwidth == flow.rate:
                        excluded_link = (inner_link._parent.get_name(), inner_link.target.get_name())
                        if excluded_link not in self.excluded_links:
                            self.excluded_links.append(excluded_link)
                    if isinstance(inner_link.target, list):
                        adapted_routing_decisions.append((inner_action, flow, inner_link))
                        target_node = confirmed_destination_node
                    else:  
                        adapted_routing_decisions.append((inner_action, flow, inner_link))  
                        target_node = inner_link.target.get_name()

                    if inner_action == RoutingAction.DELIVER:                        
                        expected_destination = utils.get_ground_station_name_by_coords(flow.destination[0], flow.destination[1]) #lat #lon
                else:
                    new_splitted_flow, remaining_flow = flow.split(available_bandwidth)
                    print(f"New  splitted flow created in check_path_for_splitted_flow {new_splitted_flow} rate {new_splitted_flow.rate} and remaining flow {remaining_flow} rate {remaining_flow.rate}")
                    if new_splitted_flow.rate > 0:
                        adapted_routing_decisions.append((inner_action, new_splitted_flow, inner_link))
                    if remaining_flow.rate > 0:
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
        if reached_node is None:
            raise ValueError("Reached_node was not set before Calculate path with exclusions")
        disjoint_paths = []
        for u, v in self.excluded_links:
            if g_auxiliary.has_edge(u, v):
                g_auxiliary.remove_edge(u, v)

        if not g_auxiliary.edges:
            raise ValueError("All links are saturated or excluded. No valid path can be calculated.")
        
        if isinstance(reached_node, str):
            source_satellite = reached_node.upper()
        else:
            source_satellite = reached_node
        destination = self.destination
        source = self
        destination_name = self.destination.get_name().upper()
        destination_satellites = []
        source_satellites = []

        closer_satellites = utils.get_closest_satellite_for_graph(self.satellites, (source.lat, source.lon))
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

        selected_path = None

        if constants.ROUTING_STRATEGY == Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB:
            for dst_sat in destination_satellites:
                if dst_sat not in g_auxiliary:
                    raise ValueError(f"Destination node {dst_sat} not found in graph!")
                try:
                    paths = list(nx.node_disjoint_paths(g_auxiliary, source_satellite, dst_sat))
                    disjoint_paths.extend(paths)
                except nx.NetworkXNoPath:
                    print(f"[DROP] Calculate with Exclusions - No Node disjoint path for Remained flow {remaining_flow} rate {remaining_flow.rate} between {source_satellite} and {dst_sat}.")
            if disjoint_paths:
                probabilities = self.calculate_path_weights_kshortest_disjoint(g_auxiliary, disjoint_paths)
                selected_path = self.select_path_with_probabilities(disjoint_paths, probabilities)
        
        elif constants.ROUTING_STRATEGY == Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB:
            for dst_sat in destination_satellites:
                try:
                    paths = list(nx.edge_disjoint_paths(g_auxiliary, source_satellite, dst_sat))
                    disjoint_paths.extend(paths)
                except nx.NetworkXNoPath:
                    print(f"[DROP] Calculate with Exclusions - No Edge disjoint path for Remained flow {remaining_flow} rate {remaining_flow.rate} between {source_satellite} and {dst_sat}.")
            if disjoint_paths:
                probabilities = self.calculate_path_weights_kshortest_disjoint(g_auxiliary, disjoint_paths)
                selected_path = self.select_path_with_probabilities(disjoint_paths, probabilities)

        elif constants.ROUTING_STRATEGY == Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING:
            for dst_sat in destination_satellites:
                try:
                    paths = list(nx.edge_disjoint_paths(g_auxiliary, source_satellite, dst_sat))
                    disjoint_paths.extend(paths)
                except nx.NetworkXNoPath:
                    print(f"[DROP] Calculate with Exclusions - No Edge disjoint path for Remained flow {remaining_flow} rate {remaining_flow.rate} between {source_satellite} and {dst_sat}.")
            if disjoint_paths:
                probabilities = self.calculate_path_weights_kshortest_disjoint(g_auxiliary, disjoint_paths)
                selected_path = self.select_path_with_probabilities(disjoint_paths, probabilities)

        elif constants.ROUTING_STRATEGY == Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK:
            for dst_sat in destination_satellites:
                if dst_sat not in g_auxiliary:
                    raise ValueError(f"Destination node {dst_sat} not found in graph!")
                try:
                    paths = list(nx.node_disjoint_paths(g_auxiliary, source_satellite, dst_sat))
                    disjoint_paths.extend(paths)
                except nx.NetworkXNoPath:
                    print(f"[DROP] Calculate with Exclusions - No Node disjoint path on saturated link for Remained flow {remaining_flow} rate {remaining_flow.rate} between {source_satellite} and {dst_sat}.")
            if disjoint_paths:
                probabilities = self.calculate_path_weights_kshortest_disjoint(g_auxiliary, disjoint_paths)
                selected_path = self.select_path_with_probabilities(disjoint_paths, probabilities)

        if selected_path is None:
            print(f"Dropped flow stored while calculate path exclusions, No valid path for {remaining_flow} rate {remaining_flow.rate} from {self.get_name()} to {self.destination.get_name()}.")
            reached_node = None
            return []
        #print(f"Selected path in calculate with exclusion: {selected_path}")
        selected_path = selected_path[0]
        return self.process_routing_output(selected_path, remaining_flow)

    def print_graph_edges(self, graph, label):
        edges_list = [f"{edge[0]} -> {edge[1]}" for edge in graph.edges(data=True)]
        total_edges = len(edges_list)
        print(f"    Edges in {label} (total: {total_edges})")

    def print_paths(self, paths, label):
        print(f"{label}:")
        for path in paths:
            print(f"  Path: {list(zip(path[:-1], path[1:]))}")

    def process_routing_output_no_lb(self, selected_path, flow):
        processed_output = []
        print(f">>> Processing Selected Path no lb: {selected_path}")
        for i in range(len(selected_path) - 1):
            current_node = selected_path[i]
            next_node = selected_path[i + 1]
            link = self._get_link_between_nodes_or_ground_station(current_node, next_node, self.satellites, self.gss)
            if not link:
                print(f"[WARNING]: No link found between {current_node} and {next_node}. Skipping.")
                continue
            processed_output.append((RoutingAction.FORWARD, flow, link))
 
        last_node = selected_path[-1]
        if (self.destination not in self.satellites[last_node]._gs_link.get_attached_gs()):
            print(f"[ERROR] Satellite {last_node} is not directly connected to GS {self.destination.get_name()}. Excluding and recalculating.")
            self.excluded_links.append((selected_path[-2], last_node))
            return self.calculate_path_with_exclusions(flow, selected_path[0], self._auxiliary_graph)

        last_link = self._get_link_to_ground_station(last_node, self.destination, self.satellites, self.gss)
        if last_link:
            processed_output.append((RoutingAction.DELIVER, flow, last_link))
        else:
            print(f"[ERROR]: No final link to GS from satellite {last_node} found. Path discarded.")
            return []
        return processed_output


    def process_routing_output(self, selected_path, flow):
        processed_output = []
        print(f">>> Processing Selected Path: {selected_path}")
        if len(selected_path) == 1:
            single_node = selected_path[0]
            last_link = self._get_link_to_ground_station(single_node, self.destination, self.satellites, self.gss)
            if last_link:
                processed_output.append((RoutingAction.DELIVER, flow, last_link))
            else:
                print(f"[ERROR]: No direct link from {single_node} to destination GS {self.destination.get_name()}.")
                return []
            return processed_output

        for i in range(len(selected_path) - 1):
            current_node = selected_path[i]
            next_node = selected_path[i + 1]
            link = self._get_link_between_nodes_or_ground_station(current_node, next_node, self.satellites, self.gss)
            if not link:
                print(f"[WARNING]: No link found between {current_node} and {next_node}. Skipping.")
                continue
            processed_output.append((RoutingAction.FORWARD, flow, link))
 
        last_node = selected_path[-1]
        if (self.destination not in self.satellites[last_node]._gs_link.get_attached_gs()):
            print(f"[ERROR] Satellite {last_node} is not directly connected to GS {self.destination.get_name()}. Excluding and recalculating.")
            self.excluded_links.append((selected_path[-2], last_node))
            return self.calculate_path_with_exclusions(flow, selected_path[0], self._auxiliary_graph)

        last_link = self._get_link_to_ground_station(last_node, self.destination, self.satellites, self.gss)
        if last_link:
            processed_output.append((RoutingAction.DELIVER, flow, last_link))
        else:
            print(f"[ERROR]: No final link to GS from satellite {last_node} found. Path discarded.")
            return []
        return processed_output

    def calculate_k_disjoint_paths(self, kwargs):
        source: dict = kwargs['source']
        destination: dict = kwargs['destination']
        satellites: dict = kwargs['satellites']
        flow: Flow = kwargs['flow']
        if constants.ROUTING_STRATEGY in [Strategy.BASELINE_DIJKSTRA,
                                        Strategy.SOURCE_ROUTING_BY_HOP_NO_LB,
                                        Strategy.SOURCE_ROUTING_BY_LENGTH_NO_LB]:
            k = constants.K_SHORTEST_VALUE
        if constants.ROUTING_STRATEGY in [Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                  Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING,
                                  Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK]:
            k = constants.K_SHORTEST_VALUE_LB
        
        k_disjoint_paths = self._get_k_disjoint_paths(satellites, source, destination)
        
        if not k_disjoint_paths:
            #print(f"[WARNING] No available path for flow {flow.id} with rate {flow.rate} Gbps")
            return []
        k_disjoint_paths = k_disjoint_paths[:k]
        return k_disjoint_paths
 
    def _get_k_disjoint_paths(self, satellites, source, destination):
        #print("Starting Main Graph", env.main_graph)
        source_satellite = []
        destination_satellite = []
        closer_satellites = utils.get_closest_satellite_for_graph(satellites, (source.lat, source.lon))
        for sat_name, sat in closer_satellites:
            if sat_name not in satellites:
                print(f"Satellite {sat_name} not found in dictionary 'satellites'")
                continue
            distance_to_sat = utils.get_distance_between_satellite_and_gs(sat, source) 
            if distance_to_sat <= constants.SATELLITE_COVERAGE_AREA_RADIUS:
                source_satellite.append(sat_name)
        closer_satellites = utils.get_closest_satellite_for_graph(satellites, (destination.lat, destination.lon))
        for sat_name, sat in closer_satellites:
            if sat_name not in satellites:
                print(f"Satellite {sat_name} not found in dictionary 'satellites'")
                continue
            distance_to_sat = utils.get_distance_between_satellite_and_gs(sat, destination)  
            if distance_to_sat <= constants.SATELLITE_COVERAGE_AREA_RADIUS:
                destination_satellite.append(sat_name)

        if constants.DEBUG:
            print("> Source satellite", source_satellite)
            print("> Destination satellite", destination_satellite)
        valid_source_sats = [sat for sat in source_satellite if sat in env.main_graph]
        valid_destination_sats = [sat for sat in destination_satellite if sat in env.main_graph]
        edges_to_remove = [(u, v) for u, v, data in env.main_graph.edges(data=True) if data.get('available_bandwidth', 0) == 0]
        for u, v in edges_to_remove:
            env.main_graph.remove_edge(u, v)
        self._graph = env.main_graph.copy()
        self._auxiliary_graph = env.main_graph.copy()
        for gs_name in env.ground_stations.keys():
            if gs_name in env.main_graph:
                self._auxiliary_graph.remove_node(gs_name)

        disjoint_paths = []
        
        if constants.ROUTING_STRATEGY == Strategy.BASELINE_DIJKSTRA:
            if source == destination:
                print(f"Source and destination are the same: {source.get_name().upper()}. No route needed.")
                closer_sats=utils.get_closer_satellites(satellites, (self.lat, self.lon), False)
                disjoint_paths = []
                disjoint_paths.append([closer_sats[0]['name']])
                return disjoint_paths
            for src_sat in source_satellite: #if more source and destination satellites (for a more complex algorithm)
                for dst_sat in destination_satellite:
                    if src_sat not in valid_source_sats:
                        print(f"[ERROR] Source satellites missing from graph!")
                        return []
                    if dst_sat not in valid_destination_sats:
                        print(f"[ERROR] Destination satellites missing from graph!")
                        return []
                    try:
                        path = nx.shortest_path(self._auxiliary_graph, src_sat, dst_sat, weight='weight')
                        disjoint_paths.append(path)
                    except nx.NetworkXNoPath:
                        print(f"[INFO] Getting K-paths - No Node disjoint path for {constants.ROUTING_STRATEGY} between {src_sat} and {dst_sat}.")

        elif constants.ROUTING_STRATEGY in [Strategy.SOURCE_ROUTING_BY_HOP_NO_LB, Strategy.SOURCE_ROUTING_BY_LENGTH_NO_LB]:
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
                        if constants.ROUTING_STRATEGY == Strategy.SOURCE_ROUTING_BY_HOP_NO_LB:
                            path = nx.shortest_path(self._auxiliary_graph, src_sat, dst_sat)
                        else:
                            path = nx.shortest_path(self._auxiliary_graph, src_sat, dst_sat, weight='weight')
                        disjoint_paths.append(path)
                    except nx.NetworkXNoPath:
                        print(f"[INFO] Getting K-paths - No Node disjoint path for {constants.ROUTING_STRATEGY} between {src_sat} and {dst_sat}.")

        elif constants.ROUTING_STRATEGY in [Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB]:
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
                        k = constants.K_SHORTEST_VALUE_LB
                        all_paths = list(nx.node_disjoint_paths(self._auxiliary_graph, src_sat, dst_sat))
                        weighted_paths = [
                            (p, sum(self._auxiliary_graph[u][v].get('weight', 1) for u, v in zip(p, p[1:])))
                            for p in all_paths
                        ]
                        weighted_paths.sort(key=lambda x: x[1])
                        disjoint_paths = [p for p, _ in weighted_paths[:k]]
                    except nx.NetworkXNoPath:
                        print(f"[INFO] Getting K-paths - No Node disjoint path for {constants.ROUTING_STRATEGY} between {src_sat} and {dst_sat}.")

        elif constants.ROUTING_STRATEGY in [Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                            Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING]:
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
                        k = constants.K_SHORTEST_VALUE_LB
                        all_paths = list(nx.edge_disjoint_paths(self._auxiliary_graph, src_sat, dst_sat))
                        weighted_paths = [
                            (p, sum(self._auxiliary_graph[u][v].get('weight', 1) for u, v in zip(p, p[1:])))
                            for p in all_paths
                        ]
                        weighted_paths.sort(key=lambda x: x[1])
                        disjoint_paths = [p for p, _ in weighted_paths[:k]]
                    except nx.NetworkXNoPath:
                        print(f"[INFO] Getting K-paths - No Edge disjoint path for {constants.ROUTING_STRATEGY} between {src_sat} and {dst_sat}.")
        
        elif constants.ROUTING_STRATEGY in [Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK]:
            if source == destination:
                print(f"Source and destination are the same: {source.get_name().upper()}. No route needed.")
                closer_sats = utils.get_closer_satellites(satellites, (self.lat, self.lon), False)
                disjoint_paths = [[closer_sats[0]['name']]]
                return disjoint_paths

            for src_sat in source_satellite:
                for dst_sat in destination_satellite:
                    if src_sat not in valid_source_sats:
                        print(f"[ERROR] Source satellite {src_sat} missing from graph!")
                        return []
                    if dst_sat not in valid_destination_sats:
                        print(f"[ERROR] Destination satellite {dst_sat} missing from graph!")
                        return []
                    try:
                        k = constants.K_SHORTEST_VALUE_LB
                        all_paths = list(nx.node_disjoint_paths(self._auxiliary_graph, src_sat, dst_sat))
                        max_bw = constants.SATELLITE_LINK_CAPACITY
                        bandwidth_paths = []
                        for path in all_paths:
                            bws = [
                                self._auxiliary_graph[u][v].get('available_bandwidth', 0) / max_bw
                                for u, v in zip(path, path[1:])
                                if self._auxiliary_graph.has_edge(u, v)
                            ]
                            if not bws or any(b == 0 for b in bws):
                                continue

                            harmonic_mean = len(bws) / sum(1 / b for b in bws)
                            bandwidth_paths.append((path, harmonic_mean))
                        bandwidth_paths.sort(key=lambda x: x[1], reverse=True)
                        disjoint_paths = [p for p, _ in bandwidth_paths[:k]]
                    except nx.NetworkXNoPath:
                        print(f"[INFO] No node-disjoint path for {constants.ROUTING_STRATEGY} between {src_sat} and {dst_sat}.")
                        continue
        return disjoint_paths
    
    def calculate_path_costs(self, graph, paths, alpha):
        path_costs = []
        alpha = constants.LOAD_BALANCING_WEIGHT_FACTOR
        for path in paths:
            if len(path) == 1:
                path_costs.append((path, 0))
                continue
            weights = []
            inv_bandwidths = []
            min_bw = float('inf')
            for u, v in zip(path, path[1:]):
                edge = graph.get_edge_data(u, v, default={})
                weight = edge.get('weight', 1)
                bandwidth = edge.get('available_bandwidth', 1)
                weights.append(weight)
                inv_bandwidths.append(1 / bandwidth if bandwidth > 0 else float('inf'))
                min_bw = min(min_bw, bandwidth)
            avg_weight = sum(weights) / len(weights)
            avg_inv_bw = sum(inv_bandwidths) / len(inv_bandwidths)
            inv_min_bw = 1 / min_bw if min_bw > 0 else float('inf')
            beta = 1 - alpha
            cost = alpha * avg_weight + beta * (0.5 * avg_inv_bw + 0.5 * inv_min_bw)
            path_costs.append((path, cost))
        path_costs.sort(key=lambda x: x[1])
        return path_costs

    def calculate_path_weights_kshortest_disjoint(self, graph, disjoint_paths):
        from link import LaserLink
        path_weights = []
        for path in disjoint_paths:
            if len(path) == 1:
                return [1.0]
            weight = 0
            for i in range(len(path) - 1):
                current_node = path[i]
                next_node = path[i + 1]
                if not graph.has_edge(current_node, next_node) or 'weight' not in graph[current_node][next_node]:
                    raise KeyError(f"Link between {current_node} and {next_node} is missing or has no weight.")
                base_weight = graph[current_node][next_node]['weight']
                link_key = (current_node, next_node)
                utilization = self.link_utilization.get(link_key, 0)
                link = self._get_link_between_nodes(current_node, next_node, self.satellites)
                max_capacity = (
                    constants.SATELLITE_LINK_CAPACITY if isinstance(link, LaserLink)
                    else constants.GROUND_STATION_LINK_CAPACITY
                )
                if max_capacity <= 0:
                    raise ValueError(f"Invalid maximum capacity for link {current_node}-{next_node}: {max_capacity}")
                penalty = utilization / max_capacity
                weight += base_weight * (1 + penalty)
            path_weights.append(weight)
        if not path_weights:
            raise ValueError("Empty weight list, no valid paths.")
        total_weight = sum(path_weights)
        if total_weight == 0:
            raise ValueError("Total weight sum is zero, unable to calculate probabilities.")
        inverted_weights = [1 / w for w in path_weights]
        total_inverted_weights = sum(inverted_weights)
        probabilities = [iw / total_inverted_weights for iw in inverted_weights]
        return probabilities

    def select_path_with_probabilities(self, paths, probabilities): 
        if len(paths) != len(probabilities):
            raise ValueError("The number of paths and probabilities must be equal.")
        paired = list(zip(probabilities, paths))
        paired.sort(key=lambda x: x[0], reverse=True)
        ranked_paths = [p for _, p in paired]
        return ranked_paths

    #obtain list of closer satellites in coverage area
    def _get_candidate_end_satellites_names(self, satellites, position):
        sat_list = utils.get_closer_satellites(satellites, position)
        return [sat['name'] for sat in sat_list if sat['distance'] < constants.SATELLITE_COVERAGE_AREA_RADIUS]

    #found the link between two nodes of the path
    def _get_link_between_nodes(self, node1, node2, satellites):        
        if node1 not in satellites:
            raise ValueError(f"Node1 '{node1}' not found in satellites.")
        if node2 not in satellites:
            raise ValueError(f"Node2 '{node2}' not found in satellites.")
        satellite1 = satellites[node1]
        for direction, link in satellite1._links.items():
            if link.target is None:
                continue
            if link.target.get_name() == node2:
                return link
        raise ValueError(f"No link exists between '{node1}' and '{node2}'.")
    
    def _get_link_to_ground_station(self, node, destination, satellites, ground_stations):
        if node not in satellites:
            raise ValueError(f"Last Node '{node}' not found in satellites.")
        if destination not in ground_stations.values():
            raise ValueError(f"Destination '{destination}' not found in ground stations.")
        destination_name = destination.get_name().upper()  #get_name (e.g. TOKYO) from the value of gs in dictionary
        if destination_name not in ground_stations:
            raise ValueError(f"Destination '{destination_name}' not found in ground stations.")
        last_satellite = satellites[node]
        destination_gs = ground_stations[destination_name]
        attached_gs_list = last_satellite._gs_link.get_attached_gs()
        if destination_gs not in attached_gs_list:
            raise ValueError(f"Ground station '{destination_gs}' not attached to satellite '{last_satellite}'.")
        return last_satellite._gs_link

    def _get_link_between_nodes_or_ground_station(self, node1, node2, satellites, ground_stations):
        if node2 in ground_stations.keys():
            node2 = ground_stations[node2]
            return self._get_link_to_ground_station(node1, node2, satellites, ground_stations)
        if node1 in ground_stations.keys():
            node1 = ground_stations[node1]
            return self._get_link_to_ground_station(node2, node1, satellites, ground_stations)
        return self._get_link_between_nodes(node1, node2, satellites)

    def drop_flow(self, flow: Flow, reason: FlowState):
        if flow.id in self.DEBUG_dropped_flows:
            print("ID already stored in dropped flows")
            return
        printing = False
        if printing:
        #if constants.DEBUG:
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
        self.DEBUG_dropped_flows.append(flow) 
        self.gss[[key for key, gs in self.gss.items() if gs.lat == flow.destination[0] and gs.lon == flow.destination[1]][0]].DEBUG_get_dropped_flow(flow)
