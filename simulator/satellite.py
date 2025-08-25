import constants
from copy import copy
from direction import Direction
import environment as env
from flow import Flow, FlowState
from geopy import distance
from ground_station import GroundStation
from link import Link, LaserLink, RadioLink
from mapping_table import MappingTable
import math
import random
from routing_action import RoutingAction
from skyfield.api import EarthSatellite, wgs84
from strategy import Strategy
import utils

class Sat:
    def __init__(self, earth_satellite, ground_stations) -> None:
        self._earth_satellite: EarthSatellite = earth_satellite
        self._lat = None
        self._lon = None
        self._links = {}
        self._links[Direction.NORTH] = LaserLink(self)
        self._links[Direction.SOUTH] = LaserLink(self)
        self._links[Direction.EAST] = LaserLink(self)
        self._links[Direction.WEST] = LaserLink(self)
        self._gs_link = RadioLink(self)
        self.flows: dict[int, tuple[Flow, Link]] = {}
        self.DEBUG_dropped_flows: list[Flow] = []
        self.mapping_table = MappingTable()
        self._ground_stations = ground_stations
        self.state = 0.0
        self.serving_gs: GroundStation = None
        self._current_round_robin_iteration = random.randint(1, 4) 
        self._is_rerouting = False

    def __eq__(self, other) -> bool:
        if isinstance(other, Sat):
            return self.get_name() == other.get_name()
        return False
    
    def __ne__(self, other) -> bool:
        return not self.__eq__(other)

    def is_operational(self) -> bool:
        return len([link for link in self._links.values() if link.is_active()]) != 0

    def add_link(self, sat, dir: Direction):
        link = self._links.get(dir)
        if link.target == sat:
            return
        self.notify_neighbor_unlink(dir)
        leftovers = link.point_to_sat(sat)
        if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_NO_LB,
                                          Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                          Strategy.POSITION_GUESSING_PROGRESSIVE_LB]:
            self._update_position()
        if leftovers:
            for flow in leftovers:
                flow.drop_steps_from(self)
                self.drop_flow(flow, FlowState.LINK_CONGESTED)
        self.update_only_network_state()

    def remove_link(self, dir: Direction, notify_neighbor=True):
        link = self._links.get(dir)
        if not link.is_active():
            return
        if notify_neighbor:
            self.notify_neighbor_unlink(dir)
        leftovers = link.idle()
        if leftovers and self.is_operational():
            for flow in leftovers:
                flow.drop_steps_from(self)
                self.drop_flow(flow, FlowState.LINK_CONGESTED)
        if not(self.is_operational()) and self.serving_gs:
            #if constants.DEBUG:
                #print("Satellite", self.get_name(), "is serving Ground Station", self.serving_gs.get_name(), "but is no longer operational. Requesting reattachment...")
            self.serving_gs.reattach()

    def get_name(self) -> int:
        return int(self._earth_satellite.name[-3:])
    
    def get_latitude(self):
        return self._lat
    
    def get_longitude(self):
        return self._lon
    
    def store_flow_direction(self, flow: Flow, link: Link):
        if flow.alias_id not in self.flows.keys():
            self.flows[flow.alias_id] = (flow, link)
            
    def get_stored_flow_direction(self, alias_id: int) -> list[(Flow, Link)]:
        if alias_id in self.flows.keys():
            return self.flows[alias_id]
        return []

    def drop_flow(self, flow: Flow, reason: FlowState):
        if flow.id in self.DEBUG_dropped_flows:
            print("[SATELLITE] ID already stored in dropped flows")
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
            print(msg)
        flow.state = reason
        self.store_flow_direction(flow, None)
        self.DEBUG_dropped_flows.append(flow)
        self._ground_stations[[key for key, gs in self._ground_stations.items() if gs.lat == flow.destination[0] and gs.lon == flow.destination[1]][0]].DEBUG_get_dropped_flow(flow)

    def update_neighbors(self):
        self._update_state()
        for dir, link in self._links.items():
            if link.is_active():
                link.send_update(self.get_latitude(), self.get_longitude(), self.state, utils.get_coupled_link_direction(dir))
                if constants.ROUTING_STRATEGY == Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB:
                    env.log_control_traffic_message(2)
                env.log_control_traffic_message(6)
    
    def _update_state(self):
        active_links = [link for link in self._links.values() if link.is_active()]
        if active_links:
            local_state = (constants.SATELLITE_LINK_CAPACITY - (sum([link.get_available_bandwidth() for link in active_links]) / len(active_links))) / constants.SATELLITE_LINK_CAPACITY
            neighbor_state = sum([link.state for link in active_links]) / len(active_links)
            self.state = local_state * (1 - constants.LOAD_BALANCING_WEIGHT_FACTOR) + neighbor_state * constants.LOAD_BALANCING_WEIGHT_FACTOR
        else:
            self.state = 0.0
        if constants.DEBUG:
            if self.state > 1:
                print(self.state, self.get_name())
                raise ValueError("State value over 1")
            
    def _update_gs_link(self):
        gs_candidates = []
        for gs in self._ground_stations.values():
            distance_from_destination = distance.distance((self.get_latitude(), self.get_longitude()), (gs.lat, gs.lon)).km
            if distance_from_destination < constants.SATELLITE_COVERAGE_AREA_RADIUS:
                gs_candidates.append(gs)
        if set(gs_candidates) != set(self._gs_link.get_attached_gs()):
            leftovers = self._gs_link.detach_from_all()
            for gs in gs_candidates:
                self._gs_link.attach_to_gs(gs)
            if leftovers:
                for flow in leftovers:
                    flow.drop_steps_from(self)
                    self.drop_flow(flow, FlowState.LINK_CONGESTED)
            self.update_only_network_state()

    def _update_position(self):
        geocentric = self._earth_satellite.at(utils.get_current_time())
        lat, lon = wgs84.latlon_of(geocentric)
        self._lat = lat.degrees 
        self._lon = lon.degrees
        
        if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_NO_LB,
                                          Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                          Strategy.POSITION_GUESSING_PROGRESSIVE_LB]:
            north_link = self._links.get(Direction.NORTH)
            south_link = self._links.get(Direction.SOUTH)
            east_link = self._links.get(Direction.EAST)
            west_link = self._links.get(Direction.WEST)
            
            if east_link.is_active() or west_link.is_active():
                longitude_delta = (40075 / 2 / 6) / (40075 / 360) * math.cos(math.radians(self._lat))
                if east_link.is_active():
                    if self.get_longitude() + longitude_delta > 180:
                        east_link.lon = -180 + (self.get_longitude() + longitude_delta - 180)
                    else:
                        east_link.lon = self.get_longitude() + longitude_delta
                if west_link.is_active():
                    if self.get_longitude() - longitude_delta < -180:
                        west_link.lon = 180 - (self.get_longitude() - longitude_delta + 180)
                    else:
                        west_link.lon = self.get_longitude() - longitude_delta
            
            if north_link.is_active() or south_link.is_active():
                latitude_delta = (40008 / 11) / (40008 / 2 / 180)
                if north_link.is_active():
                    if self.get_latitude() + latitude_delta > 90:
                        north_link.lat = 90 - (self.get_latitude() + latitude_delta - 90)
                    else:
                        north_link.lat = self.get_latitude() + latitude_delta
                if south_link.is_active():
                    if self.get_latitude() - latitude_delta < -90:
                        south_link.lat = -90 - (self.get_latitude() - latitude_delta + 90)
                    else:
                        south_link.lat = self.get_latitude() - latitude_delta

    def notify_neighbor_unlink(self, dir: Direction):
        link = self._links.get(dir)
        if link.is_active():
            link.unlink(utils.get_coupled_link_direction(dir))
    
    def send_flow(self, flow: Flow, link: Link, routing_decisions=None):
        if link.reserve_bandwidth(flow):
            self.store_flow_direction(flow, link)
            if isinstance(link, RadioLink):
                flow.travelled_distance += utils.get_distance_between_satellite_and_gs(self, link.target[0])
            else:
                flow.travelled_distance += utils.get_distance_between_satellites(self, link.target)
            if routing_decisions is not None:
                link.send_flow(flow, routing_decisions)
            else:
                link.send_flow(flow)
        else:
            self.drop_flow(flow, FlowState.LINK_CONGESTED)

    def _reopen_flow(self, flow: Flow, routing_decisions=None):
        if self.is_operational() == False:
            self._close_internal_flow(flow.alias_id)
            self.drop_flow(flow, FlowState.SATELLITE_NOT_OPERATIONAL)
        else:
            if routing_decisions == None:
                routing_decisions = self.route(flow)
                self._close_internal_flow(flow.alias_id)
                if len(routing_decisions) > 1:
                    for _, f, _ in routing_decisions[1:]:
                        f.alias_id = self.mapping_table.get_input_id(f.alias_id)
                        f.alias_id = self.mapping_table.add(f.alias_id)
                for action, f, link in routing_decisions:
                    if action == RoutingAction.FORWARD or action == RoutingAction.DELIVER:
                        self.send_flow(f, link)
                    elif action == RoutingAction.ERROR:
                        self.drop_flow(f, link)
                    elif action == RoutingAction.REOPEN:
                        f.alias_id = self.mapping_table.get_input_id(f.alias_id)
                        f.drop_steps_from(self)
                        self.open_flow(f)
            else:
                routing_centralized_decisions = []
                decision = (routing_decisions[0][0], flow, routing_decisions[0][2])
                routing_centralized_decisions.append(decision)
                self._close_internal_flow(flow.alias_id)
                
                for action, f, link in routing_centralized_decisions:
                    if action == RoutingAction.FORWARD or action == RoutingAction.DELIVER:
                        routing_decisions.pop(0)
                        self.send_flow(f, link, routing_decisions)
                    elif action == RoutingAction.ERROR:
                        routing_decisions.pop(0)
                        #print("[SATELLITE] drop flow in method _reopen_flow routing [SOURCE ROUTE ERROR]", flow.id, "with rate", flow.rate, "at", self.get_name())
                        self.drop_flow(f, link)
                    elif action == RoutingAction.REOPEN:
                        f.alias_id = self.mapping_table.get_input_id(f.alias_id)
                        f.drop_steps_from(self)
                        routing_decisions.pop(0)
                        self.open_flow(f, routing_decisions)

    def open_flow(self, flow: Flow, routing_decisions=None):
        flow.add_step(self)
        flow.alias_id = self.mapping_table.add(flow.alias_id)
        if flow.ttl == 0:
            self.drop_flow(flow, FlowState.EXPIRED_TTL)
        else:
            if routing_decisions != None:
                self._reopen_flow(flow, routing_decisions)
            else:
                self._reopen_flow(flow)

    def route(self, flow: Flow) -> list[(RoutingAction, Flow, Link)]:
        routing_decisions = self.basic_route(flow)
        routing_decisions = self.adapt_routing_decisions_to_available_link_bandwidth(flow, routing_decisions)
        return routing_decisions

    def adapt_routing_decisions_to_available_link_bandwidth(self, flow: Flow, routing_decisions: list[tuple[RoutingAction, Link]]) -> list[tuple[RoutingAction, Flow, Link]]:
        adapted_routing_decisions = []
        for action, link in routing_decisions:
            if action == RoutingAction.FORWARD or action == RoutingAction.DELIVER:
                available_bandwidth = link.get_available_bandwidth()
                if available_bandwidth == 0:
                    continue
                if available_bandwidth >= flow.rate:
                    adapted_routing_decisions.append((action, flow, link))
                    break
                else:
                    f, flow = flow.split(available_bandwidth)
                    adapted_routing_decisions.append((action, f, link))
            elif action == RoutingAction.ERROR:
                adapted_routing_decisions.append((action, flow, link))
                break
        else:
            adapted_routing_decisions.append((RoutingAction.ERROR, flow, FlowState.SATELLITE_CONGESTED))
        return adapted_routing_decisions

    def basic_route(self, flow: Flow, avoid: list[Link] = []) -> list[tuple[RoutingAction, Link]]:
        def get_nodes_to_be_excluded_from_next_hop_candidates(flow) -> list:
            if constants.LOOP_AVOIDANCE_CUTOFF == 0:
                return []
            else:
                steps = flow.get_steps() if len(flow.get_steps()) < constants.LOOP_AVOIDANCE_CUTOFF else flow.get_steps()[-constants.LOOP_AVOIDANCE_CUTOFF:]
                if steps and steps[-1] == self:
                    steps = steps[:-1]
                indices = [i+1 for i, x in enumerate(steps) if x == self]
                if len(steps) > 0:
                    indices.append(-1)
                return [steps[i] for i in indices if 0 <= i < len(steps)]

        routing_output = list()
        distance_from_destination = distance.distance((self.get_latitude(), self.get_longitude()), flow.destination).km
        if distance_from_destination < constants.SATELLITE_COVERAGE_AREA_RADIUS:
            routing_output.append((RoutingAction.DELIVER, self._gs_link))

        if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_NO_LB,
                                          Strategy.POSITION_SHARING_NO_LB]:
            nodes_to_be_excluded = get_nodes_to_be_excluded_from_next_hop_candidates(flow)

            candidates = list()
            for key, link in self._links.items():
                if link in avoid:
                    continue
                if link.is_active():
                    if link.target in nodes_to_be_excluded:
                        dist = float("inf")
                    else:
                        dist = distance.distance((link.lat, link.lon), flow.destination).km
                    candidates.append({'distance': dist, 'dir': key})
            candidates.sort(key=lambda x: x['distance'])

            if not(candidates):
                routing_output.append((RoutingAction.ERROR, FlowState.SATELLITE_NOT_OPERATIONAL))

            if candidates:
                candidate = candidates[0]
                for r_o in routing_output:
                    if r_o[0] == RoutingAction.ERROR:
                        raise RuntimeError("routing_output already contains an error action")
                routing_output.append((RoutingAction.FORWARD, self._links.get(candidate['dir'])))

        elif constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                            Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK]:
            nodes_to_be_excluded = get_nodes_to_be_excluded_from_next_hop_candidates(flow)

            candidates = list()
            for key, link in self._links.items():
                if link in avoid:
                    continue
                if link.is_active():
                    if link.target in nodes_to_be_excluded:
                        dist = float("inf")
                    else:
                        dist = distance.distance((link.lat, link.lon), flow.destination).km
                    candidates.append({'distance': dist, 'dir': key})
            candidates.sort(key=lambda x: x['distance'])

            if not(candidates):
                routing_output.append((RoutingAction.ERROR, FlowState.SATELLITE_NOT_OPERATIONAL))

            for candidate in candidates:
                for r_o in routing_output:
                    if r_o[0] == RoutingAction.ERROR:
                        raise RuntimeError("routing_output already contains an error action")
                routing_output.append((RoutingAction.FORWARD, self._links.get(candidate['dir'])))

        elif constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                            Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                            Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB]:
            nodes_to_be_excluded = get_nodes_to_be_excluded_from_next_hop_candidates(flow)

            candidates = list()
            for key, link in self._links.items():
                if link in avoid:
                    continue
                if link.is_active():
                    if link.target in nodes_to_be_excluded:
                        dist = float("inf")
                    else:
                        dist = distance.distance((link.lat, link.lon), flow.destination).km
                    
                    if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                                      Strategy.POSITION_SHARING_PROGRESSIVE_LB]:
                        load_balancing_score = link.get_available_bandwidth() / constants.SATELLITE_LINK_CAPACITY * 4
                    elif constants.ROUTING_STRATEGY == Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB:
                        load_balancing_score = (1 - link.state) * 4
                    candidates.append({'distance': dist, 'dir': key, 'load_balancing_score': load_balancing_score})
            candidates.sort(key=lambda x: x['distance'])

            for i, candidate in enumerate(candidates):
                ordering_score = 4 - i if candidate['distance'] != float('inf') else 0
                candidate['total_score'] = ordering_score + candidate['load_balancing_score']
            candidates.sort(key=lambda x: x['total_score'], reverse=True) 

            if not(candidates):
                routing_output.append((RoutingAction.ERROR, FlowState.SATELLITE_NOT_OPERATIONAL))

            for candidate in candidates:
                for r_o in routing_output:
                    if r_o[0] == RoutingAction.ERROR:
                        raise RuntimeError("routing_output already contains an error action")
                routing_output.append((RoutingAction.FORWARD, self._links.get(candidate['dir'])))

        elif constants.ROUTING_STRATEGY == Strategy.POSITION_AND_LOAD_STATE_SHARING_TWO_HOPS:
            import statistics
            nodes_to_be_excluded = get_nodes_to_be_excluded_from_next_hop_candidates(flow)
            candidates = []
            alpha = 0.4
            penalty_weight = 0.3
            for key, link in self._links.items():
                if link in avoid or not link.is_active():
                    continue
                if link.target in nodes_to_be_excluded:
                    dist = float("inf")
                else:
                    dist = distance.distance((link.lat, link.lon), flow.destination).km
                first_hop_score = (1 - link.state) * 4
                neighbor_sat = link.target
                second_hop_scores = []
                second_hop_distances = []
                for second_link in neighbor_sat._links.values():
                    if second_link.is_active() and second_link.target != self:
                        score = (1 - second_link.state) * 4
                        second_hop_scores.append(score)
                        second_hop_distances.append(distance.distance((second_link.lat, second_link.lon), flow.destination).km)
                if len(second_hop_scores) < 2 or max(second_hop_scores) < 1.0:
                    continue
                avg_second_hop_score = sum(second_hop_scores) / len(second_hop_scores)
                std_dev = statistics.stdev(second_hop_scores) if len(second_hop_scores) > 1 else 0
                connectivity_ratio = len(second_hop_scores) / len(neighbor_sat._links)
                fanout_bonus = connectivity_ratio * 1.5
                avg_second_hop_distance = sum(second_hop_distances) / len(second_hop_distances) if second_hop_distances else float("inf")
                distance_penalty = avg_second_hop_distance / 10000

                lb_score = (
                    alpha * first_hop_score +
                    (1 - alpha) * avg_second_hop_score +
                    fanout_bonus -
                    penalty_weight * std_dev -
                    distance_penalty
                )
                candidates.append({
                    'distance': dist,
                    'dir': key,
                    'first_hop_score': first_hop_score,
                    'avg_second_hop_score': avg_second_hop_score,
                    'std_dev': std_dev,
                    'lb_score': lb_score
                })
            candidates.sort(key=lambda x: x['distance'])
            for i, candidate in enumerate(candidates):
                ordering_score = max(0, 2 - i) if candidate['distance'] != float("inf") else 0
                candidate['total_score'] = ordering_score + candidate['lb_score']
            candidates.sort(key=lambda x: x['total_score'], reverse=True)

            if not candidates:
                routing_output.append((RoutingAction.ERROR, FlowState.SATELLITE_NOT_OPERATIONAL))

            for candidate in candidates:
                for r_o in routing_output:
                    if r_o[0] == RoutingAction.ERROR:
                        raise RuntimeError("routing_output already contains an error action")
                routing_output.append((RoutingAction.FORWARD, self._links.get(candidate['dir'])))
        return routing_output

    def close_flow(self, flow: Flow):
        local_ids = self.mapping_table.get_local_ids(flow.alias_id)
        for local_id in local_ids:
            self._close_internal_flow(local_id)
            if self.mapping_table.contains_local_id(local_id):
                self.mapping_table.remove(local_id)

    def _close_internal_flow(self, alias_id: int):
        flow_link_pairs = self.get_stored_flow_direction(alias_id)
        if flow_link_pairs:
            self.flows.pop(alias_id)
            flow, link = flow_link_pairs
            if isinstance(link, RadioLink):
                flow.travelled_distance -= utils.get_distance_between_satellite_and_gs(self, link.target[0])
            elif isinstance(link, LaserLink):
                flow.travelled_distance -= utils.get_distance_between_satellites(self, link.target)
            if link != None:
                link.close_flow(flow)
            else:
                #if constants.DEBUG:
                 #   print("Closed dropped flow", flow.id, "with alias id", flow.alias_id, "with rate", flow.rate, "Mbps on Satellite", self.get_name(), "at time", utils.get_current_time().utc_strftime())
                f = [f for f in self.DEBUG_dropped_flows if f.alias_id == flow.alias_id][0]
                self._ground_stations[[key for key, gs in self._ground_stations.items() if gs.lat == flow.destination[0] and gs.lon == flow.destination[1]][0]].DEBUG_close_dropped_flow(f)
                del self.DEBUG_dropped_flows[[i for i, fl in enumerate(self.DEBUG_dropped_flows) if fl.alias_id == flow.alias_id][0]]

    def update_link_info(self, lat, lon, state, dir: Direction):
        self._links.get(dir).update(lat, lon, state)

    def get_active_links(satellites):
        active_links = []
        for sat in satellites:
            if not isinstance(sat, Sat):
                print(f"Attenzione: {sat} non è un oggetto Sat!")
            for link in sat._links.values():
                if link.is_active():
                    active_links.append((sat, link.target))
        return active_links
    
    def update_only_network_state(self):
        self._update_position()
        self._update_state()
        for dir, link in self._links.items():
            if link.is_active():
                link.send_update(
                    self.get_latitude(),
                    self.get_longitude(),
                    self.state,
                    utils.get_coupled_link_direction(dir)
                )

    def extract_satellites_from_routing_decisions(self, routing_decisions: list[tuple]) -> list[str]:
        satellites = []
        if not routing_decisions:
            return satellites
        
        first_link = routing_decisions[0][2]
        if hasattr(first_link, '_parent') and first_link._parent:
            satellites.append(first_link._parent.get_name())
        
        for _, _, link in routing_decisions:
            if hasattr(link, 'target') and link.target:
                if isinstance(link.target, list):
                    for target in link.target:
                        if hasattr(target, 'get_name'):
                            satellites.append(target.get_name())
                elif hasattr(link.target, 'get_name'):
                    satellites.append(link.target.get_name())
        return satellites