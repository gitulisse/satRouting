import constants
from direction import Direction
from flow import Flow
from ground_station import GroundStation
import utils
from strategy import Strategy

class Link:
    def __init__(self, parent_sat, capacity):
        self._parent = parent_sat
        self.target = None
        self.flows: dict[int, Flow] = {}
        self.capacity = capacity #Gbps

    def reset_bandwidth(self):
        self.flows.clear()
        self.available_bandwidth = self.capacity

    #set attribute target
    def _set_target(self, target):
        self.target = target

    #check if Link is active (if it has a target)
    def is_active(self) -> bool:
        return self.target != None
    
    def reset_bandwidth(self):
        self.flows.clear()

    #calculate remaining available bandwidth
    def get_available_bandwidth(self) -> float:
        #print("Available Bandwidth", self.capacity - sum([flow.rate for flow in self.flows.values()]))
        return self.capacity - sum([flow.rate for flow in self.flows.values()])
    
    #send flows 
    def send_flow(self, flow: Flow, routing_decisions=None):
        #print("sendflow link base class")
        if flow.alias_id not in self.flows.keys(): #if alias_id isn't in flows keys raise error
            raise RuntimeError("Resources needs to be reserved before sending flow " + str(flow.id) + " with alias id " + str(flow.alias_id))
        if routing_decisions is None or isinstance(self.target, GroundStation): #if routing_decisions is None or target is a GroundStation
            self.target.open_flow(flow.clone()) #cloned flow sent to target
        else:
            self.target.open_flow(flow.clone(), routing_decisions) #cloned flow sent to target

    #close flows
    def close_flow(self, flow: Flow):
        self.flows.pop(flow.alias_id) #remove flow id
        '''
        if constants.DEBUG:
            print("Closed flow", flow.id, "with alias id", flow.alias_id, "on Satellite", self._parent.get_name(), "headed to", self.target.get_name(), "with rate", flow.rate, "Gbps at time", utils.get_current_time().utc_strftime())
        '''
        self.target.close_flow(flow.clone()) #cloned flow sent to target will be closed by the target
    
    #store flows, bandwidth is already reserved
    def reserve_centralized_bandwidth(self, flow: Flow) -> bool:
        self.flows[flow.alias_id] = flow #store flow in flows using alias_id as key
        target_name = (self.target[0].get_name() 
                if isinstance(self.target, list) and self.target 
                else self.target.get_name())
        print("For link", self._parent.get_name(), "-", target_name, "Already Reserved bandwidth centralized", flow.rate, "Gb, for flow", flow.id, "with alias id", flow.alias_id, "at time", utils.get_current_time().utc_strftime())
        return True
    
    #manage reservation of bandwidth for a specified Flow
    def reserve_bandwidth(self, flow: Flow) -> bool:
        #print("Reserve bandwidth....")
        if self.get_available_bandwidth() >= flow.rate: #the remaining capacity is calculated as the normal capacity minus the sum of all flows' rate in self.flows
            self.flows[flow.alias_id] = flow #store flow in flows using alias_id as key
            target_name = (self.target[0].get_name() 
                if isinstance(self.target, list) and self.target 
                else self.target.get_name())

            #print("Reserving for link", self._parent.get_name(), "-", target_name, "Reserved bandwidth", flow.rate, "Gb, for flow", flow.id, "with alias id", flow.alias_id, "at time", utils.get_current_time().utc_strftime()) #"remaining capacity", self.capacity
            return True
        else:
            #print("Reserving for link", self._parent.get_name(), "-", target_name, "Failed to reserve", flow.rate, "Gb, for flow", flow.id, "with alias id", flow.alias_id, "at time", utils.get_current_time().utc_strftime())
            return False
    '''
    #check bandwidth availability without reserve it
    def search_available_bandwidth(self) -> float:
        temp_capacity = self.capacity
        temp_capacity -= sum([flow.rate for flow in self.flows.values()])
        print ("Actual Capacity", temp_capacity)
        return temp_capacity
    '''

