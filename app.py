from tendo import singleton

import configparser
import datetime
import glob
import logging
import logging.handlers
import os
import signal
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

# Default directories to use if unset in config
DEFAULT_WORKING_DIR = '/tmp/HomeBroadcaster/'
DEFAULT_STREAM_DIR = '/var/www/html/tv'

# Default parameters to use for channels if unset in config
DEFAULT_ORDER = 'Ordered'
DEFAULT_SEGMENT_RUNTIME = 20
DEFAULT_CHUNK_SIZE = 1

# Declare the subdirectories to be used
logs_subdir = 'logs/'
playlist_subdir = 'playlists/'
pid_subdir = 'pid/'


def setup_logger(log_level, log_dir):
    log_location = log_directory + 'homeBroadcaster.log'
    log_handler = logging.handlers.RotatingFileHandler(filename=log_location, maxBytes=10_000_000, backupCount=5)
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


def kill_running_pid(pid):
    try:
        os.kill(int(pid), signal.SIGTERM)
    except:
        logging.error("Error ocurred when attempting to kill pid: " + pid)


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


def populate_episode_lengths(directory_full_path, show_name, db_dir):
    series_id = db_utils.get_series_id(show_name, db_dir)
    file_list = playlist_utils.list_files_with_path(directory_full_path)
    for file_full_path in file_list:
        file_name = os.path.basename(file_full_path)
        length = playlist_utils.get_video_length(file_full_path)
        season, episode = playlist_utils.parse_season_episode(os.path.basename(file_name))
        db_utils.save_local_episode(series_id, season, episode, length, file_full_path, db_dir)


# Retrieves and loads all episode information given a source directory
def populate_all_episode_info(show_name, directory_full_path, dirs):
    directory_name = os.path.basename(directory_full_path)
    if not db_utils.is_series_metadata_loaded(show_name, dirs['working_dir']):
        populate_tv_maze_episode_info(show_name, dirs['working_dir'])
        populate_episode_lengths(directory_full_path, show_name, dirs['working_dir'])
        db_utils.update_series_last_updated_time(show_name, dirs['working_dir'])


def start_channel(channel_name, channel_options, shows_list, xmltv_file, dirs):
    db_channel = db_utils.get_channel(channel_name, dirs['working_dir'])

    if db_channel is None:
        shows_concat = ','.join(shows_list)
        db_utils.save_channel(channel_name, channel_options['order'], shows_concat, dirs['working_dir'])
        db_channel = db_utils.get_channel(channel_name, dirs['working_dir'])

    if db_channel['chunkOffset'] is None:
        chunk_offset = 0
    else:
        chunk_offset = db_channel['chunkOffset']

    shows_list = db_channel['shows'].split(',')
    playlist = []

    for curr_show in shows_list:
        curr_series_id = db_utils.get_series_id(curr_show, dirs['working_dir'])
        chunks = db_utils.get_show_in_chunks(curr_series_id, chunk_offset, channel_options['chunk_size'],
                                             channel_options['segment_runtime'] * 60, dirs['working_dir'])




# -----------------SCRIPT STARTS HERE---------------------

try:
    config_path = sys.argv[1]
except Exception:
    raise Exception('No config file passed in arguments!')

try:

    config = configparser.ConfigParser()
    config.optionxform = str
    config.read(config_path)

    # Check the config file for any missing directory parameters and generate the default directories if so
    if config.has_option('General', 'Working Directory'):
        working_directory = clean_directory_path(config.get('General', 'Working Directory'))
    else:
        working_directory = DEFAULT_WORKING_DIR
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
        if not os.path.exists(DEFAULT_STREAM_DIR):
            os.mkdir(DEFAULT_STREAM_DIR)
        stream_directory = DEFAULT_STREAM_DIR

        xmltv_path = DEFAULT_STREAM_DIR + 'xmltv.xml'
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

    # Read in any global default parameters if any and create a global default dict
    # for usage throughout the application
    if config.has_section('Global Defaults'):
        GLOBAL_DEFAULTS = {}
        if config.has_option('Global Defaults', 'Segment Runtime'):
            GLOBAL_DEFAULTS['Segment Runtime'] = config.getint('Global Defaults', 'Segment Runtime')
        if config.has_option('Global Defaults', 'Chunk Size'):
            GLOBAL_DEFAULTS['Chunk Size'] = config.getint('Global Defaults', 'Chunk Size')
        if config.has_option('Global Defaults', 'Order'):
            GLOBAL_DEFAULTS['Order'] = config.get('Global Defaults', 'Order')

    logging.info("Starting the Home Broadcaster application...")

    # Process all shows in the shows config section
    input_shows = dict(config.items('Shows'))
    for show in input_shows:
        populate_series_info(show, directories['working_dir'])
        populate_all_episode_info(show, input_shows[show], directories)

    # Stop any channels that have been removed from the config
    pid_files = playlist_utils.list_files_with_path(directories['pid_dir'])
    for pid_file_path in pid_files:

        pid_channel_name = os.path.basename(pid_file_path).replace(".pid", "")

        if not config.has_section(pid_channel_name):
            old_pid_file = open(pid_file_path)
            pid = old_pid_file.readline().strip()
            old_pid_file.close()

            clear_previous_stream_files(pid_channel_name, directories['stream_dir'], directories['playlist_dir'])
            xmltv.remove_channel(pid_channel_name, file_xmltv)
            xmltv.remove_channel_programmes(pid_channel_name, file_xmltv)
            m3u.remove_channel(pid_channel_name, directories['stream_dir'])

            if check_pid_running(pid):
                logging.debug("Channel currently running but not in config. Stopping channel: " + pid_channel_name)
                kill_running_pid(pid)
            os.remove(pid_file_path)

    # Start any channels that are currently not running
    for channel in config.sections():
        if channel == 'General' or channel == 'Shows':
            continue

        # Check if the channel is currently running and if so, do nothing
        pid_file_path = directories['pid_dir'] + channel + '.pid'
        if os.path.exists(pid_file_path):
            old_pid_file = open(pid_file_path)
            ffmpeg_pid = old_pid_file.readline().strip()
            old_pid_file.close()
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

        # Create dict to hold all options for channel creation and set default values if
        # parameter not present in config
        channel_opts = {}
        if config.has_option(channel, 'Order'):
            channel_opts['order'] = config.get(channel, 'Order')
        else:
            channel_opts['order'] = DEFAULT_ORDER
        if config.has_option(channel, 'Segment Runtime'):
            channel_opts['segment_runtime'] = config.get(channel, 'Segment Runtime')
        else:
            channel_opts['segment_runtime'] = DEFAULT_SEGMENT_RUNTIME
        if config.has_option(channel, 'Chunk Size'):
            channel_opts['chunk_size'] = config.get(channel, 'Chunk Size')
        else:
            channel_opts['chunk_size'] = DEFAULT_CHUNK_SIZE

        # Before attempting to start the channel, remove all previous programming for the channel from the
        # XML TV file to avoid, overlapping programme timings
        xmltv.remove_channel_programmes(channel, file_xmltv)

        start_channel(channel, channel_opts, shows, file_xmltv, directories)

        logging.debug("Finished starting channel: " + channel)

    xmltv.remove_past_programmes(file_xmltv)
    xmltv.save_to_file(file_xmltv, xmltv_path)

except Exception:
    logging.exception("Error occurred in script")
