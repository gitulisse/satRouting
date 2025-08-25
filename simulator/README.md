# Satellite routing simulator
This project simulates the routing of data through a network of satellites.

# Usage
You can launch a simulation using the following command:
```bash
python3 main.py --strategy 5 --duration 60 --traffic 20
```
The strategy parameter defines the routing strategy to simulate. The value should belong to one on this list:
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

The duration parameter specifies the duration of the simulation, in seconds.

The traffic parameter specifies the amount of traffic to be immitted into the satellite network each second, in Gbps.

All the parameters are optional, as they assume a default value if not defined.