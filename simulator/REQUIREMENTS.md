# Satellite Routing Simulator - Execution Requirements by Algorithm

## CLI Parameters Overview

The simulator is launched via command-line arguments defined in `constants.py`:

```bash
python main.py -s <strategy> -d <duration> -t <traffic> -i <input_format>
```

| Parameter | Flag | Type | Description |
|-----------|------|------|-------------|
| `--strategy` | `-s` | `int` | Routing strategy ID (1-15) |
| `--duration` | `-d` | `int` | Simulation duration in seconds (default: 60) |
| `--traffic` | `-t` | `int` | Total traffic volume in Gbps (default: 10) |
| `--input` | `-i` | `int` | Satellite format: 0=Iridium NEXT, 1=OneWeb, other=custom OMM URL |

---

## Routing Strategies and Required Classes

### Group 1: Position Guessing Strategies (Decentralized)
**Traffic Generator:** `TrafficGenerator`  
**Used by strategies:** 1, 2, 3

| Strategy ID | Strategy Name | Constant | Key Classes Used |
|-------------|---------------|----------|------------------|
| 1 | Position Guessing No LB | `POSITION_GUESSING_NO_LB` | `TrafficGenerator`, `Flow`, `Sat`, `GroundStation` |
| 2 | Position Guessing LB on Saturated Link | `POSITION_GUESSING_LB_ON_SATURATED_LINK` | `TrafficGenerator`, `Flow`, `Sat`, `GroundStation`, `Link` |
| 3 | Position Guessing Progressive LB | `POSITION_GUESSING_PROGRESSIVE_LB` | `TrafficGenerator`, `Flow`, `Sat`, `GroundStation`, `Link` |

**Core classes involved:**
- `traffic_generator.TrafficGenerator` - Generates traffic flows
- `flow.Flow` - Represents network flow with rate, destination, state
- `satellite.Sat` - Satellite node with routing logic
- `ground_station.GroundStation` - Ground station with flow management
- `link.Link` / `LaserLink` / `RadioLink` - Communication links

---

### Group 2: Position Sharing Strategies (Decentralized)
**Traffic Generator:** `TrafficGenerator`  
**Used by strategies:** 4, 5, 6, 7, 8

| Strategy ID | Strategy Name | Constant | Key Classes Used |
|-------------|---------------|----------|------------------|
| 4 | Position Sharing No LB | `POSITION_SHARING_NO_LB` | `TrafficGenerator`, `Flow`, `Sat`, `GroundStation` |
| 5 | Position Sharing LB on Saturated Link | `POSITION_SHARING_LB_ON_SATURATED_LINK` | `TrafficGenerator`, `Flow`, `Sat`, `GroundStation`, `Link` |
| 6 | Position Sharing Progressive LB | `POSITION_SHARING_PROGRESSIVE_LB` | `TrafficGenerator`, `Flow`, `Sat`, `GroundStation`, `Link` |
| 7 | Position and Load State Sharing Adaptive LB | `POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB` | `TrafficGenerator`, `Flow`, `Sat`, `GroundStation`, `Link`, `MappingTable` |
| 8 | Position and Load State Sharing Two Hops | `POSITION_AND_LOAD_STATE_SHARING_TWO_HOPS` | `TrafficGenerator`, `Flow`, `Sat`, `GroundStation`, `Link`, `MappingTable` |

**Core classes involved:**
- `traffic_generator.TrafficGenerator` - Generates traffic flows
- `flow.Flow` - Represents network flow with rate, destination, state
- `satellite.Sat` - Satellite node with neighbor state sharing
- `ground_station.GroundStation` - Ground station with flow management
- `link.Link` / `LaserLink` / `RadioLink` - Communication links
- `mapping_table.MappingTable` - Routing table for next-hop decisions (strategies 7, 8)

---

### Group 3: Source Routing Strategies (Centralized)
**Traffic Generator:** `HeaderBuilder`  
**Used by strategies:** 9, 10, 11, 12, 13, 14, 15

