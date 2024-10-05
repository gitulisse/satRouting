import constants
from geopy import distance
from flux import Flux, FluxState
import math
from skyfield.api import Time, Timescale
import utils

class GroundStation:
    def __init__(self, lat, lon, name, keep_log: bool = True) -> None:
        self.lat = lat
        self.lon = lon
        self.sat = None
        self.serving_population = 0
        self.name = name
        self.satellites = None
        self.gss = None
        self.outgoing_fluxes: list[Flux, Time, Time] = []  #Flusso, tempo di inizio invio e tempo di fine invio
        self.incoming_fluxes: list[Flux, Time, Time] = [] #Flusso, tempo di inizio ricezione e tempo di fine ricezione
        self.DEBUG_dropped_incoming_fluxes: list[(Flux, Time, Time)] = [] #Flusso, tempo di inizio ricezione, tempo di fine ricezione e causa drop
        self.keep_log = keep_log

    #set satellite
    def set_satellites(self, satellites):
        self.satellites = satellites

    #set GS
    def set_ground_stations(self, ground_stations: dict):
        self.gss = ground_stations
    
    #set serving population
    def add_population_to_serve(self, amount: int):
        self.serving_population += amount
    
    #connect GS to satellite
    def attach_to_sat(self, sat):
        if sat != self.sat: #check if connected satellite is different from the current satellite as param
            backup_fluxes = [] #copy of fluxes
            for outgoing_flux, _, end_time in self.outgoing_fluxes: #for the outgoing fluxes check that end_time is None to copy them
                if end_time == None:
                    backup_fluxes.append(outgoing_flux)
                    self.close_outgoing_flux(outgoing_flux) #close
            if self.sat != None: 
                self.sat.serving_gs = None #change attribute serving_gs of current satellite to None
            self.sat = sat #change of satellite
            self.sat.serving_gs = self #connect to GS
            for backup_flux in backup_fluxes: 
                self.send_flux(backup_flux) #send copied fluxes

    #get name
    def get_name(self) -> str:
        return self.name

    #sender of fluxes from GS to connected satellite
    def send_flux(self, flux: Flux):
        self.outgoing_fluxes.append((flux, utils.get_current_time(), None)) #add an outgoing flux with current time, None is the time of termination of the flux
        #debug
        if constants.DEBUG:
            print("Opening flux", flux.id, "with alias id", flux.alias_id, "from", self.get_name(), "with rate", flux.rate, "at time", utils.get_current_time().utc_strftime())
        
        flux.travelled_distance += utils.get_distance_between_satellite_and_gs(self.sat, self) #update the attribute travelled_distance
        self.sat.open_flux(flux.clone()) #open cloned flux

    #close the outgoing flux
    def close_outgoing_flux(self, flux: Flux):
        if self.keep_log: #if keep_log is True maintain logs
            for i, (outgoing_flux, start_time, end_time) in enumerate(self.outgoing_fluxes): #for all fluxes going out
                if flux == outgoing_flux and flux.alias_id == outgoing_flux.alias_id and flux.rate == outgoing_flux.rate and end_time == None: #search the flux id equal to the outgoing flux and same flux rate (and not ended)
                    self.outgoing_fluxes[i] = (outgoing_flux, start_time, utils.get_current_time()) #set the end_time
                    #outgoing_flux.travelled_distance -= utils.get_distance_between_satellite_and_gs(self.sat, self)
                    outgoing_flux.travelled_distance = 0 #reset distance to 0
                    #debug
                    if constants.DEBUG:
                        print("Closed outgoing flux", flux.id, "with alias id", flux.alias_id, "from", self.get_name(), "with rate", flux.rate, "at time", utils.get_current_time().utc_strftime())
                    break
        else:
            while self.outgoing_fluxes.__contains__(flux):
                self.outgoing_fluxes.remove(flux) #close flux without saving logs
        self.sat.close_flux(flux.clone()) #after closing, send a copy of flux to satellite to remove it even there

    #open flux
    def open_flux(self, flux: Flux):
        if flux.destination[0] == self.lat and flux.destination[1] == self.lon: #verify if flux is at destination
            flux.paths.append(flux.get_steps()) #save the travelled path
            flux.state = FluxState.DELIVERED #change state to DELIVERED
            self.incoming_fluxes.append((flux, utils.get_current_time(), None)) #add to incoming_fluxes, saving start time
            #debug
            if constants.DEBUG:
                print("Flux", flux.id, "with rate", flux.rate, "Mbps has reached its destination!", "at time", utils.get_current_time().utc_strftime())
                print("Steps:", [step.get_name() for step in flux.get_steps()])
        else:
            self._discard_flux(flux) #if NOT at destination the flux is discarded

    #discard flux (only says if the flux is discarded during debug mode)
    def _discard_flux(self, flux: Flux):
        #debug
        if constants.DEBUG:
            print("Flux with id", flux.id, "has been discarded on gs", self.get_name())

    #close flux
    def close_flux(self, flux: Flux):
        if self.keep_log: #if keep_log is True maintain logs
            for i, (incoming_flux, start_time, end_time) in enumerate(self.incoming_fluxes): #for all fluxes coming in
                if flux == incoming_flux and flux.alias_id == incoming_flux.alias_id and flux.rate == incoming_flux.rate and end_time == None:
                    self.incoming_fluxes[i] = (incoming_flux, start_time, utils.get_current_time()) #set the end_time
                    #debug
                    if constants.DEBUG:
                        print("Closed incoming flux", flux.id, "with alias id", flux.alias_id, "from", self.get_name(), "with rate", flux.rate, "at time", utils.get_current_time().utc_strftime())
                    break
        else:
            while self.incoming_fluxes.__contains__(flux): 
                self.incoming_fluxes.remove(flux) #close flux without saving logs

    #verify that incoming fluxes are active
    def is_incoming_flux_alive(self, flux: Flux):
        for incoming_flux, _, end_time in self.incoming_fluxes: #check all incoming fluxes
            if flux == incoming_flux:
                if end_time == None: #if the incoming flux doesn't have an end_time it's already active
                    return True
        return False

    #retrieve flux information
    def get_flux_info(self, flux: Flux, until: Time, precision: int = 0) -> tuple[float, float, float]:
        total_data_received = 0
        total_data_sent = 0
        total_data_dropped = 0
        flux.paths = [] 
        sum_travelled_distance = 0 #km travelled
        incoming_fluxes_count = 0

        #cycle incoming fluxes
        for incoming_flux, start_time, end_time in self.incoming_fluxes:
            if flux == incoming_flux: #if current flux equal to flux in list incoming_flux
                if end_time == None or until - end_time < 0: #current until time as param
                    end_time = until
                active_time_in_seconds = utils.get_seconds_between(start_time, end_time) #seconds from start to end
                if active_time_in_seconds >= precision: #current precision as param
                    total_data_received += active_time_in_seconds * incoming_flux.rate #data received
                    flux.paths.append(incoming_flux.get_steps()) #path
                    sum_travelled_distance += incoming_flux.travelled_distance
                    incoming_fluxes_count += 1 
                    #debug
                    if constants.DEBUG:
                        print(total_data_received, utils.get_seconds_between(start_time, end_time) * incoming_flux.rate, "incoming for", utils.get_seconds_between(start_time, end_time), "from", start_time.utc_strftime(), "to", end_time.utc_strftime(), "at rate", incoming_flux.rate, "with alias id", incoming_flux.alias_id)
                        print([sat.get_name() for sat in incoming_flux.get_steps()])

        if incoming_fluxes_count > 0:
            flux.travelled_distance = sum_travelled_distance / incoming_fluxes_count #mean distance travelled per fluxes
            #debug
            if constants.DEBUG or not(constants.DEBUG):
                print("Average distance travelled by flux", flux.id, "in kms:", flux.travelled_distance)
        
        #cycle outgoing fluxes
        for outgoing_flux, start_time, end_time in self.outgoing_fluxes:
            if flux == outgoing_flux:
                if end_time == None or until - end_time < 0:
                    end_time = until
                active_time_in_seconds = utils.get_seconds_between(start_time, end_time)
                if active_time_in_seconds >= precision:
                    total_data_sent += active_time_in_seconds * outgoing_flux.rate #data sent
        
        #cycle dropped incoming fluxes
        for dropped_flux, start_time, end_time in self.DEBUG_dropped_incoming_fluxes:
            if flux == dropped_flux:
                if end_time == None or until - end_time < 0:
                    end_time = until
                active_time_in_seconds = utils.get_seconds_between(start_time, end_time)
                if active_time_in_seconds >= precision:
                    total_data_dropped += active_time_in_seconds * dropped_flux.rate

                    #Excluded so that only successful paths are stored in the flow
                    #flux.paths.append(dropped_flux.get_steps())

                    #debug
                    if constants.DEBUG:
                        print(total_data_dropped, utils.get_seconds_between(start_time, end_time) * dropped_flux.rate, "dropped for", utils.get_seconds_between(start_time, end_time), "from", start_time.utc_strftime(), "to", end_time.utc_strftime(), "at rate", dropped_flux.rate, "with alias id", dropped_flux.alias_id, "reason", dropped_flux.state)
                        print([sat.get_name() for sat in dropped_flux.get_steps()])
        return (total_data_sent, total_data_received, total_data_dropped)

    #add dropped fluxes
    def DEBUG_get_dropped_flux(self, flux: Flux):
        flux.paths.append(flux.get_steps())
        self.DEBUG_dropped_incoming_fluxes.append((flux, utils.get_current_time(), None)) #None for end_time cause the flux is still active
        #debug
        if constants.DEBUG:
            print("Logged opening of dropped flux", flux.id, "with rate", flux.rate, "Mbps at time", utils.get_current_time().utc_strftime())
            print("Steps:", [step.get_name() for step in flux.get_steps()])

    #manage closing dropped fluxes
    def DEBUG_close_dropped_flux(self, flux: Flux):
        if self.keep_log: #if keep_log attribute True
            for i, (dropped_flux, start_time, end_time) in enumerate(self.DEBUG_dropped_incoming_fluxes):
                if flux == dropped_flux and flux.alias_id == dropped_flux.alias_id and flux.rate == dropped_flux.rate and end_time == None:
                    self.DEBUG_dropped_incoming_fluxes[i] = (dropped_flux, start_time, utils.get_current_time()) #set end_time of the fluxes
                    #debug
                    if constants.DEBUG:
                        print("Logged closing of dropped flux", flux.id, "with rate", flux.rate, "Mbps at time", utils.get_current_time().utc_strftime())
                        print("Steps:", [step.get_name() for step in flux.get_steps()])
                    break
        else:
            while self.DEBUG_dropped_incoming_fluxes.__contains__(flux): 
                self.DEBUG_dropped_incoming_fluxes.remove(flux) #remove

    #attach the GS to closest satellite
    def reattach(self):
        distances = utils.get_closer_satellites(self.satellites, (self.lat, self.lon), False) # increasing distances to closer satellite
        new_sat = self.satellites.get(distances[0]['name'])  #closest satellite accessing through its name
        #debug
        if constants.DEBUG:
            if new_sat != self.sat:
                print("Attaching Ground Station", self.get_name(), "to Satellite", new_sat.get_name(), "at time", utils.get_current_time().utc_strftime())
        self.attach_to_sat(new_sat) #attach to new closest satellite