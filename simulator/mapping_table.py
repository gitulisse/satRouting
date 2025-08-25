import constants
from random import randint
import sys

class MappingTable:
    def __init__(self):
        self.table: list[(int, int)] = []
    
    #create an output_id connected to input_id passed as param
    def add(self, input_id: int) -> int:
        out_id = self._create_new_out_id()
        self.table.append((input_id, out_id)) 
        #if constants.DEBUG:      
         #   print(f"Added pair ({input_id}, {out_id}) to mapping table")
        return out_id

    def remove(self, local_id: int) -> int:
        for in_id, out_id in self.table:
            if out_id == local_id:
                self.table.remove((in_id, out_id))
                #if constants.DEBUG:
                 #   print(f"Removed pair ({in_id}, {out_id}) from mapping table")
                return in_id
        else:
            print(f"[ERROR] Attempt to remove local_id not present: {local_id}")
            #print(f"[ERROR] Current state of table mapping_table: {self.table}")
            raise RuntimeError("No mapping found for local_id: " + str(local_id))

    def contains_input_id(self, input_id: int) -> bool:
        try:
            self.get_local_ids(input_id)
        except RuntimeError:
            return False
        else:
            return True
    
    def contains_local_id(self, local_id: int) -> bool:
        try:
            self.get_input_id(local_id)
        except RuntimeError:
            return False
        else:
            return True

    def get_input_id(self, local_id: int) -> int:
        for in_id, out_id in self.table:
            if out_id == local_id:
                return in_id
        else:
            raise RuntimeError("No input_id found for local_id " + str(local_id))

    def get_local_ids(self, input_id: int) -> list[int]:
        occurrencies = []
        for in_id, out_id in self.table:
            if in_id == input_id:
                occurrencies.append(out_id)
        return occurrencies

    #create output_id
    def _create_new_out_id(self) -> int:
        out_id = randint(0, sys.maxsize) #new randomized output_id
        return out_id if out_id not in [id for (_, id) in self.table] else self._create_new_out_id()