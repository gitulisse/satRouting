# Satellite Routing Simulator - Documentation

## Overview

A discrete-event simulation framework for modeling and analyzing routing strategies in Low Earth Orbit (LEO) satellite constellations. The simulator supports multiple routing paradigms including distributed position-based routing and centralized source routing with load balancing capabilities.

---

## Core Architecture

### Simulation Paradigm

The simulator uses a **discrete-event simulation (DES)** model where:
- Time advances in discrete steps (simulated seconds)
- Events are scheduled in a priority queue ordered by timestamp
- The simulation loop processes events chronologically

**Key Files:** `environment.py`, `constants.py`

---

## File Reference

### Entry Points

#### `main.py`
**Purpose:** Main simulation entry point and configuration loader

**Key Functions:**
- `read_from_json(filename)` - Loads JSON configuration files
- `show_constellation_map(satellites, ground_stations, **kwargs)` - Visualizes satellite and ground station positions using Cartopy

**Configuration Flow:**
1. Parses command-line arguments (`--strategy`, `--duration`, `--traffic`, `--input`)
2. Initializes ground stations (Tokyo, New York, Dar Es Salaam, Buenos Aires)
3. Fetches satellite TLE/OMM data from Celestrak
4. Creates `Sat` objects for each satellite
5. Initializes `TrafficGenerator` or `HeaderBuilder` based on routing strategy
6. Launches simulation via `env.start()`

**Satellite Data Sources:**
- `--input 0`: Iridium-NEXT (TLE format)
- `--input 1`: Iridium-NEXT (JSON format)
- `--input 2`: Custom OMM JSON (user-provided URL, e.g., Starlink)

---

#### `constants.py`
**Purpose:** Global configuration and simulation parameters

**Key Constants:**

| Constant | Default | Description |
|----------|---------|-------------|
| `LATITUDE_CUTOFF` | 70 | Maximum latitude for ISL link creation |
| `SATELLITE_NEIGHBORS_UPDATE_TIME` | 10 | Interval for position/neighbor updates (simulated seconds) |
| `TOPOLOGY_UPDATE_TIME` | 30 | Interval for topology rebuilds |
| `SATELLITE_LINK_CAPACITY` | 1 Gbps | Inter-satellite link bandwidth |
| `GROUND_STATION_LINK_CAPACITY` | 1000 Gbps | Ground-to-satellite link bandwidth |
| `FLOW_TTL` | 31 | Maximum hops before flow expiration |
| `LOOP_AVOIDANCE_CUTOFF` | 9 | History length for loop detection |
| `TIME_MULTIPLIER` | 1 | Real-time scaling factor |

**Command-Line Arguments:**
- `--strategy (-s)`: Routing strategy ID (1-15)
- `--duration (-d)`: Simulation duration in seconds
- `--traffic (-t)`: Total traffic volume in Gbps
- `--input (-i)`: Satellite data format (0=TLE, 1=JSON, 2=Custom OMM)

---

### Core Simulation Objects

#### `satellite.py` - `Sat` Class
**Purpose:** Models individual satellites with routing, link management, and state tracking

**Attributes:**
- `_earth_satellite`: Skyfield `EarthSatellite` object for orbital propagation
- `_lat`, `_lon`: Current geographic coordinates (degrees)
- `_links`: Dict of 4 `LaserLink` objects (N/S/E/W directions)
- `_gs_link`: `RadioLink` for ground station communication
- `flows`: Active flows being forwarded
- `mapping_table`: `MappingTable` for flow ID translation
- `state`: Load state value (0.0-1.0)

**Key Methods:**
- `get_name()` → `int` - Returns satellite NORAD ID
- `get_latitude()`, `get_longitude()` → `float` - Current position
- `_update_position()` - Updates coordinates from orbital elements
- `_update_gs_link()` - Manages ground station attachment
- `update_neighbors()` - Broadcasts state to neighboring satellites
- `route(flow)` → `list[(RoutingAction, Flow, Link)]` - Computes next-hop decisions
- `open_flow(flow, routing_decisions)` - Initiates flow forwarding
- `send_flow(flow, link, routing_decisions)` - Transmits flow to next hop
- `drop_flow(flow, reason)` - Discards flow with specified reason
- `is_operational()` → `bool` - Checks if satellite has active links

