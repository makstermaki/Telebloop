import json
import requests

tvmaze_api_url = 'http://api.tvmaze.com'

show_single_search_path = '/singlesearch/shows?q='
show_episode_list_path = '/shows/{series_id}/episodes'


def show_single_search(name):
    resp = requests.get(tvmaze_api_url + show_single_search_path + name)
    return json.loads(json.dumps(resp.json()))


def show_episode_list(show_id):
    resp = requests.get(tvmaze_api_url + show_episode_list_path.replace('{series_id}', str(show_id)))
    return json.loads(json.dumps(resp.json()))
