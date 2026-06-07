"""
Starlink Subset Simulation Runner

This script runs the satellite routing simulator using a filtered subset of the 
Starlink constellation. It provides options to reduce the ~10,000 satellite 
constellation to a manageable size for faster simulation while maintaining 
realistic coverage.

Key Features:
- Filters satellites by orbital inclination (main 53° shell)
- Random sampling to reduce constellation size
- Initial visibility check for ground stations
- Configurable subset size via command-line argument

Usage:
    python3 starlink_main.py --strategy 5 --duration 60 --traffic 20 --subset-size 500
"""

import charts
import constants
from gravity_model import get_traffic_matrix
from ground_station import GroundStation
import environment as env
import json
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import numpy as np
import random
import requests
from satellite import Sat
from skyfield.api import load, EarthSatellite
from traffic_analyzer import AnalysisMetric, TrafficAnalyzer
from header_builder import HeaderBuilder
from traffic_generator import TrafficGenerator
import utils
from strategy import Strategy
from itertools import chain
import sys
import argparse

# Avoid crashes due to unlimited recursion
sys.setrecursionlimit(10000)

# ============================================================================
# Configuration
# ============================================================================

# Starlink data source
STARLINK_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=json"

# Orbital shell filter - main Starlink shell has ~53° inclination
INCLINATION_MIN = 50.0
INCLINATION_MAX = 56.0

# Default subset size (balance between realism and runtime)
DEFAULT_SUBSET_SIZE = 1000

# Excluded satellites (known problematic TLEs/OMM data)
EXCLUDED_SATNUMS = set()

# ============================================================================
# Ground Stations
# ============================================================================

utils.ts = load.timescale()

# Ground Stations selected for the simulation
# All within the coverage area of Starlink's 53° inclination shell
ground_stations = {
    'TOKYO': GroundStation(35.689506, 139.6917, 'Tokyo'),
    'NEW YORK': GroundStation(40.71277778, -74.00611111, 'New York'),
    'DAR ES SALAAM': GroundStation(-6.816111, 39.280278, 'Dar Es Salaam'),
    'BUENOS AIRES': GroundStation(-34.608333, -58.371944, 'Buenos Aires')
}

# ============================================================================
# Visualization
# ============================================================================

def show_constellation_map(satellites: list, ground_stations: list, **kwargs):
    """Display constellation map with satellite and ground station positions."""
    def draw_map(ax):
        ax.add_feature(cfeature.LAND, color='lightgray')
        ax.add_feature(cfeature.OCEAN, color='lightblue')
        ax.add_feature(cfeature.COASTLINE, edgecolor='black')
        ax.add_feature(cfeature.BORDERS, linestyle=':')
        gridlines = ax.gridlines(draw_labels=True, linewidth=0.5, color='gray', 
                                  alpha=0.7, linestyle='--')
        gridlines.xlabels_top = gridlines.ylabels_right = False
    
    plt.figure(figsize=(8, 6))
    ax = plt.axes(projection=ccrs.PlateCarree())
    ax.set_global()
    ax.set_extent([-180, 180, -90, 90], crs=ccrs.PlateCarree())

    draw_map(ax)

    for gs in ground_stations:
        x = gs.lon
        y = gs.lat
        plt.plot(x, y, 'or', markersize=10, transform=ccrs.PlateCarree())
        plt.text(x - 5, y + 3, str(gs.get_name()), fontsize=9, 
                 fontweight='bold', color='red', transform=ccrs.PlateCarree())

    plt.title("Starlink Constellation Map")
    plt.show()


