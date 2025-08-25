import constants
import requests

#Manage Traffic Matrix
def get_traffic_matrix(cities: list[str]):
    url = 'http://localhost:8001/traffic_matrix'
    params = {
        'total_volume_of_traffic' : constants.TOTAL_VOLUME_OF_TRAFFIC,
        'cities' : ','.join([city for city in cities])
    }

    resp = requests.get(url=url, params=params)
    return resp.json()