**Routing Strategies Implemented:**
- Position Guessing (no LB, LB on saturated links, progressive LB)
- Position Sharing (no LB, LB on saturated links, progressive LB)
- Adaptive load balancing with one-hop and two-hop neighbor information

---

#### `ground_station.py` - `GroundStation` Class
**Purpose:** Models ground stations as traffic sources/sinks with centralized routing capabilities

**Attributes:**
- `lat`, `lon`: Geographic coordinates
- `name`: Station identifier
- `satellites`: Dict of visible satellites
- `outgoing_flows`: List of `(Flow, start_time, end_time)` tuples
- `incoming_flows`: Received flows with timing info
- `DEBUG_dropped_incoming_flows`: Dropped flow log
- `_graph`: NetworkX graph for path computation

**Key Methods:**
- `attach_to_sat(sat)` - Connects to serving satellite
- `send_flow(flow, routing_decisions)` - Injects flow into network
- `open_flow(flow)` - Processes arriving flows
- `close_outgoing_flow(flow)` - Terminates flow generation
- `close_flow(flow)` - Closes received flow
- `get_flow_info(flow, until, precision)` - Retrieves flow statistics
- `calculate_k_disjoint_paths(params)` - Computes K-shortest paths
- `process_routing_output(selected_path, flow)` - Converts path to routing actions

**Centralized Routing Methods:**
- `start_centralized_routing(flow, gss)` - Initiates source routing
- `build_graph()` - Constructs network topology graph
- `adapt_routing_decisions_to_available_link_bandwidth()` - Splits flows based on available bandwidth

---

#### `flow.py` - `Flow` Class
**Purpose:** Represents network traffic flows with routing state

**Attributes:**
- `id`: Unique flow identifier
- `rate`: Traffic rate (Gbps)
- `destination`: `(lat, lon)` tuple of target ground station
- `ttl`: Time-to-live (decremented per hop)
- `steps`: List of visited satellites
- `alias_id`: Local flow ID for mapping table
- `state`: `FlowState` enum value
- `travelled_distance`: Cumulative distance (km)

**Key Methods:**
- `add_step(sat)` - Records satellite visit, decrements TTL
- `drop_steps_from(sat)` - Removes path history for loop avoidance
- `split(rate)` → `(Flow, Flow)` - Divides flow into two rates
- `clone()` → `Flow` - Creates deep copy
- `get_steps()` → `list` - Returns path history

**FlowState Enum:**
- `NOT_DEFINED`, `DELIVERED`, `SATELLITE_CONGESTED`, `LINK_CONGESTED`, `EXPIRED_TTL`, `SATELLITE_NOT_OPERATIONAL`

---

#### `link.py` - Link Classes
**Purpose:** Models communication links between nodes

**`Link` (Base Class):**
- Attributes: `parent`, `target`, `flows`, `capacity`, `state`
- Methods: `is_active()`, `get_available_bandwidth()`, `reserve_bandwidth()`, `send_flow()`, `close_flow()`

**`LaserLink` (Inter-Satellite Links):**
- Attributes: `lat`, `lon` (target position), `state` (load info)
- Methods: `point_to_sat(sat)`, `idle()`, `update()`, `send_update()`, `unlink()`

**`RadioLink` (Ground-to-Satellite Links):**
- Attributes: `target` (list of `GroundStation`)
- Methods: `attach_to_gs(gs)`, `detach_from_all()`, `get_attached_gs()`

---

#### `direction.py` - `Direction` Enum
**Purpose:** Cardinal directions for satellite interconnects

**Values:** `NORTH`, `SOUTH`, `EAST`, `WEST`

---

#### `routing_action.py` - `RoutingAction` Enum
**Purpose:** Actions for routing decisions

**Values:**
- `FORWARD` - Send to next satellite
- `DELIVER` - Send to ground station
- `CLOSE` - Terminate flow
- `ERROR` - Routing failure
- `REOPEN` - Re-initiate routing

---

