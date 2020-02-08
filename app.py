from tendo import singleton

import os
import re
import time
import xmltv
from pprint import pprint

import common.db_utils as db_utils
import common.playlist_utils as playlist_utils
import common.tv_maze as tv_maze

# Throw an exception if this script is already running
me = singleton.SingleInstance()

db_utils.initialize_db()

# input_directory = '/media/TV/Steven Universe'
input_directory = '/Volumes/TV Channels/Flying Witch'


# Given a show name, this function will populate the SQLite DB with all of the episode information
# for that show
def populate_tv_maze_episode_info(show_name):

    series_id = db_utils.get_series_id(show_name)

    current_time = int(time.time())
    episodes_api_response = tv_maze.show_episode_list(series_id)
    for curr in episodes_api_response:
        print(curr)
        episode_subtitle = 'S' + str(curr['season']) + 'E' + str(curr['number'])
        if not (curr['summary'] is None):
            description = curr['summary'].replace('<p>', '').replace('</p>', '')
        else:
            description = ''

        db_utils.save_tv_maze_episode_info(series_id, curr['season'], curr['number'], curr['name'],
                                           episode_subtitle, description, current_time)


def populate_episode_lengths(directory_full_path):
    series_directory_name = os.path.basename(directory_full_path)
    series_id = db_utils.get_series_id(series_directory_name)
    file_list = playlist_utils.list_files_with_path(directory_full_path)
    for file_full_path in file_list:
        file_name = os.path.basename(file_full_path)
        length = playlist_utils.get_video_length(file_full_path)
        season, episode = playlist_utils.parse_season_episode(os.path.basename(file_name))
        db_utils.save_episode_length(series_id, season, episode, length)


def populate_all_episode_info(directory_full_path):
    directory_name = os.path.basename(directory_full_path)
    populate_tv_maze_episode_info(directory_name)
    populate_episode_lengths(directory_full_path)


# populate_all_episode_info(input_directory)

pprint(xmltv.read_channels(open('/Users/andrew/Desktop/xmltv.xml', 'r')))


