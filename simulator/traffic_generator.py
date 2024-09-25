import constants
import environment as env
from ground_station import GroundStation
import random
from skyfield.api import Timescale
from flux import Flux
import utils

class TrafficGenerator:
    def __init__(self, rate, duration, **kwargs):
        self.source_gs = kwargs['source_gs'] if 'source_gs' in kwargs else None
        self.destination_gs = kwargs['destination_gs'] if 'destination_gs' in kwargs else None
        self.delayed_start = kwargs['delayed_start'] if 'delayed_start' in kwargs else 0
        self.duration = duration
        self.flux = Flux(random.randint(1, 1000000), rate, (self.destination_gs.lat, self.destination_gs.lon))
        env.put(self.delayed_start, self._begin_generating)
        env.put(self.duration, self._end_generating)

    def set_source(self, gs: GroundStation):
        self.source_gs = gs

    def set_destination(self, gs: GroundStation):
        self.destination_gs = gs
    
    def draw_flux_paths(self, flux):
        for path in flux.paths:
            print([sat.get_name() for sat in path])
        #constants.drawing_queue.put(flux.paths)

    def _begin_generating(self):
        print("Generating", self.flux.rate, "Mbps from", self.source_gs.get_name(), "to", self.destination_gs.get_name(), "for", self.duration, "seconds.")
        self.source_gs.send_flux(self.flux)

    def _end_generating(self):
        self.source_gs.close_outgoing_flux(self.flux)
        end_time = utils.get_current_time()
        source_gs_flux_info = self.source_gs.get_flux_info(self.flux, end_time, precision=1)
        destination_gs_flux_info = self.destination_gs.get_flux_info(self.flux, end_time, precision=1)
        print("Sent", source_gs_flux_info[0], "Mb from", self.source_gs.get_name(), "to", self.destination_gs.get_name())
        print("Received", destination_gs_flux_info[1], "Mb from", self.source_gs.get_name(), "to", self.destination_gs.get_name())
        print("Lost", destination_gs_flux_info[2], "Mb from", self.source_gs.get_name(), "to", self.destination_gs.get_name())

        if constants.DEBUG:
            all_ids = []
            all_sats = []
            for name, sat in self.source_gs.satellites.items():
                if sat.fluxes.values():
                    all_sats.append(name)
                    fluxes_leftovers_info = []
                    for f, _ in sat.fluxes.values():
                        all_ids.append(f.id)
                        if f.id == self.flux.id:
                            fluxes_leftovers_info.append((f.id, f.rate, f.alias_id, f.state))
                    if fluxes_leftovers_info:
                        print("Satellite", name, "has", len(fluxes_leftovers_info), "active fluxes. (flux from", self.source_gs.get_name(), "to", self.destination_gs.get_name(), ")")
                        print("Satellite", name, "mapping table:", sat.mapping_table.table)
                        for id, r, alias_id, state in fluxes_leftovers_info:
                            print(id, r, alias_id, state)

            print("Totale satelliti con strutture fluxes occupate:", len(all_sats))
            print("Totale flussi in giro:", len(set(all_ids)))
        
        #self.draw_flux_paths(flux)