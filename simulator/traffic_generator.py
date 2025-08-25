import environment as env
from ground_station import GroundStation
import random
from skyfield.api import Timescale
from flow import Flow
from strategy import Strategy
import utils


class TrafficGenerator:
    def __init__(self, rate, duration, **kwargs): 
        self.source_gs = kwargs['source_gs'] if 'source_gs' in kwargs else None
        self.destination_gs = kwargs['destination_gs'] if 'destination_gs' in kwargs else None
        self.delayed_start = kwargs['delayed_start'] if 'delayed_start' in kwargs else 0
        self.duration = duration
        self.flow = Flow(random.randint(1, 1000000), rate, (self.destination_gs.lat, self.destination_gs.lon))
        env.put(self.delayed_start, self._begin_generating)
        env.put(self.duration, self._end_generating)
        
    def set_source(self, gs: GroundStation):
        self.source_gs = gs

    def set_destination(self, gs: GroundStation):
        self.destination_gs = gs
    
    def draw_flow_paths(self, flow):
        for path in flow.paths:
            print([sat.get_name() for sat in path])

    def _begin_generating(self):
        print("\n-----> Generating from <<<", self.source_gs.get_name().upper(), "to", self.destination_gs.get_name().upper(), ">>> flow", self.flow, "ID", self.flow.id, "alias", self.flow.alias_id, "with rate", self.flow.rate, "Gbps")
        self.source_gs.send_flow(self.flow)

    def _end_generating(self):
        self.source_gs.close_outgoing_flow(self.flow)
        end_time = utils.get_current_time()
        source_gs_flow_info = self.source_gs.get_flow_info(self.flow, end_time, precision=1)
        destination_gs_flow_info = self.destination_gs.get_flow_info(self.flow, end_time, precision=1)
        print(">> Sent", source_gs_flow_info[0], "Gb from", self.source_gs.get_name(), "to", self.destination_gs.get_name())
        print("     Received", destination_gs_flow_info[1], "Gb from", self.source_gs.get_name(), "to", self.destination_gs.get_name())
        print("         Lost", destination_gs_flow_info[2], "Gb from", self.source_gs.get_name(), "to", self.destination_gs.get_name())

        for name, sat in self.source_gs.satellites.items():
            flows_to_remove = [
                flow_id for flow_id, (f, link) in sat.flows.items()
                if f.id == self.flow.id and getattr(f, "end_time", None) is None
            ]
            for flow_id in flows_to_remove:
                f, _ = sat.flows.pop(flow_id, None)

        control = True
        if control:
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
                    if flows_leftovers_info:
                        print("Satellite", name, "has", len(flows_leftovers_info), "active flows. (flow from", self.source_gs.get_name(), "to", self.destination_gs.get_name(), ")")
                        print("Satellite", name, "mapping table:", sat.mapping_table.table)
                        for id, r, alias_id, state in flows_leftovers_info:
                            print(f"+ Flow id {id}, rate {r}, alias_id {alias_id}, state {state}")
            
            print("         Totale satelliti con strutture flows occupate:", len(all_sats))
            print("         Totale flussi in giro:", len(set(all_ids)))