#### `mapping_table.py` - `MappingTable` Class
**Purpose:** Manages flow ID translation for multi-hop routing

**Attributes:**
- `table`: List of `(input_id, output_id)` tuples

**Key Methods:**
- `add(input_id)` → `int` - Creates new output ID
- `remove(local_id)` → `int` - Removes mapping, returns input ID
- `get_input_id(local_id)` → `int` - Reverse lookup
- `get_local_ids(input_id)` → `list[int]` - Forward lookup
- `contains_input_id(input_id)`, `contains_local_id(local_id)` - Existence checks

---

#### `strategy.py` - `Strategy` Enum
**Purpose:** Routing strategy identifiers

**Strategies:**

| ID | Name | Paradigm | Load Balancing |
|----|------|----------|----------------|
| 1 | `POSITION_GUESSING_NO_LB` | Distributed | No |
| 2 | `POSITION_GUESSING_LB_ON_SATURATED_LINK` | Distributed | On saturated links |
| 3 | `POSITION_GUESSING_PROGRESSIVE_LB` | Distributed | Progressive |
| 4 | `POSITION_SHARING_NO_LB` | Distributed | No |
| 5 | `POSITION_SHARING_LB_ON_SATURATED_LINK` | Distributed | On saturated links |
| 6 | `POSITION_SHARING_PROGRESSIVE_LB` | Distributed | Progressive |
| 7 | `POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB` | Distributed | Adaptive (1-hop) |
| 8 | `POSITION_AND_LOAD_STATE_SHARING_TWO_HOPS` | Distributed | Adaptive (2-hop) |
| 9 | `BASELINE_DIJKSTRA` | Centralized | No |
| 10 | `SOURCE_ROUTING_BY_HOP_NO_LB` | Centralized | No (min hops) |
| 11 | `SOURCE_ROUTING_BY_LENGTH_NO_LB` | Centralized | No (min distance) |
| 12 | `NODE_DISJOINT_SOURCE_ROUTING_LB` | Centralized | Yes (K=4 node-disjoint) |
| 13 | `EDGE_DISJOINT_SOURCE_ROUTING_LB` | Centralized | Yes (K=4 edge-disjoint) |
| 14 | `NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK` | Centralized | Link occupation |
| 15 | `EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING` | Centralized | Cost-based |

---

### Traffic Generation

#### `traffic_generator.py` - `TrafficGenerator` Class
**Purpose:** Generates continuous traffic flows for distributed routing strategies

**Attributes:**
- `source_gs`, `destination_gs`: Endpoint ground stations
- `duration`: Flow generation duration
- `flow`: `Flow` object

**Key Methods:**
- `_begin_generating()` - Starts flow injection
- `_end_generating()` - Stops flow and logs statistics

**Usage:** Strategies 1-8 (distributed paradigms)

---

#### `header_builder.py` - `HeaderBuilder` Class
**Purpose:** Generates traffic with centralized source routing

**Attributes:** Same as `TrafficGenerator`

**Key Methods:**
- `_begin_centralized_generation()` - Initiates source routing
- `_end_centralized_generation()` - Terminates and logs

**Usage:** Strategies 9-15 (centralized paradigms)

---

#### `gravity_model.py`
**Purpose:** External traffic matrix generation

**Function:**
- `get_traffic_matrix(cities: list[str])` → `dict`
  - Calls external API (`http://localhost:8001/traffic_matrix`)
  - Returns traffic distribution based on gravity model
  - Parameters: `total_volume_of_traffic`, `cities`

---

### Environment & Scheduling

#### `environment.py`
**Purpose:** Discrete-event simulation engine

**Global Variables:**
- `main_graph`: NetworkX graph of topology
- `satellites`, `ground_stations`: Simulation objects
- `actions_queue`: Priority queue of scheduled events
- `elapsed_time`: Current simulation time
- `_position_cache`, `_distance_cache`, `_graph_cache`: Performance caches

**`PriorityQueue` Class:**
- `put(priority, function, **kwargs)` - Schedules event
- `get()` - Retrieves next event
- `is_not_empty()`, `clear()`