def check_initial_visibility(satellites, ground_stations):
    """
    Check which ground stations have satellite coverage at simulation start.
    
    Prints visibility report for debugging constellation coverage.
    """
    from geopy import distance
    
    print("\n" + "="*60)
    print("INITIAL SATELLITE VISIBILITY CHECK")
    print("="*60)
    
    visible_count = {gs.get_name(): 0 for gs in ground_stations.values()}
    
    for sat in satellites.values():
        lat = sat.get_latitude()
        lon = sat.get_longitude()
        if lat is None or lon is None:
            continue
        for gs in ground_stations.values():
            dist = distance.distance((lat, lon), (gs.lat, gs.lon)).km
            if dist < constants.SATELLITE_COVERAGE_AREA_RADIUS:
                visible_count[gs.get_name()] += 1
    
    all_covered = True
    for gs_name, count in visible_count.items():
        status = "✓" if count > 0 else "✗ NO COVERAGE"
        if count == 0:
            all_covered = False
        print(f"  {gs_name:20s}: {count:4d} satellites {status}")
    
    print("="*60)
    
    if not all_covered:
        print("\n⚠ WARNING: Some ground stations have no initial coverage.")
        print("   Flows will queue until satellites pass overhead (~5-10 min).")
        print("   Consider increasing --subset-size for better coverage.\n")
    else:
        print("\n✓ All ground stations have satellite coverage.\n")
    
    return visible_count


# ============================================================================
# Satellite Loading and Filtering
# ============================================================================

def load_starlink_subset(subset_size=DEFAULT_SUBSET_SIZE, 
                         inclination_min=INCLINATION_MIN, 
                         inclination_max=INCLINATION_MAX,
                         excluded_satnums=EXCLUDED_SATNUMS,
                         random_seed=None):
    """
    Load a filtered subset of Starlink satellites.
    
    Filtering Strategy:
    1. Filter by inclination to get coherent orbital shell (53° main shell)
    2. Remove satellites with missing/invalid orbital data
    3. Random sample to target subset size
    
    Args:
        subset_size: Target number of satellites (default: 500)
        inclination_min: Minimum inclination for shell filter (default: 50°)
        inclination_max: Maximum inclination for shell filter (default: 56°)
        excluded_satnums: Set of NORAD IDs to exclude
        random_seed: Random seed for reproducibility (default: None)
    
    Returns:
        dict: Mapping of satnum -> Sat object
    """
    if random_seed is not None:
        random.seed(random_seed)
    
    print("="*60)
    print("LOADING STARLINK SATELLITES")
    print("="*60)
    print(f"Source: {STARLINK_URL}")
    print(f"Target subset size: {subset_size} satellites")
    print(f"Inclination filter: {inclination_min}° - {inclination_max}°")
    print()
    
    # Fetch all Starlink data
    print("Fetching Starlink data from Celestrak...")
    try:
        response = requests.get(STARLINK_URL, timeout=60)
        response.raise_for_status()
        stations_json = response.json()
        print(f"  Retrieved {len(stations_json)} satellites")
    except requests.RequestException as e:
        print(f"ERROR: Failed to fetch satellite data: {e}")
        sys.exit(1)
    
    # Filter by inclination (main orbital shell)
    print(f"Filtering by inclination ({inclination_min}°-{inclination_max}°)...")
    filtered_json = []
    for jsat in stations_json:
        inc = jsat.get('INCLINATION')
        if inc is not None and inclination_min <= inc <= inclination_max:
            filtered_json.append(jsat)
    
    print(f"  {len(filtered_json)} satellites in main shell "
          f"({100*len(filtered_json)/len(stations_json):.1f}% of total)")
    
    # Validate orbital data
    print("Validating orbital elements...")
    valid_json = []
    excluded_count = 0
    for jsat in filtered_json:
        satnum = int(jsat["NORAD_CAT_ID"])
        
        # Check for excluded satellites
        if satnum in excluded_satnums:
            excluded_count += 1
            continue
        
        # Check for required fields
        essential = ["EPOCH", "MEAN_MOTION", "ECCENTRICITY", "INCLINATION"]
        missing = [f for f in essential if f not in jsat or jsat[f] is None]
        if missing:
            print(f"  Skipping {jsat['OBJECT_NAME']}: missing {missing}")
            excluded_count += 1
            continue
        
        valid_json.append(jsat)
    
    print(f"  {len(valid_json)} satellites with valid data "
          f"({excluded_count} excluded)")
    
    # Random sampling
    if len(valid_json) > subset_size:
        print(f"Random sampling {subset_size} satellites from {len(valid_json)}...")
        if random_seed is not None:
            random.seed(random_seed)
        selected_json = random.sample(valid_json, subset_size)
    else:
        print(f"Using all {len(valid_json)} valid satellites "
              f"(subset_size={subset_size} not reached)")
        selected_json = valid_json
    
    # Create Sat objects
    print("Creating satellite objects...")
    satellites = {}
    for jsat in selected_json:
        try:
            sat = EarthSatellite.from_omm(utils.ts, jsat)
            satnum = int(jsat["NORAD_CAT_ID"])
            satellites[satnum] = Sat(sat, ground_stations)
        except Exception as e:
            print(f"  Warning: Failed to create satellite {jsat['OBJECT_NAME']}: {e}")
            continue
    
    print(f"\n✓ Loaded {len(satellites)} satellites")
    print("="*60)
    
    return satellites


