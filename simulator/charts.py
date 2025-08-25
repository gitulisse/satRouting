import constants
import environment as env
import matplotlib.pyplot as plt 
import numpy as np
import plotly.graph_objects as go
import statistics
from strategy import Strategy

def show_shortest_paths_table(results: dict):
    strategies = []
    trajectories = []
    means = []
    variances = []
    failed = []
    distances = []
    means_wrt_dijkstra = []
    variances_wrt_dijkstra = []
    failed_percentage = []
    distances_wrt_dijkstra = []
    for trajectory, strategy_data in results.items():
        dijkstra_mean = 0
        dijkstra_variance = 0
        dijkstra_distance = 0
        for strategy, data in strategy_data.items():
            if strategy == 'BASELINE_DIJKSTRA':
                dijkstra_mean = round(statistics.mean(data['successful']), 2) if len(data['successful']) > 0 else 0
                dijkstra_variance = round(statistics.variance(data['successful']), 2) if len(data['successful']) > 1 else 0
                dijkstra_distance = round(statistics.mean(data['distance']), 2) if len(data['distance']) > 0 else 0
            strategies.append(strategy)
            trajectories.append(trajectory)
            means.append(round(statistics.mean(data['successful']), 2) if len(data['successful']) > 0 else 0)
            variances.append(round(statistics.variance(data['successful']), 2) if len(data['successful']) > 1 else 0)
            failed.append(data['failed'])
            distances.append(round(statistics.mean(data['distance']), 2) if len(data['distance']) > 0 else 0)
            means_wrt_dijkstra.append("+" + str(round(((means[-1] - dijkstra_mean) / dijkstra_mean) * 100, 2)) + "%")
            variances_wrt_dijkstra.append("+" + str(round(((variances[-1] - dijkstra_variance) / dijkstra_variance) * 100, 2)) + "%")
            failed_percentage.append(str(round((data['failed'] / (data['failed'] + len(data['successful']))) * 100, 2)) + "%")
            distances_wrt_dijkstra.append("+" + str(round(((distances[-1] - dijkstra_distance) / dijkstra_distance) * 100, 2)) + "%")
            
    fig = go.Figure(data=[go.Table(header=dict(values=["Trajectory", "Strategy", "Mean", "Mean increase from Dijkstra", "Variance", "Variance increase from Dijkstra", "Failed routing", "Failed routing percentage", "Distance (km)", "Distance increase from Dijkstra"], height=26),
                    cells=dict(values=[trajectories, strategies, means, means_wrt_dijkstra, variances, variances_wrt_dijkstra, failed, failed_percentage, distances, distances_wrt_dijkstra], height=26))
                        ])
    #fig.show()

    ax = plt.subplot()

    #initialization of lists
    trajectories.insert(0, "Trajectory")
    strategies.insert(0, "Strategy")
    means.insert(0, "Average hop count")
    variances.insert(0, "Variance of hop count")
    failed_percentage.insert(0, "Failed routings")
    distances.insert(0, "Average path length (km)")

    #create columns for table
    table_data = [[trajectories[i], strategies[i], means[i], variances[i], failed_percentage[i] if strategies[i] != 'BASELINE_DIJKSTRA' else '-', distances[i]] for i in range(len(trajectories)) if i == 0 or trajectories[i] == "Buenos Aires - New York" or trajectories[i] == "Buenos Aires - Dar Es Salaam" or trajectories[i] == "Buenos Aires - Tokyo"]

    #create table
    table = ax.table(cellText=table_data, loc='center', cellLoc='center')

    #modify table
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.auto_set_column_width(col=list(range(6)))
    table.scale(0.9, 0.6) #(larghezza, altezza) modificata
    ax.axis('off')

    table_props = table.properties()
    table_cells = table_props['celld']
    for indices, cell in table_cells.items():
        if indices[0] == 0:
            cell.set_text_props(weight='black', size='medium')
        elif indices[0] % 3 == 2:
            cell.get_text().set_color('black')
        elif indices[0] % 3 == 0:
            cell.get_text().set_color('black')

    #display table
    plt.show()

    refactored_results = {#Strategy.BASELINE_DIJKSTRA.name : {},  #key that will contain results for the used strategy
        #Strategy.POSITION_GUESSING_NO_LB.name : {},
        #Strategy.POSITION_GUESSING_LB_ON_SATURATED_LINK.name : {},
        #Strategy.POSITION_GUESSING_PROGRESSIVE_LB.name : {},
        #Strategy.POSITION_SHARING_NO_LB.name : {},
        #Strategy.POSITION_SHARING_LB_ON_SATURATED_LINK.name : {},
        #Strategy.POSITION_SHARING_PROGRESSIVE_LB.name : {},
        #Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB.name : {},
        #Strategy.POSITION_AND_LOAD_STATE_SHARING_TWO_HOPS.name : {},  #key that will contain results for the used strategy
        Strategy.SOURCE_ROUTING_BY_HOP_NO_LB.name : {},
        Strategy.SOURCE_ROUTING_BY_LENGTH_NO_LB.name : {},
        Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB.name : {},
        Strategy.EDGE_DISJOINT_SOURCE_ROUTING_LB.name : {},
        Strategy.NODE_DISJOINT_SOURCE_ROUTING_LB_ON_SATURATED_LINK.name : {},
        Strategy.EDGE_DISJOINT_SOURCE_ROUTING_COST_BALANCING.name : {}
    }

    for key in refactored_results.keys():
        refactored_results[key] = {
            "successful" : [],
            "failed" : 0,
            "distance" : []
        }

    for trajectory, strategy_data in results.items():
        for strategy, data in strategy_data.items():
            refactored_results[strategy]['successful'].extend(data['successful'])
            refactored_results[strategy]['failed'] += data['failed']
            refactored_results[strategy]['distance'].extend(data['distance'])

    strategies = ["Strategy"]
    failed_percentage = ["Failed routings"]
    distances_wrt_dijkstra = ["Average path length increase wrt Dijkstra"]
    distances = []
    for strategy, data in refactored_results.items():
        if strategy == 'BASELINE_DIJKSTRA':
            dijkstra_distance = round(statistics.mean(data['distance']), 2) if len(data['distance']) > 0 else 0
        strategies.append(strategy)
        failed_percentage.append(str(round((data['failed'] / (data['failed'] + len(data['successful']))) * 100, 2)) + "%")
        distances.append(round(statistics.mean(data['distance']), 2) if len(data['distance']) > 0 else 0)
        distances_wrt_dijkstra.append("+" + str(round(((distances[-1] - dijkstra_distance) / dijkstra_distance) * 100, 2)) + "%")

    ax = plt.subplot()

    #generate columns for table
    table_data = [[strategies[i], failed_percentage[i], distances_wrt_dijkstra[i]] for i in range(len(strategies)) if strategies[i] != 'DIJKSTRA']

    #create table
    table = ax.table(cellText=table_data, loc='center', cellLoc='center')

    #modify table
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.auto_set_column_width(col=list(range(6)))
    #table.scale(1, 0.7)
    ax.axis('off')

    table_props = table.properties()
    #print(table_props)
    table_cells = table_props['celld']
    for indices, cell in table_cells.items():
        if indices[0] == 0:
            cell.set_text_props(weight='black', size='medium')
        elif indices[0] == 1 and (indices[1] == 1 or indices[1] == 2):
            cell.get_text().set_color('red')
            cell.set_text_props(weight='black', size='medium')
        elif indices[0] == 2 and (indices[1] == 1 or indices[1] == 2):
            cell.get_text().set_color('green')
            cell.set_text_props(weight='black', size='medium')

    #display table
    plt.show()


