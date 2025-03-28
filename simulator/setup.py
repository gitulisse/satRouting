from setuptools import Extension, setup
from Cython.Build import cythonize

#Custom file encoding in C-like files to improve perfomances
extensions = Extension("simulator", [
                                "constants.py", 
                                "direction.py", 
                                "environment.py", 
                                "flow.py", 
                                "gravity_model.py", 
                                "ground_station.py", 
                                "header_builder.py",
                                "link.py",
                                "main.py", 
                                "mapping_table.py",
                                "message.py",
                                "port_queue.py",
                                "routing_action.py",
                                "satellite.py",
                                "strategy.py",
                                "traffic_analyzer.py",
                                "traffic_generator.py",
                                "utils.py"])

setup(
    ext_modules=cythonize(extensions, language_level=3)
)