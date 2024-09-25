import constants
from direction import Direction
from flux import Flux
from ground_station import GroundStation
import utils

class Link:
    def __init__(self, parent_sat, capacity):
        self._parent = parent_sat
        self.target = None
        self.fluxes: dict[int, Flux] = {}
        self.capacity = capacity #Mbps

    def _set_target(self, target):
        self.target = target

    def is_active(self) -> bool:
        return self.target != None
    
    def get_available_bandwidth(self) -> float:
        return self.capacity - sum([flux.rate for flux in self.fluxes.values()])
    
    def send_flux(self, flux: Flux):
        if flux.alias_id not in self.fluxes.keys():
            raise RuntimeError("Resources needs to be reserved before sending flux " + str(flux.id) + " with alias id " + str(flux.alias_id))
        self.target.open_flux(flux.clone())

    def close_flux(self, flux: Flux):
        self.fluxes.pop(flux.alias_id)
        if constants.DEBUG:
            print("Closed flux", flux.id, "with alias id", flux.alias_id, "on Satellite", self._parent.get_name(), "headed to", self.target.get_name(), "with rate", flux.rate, "Mbps at time", utils.get_current_time().utc_strftime())
        self.target.close_flux(flux.clone())

    def reserve_bandwidth(self, flux: Flux) -> bool:
        if self.get_available_bandwidth() >= flux.rate:
            self.fluxes[flux.alias_id] = flux
            if constants.DEBUG:
                print("Reserved", flux.rate, "Mb for flux", flux.id, "with alias id", flux.alias_id, "at time", utils.get_current_time().utc_strftime())
            return True
        else:
            if constants.DEBUG:
                print("Failed to reserve", flux.rate, "Mb for flux", flux.id, "with alias id", flux.alias_id, "at time", utils.get_current_time().utc_strftime())
            return False

class LaserLink(Link):
    def __init__(self, parent_sat):
        super().__init__(parent_sat, constants.SATELLITE_LINK_CAPACITY)
        self.lat = None
        self.lon = None
        self.state = None

    def point_to_sat(self, sat) -> list[Flux]:
        leftovers = []
        while len(self.fluxes.values()) > 0:
            flux = list(self.fluxes.values())[0]
            leftovers.append(flux.clone())
            input_id = self._parent.mapping_table.remove(flux.alias_id)
            self._parent._close_internal_flux(flux.alias_id)
            leftovers[-1].alias_id = input_id
        self.lat = sat.get_latitude()
        self.lon = sat.get_longitude()
        self.state = 0.0
        self._set_target(sat)
        return leftovers
    
    def idle(self) -> list[Flux]:
        leftovers = []
        while len(self.fluxes.values()) > 0:
            flux = list(self.fluxes.values())[0]
            leftovers.append(flux.clone())
            input_id = self._parent.mapping_table.remove(flux.alias_id)
            self._parent._close_internal_flux(flux.alias_id)
            leftovers[-1].alias_id = input_id
        self._set_target(None)
        self.lat = None
        self.lon = None
        self.state = None
        return leftovers
    
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

    def attach_to_gs(self, gs):
        if not(self.target.__contains__(gs)):
            self.target.append(gs)

    def detach_from_all(self):
        leftovers = []
        while len(self.fluxes.values()) > 0:
            flux = list(self.fluxes.values())[0]
            leftovers.append(flux.clone())
            input_id = self._parent.mapping_table.remove(flux.alias_id)
            self._parent._close_internal_flux(flux.alias_id)
            leftovers[-1].alias_id = input_id
        for gs in self.target:
            self.target.remove(gs)
        return leftovers

    def get_attached_gs(self) -> list[GroundStation]:
        return self.target

    def send_flux(self, flux: Flux):
        if flux.alias_id not in self.fluxes.keys():
            raise RuntimeError("Resources needs to be reserved before sending flux " + str(flux.id) + " with alias id " + str(flux.alias_id))
        for gs in self.target:
            gs.open_flux(flux.clone())

    def close_flux(self, flux: Flux):
        self.fluxes.pop(flux.alias_id)
        for gs in self.target:
            if constants.DEBUG:
                print("Closed flux", flux.id, "with alias id", flux.alias_id, "on Satellite", self._parent.get_name(), "headed to", gs.get_name(), "with rate", flux.rate, "Mbps at time", utils.get_current_time().utc_strftime())
            gs.close_flux(flux.clone())
