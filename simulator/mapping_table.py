import constants
from random import randint
import sys

class MappingTable:
    def __init__(self):
        self.table: list[(int, int)] = [] #associates input_id, output_id
    
    #create an output_id connected to input_id passed as param
    def add(self, input_id: int) -> int:
        out_id = self._create_new_out_id() #output_id
        self.table.append((input_id, out_id)) 
        '''
        #debug
        if constants.DEBUG:      
            print(f"Added pair ({input_id}, {out_id}) to mapping table")
        '''
        #print(f"Added mapping: {input_id} -> {out_id}")
        return out_id

    def remove(self, local_id: int) -> int:
        for in_id, out_id in self.table:
            if out_id == local_id:
                self.table.remove((in_id, out_id))
                #if constants.DEBUG:
                 #   print(f"Removed pair ({in_id}, {out_id}) from mapping table")
                return in_id
        else:
            print(f"[ERRORE] Tentativo di rimuovere local_id non presente: {local_id}")
            print(f"[ERRORE] Stato attuale della tabella mapping_table: {self.table}")
            raise RuntimeError("No mapping found for local_id: " + str(local_id))

    #check if input_id is in table to get output_id
    def contains_input_id(self, input_id: int) -> bool:
        try:
            self.get_local_ids(input_id)
        except RuntimeError:
            return False
        else:
            return True
    
    #check if local_id is in table to get input_id
    def contains_local_id(self, local_id: int) -> bool:
        try:
            self.get_input_id(local_id)
        except RuntimeError:
            return False
        else:
            return True

    #get the input_id associated with current output_id
    def get_input_id(self, local_id: int) -> int:
        for in_id, out_id in self.table:
            if out_id == local_id:
                return in_id
        else:
            raise RuntimeError("No input_id found for local_id " + str(local_id))

    #get the List of output_id(S) associated with current input_id
    def get_local_ids(self, input_id: int) -> list[int]:
        occurrencies = []
        for in_id, out_id in self.table:
            if in_id == input_id:
                occurrencies.append(out_id)
        return occurrencies

    #create output_id
    def _create_new_out_id(self) -> int:
        out_id = randint(0, sys.maxsize) #new randomized output_id
        return out_id if out_id not in [id for (_, id) in self.table] else self._create_new_out_id() #return out_id if out_id is not in the list of output_id in self.table ELSE recursion
    