def show_average_link_occupation_chart(results: dict):
    colors = ['r', 'g', 'b', 'c', 'm', 'y', 'k',
              'tab:orange', 'tab:purple', 'tab:brown', 'tab:pink', 'tab:gray', 'tab:olive', 'tab:cyan',
              '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
              '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf', '#000000']
    
    markers = ['.', 'v', 's', 'p', 'H', 'x', 'd', '|', '_', 'o', 'D', '*', 'X', '+', '>', '<', '1', '2',
               '^', '8', 'h', 'P', '3', '4']

    ax1 = plt.subplot(1, 2, 1)
    ax2 = plt.subplot(1, 2, 2)
    
    #chart positioning
    box = ax1.get_position()
    ax1.set_position([box.x0, box.y0 + box.height * 0.2, box.width, box.height * 0.8])
    ax1.set_title("Average link occupation", fontsize=16)

    for i, (strategy, data) in enumerate(results.items()):
        ax1.plot(
            [data['volume_of_traffic'][index] for index in range(0, len(data['volume_of_traffic']), 10)],
            [statistics.mean(data['average_link_occupation'][index:index + 10]) * 100 / constants.SATELLITE_LINK_CAPACITY
             for index in range(0, len(data['average_link_occupation']), 10)],
            label=strategy, color=colors[i], marker=markers[i])

    box = ax2.get_position()
    ax2.set_position([box.x0, box.y0 + box.height * 0.2, box.width, box.height * 0.8])
    ax2.set_title("Involved satellites", fontsize=16)

    for i, (strategy, data) in enumerate(results.items()):
        ax2.plot(
            [data['volume_of_traffic'][index] for index in range(0, len(data['volume_of_traffic']), 10)],
            [statistics.mean(data['involved_satellites'][index:index + 10]) * 100 / 66
             for index in range(0, len(data['involved_satellites']), 10)],
            label=strategy, color=colors[i], marker=markers[i])

    ax1.set_xlabel("Volume of traffic (in Gbps)", fontsize=13)
    ax1.set_ylabel("Link occupation (in percentage)", fontsize=13)

    ax2.set_xlabel("Volume of traffic (in Gbps)", fontsize=13)
    ax2.set_ylabel("Involved satellites (in percentage)", fontsize=13)

    ax1.legend(loc='upper center', bbox_to_anchor=(1.15, -0.1), ncol=2, fontsize=12)

    for label in (ax1.get_xticklabels() + ax1.get_yticklabels()):
        label.set_fontsize(13)

    for label in (ax2.get_xticklabels() + ax2.get_yticklabels()):
        label.set_fontsize(13)

    #Set fixed limits for the y-axes
    ax1.set_ylim(0, 70)  # "Average link occupation"
    ax2.set_ylim(0, 55)  # "Involved satellites"

    plt.show()


