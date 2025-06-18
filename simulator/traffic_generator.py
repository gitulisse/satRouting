import constants
import environment as env
from ground_station import GroundStation
import random
from skyfield.api import Timescale
from flow import Flow
from strategy import Strategy
import utils


class TrafficGenerator:
    def __init__(self, rate, duration, **kwargs): 
        self.source_gs = kwargs['source_gs'] if 'source_gs' in kwargs else None #optional param 
        self.destination_gs = kwargs['destination_gs'] if 'destination_gs' in kwargs else None #optional param
        self.delayed_start = kwargs['delayed_start'] if 'delayed_start' in kwargs else 0 #optional param
        self.duration = duration
        self.flow = Flow(random.randint(1, 1000000), rate, (self.destination_gs.lat, self.destination_gs.lon)) #generate the flow
        env.put(self.delayed_start, self._begin_generating) #start generating
        env.put(self.duration, self._end_generating) #stop generating
        
    #set the starting GS
    def set_source(self, gs: GroundStation):
        self.source_gs = gs

    #set the destination GS
    def set_destination(self, gs: GroundStation):
        self.destination_gs = gs
    
    #print names of all satellites in the paths
    def draw_flow_paths(self, flow):
        for path in flow.paths:
            print([sat.get_name() for sat in path]) #print every satellite in path
        #constants.drawing_queue.put(flow.paths)

    #start generating traffic
    def _begin_generating(self):
        print("\n -----|> Generating distributed flow", self.flow, self.flow.rate, "Gbps from", self.source_gs.get_name().upper(), "to", self.destination_gs.get_name().upper(), "for", self.duration, "seconds.")
        self.source_gs.send_flow(self.flow)

    #stop generating traffic
    def _end_generating(self):
        self.source_gs.close_outgoing_flow(self.flow) #close the flow outgoing
        end_time = utils.get_current_time() #set end_time
        source_gs_flow_info = self.source_gs.get_flow_info(self.flow, end_time, precision=1) #get flow info from source GS
        destination_gs_flow_info = self.destination_gs.get_flow_info(self.flow, end_time, precision=1) #get flow info from destination GS
        print(">> Sent", source_gs_flow_info[0]  / 10, "Gb from", self.source_gs.get_name(), "to", self.destination_gs.get_name())
        print("     Received", destination_gs_flow_info[1]  / 10, "Gb from", self.source_gs.get_name(), "to", self.destination_gs.get_name())
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
            
            print("         Totale satelliti con strutture flows occupate:", len(all_sats))
            print("         Totale flussi in giro:", len(set(all_ids)))
            
        #self.draw_flow_paths(flow) #draw the flow paths made by satellite sequela 