**Key Functions:**
- `prepare()` - Schedules topology and position updates
- `start()` - Main simulation loop
- `reset()` - Resets simulation state
- `update_satellites_position()` - Updates all satellite coordinates
- `update_all_satellites_positions_and_neighbors()` - Combined update
- `topology_builder()` - Builds ISL topology using KDTree

**Topology Builder Algorithm:**
1. Filters satellites by latitude cutoff (±70°)
2. Builds KDTree from valid satellite coordinates
3. Queries neighbors within 5100km radius
4. Applies longitude-based link creation rules
5. Updates satellite link tables
6. Rebuilds NetworkX graph

---

#### `utils.py`
**Purpose:** Utility functions for geography, time, and flow management

**Key Functions:**

**Geographic:**
- `get_closer_satellites(satellites, position, operational_only)` → `list`
- `get_closest_satellite_for_graph(satellites, position)` → `tuple`
- `get_distance_between_satellites(sat1, sat2)` → `float` (km)
- `get_distance_between_satellite_and_gs(sat, gs)` → `float` (km, hypotenuse)
- `get_distance_between_earth_coordinates(coord1, coord2)` → `float` (km)

**Time Management:**
- `get_current_time()` → `Time` - Current simulation time
- `get_seconds_between(time1, time2)` → `int`
- `add_seconds_to_time(time, seconds)` → `Time`
- `get_sleep_delay(seconds)` → `float`

**Flow Management:**
- `create_new_flow(destination, rate)` → `Flow`
- `get_satellites_in_path(routing_decisions)` → `list`

**Data Sources:**
- `get_countries_population()` → `DataFrame`
- `get_countries_internet_penetration()` → `DataFrame`
- `get_countries_coordinates()` → `DataFrame`

**Other:**
- `get_coupled_link_direction(dir)` → `Direction` (opposite direction)
- `queuing_delay(queue_size, bandwidth)` → `float`
- `transmission_delay(packet_size, bandwidth)` → `float`
- `propagation_delay(position1, position2)` → `float` (seconds)

---

### Analysis & Visualization

#### `traffic_analyzer.py` - `TrafficAnalyzer` Class
**Purpose:** Metrics collection and analysis

**`AnalysisMetric` Enum:**
1. `COMPARISON_WITH_DIJKSTRA`
2. `AVERAGE_LINK_OCCUPATION`
3. `DELIVERED_DROPPED_RATIO`
4. `CONTROL_TRAFFIC_COMPARISON`
5. `WEIGHT_SENSITIVITY_ANALYSIS`
6. `TIME_PASSING_SIMULATION`

**Key Methods:**
- `analyze(metric)` - Runs analysis for specified metric
- `prepare_results_for_comparison()` - Sets up Dijkstra comparison
- `prepare_link_occupation_analysis()` - Configures link monitoring
- `prepare_delivered_dropped_ratio()` - Sets up delivery tracking
- `prepare_control_traffic_comparison()` - Monitors control overhead
- `prepare_weight_sensitivity_analysis()` - Tests LB weight factors
- `prepare_time_passing_simulation()` - Time-series analysis

---

#### `charts.py`
**Purpose:** Visualization of simulation results

**Functions:**
- `show_shortest_paths_table(results)` - Interactive table comparing strategies
- `show_average_link_occupation_chart(results)` - Link utilization over time
- `show_delivered_dropped_ratio_chart(results)` - Delivery success rates
- `show_control_traffic_comparison_chart(results)` - Control overhead comparison
- `show_weight_sensitivity_analysis_chart(results)` - LB parameter sensitivity
- `show_time_passing_simulation_chart(results)` - Time-series metrics

**Output:** Matplotlib and Plotly interactive visualizations

---

### Supporting Classes

#### `message.py` - `Message` Class
**Purpose:** Control message propagation (unused in current implementation)

**Attributes:** `lat`, `lon`, `message`, `is_link_update`, `steps`, `ttl`

---

#### `port_queue.py` - `PortQueue` Class
**Purpose:** Queue model for link ports (unused in current implementation)

**Attributes:** `queue`, `capacity`

---

## Simulation Workflow

### Initialization Phase

