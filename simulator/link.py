import constants
from direction import Direction
from flow import Flow
from ground_station import GroundStation
import utils
from strategy import Strategy
import environment as env

class Link:
    def __init__(self, parent_sat, capacity):
        self._parent = parent_sat
        self.target = None
        self.flows: dict[int, Flow] = {}
        self.capacity = capacity #Gbps

    def _set_target(self, target):
        self.target = target

    def is_active(self) -> bool:
        return self.target != None

    #calculate remaining available bandwidth
    def get_available_bandwidth(self) -> float:
        return self.capacity - sum([flow.rate for flow in self.flows.values()])
    
    #send flows 
    def send_flow(self, flow: Flow, routing_decisions=None):
        if flow.alias_id not in self.flows.keys():
            raise RuntimeError("Resources needs to be reserved before sending flow " + str(flow.id) + " with alias id " + str(flow.alias_id))
        if routing_decisions == None or isinstance(self.target, GroundStation):
            self.target.open_flow(flow.clone())
        else:
            self.target.open_flow(flow.clone(), routing_decisions)

    #close flows
    def close_flow(self, flow: Flow):
        self.flows.pop(flow.alias_id) #remove flow id
        #if constants.DEBUG:
            #print("Closed flow on general link", flow.id, "with alias id", flow.alias_id, "on Satellite", self._parent.get_name(), "headed to", self.target.get_name(), "with rate", flow.rate) # "Gbps at time", utils.get_current_time().utc_strftime())
        self.target.close_flow(flow.clone())         
        alpha = 0.5
        measured_utilization = 1 - self.get_available_bandwidth() / self.capacity
        self.state = alpha * measured_utilization + (1 - alpha) * self.state
    
    #manage reservation of bandwidth
    def reserve_bandwidth(self, flow: Flow) -> bool:
        if self.get_available_bandwidth() >= flow.rate:
            self.flows[flow.alias_id] = flow
            self.state = 1 - self.get_available_bandwidth() / self.capacity
            if constants.ROUTING_STRATEGY in [Strategy.SOURCE_ROUTING_BY_HOP_NO_LB, 
                                              Strategy.SOURCE_ROUTING_BY_LENGTH_NO_LB,
                                              Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
                                              Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                              Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,
                                              Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING]:
                target_name = (self.target[0].get_name() 
                    if isinstance(self.target, list) and self.target 
                    else self.target.get_name())

                if isinstance(target_name, str):
                    target_name = target_name.upper()

                env.main_graph[self._parent.get_name()][target_name]['available_bandwidth'] = self.get_available_bandwidth()
                print(f"[DEBUG] Updated bandwidth on graph: {self._parent.get_name()} <-> {target_name} now {env.main_graph[self._parent.get_name()][target_name]['available_bandwidth']} Gbps")
            return True
        else:
            return False

class LaserLink(Link):
    def __init__(self, parent_sat):
        super().__init__(parent_sat, constants.SATELLITE_LINK_CAPACITY)
        self.lat = None
        self.lon = None
        self.state = None

    def point_to_sat(self, sat) -> list[Flow]:
        leftovers = []
        while len(self.flows.values()) > 0:
            flow = list(self.flows.values())[0]
            leftovers.append(flow.clone())
            input_id = self._parent.mapping_table.remove(flow.alias_id)
            self._parent._close_internal_flow(flow.alias_id)
            leftovers[-1].alias_id = input_id
        self.lat = sat.get_latitude()
        self.lon = sat.get_longitude()
        self.state = 0.0
        self._set_target(sat)
        return leftovers 
    
    #put link in idle state
    def idle(self) -> list[Flow]:
        leftovers = []
        while len(self.flows.values()) > 0:
            flow = list(self.flows.values())[0]
            if constants.ROUTING_STRATEGY in [Strategy.SOURCE_ROUTING_BY_HOP_NO_LB,
                                              Strategy.SOURCE_ROUTING_BY_LENGTH_NO_LB,
                                              Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
                                              Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
                                              Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,
                                              Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING]:
                leftovers.append(flow.clone())
                input_id = self._parent.mapping_table.remove(flow.alias_id)
                self._parent._close_internal_flow(flow.alias_id)
                leftovers[-1].alias_id = input_id
            else:
                leftovers.append(flow.clone())
                input_id = self._parent.mapping_table.remove(flow.alias_id)
                self._parent._close_internal_flow(flow.alias_id)
                leftovers[-1].alias_id = input_id
        self._set_target(None)
        self.lat = None
        self.lon = None
        self.state = None
        return leftovers
    
    #update coordinates and state
    def update(self, lat, lon, state):
        self.lat = lat
        self.lon = lon
        self.state = state

    def send_update(self, lat, lon, state, dir: Direction):
        if self.is_active():
            self.target.update_link_info(lat, lon, state, dir)

    def unlink(self, dir: Direction):
        if self.is_active():
            self.target.remove_link(dir, False)

class RadioLink(Link):
    def __init__(self, parent_sat):
        super().__init__(parent_sat, constants.GROUND_STATION_LINK_CAPACITY)
        self.target: list[GroundStation] = []
        self.state = 0.0

    #connect link to GS
    def attach_to_gs(self, gs):
        if not(self.target.__contains__(gs)):
            self.target.append(gs)

    #disconnect link from GS
    def detach_from_all(self):
        leftovers = []
        while len(self.flows.values()) > 0:
            flow = list(self.flows.values())[0]
            leftovers.append(flow.clone())
            input_id = self._parent.mapping_table.remove(flow.alias_id)
            self._parent._close_internal_flow(flow.alias_id)
            leftovers[-1].alias_id = input_id
        for gs in self.target:
            self.target.remove(gs)
        return leftovers

    def get_attached_gs(self) -> list[GroundStation]:
        return self.target

    #send flow
    def send_flow(self, flow: Flow, routing_decisions=None):
        if flow.alias_id not in self.flows.keys():
            raise RuntimeError("Resources needs to be reserved before sending flow " + str(flow.id) + " with alias id " + str(flow.alias_id))
        for gs in self.target:
            gs.open_flow(flow.clone())


    #close flow
    def close_flow(self, flow: Flow):
        self.flows.pop(flow.alias_id)
        self.state = 1 - self.get_available_bandwidth() / self.capacity 
        for gs in self.target:
            #if constants.DEBUG:
                #print("Closed flow on radiolink", flow.id, "with alias id", flow.alias_id, "on Satellite", self._parent.get_name(), "headed to", gs.get_name(), "with rate", flow.rate) # "Gbps at time", utils.get_current_time().utc_strftime())
            gs.close_flow(flow.clone()) #every GS in self.target close the flow