def show_delivered_dropped_ratio_chart(results: dict):
    #colors = ['r', 'g', 'b', 'c', 'm', 'y', 'k']
    markers = ['.', 'v', 's', 'p', 'H', 'x', 'd', '|', '_', 'o', 'D', '*', 'X', '+', '>', '<', '1', '2',
           '^', '8', 'h', 'P', '3', '4']  
    ax = plt.subplot()
    box = ax.get_position()
    ax.set_position([box.x0, box.y0 + box.height * 0.15, box.width, box.height * 0.85])

    for i, (strategy, data) in enumerate((s for s in results.items() if s[1]['delivered'] and s[1]['dropped'])):
        plt.plot(data['volume_of_traffic'],
                [dropped * 100 / (delivered + dropped)
                for delivered, dropped in zip(data['delivered'], data['dropped'])],
                label=strategy,
                marker=markers[i])


    plt.legend(loc='upper center', bbox_to_anchor=(0.5, -0.1), ncol=2)
    plt.title("Dropped data per routing strategy")
    plt.suptitle(f"Ground station involved: {len(env.ground_stations)}, iteration duration: {constants.SIMULATION_DURATION}")
    plt.xlabel("Traffic forwarded through the network (in Gbps)")
    plt.ylabel("Packet loss (%)")
    plt.show()

