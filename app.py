from tendo import singleton

import configparser
import datetime
import glob
import logging
import logging.handlers
import os
import subprocess
import sys
import time

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


def setup_logger(log_level, log_dir):
    log_location = log_directory + 'homeBroadcaster.log'
    log_handler = logging.handlers.RotatingFileHandler(filename=log_location, maxBytes=20_000, backupCount=5)
    formatter = logging.Formatter(fmt='[%(asctime)s] %(levelname)s - %(filename)s: %(message)s')
    log_handler.setFormatter(formatter)
    logger = logging.getLogger()
    logger.addHandler(log_handler)
    logger.setLevel(log_level)


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
        os.remove(file)
    if os.path.exists(playlist_dir + channel_name + ".txt"):
        os.remove(playlist_dir + channel_name + ".txt")


def populate_series_info(local_series_name, db_dir):
    db_utils.save_series(local_series_name, db_dir)


# Given a show name, this function will populate the SQLite DB with all of the episode information
# for that show
def populate_tv_maze_episode_info(show_name, db_dir):
    series_id = db_utils.get_series_id(show_name, db_dir)

    episodes_api_response = tv_maze.show_episode_list(series_id)
    for curr in episodes_api_response:
        episode_subtitle = 'S' + str(curr['season']) + 'E' + str(curr['number'])
        if not (curr['summary'] is None):
            description = curr['summary'].replace('<p>', '').replace('</p>', '').replace('<i>', '').replace('</i>', '')
        else:
            description = ''

        db_utils.save_tv_maze_episode(series_id, curr['season'], curr['number'], curr['name'],
                                      episode_subtitle, description, db_dir)
    db_utils.populate_series_absolute_order(series_id, db_dir)


def populate_episode_lengths(directory_full_path, db_dir):
    series_directory_name = os.path.basename(directory_full_path)
    series_id = db_utils.get_series_id(series_directory_name, db_dir)
    file_list = playlist_utils.list_files_with_path(directory_full_path)
    for file_full_path in file_list:
        file_name = os.path.basename(file_full_path)
        length = playlist_utils.get_video_length(file_full_path)
        season, episode = playlist_utils.parse_season_episode(os.path.basename(file_name))
        db_utils.save_local_episode(series_id, season, episode, length, file_full_path, db_dir)


# Retrieves and loads all episode information given a source directory
def populate_all_episode_info(directory_full_path, dirs):
    directory_name = os.path.basename(directory_full_path)
    if not db_utils.is_series_metadata_loaded(directory_name, dirs['working_dir']):
        populate_tv_maze_episode_info(directory_name, dirs['working_dir'])
        populate_episode_lengths(directory_full_path, dirs['working_dir'])
        db_utils.update_series_last_updated_time(directory_name, dirs['working_dir'])