# ============================================================================
# Main Simulation Setup
# ============================================================================

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Starlink Subset Simulation Runner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 starlink_main.py --strategy 5 --duration 60 --traffic 20
  python3 starlink_main.py -s 5 -d 60 -t 20 --subset-size 300
  python3 starlink_main.py -s 5 -d 60 -t 20 --subset-size 1000 --seed 42
        """
    )
    parser.add_argument("-s", "--strategy", type=int, required=True,
                        help="Routing strategy (1-15)")
    parser.add_argument("-d", "--duration", type=int, default=60,
                        help="Simulation duration in seconds (default: 60)")
    parser.add_argument("-t", "--traffic", type=int, default=10,
                        help="Total traffic volume in Gbps (default: 10)")
    parser.add_argument("--subset-size", type=int, default=DEFAULT_SUBSET_SIZE,
                        help=f"Number of satellites to simulate (default: {DEFAULT_SUBSET_SIZE})")
    parser.add_argument("--inclination-min", type=float, default=INCLINATION_MIN,
                        help=f"Minimum inclination filter (default: {INCLINATION_MIN})")
    parser.add_argument("--inclination-max", type=float, default=INCLINATION_MAX,
                        help=f"Maximum inclination filter (default: {INCLINATION_MAX})")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed for reproducibility")
    parser.add_argument("--show-map", action="store_true",
                        help="Show constellation map before simulation")
    
    args = parser.parse_args()
    
    # Update constants with command-line arguments
    constants.ROUTING_STRATEGY = Strategy(args.strategy)
    constants.SIMULATION_DURATION = args.duration
    constants.TOTAL_VOLUME_OF_TRAFFIC = args.traffic
    constants.SAT_FORMAT = 2  # Custom OMM JSON
    
    print("\n" + "="*60)
    print("STARLINK SUBSET SIMULATION")
    print("="*60)
    print(f"Routing Strategy: {constants.ROUTING_STRATEGY.name} (ID: {args.strategy})")
    print(f"Simulation Duration: {args.duration} seconds")
    print(f"Total Traffic: {args.traffic} Gbps")
    print(f"Ground Stations: {len(ground_stations)}")
    for gs_name in ground_stations.keys():
        print(f"  - {gs_name}")
    print("="*60 + "\n")
    
    # Load satellite subset
    satellites = load_starlink_subset(
        subset_size=args.subset_size,
        inclination_min=args.inclination_min,
        inclination_max=args.inclination_max,
        excluded_satnums=EXCLUDED_SATNUMS,
        random_seed=args.seed
    )
    
    # Configure ground stations
    for gs in ground_stations.values():
        gs.set_satellites(satellites)
    
    # Initialize environment
    env.satellites = satellites
    env.ground_stations = ground_stations
    
    # Check initial visibility
    check_initial_visibility(satellites, ground_stations)
    
    # Show constellation map if requested
    if args.show_map:
        print("Displaying constellation map...")
        show_constellation_map(satellites.values(), ground_stations.values(), links=[], paths=[])
    
    # Prepare environment (schedule events)
    env.prepare()
    
    # Obtain traffic matrix
    print("Obtaining traffic matrix from gravity model API...")
    try:
        traffic_matrix = get_traffic_matrix([gs.get_name() for gs in ground_stations.values()])
        print(f"Traffic matrix: {traffic_matrix}")
    except requests.RequestException as e:
        print(f"WARNING: Failed to fetch traffic matrix: {e}")
        print("Using default uniform traffic distribution...")
        # Fallback: uniform traffic distribution
        gs_names = list(ground_stations.keys())
        traffic_matrix = {name: {} for name in gs_names}
        per_destination = args.traffic / (len(gs_names) - 1)
        for src in gs_names:
            for dst in gs_names:
                if src != dst:
                    traffic_matrix[src][dst] = per_destination
    
    # Create traffic generators based on routing strategy
    traffic_generators = []
    header_builders = []
    
    # Centralized routing strategies (source routing)
    if constants.ROUTING_STRATEGY in [
        Strategy.BASELINE_DIJKSTRA,
        Strategy.SOURCE_ROUTING_BY_HOP_NO_LB,
        Strategy.SOURCE_ROUTING_BY_LENGTH_NO_LB,
        Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB,
        Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB,
        Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING,
        Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK,
        Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING
    ]:
        print(f"\nUsing CENTRALIZED routing paradigm")
        for gs in ground_stations.values():
            gs_traffic_details = traffic_matrix[gs.get_name()]
            for destination in gs_traffic_details:
                hb = HeaderBuilder(
                    gs_traffic_details[destination], 
                    constants.SIMULATION_DURATION, 
                    gss=ground_stations, 
                    source_gs=gs, 
                    destination_gs=ground_stations[destination.upper()]
                )
                header_builders.append(hb)
        print(f"Created {len(header_builders)} HeaderBuilder instances")
    
    # Distributed routing strategies (position-based)
    if constants.ROUTING_STRATEGY in [
        Strategy.POSITION_GUESSING_NO_LB,
        Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK,
        Strategy.POSITION_GUESSING_PROGRESSIVE_LB,
        Strategy.POSITION_SHARING_NO_LB,
        Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK,
        Strategy.POSITION_SHARING_PROGRESSIVE_LB,
        Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB,
        Strategy.POSITION_AND_LOAD_STATE_SHARING_TWO_HOPS
    ]:
        print(f"\nUsing DISTRIBUTED routing paradigm")
        for gs in ground_stations.values():
            gs_traffic_details = traffic_matrix[gs.get_name()]
            for destination in gs_traffic_details:
                tg = TrafficGenerator(
                    gs_traffic_details[destination], 
                    constants.SIMULATION_DURATION, 
                    source_gs=gs, 
                    destination_gs=ground_stations[destination.upper()]
                )
                traffic_generators.append(tg)
        print(f"Created {len(traffic_generators)} TrafficGenerator instances")
    
    # Start simulation
    print("\n" + "="*60)
    print("STARTING SIMULATION")
    print("="*60)
    env.start()
    
    # Analysis (uncomment to generate metrics)
    print("\nSimulation completed.")
    traffic_analyzer = TrafficAnalyzer(ground_stations, satellites)
    
    # Example analysis (uncomment to use):
    # print("Analyzing results...")
    # results = traffic_analyzer.analyze(AnalysisMetric.COMPARISON_WITH_DIJKSTRA)
    # charts.show_shortest_paths_table(results)
    
    print("Done.")


if __name__ == "__main__":
    main()
