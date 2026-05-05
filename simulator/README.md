# Satellite routing simulator
This project simulates the routing of data through a network of satellites.

# Usage
You can launch a simulation using the following command:
```bash
python3 main.py --strategy 5 --duration 60 --traffic 20
```

### Parameters
- `--strategy (-s)`: Routing strategy ID (1-15)
- `--duration (-d)`: Simulation duration in seconds
- `--traffic (-t)`: Total traffic volume in Gbps
- `--input (-i)`: Satellite data format (0=TLE, 1=JSON, 2=Custom/Local File)
- `--gs-config`: Path to ground stations YAML config
- `--sat-file`: Path to local satellite JSON file
- `--analyze`: Run a specific analysis (dijkstra, link_occupation, delivery_ratio, control_traffic, weight_sensitivity, time_passing)
- `--plot`: Path to a JSON file to visualize results without re-running the simulation

### Strategies List
- 1: Position guessing without load balancing
- 2: Position guessing with load balancing on saturated link
- 3: Position guessing with progressive load balancing
- 4: Position sharing without load balancing
- 5: Position sharing with load balancing on saturated link
- 6: Position sharing with progressive load balancing
- 7: Position and load state sharing with adaptive load balancing
- 8: Position and load state sharing with two-hop adaptive load balancing
- 9: Baseline Dijkstra
- 10: Hop-based source routing without load balancing
- 11: Length-based source routing without load balancing
- 12: Node disjoint source routing with load balancing
- 13: Edge disjoint source routing with load balancing
- 14: Node disjoint source routing with saturation aware load balancing
- 15: Edge disjoint source routing with costs load balancing

### Examples
```bash
# Run a specific analysis
python3 main.py --analyze dijkstra

# Plot existing results
python3 main.py --analyze dijkstra --plot my_results.json
```

All the parameters are optional, as they assume a default value if not defined.