import constants
import environment as env
from ground_station import GroundStation
import random
from skyfield.api import Timescale
from flux import Flux
import utils

class TrafficGenerator:
    def __init__(self, rate, duration, **kwargs):
        self.source_gs = kwargs['source_gs'] if 'source_gs' in kwargs else None #optional param 
        self.destination_gs = kwargs['destination_gs'] if 'destination_gs' in kwargs else None #optional param
        self.delayed_start = kwargs['delayed_start'] if 'delayed_start' in kwargs else 0 #optional param
        self.duration = duration
        self.flux = Flux(random.randint(1, 1000000), rate, (self.destination_gs.lat, self.destination_gs.lon)) #generate the flux
        env.put(self.delayed_start, self._begin_generating) #start generating
        env.put(self.duration, self._end_generating) #stop generating

    #set the starting GS
    def set_source(self, gs: GroundStation):
        self.source_gs = gs

    #set the destination GS
    def set_destination(self, gs: GroundStation):
        self.destination_gs = gs
    
    #print names of all satellites in the paths
    def draw_flux_paths(self, flux):
        for path in flux.paths:
            print([sat.get_name() for sat in path]) #print every satellite in path
        #constants.drawing_queue.put(flux.paths)

    #start generating traffic
    def _begin_generating(self):
        print("Generating", self.flux.rate, "Mbps from", self.source_gs.get_name(), "to", self.destination_gs.get_name(), "for", self.duration, "seconds.")
        self.source_gs.send_flux(self.flux)

    #stop generating traffic
    def _end_generating(self):
        self.source_gs.close_outgoing_flux(self.flux) #close the flux otugoing
        end_time = utils.get_current_time() #set end_time
        source_gs_flux_info = self.source_gs.get_flux_info(self.flux, end_time, precision=1) #get flux info from source GS
        destination_gs_flux_info = self.destination_gs.get_flux_info(self.flux, end_time, precision=1) #get flux info from destination GS
        print("Sent", source_gs_flux_info[0], "Mb from", self.source_gs.get_name(), "to", self.destination_gs.get_name())
        print("Received", destination_gs_flux_info[1], "Mb from", self.source_gs.get_name(), "to", self.destination_gs.get_name())
        print("Lost", destination_gs_flux_info[2], "Mb from", self.source_gs.get_name(), "to", self.destination_gs.get_name())

        #debug
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
        
        #self.draw_flux_paths(flux) #draw the flux paths made by satellite sequela 