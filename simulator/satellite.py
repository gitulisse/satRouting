import constants
from copy import copy
from direction import Direction
import environment as env
from flux import Flux, FluxState
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
        self.fluxes: dict[int, (Flux, Link)] = {}
        self.DEBUG_dropped_fluxes: list[Flux] = []
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
    
        if constants.DEBUG:
            print("Adding link from Satellite", self.get_name(), "to Satellite", sat.get_name(), "at time", utils.get_current_time().utc_strftime())
        
        self.notify_neighbor_unlink(dir)
        leftovers = link.point_to_sat(sat)
        if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_NO_LB,
                                          Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                          Strategy.POSITION_GUESSING_PROGRESSIVE_LB]:
            self._update_position()
        if leftovers:
            for flux in leftovers:
                if constants.DEBUG:
                    print("Leftover from link:", dir, "on Satellite", self.get_name(), "at time", utils.get_current_time().utc_strftime(), "flux:", flux.id, [step.get_name() for step in flux.get_steps()])
                flux.drop_steps_from(self)
                self.open_flux(flux)
        self._reroute_all()
        #env.put(env.elapsed_time, self._reroute_all)
    
    def remove_link(self, dir: Direction, notify_neighbor = True):
        link = self._links.get(dir)
        if not(link.is_active()):
            return
        if notify_neighbor:
            self.notify_neighbor_unlink(dir)
        
        if constants.DEBUG:
            print("Removing link from Satellite", self.get_name(), "to Satellite", self._links[dir].target.get_name(), "at time", utils.get_current_time().utc_strftime())
        
        leftovers = self._links[dir].idle()
        if leftovers and self.is_operational():
            for flux in leftovers:
                if constants.DEBUG:
                    print("Leftover from link:", dir, "on Satellite", self.get_name(), "at time", utils.get_current_time().utc_strftime(), "flux:", flux.id, [step.get_name() for step in flux.get_steps()])
                flux.drop_steps_from(self)
                self.open_flux(flux)
        if not(self.is_operational()):
            if self.serving_gs:
                if constants.DEBUG:
                    print("Satellite", self.get_name(), "is serving Ground Station", self.serving_gs.get_name(), "but is no longer operational. Requesting reattachment...")
                self.serving_gs.reattach()
    
    def get_name(self) -> int:
        return int(self._earth_satellite.name[-3:])
    
    def get_latitude(self):
        return self._lat
    
    def get_longitude(self):
        return self._lon
    
    def store_flux_direction(self, flux: Flux, link: Link):
        if flux.alias_id not in self.fluxes.keys():
            self.fluxes[flux.alias_id] = (flux, link)
        else:
            raise RuntimeError("Alias id already present in fluxes structure.", flux.alias_id)
        if constants.DEBUG:
            print("Stored new flux with alias id", flux.alias_id, "with rate", flux.rate, "headed to link", link if link != None else None, "on Satellite", self.get_name(), "at time", utils.get_current_time().utc_strftime())

    def get_stored_flux_direction(self, alias_id: int) -> list[(Flux, Link)]:
        if alias_id in self.fluxes.keys():
            return self.fluxes[alias_id]
        return []
    
    def drop_flux(self, flux: Flux, reason: FluxState):
        if constants.DEBUG:
            msg = "Flux " + str(flux.id) + " with alias id " + str(flux.alias_id) + " with rate " + str(flux.rate) + " Mbps has been dropped by Satellite " + str(self.get_name()) + " at time " + utils.get_current_time().utc_strftime() + ". "
            if reason == FluxState.SATELLITE_CONGESTED:
                msg += "Satellite is congested."
            elif reason == FluxState.LINK_CONGESTED:
                msg += "Link is congested."
            elif reason == FluxState.EXPIRED_TTL:
                msg += "TTL is 0."
            elif reason == FluxState.SATELLITE_NOT_OPERATIONAL:
                msg += "Satellite is not operational."
            else:
                raise ValueError("The reason is not expected.", reason)
            print(msg)

        flux.state = reason
        self.store_flux_direction(flux, None)
        self.DEBUG_dropped_fluxes.append(flux)
        self._ground_stations[[key for key, gs in self._ground_stations.items() if gs.lat == flux.destination[0] and gs.lon == flux.destination[1]][0]].DEBUG_get_dropped_flux(flux)
    
    def update_neighbors(self):
        #self._update_position()
        #self._update_gs_link()
        self._update_state()
        for dir, link in self._links.items():
            if link.is_active():
                link.send_update(self.get_latitude(), self.get_longitude(), self.state, utils.get_coupled_link_direction(dir))
                if constants.ROUTING_STRATEGY == Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB:
                    env.log_control_traffic_message(2)
                env.log_control_traffic_message(6)
    
    def _update_state(self):
        if any([link for link in self._links.values() if link.is_active()]):
            local_state = (constants.SATELLITE_LINK_CAPACITY - (sum([link.get_available_bandwidth() for link in self._links.values() if link.is_active()]) / len([link for link in self._links.values() if link.is_active()]))) / constants.SATELLITE_LINK_CAPACITY
            neighbor_state = sum([link.state for link in self._links.values() if link.is_active()]) / len([link for link in self._links.values() if link.is_active()])
            self.state = local_state * (1 - constants.LOAD_BALANCING_WEIGHT_FACTOR) + neighbor_state * constants.LOAD_BALANCING_WEIGHT_FACTOR
        else:
            self.state = 0

        if constants.DEBUG:
            if self.state > 1:
                print(self.state, self.get_name())
                raise ValueError("STATE MAGGIORE DI 1")
            if self.state > 0.1:
                print("State:", self.state, "sat:", self.get_name())

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
                for flux in leftovers:
                    if constants.DEBUG:
                        print("Leftover from gs_link on Satellite", self.get_name(), "at time", utils.get_current_time().utc_strftime(), "flux:", flux.id, [step.get_name() for step in flux.get_steps()])
                    flux.drop_steps_from(self)
                    self.open_flux(flux)
            self._reroute_all()
            #env.put(env.elapsed_time, self._reroute_all)

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
                longitude_delta = (40075 / 2 / 6) / (40075 / 360) * math.cos(self._lat)
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
            if constants.DEBUG:
                print("Dropping link between", self.get_name(), "and", link.target.get_name())
            link.unlink(utils.get_coupled_link_direction(dir))

    def send_flux(self, flux: Flux, link: Link):
        if link.reserve_bandwidth(flux):
            if constants.DEBUG:
                if isinstance(link, RadioLink):
                    print("Opened flux", flux.id, "on Satellite", self.get_name(), "with rate", flux.rate, "Mbps on link headed to", [gs.get_name() for gs in link.target], "at time", utils.get_current_time().utc_strftime())
                else:
                    print("Opened flux", flux.id, "on Satellite", self.get_name(), "with rate", flux.rate, "Mbps on link headed to", link.target.get_name(), "at time", utils.get_current_time().utc_strftime())
            self.store_flux_direction(flux, link)
            if isinstance(link, RadioLink):
                flux.travelled_distance += utils.get_distance_between_satellite_and_gs(self, link.target[0])
            else:
                flux.travelled_distance += utils.get_distance_between_satellites(self, link.target)
            link.send_flux(flux)
        else:
            self.drop_flux(flux, FluxState.LINK_CONGESTED)

    def _reopen_flux(self, flux: Flux):
        if self.is_operational() == False:
            self._close_internal_flux(flux.alias_id)
            self.drop_flux(flux, FluxState.SATELLITE_NOT_OPERATIONAL)
        else:
            routing_decisions = self.route(flux)
            self._close_internal_flux(flux.alias_id)
            if len(routing_decisions) > 1:
                for _, f, _ in routing_decisions[1:]:
                    f.alias_id = self.mapping_table.get_input_id(f.alias_id)
                    f.alias_id = self.mapping_table.add(f.alias_id)
            for action, f, link in routing_decisions:
                if action == RoutingAction.FORWARD or action == RoutingAction.DELIVER:
                    self.send_flux(f, link)
                elif action == RoutingAction.ERROR:
                    self.drop_flux(f, link)
                elif action == RoutingAction.REOPEN:
                    f.alias_id = self.mapping_table.get_input_id(f.alias_id)
                    f.drop_steps_from(self)
                    self.open_flux(f)

    def open_flux(self, flux: Flux):
        if constants.DEBUG:
            print("Opening flux", flux.id, "on Satellite", self.get_name(), "with rate:", flux.rate, "Mbps", "at time", utils.get_current_time().utc_strftime())
        flux.add_step(self)
        flux.alias_id = self.mapping_table.add(flux.alias_id)
        if flux.ttl == 0:
            self.drop_flux(flux, FluxState.EXPIRED_TTL)
        else:
            self._reopen_flux(flux)

    def route(self, flux: Flux) -> list[(RoutingAction, Flux, Link)]:
        routing_decisions = self.basic_route(flux)
        routing_decisions = self.adapt_routing_decisions_to_available_link_bandwidth(flux, routing_decisions)
        return routing_decisions

    def simulate_adapt_routing_decisions_to_available_link_bandwidth(self, routing_decisions: list[(Flux, list[tuple[RoutingAction, Link]])]) -> dict[int, list[tuple[RoutingAction, Flux, Link]]]:
        link_availability: dict[Link, float] = {}
        for link in self._links.values():
            link_availability[link] = constants.SATELLITE_LINK_CAPACITY
        link_availability[self._gs_link] = constants.GROUND_STATION_LINK_CAPACITY

        adapted_routing_decisions: dict[int, list] = {}
        for flux, routing_decision in routing_decisions:
            adapted_routing_decision = []
            for action, link in routing_decision:
                if action == RoutingAction.FORWARD or action == RoutingAction.DELIVER:
                    available_bandwidth = link_availability[link]
                    if available_bandwidth == 0:
                        continue
                    if available_bandwidth >= flux.rate:
                        adapted_routing_decision.append((action, flux, link))
                        break
                    else:
                        f, flux = flux.split(available_bandwidth)
                        adapted_routing_decision.append((action, f, link))
                elif action == RoutingAction.ERROR:
                    adapted_routing_decision.append((action, flux, link))
                    break
            else:
                adapted_routing_decision.append((RoutingAction.ERROR, flux, FluxState.SATELLITE_CONGESTED))
            adapted_routing_decisions[flux.alias_id] = adapted_routing_decision
            if adapted_routing_decision[0][0] != RoutingAction.ERROR:
                link_availability[adapted_routing_decision[0][2]] -= adapted_routing_decision[0][1].rate
        return adapted_routing_decisions

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

    def basic_route(self, flux: Flux, avoid: list[Link] = []) -> list[tuple[RoutingAction, Link]]:
        def get_nodes_to_be_excluded_from_next_hop_candidates(flux) -> list:
            if constants.LOOP_AVOIDANCE_CUTOFF == 0:
                return []
            else:
                steps = flux.get_steps() if len(flux.get_steps()) < constants.LOOP_AVOIDANCE_CUTOFF else flux.get_steps()[-constants.LOOP_AVOIDANCE_CUTOFF:]
                if steps[-1] == self:
                    steps = steps[:-1]
                indices = [i+1 for i, x in enumerate(steps) if x == self]
                if len(steps) > 0:
                    indices.append(-1)
                return [steps[i] for i in indices]
        
        routing_output = list()
        distance_from_destination = distance.distance((self.get_latitude(), self.get_longitude()), flux.destination).km
        if distance_from_destination < constants.SATELLITE_COVERAGE_AREA_RADIUS:
            routing_output.append((RoutingAction.DELIVER, self._gs_link))

        if constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_NO_LB,
                                          Strategy.POSITION_SHARING_NO_LB]:
            nodes_to_be_excluded = get_nodes_to_be_excluded_from_next_hop_candidates(flux)

            candidates = list()
            for key, link in self._links.items():
                if link in avoid:
                    continue
                if link.is_active():
                    if link.target in nodes_to_be_excluded:
                        dist = float("inf")
                    else:
                        dist = distance.distance((link.lat, link.lon), flux.destination).km
                        #if dist > distance.distance((self.get_latitude(), self.get_longitude()), flux.destination).km:
                        #    dist = float('inf')
                    candidates.append({'distance': dist, 'dir': key})
            candidates.sort(key=lambda x: x['distance'])

            if not(candidates):
                routing_output.append((RoutingAction.ERROR, FluxState.SATELLITE_NOT_OPERATIONAL))

            candidate = candidates[0]
            for r_o in routing_output:
                if r_o[0] == RoutingAction.ERROR:
                    raise RuntimeError("routing_output already contains an error action")
            routing_output.append((RoutingAction.FORWARD, self._links.get(candidate['dir'])))

        elif constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
                                            Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK]:
            nodes_to_be_excluded = get_nodes_to_be_excluded_from_next_hop_candidates(flux)

            candidates = list()
            for key, link in self._links.items():
                if link in avoid:
                    continue
                if link.is_active():
                    if link.target in nodes_to_be_excluded:
                        dist = float("inf")
                    else:
                        dist = distance.distance((link.lat, link.lon), flux.destination).km
                        #if dist > distance.distance((self.get_latitude(), self.get_longitude()), flux.destination).km:
                        #    dist = float('inf')
                    candidates.append({'distance': dist, 'dir': key})
            candidates.sort(key=lambda x: x['distance'])

            if not(candidates):
                routing_output.append((RoutingAction.ERROR, FluxState.SATELLITE_NOT_OPERATIONAL))

            for candidate in candidates:
                for r_o in routing_output:
                    if r_o[0] == RoutingAction.ERROR:
                        raise RuntimeError("routing_output already contains an error action")
                routing_output.append((RoutingAction.FORWARD, self._links.get(candidate['dir'])))

        elif constants.ROUTING_STRATEGY in [Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
                                            Strategy.POSITION_SHARING_PROGRESSIVE_LB,
                                            Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB]:
            nodes_to_be_excluded = get_nodes_to_be_excluded_from_next_hop_candidates(flux)

            candidates = list()
            for key, link in self._links.items():
                if link in avoid:
                    continue
                if link.is_active():
                    if link.target in nodes_to_be_excluded:
                        dist = float("inf")
                    else:
                        dist = distance.distance((link.lat, link.lon), flux.destination).km
                        #if dist > distance.distance((self.get_latitude(), self.get_longitude()), flux.destination).km:
                        #    dist = float('inf')
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
                routing_output.append((RoutingAction.ERROR, FluxState.SATELLITE_NOT_OPERATIONAL))

            for candidate in candidates:
                for r_o in routing_output:
                    if r_o[0] == RoutingAction.ERROR:
                        raise RuntimeError("routing_output already contains an error action")
                routing_output.append((RoutingAction.FORWARD, self._links.get(candidate['dir'])))

        return routing_output
    
    def _reroute_all(self):
        if self._is_rerouting:
            return
        self._is_rerouting = True
        if self.fluxes.keys():
            if constants.DEBUG:
                print("Rerouting traffic from satellite", self.get_name())

            fluxes_copy = []
            pointer = 0
            basic_route_decisions = []
            for flux, _ in self.fluxes.values():
                basic_route_decisions.append((flux, [(action, link) for action, link in self.basic_route(flux.clone())]))
            simulation = self.simulate_adapt_routing_decisions_to_available_link_bandwidth(basic_route_decisions)
            while pointer < len(self.fluxes.values()):
                flux, link = list(self.fluxes.values())[pointer]
                flux_simulation = simulation.get(flux.alias_id)
                if flux_simulation and flux_simulation[0][2] != link and not(isinstance(flux_simulation[0][2], FluxState) and link == None):
                    if constants.DEBUG:
                        print("Flux", flux.id, "with alias id", flux.alias_id, "is being rerouted from link", link, "to link", flux_simulation[0][2], "on Satellite", self.get_name(), "at time:", utils.get_current_time().utc_strftime())
                    fluxes_copy.append(flux.clone())
                    input_id = self.mapping_table.remove(flux.alias_id)
                    self._close_internal_flux(flux.alias_id)
                    fluxes_copy[-1].alias_id = input_id
                else:
                    pointer += 1
            for flux in fluxes_copy:
                flux.drop_steps_from(self)
                self.open_flux(flux)
        self._is_rerouting = False

    def check_for_routing_decisions_differences(self, routing_decisions: list[(RoutingAction, Flux, Link)]) -> bool:
        for action, flux, link in routing_decisions:
            if action == RoutingAction.FORWARD or action == RoutingAction.DELIVER or action == RoutingAction.ERROR:
                stored_flux, stored_link = self.get_stored_flux_direction(flux.alias_id)
                if stored_flux.rate == flux.rate and stored_link == link:
                    break
                else:
                    return True
        return False

    def close_flux(self, flux: Flux):
        local_ids = self.mapping_table.get_local_ids(flux.alias_id)

        for local_id in local_ids:
            self._close_internal_flux(local_id)
            if self.mapping_table.contains_local_id(local_id):
                self.mapping_table.remove(local_id)
        
        #self._reroute_all()
        #env.put(env.elapsed_time, self._reroute_all)

    def _close_internal_flux(self, alias_id: int):
        flux_link_pairs = self.get_stored_flux_direction(alias_id)
        if flux_link_pairs:
            self.fluxes.pop(alias_id)
            flux, link = flux_link_pairs
            if isinstance(link, RadioLink):
                flux.travelled_distance -= utils.get_distance_between_satellite_and_gs(self, link.target[0])
            elif isinstance(link, LaserLink):
                flux.travelled_distance -= utils.get_distance_between_satellites(self, link.target)
            #Link can be None when the flux is dropped on the current satellite.
            if link != None:
                link.close_flux(flux)
            else:
                if constants.DEBUG:
                    print("Closed dropped flux", flux.id, "with alias id", flux.alias_id, "with rate", flux.rate, "Mbps on Satellite", self.get_name(), "at time", utils.get_current_time().utc_strftime())
                f = [f for f in self.DEBUG_dropped_fluxes if f.alias_id == flux.alias_id][0]
                self._ground_stations[[key for key, gs in self._ground_stations.items() if gs.lat == flux.destination[0] and gs.lon == flux.destination[1]][0]].DEBUG_close_dropped_flux(f)
                del self.DEBUG_dropped_fluxes[[i for i, fl in enumerate(self.DEBUG_dropped_fluxes) if fl.alias_id == flux.alias_id][0]]

    def update_link_info(self, lat, lon, state, dir: Direction):
        self._links.get(dir).update(lat, lon, state)
        #self._reroute_all()
        #env.put(env.elapsed_time, self._reroute_all)