def start_channel(channel_name, order, shows_list, xmltv_file, dirs):
    channel_result = db_utils.get_channel(channel_name, dirs['working_dir'])

    shows_concat = ','.join(shows_list)

    if channel_result is None:
        db_utils.save_channel(channel_name, order, shows_concat, dirs['working_dir'])
        next_episode_string = ""
        for i in range(len(shows)):
            next_episode_string += "0,"
        next_episode_string = next_episode_string[:-1]
        channel_result = {
            'channel': channel_name,
            'playbackOrder': order,
            'shows': shows_concat.split(','),
            'nextEpisode': next_episode_string
        }
    else:
        channel_result['shows'] = channel_result['shows'].split(',')

    next_episodes_list = channel_result['nextEpisode'].split(',')

    playlist = []

    xmltv.add_channel_if_not_exists(xmltv_file, channel_name)

    # The playlist will be generated such that it ends at the specified time.
    # DEFAULT: 5 AM
    now = datetime.datetime.now()
    day_delta = datetime.timedelta(days=1)
    target = now + day_delta

    target_timestamp = target.replace(hour=5, minute=0, second=0, microsecond=0).timestamp()
    current_timestamp = now.timestamp()

    db_series_ids = []
    db_episodes = []
    for idx, channel_show in enumerate(channel_result['shows']):
        series_id = db_utils.get_series_id(channel_show, dirs['working_dir'])
        db_series_ids.append(series_id)
        db_episodes.append(db_utils.get_episodes_in_order(series_id, next_episodes_list[idx], directories['working_dir']))

    # Keep adding to the playlist until it ends past the target timestamp
    # When adding episodes from multiple series into a single channel, alternate between the shows
    # in approx. 20 min blocks (basically aiming to match the content found in a 30 min time block
    # on standard tv)
    current_show_index = 0
    while current_timestamp < target_timestamp:

        current_block_runtime = 0
        num_episodes_added_to_playlist = 0

        for episode in db_episodes[current_show_index]:
            playlist.append(episode['filePath'])

            time_format = '%Y%m%d%H%M%S %z'
            start_time = time.strftime(time_format, time.localtime(current_timestamp))
            stop_time = time.strftime(time_format, time.localtime(current_timestamp + episode['length']))

            xmltv.add_programme(xmltv_file, channel_name, start_time, stop_time, episode['title'],
                                episode['subtitle'], episode['description'])

            current_timestamp = current_timestamp + episode['length']

            next_episodes_list[current_show_index] = episode['absoluteOrder']

            num_episodes_added_to_playlist += 1

            if current_timestamp > target_timestamp:
                break

            current_block_runtime = current_block_runtime + episode['length']
            if current_block_runtime > (20 * 60):
                break

        # Remove the episodes already added to the playlist from the DB episodes list
        # so they are not re-added to the playlist on the next iteration
        del db_episodes[current_show_index][:num_episodes_added_to_playlist]

        if not len(db_episodes[current_show_index]) and current_timestamp < target_timestamp:
            db_episodes[current_show_index] = db_utils.get_episodes_in_order(db_series_ids[current_show_index], 0, directories['working_dir'])

        current_show_index = (current_show_index + 1) % len(db_series_ids)

    # Update the next episode to play for the channel for the next run
    last_episode_in_playlist_string = ",".join([str(x+1) for x in next_episodes_list])
    db_utils.update_channel_next_episode(channel_name, last_episode_in_playlist_string, directories['working_dir'])

    # Generate the FFMPEG concat playlist
    concat_playlist = playlist_utils.generate_concat_playlist(playlist, dirs['playlist_dir'], channel_name)

    # At this point, the FFMPEG playlist has been generated so the stream can be started
    if not os.path.exists("./pid"):
        os.mkdir("./pid")

    m3u8_path = dirs['stream_dir'] + channel_name + '.m3u8'

    with open(dirs['log_dir'] + 'ffmpeg.log', "w") as ffmpeg_log_file:
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
config.optionxform = str
config.read(config_path)

# Check the config file for any missing parameters and generate the default directories if so
if config.has_option('General', 'Working Directory'):
    working_directory = clean_directory_path(config.get('General', 'Working Directory'))
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
if config.has_option('General', 'Stream Directory'):
    stream_directory = clean_directory_path(config.get('General', 'Stream Directory'))

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

if config.has_option('General', 'Log Level'):
    logging_level = logging.getLevelName(config.get('General', 'Log Level'))
else:
    logging_level = logging.INFO

# Create a dictionary for all of the working directories
directories = {
    'working_dir': working_directory,
    'stream_dir': stream_directory,
    'playlist_dir': playlist_directory,
    'pid_dir': pid_directory,
    'log_dir': log_directory
}

setup_logger(logging_level, directories['log_dir'])
db_utils.initialize_db(directories['working_dir'])

logging.info("Starting the Home Broadcaster application...")

# Process all shows in the shows config section
input_shows = dict(config.items('Shows'))
for show in input_shows:
    populate_series_info(show, directories['working_dir'])
    populate_all_episode_info(input_shows[show], directories)


for channel in config.sections():
    if channel == 'General' or channel == 'Shows':
        continue

    # Check if the channel is currently running and if so, do nothing
    pid_file_path = directories['pid_dir'] + channel + '.pid'
    if os.path.exists(pid_file_path):
        old_pid_file = open(pid_file_path)
        ffmpeg_pid = old_pid_file.readline().strip()
        if check_pid_running(ffmpeg_pid):
            # If the channel is already running, nothing needs to be done
            logging.debug(channel + ' already running, skipping...')
            continue
        else:
            # Channel stopped running. Clear the old stream files
            clear_previous_stream_files(channel, directories['stream_dir'], directories['playlist_dir'])

    logging.debug("Attempting to start channel: " + channel)

    # Read all of the shows to be on the channel and trim whitespaces
    shows = config.get(channel, "Shows").split(',')
    shows = [x.strip() for x in shows]

    # Before attempting to start the channel, remove all previous programming for the channel from the
    # XML TV file to avoid, overlapping programme timings
    xmltv.remove_channel_programmes(channel, file_xmltv)

    start_channel(channel, 'IN_ORDER', shows, file_xmltv, directories)

    logging.debug("Finished starting channel: " + channel)

xmltv.remove_past_programmes(file_xmltv)
xmltv.save_to_file(file_xmltv, xmltv_path)