```
1. Parse command-line arguments
2. Initialize ground stations (4 default locations)
3. Fetch satellite TLE/OMM data from Celestrak
4. Create Sat objects (~66 for Iridium, ~10000 for Starlink)
5. Build initial topology (KDTree neighbor discovery)
6. Schedule periodic events:
   - Topology updates every 30s
   - Position updates every 10s
7. Create TrafficGenerator/HeaderBuilder instances
8. Call env.prepare()
```

### Execution Phase

```
while actions_queue not empty:
    1. Pop next event (priority = timestamp)
    2. Advance elapsed_time if needed
    3. Execute event function:
       - topology_builder(): Rebuild ISL graph
       - update_all_satellites_positions_and_neighbors(): Update positions
       - TrafficGenerator._begin_generating(): Start flow
       - TrafficGenerator._end_generating(): Stop flow
       - GroundStation.send_flow(): Inject traffic
       - Satellite.open_flow(): Route packet
    4. Log metrics
```

### Termination Phase

```
1. Process remaining events
2. Close all active flows
3. Aggregate statistics
4. Generate visualizations via TrafficAnalyzer
```

---

## Routing Strategy Details

### Distributed Paradigm (Strategies 1-8)

**Characteristics:**
- Each satellite makes independent routing decisions
- No global topology knowledge required
- Neighbors exchange position/load state periodically

**Position Guessing (1-3):**
- Satellites estimate neighbor positions based on orbital mechanics
- No explicit position sharing
- Selects next hop minimizing distance to destination

**Position Sharing (4-8):**
- Satellites broadcast actual positions to neighbors
- More accurate routing decisions
- Variants differ in load balancing approach

**Load Balancing Mechanisms:**
- **No LB:** Single best path
- **LB on Saturated Links:** Split flows when primary link congested
- **Progressive LB:** Gradually distribute across multiple paths
- **Adaptive LB:** Weight-based scoring using neighbor state

---

### Centralized Paradigm (Strategies 9-15)

**Characteristics:**
- Source ground station computes complete path
- Path embedded in flow header
- Satellites follow predetermined route

**Baseline Dijkstra (9):**
- Standard shortest path (hop count)

**Source Routing by Hop/Length (10-11):**
- Minimum hop count or geographic distance

**K-Disjoint Paths (12-15):**
- Computes 4 node/edge-disjoint paths
- Distributes traffic across paths
- Variants use different cost metrics

---

## Data Structures

### Caching System

**`_position_cache`:** Stores satellite coordinates per timestep

**`_distance_cache`:** Cached distances between satellite pairs
- Key: `(min_id, max_id)` tuple
- Value: Distance in km

**`_graph_cache`:** Cached NetworkX graph
- Keys: `edges`, `graph`

### Graph Structure

**NetworkX Graph (`main_graph`):**
- Nodes: Satellite names (NORAD IDs)
- Edges: Active ISLs
- Edge attributes: `available_bandwidth`, `weight`

---

## Performance Considerations

### Bottlenecks

1. **Topology Builder:** O(n log n) with KDTree, called every 30s
2. **Position Updates:** O(n) per satellite, every 10s
3. **Flow Routing:** Per-hop computation with loop avoidance checks
4. **Distance Calculations:** Cached but cleared each topology update

### Scalability

| Constellation | Satellites | Expected Runtime (60s sim) |
|---------------|------------|---------------------------|
| Iridium-NEXT | 66 | ~30 seconds |
| Starlink (subset) | 500 | ~5-10 minutes |
| Starlink (full) | 10000 | ~12-24 hours |

### Memory Usage

- **Per Satellite:** ~50 KB (links, flows, mapping table)
- **Per Flow:** ~2 KB (path history, metadata)
- **Graph:** O(E) where E = edges (~4 × satellites)
- **10K satellites:** ~500 MB estimated

---

## Error Handling

### Coordinate Validation

**`satellite._update_position()`:**
```python
if not (math.isfinite(lat.degrees) and math.isfinite(lon.degrees)):
    print("BAD SAT:", self.get_name(), lat, lon)
    return  # Prevents storing NaN coordinates
```

