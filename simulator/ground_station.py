import constants
from geopy import distance
from flux import Flux, FluxState
import math
from skyfield.api import Time, Timescale
from routing_action import RoutingAction
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
        self.outgoing_fluxes: list[Flux, Time, Time] = [] #Flusso, tempo di inizio invio e tempo di fine invio
        self.incoming_fluxes: list[Flux, Time, Time] = [] #Flusso, tempo di inizio ricezione e tempo di fine ricezione
        self.DEBUG_dropped_incoming_fluxes: list[(Flux, Time, Time)] = [] #Flusso, tempo di inizio ricezione, tempo di fine ricezione e causa drop
        self.keep_log = keep_log

    #set satellite
    def set_satellites(self, satellites):
        self.satellites = satellites

    #set GS
    def set_ground_stations(self, ground_stations: dict):
        self.gss = ground_stations
    
    #get latitude of GS
    def get_latitudeGS(self):
        return self.lat
    
    #get longitude of GS
    def get_longitudeGS(self):
        return self.lon
    
    #set serving population
    def add_population_to_serve(self, amount: int):
        self.serving_population += amount
   
    #connect GS to satellite
    def attach_to_sat(self, sat):
       #### print("ATTACHHHHHHHHHH")
        if sat != self.sat: #check if connected satellite is different from the current satellite (connected to GS) as param
            backup_fluxes = [] #copy of fluxes
            for outgoing_flux, _, end_time in self.outgoing_fluxes: #for the outgoing fluxes check that end_time is None to copy them
                if end_time == None:
                    backup_fluxes.append(outgoing_flux)
                    self.close_outgoing_flux(outgoing_flux) #close
            if self.sat != None: 
                self.sat.serving_gs = None #change attribute serving_gs of current satellite to None
            self.sat = sat #change of satellite that is serving the GS
            self.sat.serving_gs = self #connect to GS
            for backup_flux in backup_fluxes: 
                self.send_flux(backup_flux) #send copied fluxes

    #get name
    def get_name(self) -> str:
        return self.name

    #sender of fluxes from GS to connected satellite
    def send_centralized_flux(self, flux: Flux, routing_decisions):
        if routing_decisions:
            first_link = routing_decisions[0][2]  # extract link
            if hasattr(first_link, '_parent') and first_link._parent:
                self.sat = first_link._parent  #extraxt first satellite on the path
        self.outgoing_fluxes.append((flux, utils.get_current_time(), None))
        if constants.DEBUG:
           print("OPENING FLUX on GS -centralized-", flux, "id", flux.id, "with alias id", flux.alias_id, "from", self.get_name(), "with rate", flux.rate, "at time", utils.get_current_time().utc_strftime())
        flux.travelled_distance += utils.get_distance_between_satellite_and_gs(self.sat, self) #distance from source GS to first satellite
        #print("flux travelled distance to first Sat", flux.travelled_distance)
        #flux.add_all_centralized_steps(routing_decisions) 
        #####print("satellites in path",utils.get_satellites_in_path(routing_decisions)) #debug print
        #####print("flux steps", flux.get_steps()) #debug print
        self.sat.open_centralized_flux(flux.clone(), routing_decisions) #errore col clone
 
    #sender of fluxes from GS to connected satellite
    def send_flux(self, flux: Flux):
        self.outgoing_fluxes.append((flux, utils.get_current_time(), None)) #add an outgoing flux with current time, None is the time of termination of the flux
        if constants.DEBUG:
            print("OPENING FLUX on GS", flux.id, "with alias id", flux.alias_id, "from", self.get_name(), "with rate", flux.rate, "at time", utils.get_current_time().utc_strftime())
        flux.travelled_distance += utils.get_distance_between_satellite_and_gs(self.sat, self)
        self.sat.open_flux(flux.clone())

    #close the outgoing flux
    def close_outgoing_flux(self, flux: Flux):
        if self.keep_log:
            for i, (outgoing_flux, start_time, end_time) in enumerate(self.outgoing_fluxes):
                if flux == outgoing_flux and flux.alias_id == outgoing_flux.alias_id and flux.rate == outgoing_flux.rate and end_time == None:
                    self.outgoing_fluxes[i] = (outgoing_flux, start_time, utils.get_current_time())
                    #outgoing_flux.travelled_distance -= utils.get_distance_between_satellite_and_gs(self.sat, self)
                    outgoing_flux.travelled_distance = 0
                    '''
                    if constants.DEBUG:
                        print("Closed outgoing flux", flux.id, "with alias id", flux.alias_id, "from", self.get_name(), "with rate", flux.rate, "at time", utils.get_current_time().utc_strftime())
                    '''
                    break
        else:
            while self.outgoing_fluxes.__contains__(flux):
                self.outgoing_fluxes.remove(flux)
        self.sat.close_flux(flux.clone())

    def open_flux(self, flux: Flux): #apre il flux se è alla ground station di destinazione allora copia gli step in path e diventano il percorso attuato
        if flux.destination[0] == self.lat and flux.destination[1] == self.lon:
            flux.paths.append(flux.get_steps())
            flux.state = FluxState.DELIVERED
            self.incoming_fluxes.append((flux, utils.get_current_time(), None))
            '''
            if constants.DEBUG:
                print("Flux", flux.id, "with rate", flux.rate, "Mbps has reached its destination!", "at time", utils.get_current_time().utc_strftime())
                print("Steps:", [step.get_name() for step in flux.get_steps()])
            '''
        else:
            self._discard_flux(flux)
        
    def _discard_flux(self, flux: Flux):
        if constants.DEBUG:
            print("Flux with id", flux.id, "has been discarded on gs", self.get_name())

    def close_flux(self, flux: Flux):
        if self.keep_log:
            for i, (incoming_flux, start_time, end_time) in enumerate(self.incoming_fluxes):
                if flux == incoming_flux and flux.alias_id == incoming_flux.alias_id and flux.rate == incoming_flux.rate and end_time == None:
                    self.incoming_fluxes[i] = (incoming_flux, start_time, utils.get_current_time())
                    '''
                    if constants.DEBUG:
                        print("Closed incoming flux", flux.id, "with alias id", flux.alias_id, "from", self.get_name(), "with rate", flux.rate, "at time", utils.get_current_time().utc_strftime())
                    '''
                    break
        else:
            while self.incoming_fluxes.__contains__(flux):
                self.incoming_fluxes.remove(flux)

    def is_incoming_flux_alive(self, flux: Flux):
        for incoming_flux, _, end_time in self.incoming_fluxes:
            if flux == incoming_flux:
                if end_time == None:
                    return True
        return False

    def get_flux_info(self, flux: Flux, until: Time, precision: int = 0) -> tuple[float, float, float]:
        total_data_received = 0
        total_data_sent = 0
        total_data_dropped = 0
        flux.paths = []
        sum_travelled_distance = 0 #km
        incoming_fluxes_count = 0
        for incoming_flux, start_time, end_time in self.incoming_fluxes:
            if flux == incoming_flux:
                if end_time == None or until - end_time < 0:
                    end_time = until
                active_time_in_seconds = utils.get_seconds_between(start_time, end_time)
                if active_time_in_seconds >= precision:
                    total_data_received += active_time_in_seconds * incoming_flux.rate
                    flux.paths.append(incoming_flux.get_steps())
                    sum_travelled_distance += incoming_flux.travelled_distance
                    incoming_fluxes_count += 1 
                    '''
                    #debug 
                    if constants.DEBUG:
                        print(total_data_received, utils.get_seconds_between(start_time, end_time) * incoming_flux.rate, "incoming for", utils.get_seconds_between(start_time, end_time), "from", start_time.utc_strftime(), "to", end_time.utc_strftime(), "at rate", incoming_flux.rate, "with alias id", incoming_flux.alias_id)
                        print([sat.get_name() for sat in incoming_flux.get_steps()])
                    '''
        if incoming_fluxes_count > 0:
            flux.travelled_distance = sum_travelled_distance / incoming_fluxes_count
            if constants.DEBUG or not(constants.DEBUG):
                print("Average distance travelled by flux", flux.id, "in kms:", flux.travelled_distance)
        for outgoing_flux, start_time, end_time in self.outgoing_fluxes:
            if flux == outgoing_flux:
                if end_time == None or until - end_time < 0:
                    end_time = until
                active_time_in_seconds = utils.get_seconds_between(start_time, end_time)
                if active_time_in_seconds >= precision:
                    total_data_sent += active_time_in_seconds * outgoing_flux.rate
        for dropped_flux, start_time, end_time in self.DEBUG_dropped_incoming_fluxes:
            if flux == dropped_flux:
                if end_time == None or until - end_time < 0:
                    end_time = until
                active_time_in_seconds = utils.get_seconds_between(start_time, end_time)
                if active_time_in_seconds >= precision:
                    total_data_dropped += active_time_in_seconds * dropped_flux.rate
                    #Escluso in modo tale da memorizzare solo i path a buon fine nel flux
                    #flux.paths.append(dropped_flux.get_steps())
                    '''
                    if constants.DEBUG:
                        print(total_data_dropped, utils.get_seconds_between(start_time, end_time) * dropped_flux.rate, "dropped for", utils.get_seconds_between(start_time, end_time), "from", start_time.utc_strftime(), "to", end_time.utc_strftime(), "at rate", dropped_flux.rate, "with alias id", dropped_flux.alias_id, "reason", dropped_flux.state)
                        print([sat.get_name() for sat in dropped_flux.get_steps()])
                    '''
        # Stampa tutti i percorsi del flusso
        #print("\nPercorsi per il flusso", flux.id, ":")
        #for idx, path in enumerate(flux.paths):
         #   print(f"Path {idx + 1}: {[sat.get_name() for sat in path]}")
        return (total_data_sent, total_data_received, total_data_dropped)
        
    def DEBUG_get_dropped_flux(self, flux: Flux):
        flux.paths.append(flux.get_steps())
        self.DEBUG_dropped_incoming_fluxes.append((flux, utils.get_current_time(), None))
        '''
        if constants.DEBUG:
            print("Logged opening of dropped flux", flux.id, "with rate", flux.rate, "Mbps at time", utils.get_current_time().utc_strftime())
            print("Steps:", [step.get_name() for step in flux.get_steps()])
        '''
  
    def DEBUG_close_dropped_flux(self, flux: Flux):
        if self.keep_log:
            for i, (dropped_flux, start_time, end_time) in enumerate(self.DEBUG_dropped_incoming_fluxes):
                if flux == dropped_flux and flux.alias_id == dropped_flux.alias_id and flux.rate == dropped_flux.rate and end_time == None:
                    self.DEBUG_dropped_incoming_fluxes[i] = (dropped_flux, start_time, utils.get_current_time())
                    '''
                    if constants.DEBUG:
                        print("Logged closing of dropped flux", flux.id, "with rate", flux.rate, "Mbps at time", utils.get_current_time().utc_strftime())
                        print("Steps:", [step.get_name() for step in flux.get_steps()])
                    '''
                    break
        else:
            while self.DEBUG_dropped_incoming_fluxes.__contains__(flux):
                self.DEBUG_dropped_incoming_fluxes.remove(flux)

    def reattach(self):
        ####print("REEEEEEEEEEATTACH")
        distances = utils.get_closer_satellites(self.satellites, (self.lat, self.lon), False)
        new_sat = self.satellites.get(distances[0]['name'])
        '''
        if constants.DEBUG:
            if new_sat != self.sat:
                print("Attaching Ground Station", self.get_name(), "to Satellite", new_sat.get_name(), "at time", utils.get_current_time().utc_strftime())
        '''
        self.attach_to_sat(new_sat)