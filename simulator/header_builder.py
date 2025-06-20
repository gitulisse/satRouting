from flow import Flow, FlowState
from link import Link, LaserLink, RadioLink
from strategy import Strategy
import utils
import networkx as nx
import matplotlib.pyplot as plt
from routing_action import RoutingAction
#from ground_station import GroundStation
from geopy import distance
import environment as env
import random
from itertools import islice
from networkx.algorithms.flow import build_residual_network
from networkx.algorithms.connectivity import (
    build_auxiliary_node_connectivity,
    build_auxiliary_edge_connectivity,
)
from typing import Dict, List, Tuple, Self
from networkx.classes.function import path_weight
from mapping_table import MappingTable
import constants

class HeaderBuilder:
    def __init__(self, rate, duration, gss, **kwargs):
        self.source_gs = kwargs['source_gs'] if 'source_gs' in kwargs else None #optional param 
        self.destination_gs = kwargs['destination_gs'] if 'destination_gs' in kwargs else None #optional param
        self.delayed_start = kwargs['delayed_start'] if 'delayed_start' in kwargs else 0 #optional param
        self.duration = duration
        self.gss = gss #gss aka ground stations
        self.flow = Flow(random.randint(1, 1000000), rate, (self.destination_gs.lat, self.destination_gs.lon)) #generate the flow
        env.put(self.delayed_start, self._begin_centralized_generation) #start generating
        env.put(self.duration, self._end_centralized_generation) #stop generating

    def _begin_centralized_generation(self):
        print("\n-----> Generating from <<<", self.source_gs.get_name().upper(), "to", self.destination_gs.get_name().upper(), ">>> flow", self.flow, "with rate", self.flow.rate, "Gbps")
        self.source_gs.start_centralized_routing(self.flow, self.gss) #send the flow to the source GS
            
    def _end_centralized_generation(self):
        self.source_gs.close_outgoing_flow(self.flow) #close the flow outgoing
        end_time = utils.get_current_time() #set end_time
        source_gs_flow_info = self.source_gs.get_flow_info(self.flow, end_time, precision=1) #get flow info from source GS
        destination_gs_flow_info = self.destination_gs.get_flow_info(self.flow, end_time, precision=1) #get flow info from destination GS
        print(">> Sent", source_gs_flow_info[0] / 10, "Gb from", self.source_gs.get_name(), "to", self.destination_gs.get_name())
        print("     Received", destination_gs_flow_info[1] / 10, "Gb from", self.source_gs.get_name(), "to", self.destination_gs.get_name())
        print("         Lost", destination_gs_flow_info[2]  / 10, "Gb from", self.source_gs.get_name(), "to", self.destination_gs.get_name())
          
        if constants.DEBUG:
            all_ids = []
            all_sats = []
            for name, sat in self.source_gs.satellites.items():
                if sat.flows.values():
                    all_sats.append(name)
                    flows_leftovers_info = []
                    for f, _ in sat.flows.values():
                        all_ids.append(f.id)
                        if f.id == self.flow.id:
                            flows_leftovers_info.append((f.id, f.rate, f.alias_id, f.state))
                    #print("LEFTOVERRRRS", flows_leftovers_info)
                    if flows_leftovers_info:
                        print("Satellite", name, "has", len(flows_leftovers_info), "active flows. (flow from", self.source_gs.get_name(), "to", self.destination_gs.get_name(), ")")
                        print("Satellite", name, "mapping table:", sat.mapping_table.table)
                        for id, r, alias_id, state in flows_leftovers_info:
                            print(id, r, alias_id, state)
        
            print("             Totale satelliti con strutture flows occupate:", len(all_sats))
            print("             Totale flussi in giro:", len(set(all_ids)))