| Strategy ID | Strategy Name | Constant | Key Classes Used |
|-------------|---------------|----------|------------------|
| 9 | Baseline Dijkstra | `BASELINE_DIJKSTRA` | `HeaderBuilder`, `Flow`, `GroundStation`, `nx.Graph` |
| 10 | Source Routing by Hop No LB | `SOURCE_ROUTING_BY_HOP_NO_LB` | `HeaderBuilder`, `Flow`, `GroundStation`, `nx.Graph` |
| 11 | Source Routing by Length No LB | `SOURCE_ROUTING_BY_LENGTH_NO_LB` | `HeaderBuilder`, `Flow`, `GroundStation`, `nx.Graph` |
| 12 | Node Disjoint Source Routing LB | `NODE_DISJOINT_SOURCE_ROUTING_LB` | `HeaderBuilder`, `Flow`, `GroundStation`, `nx.Graph`, `MappingTable` |
| 13 | Edge Disjoint Source Routing LB | `EDGE_DISJOINT_SOURCE_ROUTING_LB` | `HeaderBuilder`, `Flow`, `GroundStation`, `nx.Graph`, `MappingTable` |
| 14 | Node Disjoint Source Routing LB on Saturated Link | `NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK` | `HeaderBuilder`, `Flow`, `GroundStation`, `nx.Graph`, `MappingTable`, `Link` |
| 15 | Edge Disjoint Source Routing Cost Balancing | `EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING` | `HeaderBuilder`, `Flow`, `GroundStation`, `nx.Graph`, `MappingTable`, `Link` |

**Core classes involved:**
- `header_builder.HeaderBuilder` - Builds routing headers for centralized routing
- `flow.Flow` - Represents network flow with rate, destination, state
- `ground_station.GroundStation` - Ground station with centralized routing logic
- `satellite.Sat` - Satellite node executing pre-computed paths
- `link.Link` / `LaserLink` / `RadioLink` - Communication links with cost/occupation
- `mapping_table.MappingTable` - Stores pre-computed paths (strategies 12-15)
- `networkx.Graph` - Graph structure for path computation

---

## Class Dependency Summary

### Always Required (All Strategies)
| Class | Module | Purpose |
|-------|--------|---------|
| `Flow` | `flow` | Network flow representation |
| `Sat` | `satellite` | Satellite entity |
| `GroundStation` | `ground_station` | Ground station entity |
| `Strategy` | `strategy` | Strategy enumeration |

### Required by Decentralized Strategies (1-8)
| Class | Module | Purpose |
|-------|--------|---------|
| `TrafficGenerator` | `traffic_generator` | Flow generation with start/end events |

### Required by Centralized Strategies (9-15)
| Class | Module | Purpose |
|-------|--------|---------|
| `HeaderBuilder` | `header_builder` | Centralized path computation and header creation |

### Conditionally Required
| Class | Module | Used By Strategies | Purpose |
|-------|--------|-------------------|---------|
| `MappingTable` | `mapping_table` | 7, 8, 12, 13, 14, 15 | Next-hop routing table |
| `Link` (occupation tracking) | `link` | 2, 3, 5, 6, 7, 8, 14, 15 | Link state/cost management |

---

## Execution Examples

```bash
# Position Guessing with Load Balancing on Saturated Links (Strategy 5)
python main.py -s 5 -d 60 -t 10 -i 0

# Source Routing by Hop Count (Strategy 10)
python main.py -s 10 -d 120 -t 20 -i 1

# Edge Disjoint Source Routing with Cost Balancing (Strategy 15)
python main.py -s 15 -d 60 -t 15 -i 0
```

---

## Supporting Classes (Infrastructure)

| Class | Module | Purpose |
|-------|--------|---------|
| `TrafficAnalyzer` | `traffic_analyzer` | Metrics collection and analysis |
| `AnalysisMetric` | `traffic_analyzer` | Metric type enumeration |
| `RoutingAction` | `routing_action` | Routing decision actions |
| `utils` | `utils` | Time handling, Skyfield integration |
| `env` (environment) | `environment` | Simulation environment (SimPy-based) |

---

## Notes

- **Strategy Selection:** The `ROUTING_STRATEGY` constant determines which traffic generator class is instantiated:
  - Strategies 1-8 → `TrafficGenerator` instances
  - Strategies 9-15 → `HeaderBuilder` instances

- **Satellite Format (`-i` parameter):**
  - `0` = Iridium NEXT constellation (NORAD TLE)
  - `1` = OneWeb constellation (JSON format)
  - Other = Custom OMM JSON URL (user input required)

- **Default Strategy:** If no `-s` argument is provided, defaults to `POSITION_SHARING_LB_ON_SATURATED_LINK` (Strategy 5)
