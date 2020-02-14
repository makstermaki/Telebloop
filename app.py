from tendo import singleton

import configparser
import datetime
import glob
import os
import subprocess
import sys
import time
from pprint import pprint

import common.db_utils as db_utils
import common.m3u as m3u
import common.playlist_utils as playlist_utils
import common.tv_maze as tv_maze
import common.xmltv as xmltv

# Throw an exception if this script is already running
me = singleton.SingleInstance()

# Default Parameters
default_working_dir = '/tmp/HomeBroadcaster/'
default_stream_dir = '/var/www/html/tv'

# Declare the subdirectories to be used
logs_subdir = 'logs/'
playlist_subdir = 'playlists/'
pid_subdir = 'pid/'

db_utils.initialize_db()


def check_pid_running(pid):
    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    else:
        return True


def clean_directory_path(path):
    if not path.endswith('/'):
        return path + '/'
    return path


def clear_previous_stream_files(channel_name, stream_dir, playlist_dir):
    file_list = glob.glob(stream_dir + channel_name + '*')
    for file in file_list:
        try:
            os.remove(file)
        except:
            print("Error occurred while deleting file: ", file)
    if os.path.exists(playlist_dir + channel_name + ".txt"):
        os.remove(playlist_dir + channel_name + ".txt")


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


def start_channel(channel_name, order, channel_series_id, xmltv_file, dirs):
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
            db_episodes = db_utils.get_episodes_in_order(channel_result['seriesID'], 0)

    # Update the next episode to play for the channel for the next run
    db_utils.update_channel_next_episode(channel_name, last_episode_in_playlist + 1)

    # Generate the FFMPEG concat playlist
    concat_playlist = playlist_utils.generate_concat_playlist(playlist, dirs['playlist_dir'], channel_name)

    # At this point, the FFMPEG playlist has been generated so the stream can be started
    if not os.path.exists("./pid"):
        os.mkdir("./pid")

    ffmpeg_log_file = open(dirs['log_dir'] + 'ffmpeg.log', "w")
    m3u8_path = dirs['stream_dir'] + channel_name + '.m3u8'

    proc = subprocess.Popen([
        "ffmpeg", "-re", "-loglevel", "warning", "-fflags", "+genpts", "-f", "concat", "-safe", "0", "-i",
        concat_playlist, "-map", "0:a?", "-map", "0:v?", "-strict", "-2", "-dn", "-c", "copy",
        "-hls_time", "10", "-hls_list_size", "6", "-hls_wrap", "7", m3u8_path
    ], stderr=ffmpeg_log_file)

    pid_file = open(dirs['pid_dir'] + channel_name + ".pid", "w")
    pid_file.write(str(proc.pid))
    pid_file.close()

    # Add the channel to the central streams playlist
    m3u.add_channel_if_not_exists(dirs['stream_dir'], channel_name)


# -----------------SCRIPT STARTS HERE---------------------

try:
    config_path = sys.argv[1]
except Exception:
    raise Exception('No config file passed in arguments!')

config = configparser.ConfigParser()
config.read(config_path)

# Check the config file for any missing parameters and generate the default directories if so
if config.has_option('GENERAL', 'working_directory'):
    working_directory = clean_directory_path(config.get('GENERAL', 'working_directory'))
else:
    working_directory = default_working_dir
    if not os.path.exists(working_directory):
        os.mkdir(working_directory)

log_directory = working_directory + logs_subdir
playlist_directory = working_directory + playlist_subdir
pid_directory = working_directory + pid_subdir

if not os.path.exists(log_directory):
    os.mkdir(log_directory)
if not os.path.exists(playlist_directory):
    os.mkdir(playlist_directory)
if not os.path.exists(pid_directory):
    os.mkdir(pid_directory)

# Populate stream directory and XML TV location
if config.has_option('GENERAL', 'stream_directory'):
    stream_directory = clean_directory_path(config.get('GENERAL', 'stream_directory'))

    if not os.path.exists(stream_directory):
        os.mkdir(stream_directory)

    xmltv_path = stream_directory + 'xmltv.xml'

    if os.path.exists(xmltv_path):
        file_xmltv = xmltv.open_xmltv(xmltv_path)
    else:
        file_xmltv = xmltv.generate_new_xmltv()
else:
    if not os.path.exists(default_stream_dir):
        os.mkdir(default_stream_dir)
    stream_directory = default_stream_dir

    xmltv_path = default_stream_dir + 'xmltv.xml'
    if os.path.exists(xmltv_path):
        file_xmltv = xmltv.open_xmltv(xmltv_path)
    else:
        file_xmltv = xmltv.generate_new_xmltv()

# Create a dictionary for all of the working directories
directories = {
    'working_dir': working_directory,
    'stream_dir': stream_directory,
    'playlist_dir': playlist_directory,
    'pid_dir': pid_directory,
    'log_dir': log_directory
}


# All input parameters have now been processed and the channels can now be started

for channel in config.sections():
    if channel == 'GENERAL':
        continue

    # Check if the channel is currently running and if so, do nothing
    pid_file_path = directories['pid_dir'] + channel + '.pid'
    if os.path.exists(pid_file_path):
        old_pid_file = open(pid_file_path)
        ffmpeg_pid = old_pid_file.readline().strip()
        if check_pid_running(ffmpeg_pid):
            # If the channel is already running, nothing needs to be done
            print(channel + " already running...")
            continue
        else:
            # Channel stopped running. Clear the old stream files
            print("Deleting old stream files...")
            clear_previous_stream_files(channel, directories['stream_dir'], directories['playlist_dir'])

    print("Starting channel: " + channel)

    directory = config.get(channel, "directory")
    playback_order = config.get(channel, "order")

    directory_series_id = db_utils.get_series_id(os.path.basename(directory))

    populate_all_episode_info(directory)
    xmltv.remove_channel_programmes(channel, file_xmltv)
    start_channel(channel, playback_order, directory_series_id, file_xmltv, directories)

xmltv.remove_past_programmes(file_xmltv)
xmltv.save_to_file(file_xmltv, xmltv_path)