#Laserlink between satellites
class LaserLink(Link):
    def __init__(self, parent_sat):
        super().__init__(parent_sat, constants.SATELLITE_LINK_CAPACITY)
        self.lat = None
        self.lon = None
        self.state = None

    #maintain trace of the leftover flows & redirect the LaserLink
    def point_to_sat(self, sat) -> list[Flow]:
        leftovers = [] #residual flows
        #print(f"Flowes: {self.flows}")
        while len(self.flows.values()) > 0: #if there are flows
            print("Flowes in point_to_sat", self.flows)##########
            flow = list(self.flows.values())[0] #take first value of flows
            print(f"first flow is.. {flow} id {flow.id} alias_id {flow.alias_id}")##########
            leftovers.append(flow.clone()) #add this flow to leftovers
            print(f"leftovers list: {leftovers}")
            input_id = self._parent.mapping_table.remove(flow.alias_id) #remove flow id from parent mapping table & save it as input_id
            print(f"input:id: {input_id}")
            self._parent._close_internal_flow(flow.alias_id) #close the flow internal to parent satellite
            leftovers[-1].alias_id = input_id #set the input of the last inserted flow in leftovers
        self.lat = sat.get_latitude() #lat
        self.lon = sat.get_longitude() #lon
        self.state = 0.0 #state
        self._set_target(sat) #set new target satellite
        return leftovers 
    
    #put link in idle state
    def idle(self) -> list[Flow]:
        print(f"Link {self._parent.get_name()} -> {self.target.get_name()} going idle with flows: {self.flows}")##########
        leftovers = []
        while len(self.flows.values()) > 0:
            flow = list(self.flows.values())[0]
            if constants.ROUTING_STRATEGY in [Strategy.BASELINE_DIJKSTRA,
                                    Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                    Strategy.KSHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                    Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING,
                                    Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                    Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING,
                                    Strategy.LENGTH_SHORTEST_NODE_DISJOINT_SOURCE_ROUTING_WITH_LB,
                                    Strategy.KSHORTEST_EDGE_DISJOINT_SOURCE_ROUTING_WITH_COSTS_SELECTION]:
                #print(f"IDLE FLOW ID {flow.id} & Alias id {flow.alias_id} on parent Mapping Table {self._parent.mapping_table.table}")
                #if flow.alias_id not in self._parent.mapping_table.table:
                 #   print(f"Skipping invalid alias_id -centralized-: {flow.alias_id}")
                  #  return
                leftovers.append(flow.clone())
                input_id = self._parent.mapping_table.remove(flow.alias_id)
                self._parent._close_internal_flow(flow.alias_id)
                leftovers[-1].alias_id = input_id
            else:
                #if flow.alias_id not in self._parent.mapping_table.table:
                 #   print(f"Skipping invalid alias_id -distributed-: {flow.alias_id}")
                  #  return
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

    #send the update to a target(if active)
    def send_update(self, lat, lon, state, dir: Direction):
        if self.is_active():
            self.target.update_link_info(lat, lon, state, dir)

    #remove the link of a target with the specified direction(dir)
    def unlink(self, dir: Direction):
        if self.is_active():
            self.target.remove_link(dir, False)

#RadioLink between Ground Station and satellite
class RadioLink(Link):
    def __init__(self, parent_sat):
        super().__init__(parent_sat, constants.GROUND_STATION_LINK_CAPACITY)
        self.target: list[GroundStation] = []  #maybe a list as target for radiolink can be trivial

    #attach link to GS
    def attach_to_gs(self, gs):
        if not(self.target.__contains__(gs)): #if the GS isn't already in the target list of the link
            self.target.append(gs) #add to list

    #disconnect link from GS
    def detach_from_all(self):
        leftovers = [] #residual flows
        while len(self.flows.values()) > 0: #if there are flows
            flow = list(self.flows.values())[0] #take first value of flows
            leftovers.append(flow.clone()) #add cloned flow to leftovers
            input_id = self._parent.mapping_table.remove(flow.alias_id) #remove id from parent table and store id value in input_id
            self._parent._close_internal_flow(flow.alias_id) #close internal flow in parent
            leftovers[-1].alias_id = input_id #set the input of the last inserted flow in leftovers
        for gs in self.target: 
            self.target.remove(gs) #every GS in self.target is removed
        return leftovers

    #get the self.target list of GS connected to RadioLink
    def get_attached_gs(self) -> list[GroundStation]:
        return self.target

    #send flow
    def send_flow(self, flow: Flow, routing_decisions=None):
        # print("sendflow radiolink")
        if flow.alias_id not in self.flows.keys(): #if id isn't among the keys of flows return error
            raise RuntimeError("Resources needs to be reserved before sending flow " + str(flow.id) + " with alias id " + str(flow.alias_id))
        for gs in self.target:
            gs.open_flow(flow.clone())


    #close flow
    def close_flow(self, flow: Flow):
        self.flows.pop(flow.alias_id) #remove flow using id
        for gs in self.target:
            '''
            #debug
            if constants.DEBUG:
                print("Closed flow", flow.id, "with alias id", flow.alias_id, "on Satellite", self._parent.get_name(), "headed to", gs.get_name(), "with rate", flow.rate, "Gbps at time", utils.get_current_time().utc_strftime())
            '''
            gs.close_flow(flow.clone()) #every GS in self.target close the flow
            