def show_control_traffic_comparison_chart(results: dict):
    width = 0.21
    multiplier = 0
    x = np.arange(len(list(results.values())[0].keys()))
    y = np.arange(0, 101, 20)

    ax = plt.subplot()
    box = ax.get_position()
    ax.set_position([box.x0, box.y0 + box.height * 0.15, box.width, box.height * 0.85])

    preprocessed_results = {}

    for i, (strategy, data) in enumerate(results.items()):
        delivered = []
        dropped = []
        control_traffic = []
        multiplier = 0
        for time, _data in data.items():
            total = statistics.mean(_data['delivered']) + statistics.mean(_data['dropped'])
            delivered.append(round(statistics.mean(_data['delivered']) * 100 / total, 2))
            dropped.append(round(statistics.mean(_data['dropped']) * 100 / total, 2))
            control_traffic.append(round(statistics.mean(_data['control_traffic']), 2))
        preprocessed_results[strategy] = dropped

    for metric, data in preprocessed_results.items():
        offset = width * multiplier
        rects = ax.bar(x + offset, data, width, label=metric)
        ax.bar_label(rects, padding=5)
        multiplier += 1


    ax.set_title("Packet loss per strategy", fontsize=16)
    ax.set_xticks(x + width * 1.5, list(list(results.values())[0].keys()))
    plt.legend(loc='upper center', bbox_to_anchor=(0.5, -0.08), ncol=2, prop={"size" : 13})
    plt.xlabel("Position update time (in seconds)", fontsize=13)
    plt.ylabel("Packet loss (%)", fontsize=13)

    for label in (ax.get_xticklabels() + ax.get_yticklabels()):
        label.set_fontsize(13)

    #display table
    plt.show()

    ax = plt.subplot()

    for i, (strategy, data) in enumerate(results.items()):
        times = []
        control_traffic = []
        for time, _data in data.items():
            times.append(time)
            control_traffic.append(statistics.mean(_data['control_traffic']) * 1000)
        if i == 0:
            ax.plot(times, control_traffic, label="POSITION SHARING", marker='.')
        elif i == 3:
            ax.plot(times, control_traffic, label="POSITION AND LOAD STATE SHARING", marker='s')
    
    plt.legend(loc='upper right', ncol=1, prop={"size" : 13})
    plt.xlabel("Position update time (in seconds)", fontsize=13)
    plt.ylabel("Control traffic overhead in network (in KB)", fontsize=13)
    plt.title("Control traffic per strategy", fontsize=16)

    for label in (ax.get_xticklabels() + ax.get_yticklabels()):
        label.set_fontsize(13)

    #display table
    plt.show()

    # Specific data points and representation
    most_control_traffic_congesting = list(results[Strategy.POSITION_AND_LOAD_STATE_SHARING_ADAPTIVE_LB.name].values())[0]
    user_traffic_squares = int((statistics.mean(most_control_traffic_congesting['delivered']) + statistics.mean(most_control_traffic_congesting['dropped'])) * 1000 * 1000 * 1000 / 8 / 16636)
    control_traffic_squares = int(statistics.mean(most_control_traffic_congesting['control_traffic']) * 1000 * 1000 / 16636) # 1,000 bytes / 500 bytes per square
    print(user_traffic_squares)
    print(control_traffic_squares)
    # Total squares needed
    total_squares = user_traffic_squares + control_traffic_squares

    # Create a grid for visualization, ensuring it's large enough for all squares
    grid_side = int(np.ceil(np.sqrt(total_squares)))
    traffic_grid_specific = np.zeros((grid_side, grid_side))

    # Populate the grid with user (blue) and control (red) traffic
    # Blue squares (-1) for user traffic
    traffic_grid_specific.flat[:user_traffic_squares] = -1
    # Red squares (1) for control traffic
    traffic_grid_specific.flat[user_traffic_squares:user_traffic_squares + control_traffic_squares] = 1

    # Shuffle the grid to mix the traffic types
    #np.random.shuffle(traffic_grid_specific.flat)

    # Plotting the specific data
    plt.figure(figsize=(12, 12))
    plt.imshow(traffic_grid_specific, cmap='bwr', vmin=-1, vmax=1)
    plt.title('Network Traffic Visualization: User vs Control Traffic')
    plt.suptitle('Traffic Type (Blue: User, Red: Control)')
    plt.axis('off')  # Hide grid lines
    plt.show()

def show_weight_sensitivity_analysis_chart(results: dict):
    colors = ['r', 'g', 'b', 'c', 'm', 'y', 'k']

    ax = plt.subplot()

    weights = []
    average_link_occupation = []
    involved_satellites = []
    cumulative_dropped_data = []
    
    for weight, data in results.items():
        weights.append(float(weight))
        average_link_occupation.append(statistics.mean(data['average_link_occupation']) * 100 / constants.SATELLITE_LINK_CAPACITY)
        involved_satellites.append(statistics.mean(data['involved_satellites']) * 100 / 66)
        cumulative_dropped_data.append(statistics.mean(data['cumulative_dropped_data']) / 60 * 100 / data['volume_of_traffic'][0])

    ax.plot(weights, cumulative_dropped_data, label='Dropped data', marker='.')

    plt.legend(loc='upper right', ncol=1)
    plt.title("Weight sensitivity analysis")
    plt.xlabel("Weight variation (α)")
    plt.ylabel("Packet loss (%)")
    plt.xticks(np.arange(0, 1.1, 0.1))
    #plt.yticks(np.arange(0, 11, 2))
    plt.show()

def show_time_passing_simulation_chart(results: dict):
    colors = ['r', 'g', 'b', 'c', 'm', 'y', 'k']
    markers = ['.','v','s','p','H','x','d','|','_']

    ax1 = plt.subplot()
    box = ax1.get_position()
    ax1.set_position([box.x0, box.y0 + box.height * 0.2, box.width, box.height * 0.8])

    for i, (strategy, data) in enumerate(results.items()):
        ax1.plot([j for j in range(len(data['delivered'][1:]))], [delivered * 100 / (delivered + dropped) if delivered + dropped != 0 else 0 for delivered, dropped in zip(data['delivered'][1:], data['dropped'][1:])], label=f"{strategy} - DELIVERED", color=colors[i])

    for i, (strategy, data) in enumerate(results.items()):
        ax1.plot([j for j in range(len(data['delivered'][1:]))], [dropped * 100 / (delivered + dropped) if delivered + dropped != 0 else 0 for delivered, dropped in zip(data['delivered'][1:], data['dropped'][1:])], label=f"{strategy} - DROPPED", color=colors[i], linestyle="--")

    ax1.set_title("Delivered and dropped traffic per strategy")
    ax1.set_xlabel("Time (in seconds)")
    ax1.set_ylabel("Traffic in network (in percentage)")

    ax1.legend(loc='upper center', bbox_to_anchor=(0.5, -0.08), ncol=2)

    plt.show()

