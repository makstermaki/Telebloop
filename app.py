from tendo import singleton

import configparser
import datetime
import os
import re
import time
from pprint import pprint

import common.db_utils as db_utils
import common.playlist_utils as playlist_utils
import common.tv_maze as tv_maze
import common.xmltv as xmltv

# Throw an exception if this script is already running
me = singleton.SingleInstance()

db_utils.initialize_db()


# Given a show name, this function will populate the SQLite DB with all of the episode information
# for that show
def populate_tv_maze_episode_info(show_name):
    series_id = db_utils.get_series_id(show_name)

    episodes_api_response = tv_maze.show_episode_list(series_id)
    for curr in episodes_api_response:
        episode_subtitle = 'S' + str(curr['season']) + 'E' + str(curr['number'])
        if not (curr['summary'] is None):
            description = curr['summary'].replace('<p>', '').replace('</p>', '')
        else:
            description = ''

        db_utils.save_tv_maze_episode(series_id, curr['season'], curr['number'], curr['name'],
                                      episode_subtitle, description)
    db_utils.populate_series_absolute_order(series_id)


def populate_episode_lengths(directory_full_path):
    series_directory_name = os.path.basename(directory_full_path)
    series_id = db_utils.get_series_id(series_directory_name)
    file_list = playlist_utils.list_files_with_path(directory_full_path)
    for file_full_path in file_list:
        file_name = os.path.basename(file_full_path)
        length = playlist_utils.get_video_length(file_full_path)
        season, episode = playlist_utils.parse_season_episode(os.path.basename(file_name))
        db_utils.save_local_episode(series_id, season, episode, length, file_full_path)


def populate_all_episode_info(directory_full_path):
    directory_name = os.path.basename(directory_full_path)
    if not db_utils.is_series_metadata_loaded(directory_name):
        populate_tv_maze_episode_info(directory_name)
        populate_episode_lengths(directory_full_path)
        db_utils.update_series_last_updated_time(directory_name)


def start_channel(channel_name, order, channel_series_id, xmltv_file):
    channel_result = db_utils.get_channel(channel_name)
    if channel_result is None:
        db_utils.save_channel(channel_name, order, channel_series_id)
        channel_result = {
            'channel': channel_name,
            'playbackOrder': order,
            'seriesID': channel_series_id,
            'nextEpisode': 0
        }

    playlist = []

    xmltv.add_channel_if_not_exists(xmltv_file, channel_name)

    # The playlist will be generated such that it ends at the specified time.
    # DEFAULT: 5 AM
    now = datetime.datetime.now()
    day_delta = datetime.timedelta(days=1)
    target = now + day_delta

    target_timestamp = target.replace(hour=5, minute=0, second=0, microsecond=0).timestamp()
    current_timestamp = now.timestamp()

    db_episodes = db_utils.get_episodes_in_order(channel_result['seriesID'], channel_result['nextEpisode'])

    # Keep adding to the playlist until it ends past the target timestamp
    while current_timestamp < target_timestamp:

        for episode in db_episodes:

            print(episode)

            playlist.append(episode['filePath'])

            time_format = '%Y%m%d%H%M%S %z'
            start_time = time.strftime(time_format, time.localtime(current_timestamp))
            stop_time = time.strftime(time_format, time.localtime(current_timestamp + episode['length']))

            xmltv.add_programme(xmltv_file, channel_name, start_time, stop_time, episode['title'],
                                episode['subtitle'], episode['description'])

            current_timestamp = current_timestamp + episode['length']

            last_episode_in_playlist = episode['absoluteOrder']

            if current_timestamp > target_timestamp:
                break

        # If the playlist end time still hasn't reached the target time, retrieve all the
        # episodes in the series starting from absolute order zero and continue adding
        # to the playlist from there
        if current_timestamp < target_timestamp:
            result = db_utils.get_episodes_in_order(channel_result['seriesID'], 0)

    # Update the next episode to play for the channel for the next run
    db_utils.update_channel_next_episode(channel_name, last_episode_in_playlist + 1)

    # At this point, the playlist is complete along with the XML TV
    print(playlist)


config = configparser.ConfigParser()
config.read('config.ini')

# Retrieve already existing XML TV file or generate a new one
xmltv_path = config.get('GENERAL', 'xmltv_path')
if os.path.exists(xmltv_path):
    xmltv_file = xmltv.open_xmltv(xmltv_path)
else:
    xmltv_file = xmltv.generate_new_xmltv()


for channel in config.sections():
    if channel == 'GENERAL':
        continue

    directory = config.get(channel, "directory")
    playback_order = config.get(channel, "order")

    directory_series_id = db_utils.get_series_id(os.path.basename(directory))

    populate_all_episode_info(directory)
    start_channel(channel, playback_order, directory_series_id, xmltv_file)

xmltv.remove_past_programmes(xmltv_file)
xmltv.save_to_file(xmltv_file, xmltv_path)