**`environment.topology_builder()`:**
```python
if lat is None or lon is None or not (math.isfinite(lat) and math.isfinite(lon)):
    print(f"Satellite {sat.get_name()} has invalid coordinates: {lat}, {lon}")
    continue  # Skip invalid satellites
```

### Flow Management

- **TTL Expiration:** Flows dropped after 31 hops
- **Loop Avoidance:** Last 9 visited satellites tracked
- **Bandwidth Exhaustion:** Flows split or dropped

---

## External Dependencies

### Python Packages

- `skyfield`: Orbital propagation (TLE/OMM parsing)
- `networkx`: Graph algorithms
- `scipy.spatial.KDTree`: Spatial indexing
- `geopy`: Geographic distance calculations
- `matplotlib`, `plotly`: Visualization
- `requests`: HTTP API calls
- `pandas`: Data manipulation
- `cartopy`: Map projections

### External Services

- **Celestrak:** Satellite TLE/OMM data
  - URL: `https://celestrak.org/NORAD/elements/gp.php`
  - Groups: `starlink`, `iridium-NEXT`

- **Gravity Model API:** Traffic matrix generation
  - URL: `http://localhost:8001/traffic_matrix`
  - Must be running locally

---

## Usage Examples

### Basic Simulation

```bash
# Position Sharing with LB on saturated links, 60s duration, 20 Gbps, Starlink
python3 main.py --strategy 5 --duration 60 --traffic 20 --input 2
# Enter URL: https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=json
```

### Analysis Metrics

```python
# In main.py, uncomment analysis lines:
traffic_analyzer = TrafficAnalyzer(ground_stations, satellites)
results = traffic_analyzer.analyze(AnalysisMetric.COMPARISON_WITH_DIJKSTRA)
charts.show_shortest_paths_table(results)
```

### Custom Ground Stations

```python
# In main.py, modify ground_stations dict:
ground_stations = {
    'LONDON': GroundStation(51.5074, -0.1278, 'London'),
    'SYDNEY': GroundStation(-33.8688, 151.2093, 'Sydney'),
    # ...
}
```

---

## Debugging

### Debug Mode

Set `DEBUG = True` in `constants.py` for verbose logging:
- Flow open/close events
- Satellite state updates
- Routing decisions
- Topology changes

### Common Issues

**ValueError: Point coordinates must be finite**
- Cause: Invalid TLE/OMM data producing NaN coordinates
- Fix: Code now filters invalid satellites (see Error Handling section)

**Simulation hangs indefinitely**
- Cause: Large constellation (10K+ satellites)
- Fix: Reduce satellite count or simulation duration

**Memory exhaustion**
- Cause: Too many satellites/flows
- Fix: Limit constellation size, reduce traffic volume

---

## File Dependencies

```
main.py
├── constants.py
├── environment.py
│   ├── utils.py
│   │   └── flow.py
│   ├── satellite.py
│   │   ├── link.py
│   │   │   └── flow.py
│   │   ├── mapping_table.py
│   │   └── routing_action.py
│   └── ground_station.py
│       ├── flow.py
│       └── dijkstra (imported)
├── traffic_generator.py / header_builder.py
│   └── flow.py
├── gravity_model.py
└── charts.py / traffic_analyzer.py
```

---

## Version Information

- **Python:** 3.10+ (uses match-case syntax)
- **Skyfield:** 1.46+ (supports `from_omm()`)
- **SciPy:** 1.11+ (KDTree API changes)
- **NetworkX:** 3.0+

---

## Contributing

### Adding New Routing Strategies

1. Add strategy to `Strategy` enum in `strategy.py`
2. Implement routing logic in `satellite.route()` (distributed) or `ground_station.calculate_k_disjoint_paths()` (centralized)
3. Update `main.py` to initialize appropriate traffic generators
4. Add analysis case in `traffic_analyzer.analyze()`

### Adding Metrics

1. Add metric to `AnalysisMetric` enum
2. Implement `prepare_*()` and `sample_*()` methods in `TrafficAnalyzer`
3. Add visualization in `charts.py`

---

## License

[Not specified in codebase]

## Authors

[Not specified in codebase]