def show_loop_avoidance_analysis_chart():
    import json

    results = list()

    with open(f'dijkstra_table_0.json', 'r', encoding='utf-8') as f:
        results.append((0, json.load(f)))
    with open(f'dijkstra_table_3.json', 'r', encoding='utf-8') as f:
        results.append((3, json.load(f)))
    with open(f'dijkstra_table_6.json', 'r', encoding='utf-8') as f:
        results.append((6, json.load(f)))
    with open(f'dijkstra_table_9.json', 'r', encoding='utf-8') as f:
        results.append((9, json.load(f)))
    with open(f'dijkstra_table.json', 'r', encoding='utf-8') as f:
        results.append(('inf', json.load(f)))

    width = 0.15
    multiplier = 0
    x = np.arange(2)

    ax = plt.subplot()

    refactored_results = {}
    for strategy in [Strategy.POSITION_GUESSING_NO_LB.name, Strategy.POSITION_SHARING_NO_LB.name]:
        refactored_results[strategy] = {}
        for tracked_nodes_number in [0, 3, 6, 9, 'inf']:
            refactored_results[strategy][tracked_nodes_number] = {}
            refactored_results[strategy][tracked_nodes_number]['failed'] = 0
            refactored_results[strategy][tracked_nodes_number]['distance'] = []

    for tracked_nodes_number, result in results:
        for _, strategy_data in result.items():
            for strategy, data in strategy_data.items():
                if strategy == 'DIJKSTRA': continue
                refactored_results[strategy][tracked_nodes_number]['failed'] += data['failed']
                refactored_results[strategy][tracked_nodes_number]['distance'].extend(data['distance'])

    preprocessed_results = {}
    for tracked_nodes_number in [0, 3, 6, 9, 'inf']:
        preprocessed_results[tracked_nodes_number] = [0, 0]

    for strategy, data in refactored_results.items():
        if strategy == 'DIJKSTRA': 
            continue
            for tracked_nodes_number, strategy_data in data.items():
                preprocessed_results[tracked_nodes_number][0] += strategy_data['failed']
                #preprocessed_results[tracked_nodes_number][0].extend(strategy_data['distance'])
        if strategy == Strategy.POSITION_GUESSING_NO_LB.name:
            for tracked_nodes_number, strategy_data in data.items():
                preprocessed_results[tracked_nodes_number][0] += strategy_data['failed']
                #preprocessed_results[tracked_nodes_number][0].extend(strategy_data['distance'])
        if strategy == Strategy.POSITION_SHARING_NO_LB.name:
            for tracked_nodes_number, strategy_data in data.items():
                preprocessed_results[tracked_nodes_number][1] += strategy_data['failed']
                #preprocessed_results[tracked_nodes_number][1].extend(strategy_data['distance'])
    
    #for metric, data in preprocessed_results.items():
    #    preprocessed_results[metric][0] = round(statistics.mean(preprocessed_results[metric][0]))
    #    preprocessed_results[metric][1] = round(statistics.mean(preprocessed_results[metric][1]))

    for metric, data in preprocessed_results.items():
        offset = width * multiplier
        rects = ax.bar(x + offset, data, width, label=metric)
        ax.bar_label(rects, padding=5)
        multiplier += 1

    ax.set_title("Packet loss per node tracking parameter", fontsize=16)
    #ax.set_title("Average path length per node tracking parameter", fontsize=16)
    ax.set_xticks(x + width * 2, [Strategy.POSITION_GUESSING_NO_LB.name, Strategy.POSITION_SHARING_NO_LB.name], fontsize=13)
    #ax.set_yticks(y)
    #ax.tick_params(axis='x', labelsize=10)
    plt.legend(loc='upper right', prop={"size" : 13})
    plt.xlabel("Strategy", fontsize=13)
    plt.ylabel("Packet loss", fontsize=13)
    #plt.ylabel("Average path length", fontsize=13)

    for label in (ax.get_xticklabels() + ax.get_yticklabels()):
        label.set_fontsize(13)
    
    plt.show()