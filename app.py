from tendo import singleton

import configparser
import datetime
import glob
import hashlib
import logging
import logging.handlers
import os
import random
import shutil
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
    if not db_utils.is_series_metadata_loaded(show_name, dirs['working_dir']):
        populate_tv_maze_episode_info(show_name, dirs['working_dir'])
        populate_episode_lengths(directory_full_path, show_name, dirs['working_dir'])
        db_utils.update_series_last_updated_time(show_name, dirs['working_dir'])


def start_channel(channel_name, channel_options, shows_list, xmltv_file, dirs):
    db_channel = db_utils.get_channel(channel_name, dirs['working_dir'])

    # Generate the channel configuration hash used to determine if the channel
    # has been updated
    config_string = ' '.join(shows_list) + channel_options['order'] + str(channel_options['segment_runtime']) + str(channel_options['chunk_size'])
    hash_object = hashlib.sha1(config_string.encode())
    curr_config_hash = hash_object.hexdigest()

    if db_channel is None:
        shows_concat = ','.join(shows_list)
        db_utils.save_channel(channel_name, channel_options['order'], shows_concat, curr_config_hash, dirs['working_dir'])
        db_channel = db_utils.get_channel(channel_name, dirs['working_dir'])
    else:
        # Check if the channel is currently running
        pid_file_path = dirs['pid_dir'] + channel_name + '.pid'
        if os.path.exists(pid_file_path):
            old_pid_file = open(pid_file_path)
            ffmpeg_pid = old_pid_file.readline().strip()
            old_pid_file.close()
            if check_pid_running(ffmpeg_pid):
                # If the channel is already running, check if the configuration of the channel
                # has changed. If so, stop the channel and restart it with the updated configuration
                prev_config_hash = db_utils.get_channel_config_hash(channel_name, dirs['working_dir'])

                if (curr_config_hash == prev_config_hash):
                    logging.debug(channel + ' already running, skipping...')
                    return
                else:
                    logging.debug(channel + ' configuration has changed. Restarting channel...')
                    kill_running_pid(ffmpeg_pid)

                    shows_concat = ','.join(shows_list)
                    db_utils.update_and_reset_channel(channel_name, channel_options['order'], shows_concat, curr_config_hash, dirs['working_dir'])
                    db_channel = db_utils.get_channel(channel_name, dirs['working_dir'])

                    clear_previous_stream_files(channel_name, dirs['stream_dir'], dirs['playlist_dir'])
            else:
                # Channel stopped running. Clear the old stream files
                clear_previous_stream_files(channel, dirs['stream_dir'], dirs['playlist_dir'])

    # Before attempting to start the channel, remove all previous programming for the channel from the
    # XML TV file to avoid overlapping programme timings
    xmltv.remove_channel_programmes(channel, file_xmltv)

    # Retrieve the current chunk offset and previously  played chunks from the DB if the channel already exists
    if db_channel['chunkOffset'] is None:
        chunk_offset_list = [0] * len(shows_list)
    else:
        chunk_offset_list = str(db_channel['chunkOffset']).split('|')
        chunk_offset_list = list(map(int, chunk_offset_list))

    if db_channel['playedChunks'] is None:
        previously_played_chunks = []
        for _ in range(len(shows_list)):
            previously_played_chunks.append([])
    else:
        previously_played_chunks = []
        temp_list = []
        prev_chunk_strings = db_channel['playedChunks'].split('|')
        for chunk_string in prev_chunk_strings:
            temp_list.append(chunk_string.split(','))
        for chunk_string_list in temp_list:
            if len(chunk_string_list) == 1 and not chunk_string_list[0]:
                previously_played_chunks.append([])
            else:
                previously_played_chunks.append(list(map(int, chunk_string_list)))

    shows_list = db_channel['shows'].split(',')
    series_id_list = [None] * len(shows_list)

    chunked_shows = [None] * len(shows_list)

    # Retrieve all of the episodes for each show in the channel separated into chunks
    for idx, curr_show in enumerate(shows_list):
        curr_series_id = db_utils.get_series_id(curr_show, dirs['working_dir'])
        series_id_list[idx] = curr_series_id
        chunked_shows[idx] = db_utils.get_show_in_chunks(curr_series_id, chunk_offset_list[idx], channel_options['chunk_size'],
                                                         channel_options['segment_runtime'] * 60, dirs['working_dir'])

        # Remove the previously played chunks
        temp_list = []
        for chunk in chunked_shows[idx]:
            if chunk[0]['absoluteOrder'] not in previously_played_chunks[idx]:
                temp_list.append(chunk)
        chunked_shows[idx] = temp_list

    # If the ordering of the channel is set to random, shuffle the episode chunks retreived from the DB
    if channel_options['order'] == 'Random':
        for show_chunks in chunked_shows:
            random.shuffle(show_chunks)

    # Start adding episode chunks to the playlist until the desired end time is reached
    # DEFAULT END TIME: 5 AM next day
    now = datetime.datetime.now()
    day_delta = datetime.timedelta(days=1)
    target = now + day_delta
    target_timestamp = target.replace(hour=5, minute=0, second=0, microsecond=0).timestamp()
    current_timestamp = now.timestamp()

    # Keep track of the chunks added to the playlist so on next playlist generation, only the unplayed chunks get
    # added first. A chunk ID is defined as the lowest absolute order in the chunk
    added_chunk_ids = previously_played_chunks

    # Used to determine from which list of episodes chunks to add into the playlist
    current_show_index = 0

    playlist = []

    while current_timestamp < target_timestamp:

        # If the list of episode chunks is empty for a show, regenerate the complete set of chunks from the DB
        if not chunked_shows[current_show_index]:
            # Increment the chunk offset so on chunk retrieval, all of the chunks will be different than the previous grab
            chunk_offset_list[current_show_index] = (chunk_offset_list[current_show_index] + 1) % channel_options['chunk_size']
            chunked_shows[current_show_index] = db_utils.get_show_in_chunks(series_id_list[current_show_index],
                                                                            chunk_offset_list[current_show_index],
                                                                            channel_options['chunk_size'],
                                                                            channel_options['segment_runtime'] * 60,
                                                                            dirs['working_dir'])
                                                                                        
            if channel_options['order'] == 'Random':
                random.shuffle(chunked_shows[current_show_index])

            added_chunk_ids[current_show_index].clear()

        chunk_to_add = chunked_shows[current_show_index][0]

        playlist.append(chunk_to_add)
        added_chunk_ids[current_show_index].append(chunk_to_add[0]['absoluteOrder'])

        # Add the runtime of the chunk to the current timestamp
        for episode in chunk_to_add:
            current_timestamp += episode['length']

        del chunked_shows[current_show_index][0]

        current_show_index = (current_show_index + 1) % len(shows_list)

    # If the channel is set to Extra Random, shuffle the playlist of episodes one more time
    if channel_options['order'] == 'Extra Random':
        random.shuffle(playlist)

    flattened_playlist = []
    for sublist in playlist:
        for item in sublist:
            flattened_playlist.append(item)
    playlist = flattened_playlist

    # Save the chunks added to the playlist back to the DB, along with the chunk offset
    played_chunks_string_list = []
    for chunk_list in added_chunk_ids:
        played_chunks_string_list.append(','.join(list(map(str, chunk_list))))
    played_chunks_string = '|'.join(list(map(str, played_chunks_string_list)))
    chunk_offset_string = '|'.join(list(map(str, chunk_offset_list)))
    db_utils.update_channel_chunks(channel, played_chunks_string, chunk_offset_string, dirs['working_dir'])

    # Generate the list of file paths for the FFMPEG playlist along with the XMLTV file
    xmltv.add_channel_if_not_exists(xmltv_file, channel_name)
    tv_guide_time = now.timestamp()
    time_format = '%Y%m%d%H%M%S %z'
    playlist_filepaths = []
    for episode in playlist:
        playlist_filepaths.append(episode['filePath'])

        start_time = time.strftime(time_format, time.localtime(tv_guide_time))
        stop_time = time.strftime(time_format, time.localtime(tv_guide_time + episode['length']))

        xmltv.add_programme(xmltv_file, channel_name, start_time, stop_time, episode['title'],
                            episode['subtitle'], episode['description'])

        tv_guide_time = tv_guide_time + episode['length']

    # Generate the FFMPEG concat playlist
    concat_playlist = playlist_utils.generate_concat_playlist(playlist_filepaths, dirs['playlist_dir'], channel_name)

    # At this point, the FFMPEG playlist has been generated so the stream can be started
    m3u8_path = dirs['stream_dir'] + channel_name + '.m3u8'

    with open(dirs['log_dir'] + 'ffmpeg.log', "w") as ffmpeg_log_file:
        proc = subprocess.Popen([
            "ffmpeg", "-re", "-loglevel", "warning", "-fflags", "+genpts", "-f", "concat", "-safe", "0", "-i",
            concat_playlist, "-map", "0:a?", "-map", "0:v?", "-strict", "-2", "-dn", "-c", "copy",
            "-hls_time", "10", "-hls_list_size", "6", "-hls_wrap", "7", m3u8_path
        ], stderr=ffmpeg_log_file)

    # Save the PID of the FFMPEG process to a file which will be used to determine if a channel is currently running
    pid_file = open(dirs['pid_dir'] + channel_name + ".pid", "w")
    pid_file.write(str(proc.pid))
    pid_file.close()

    # Add the channel to the central streams playlist
    if 'logo' in channel_options:
        m3u.add_channel_with_logo(channel_name, channel_options['logo'], channel_options['domain_name'], channel_options['port'], channel_options['auth'], dirs['stream_dir'])
    else:
        m3u.add_channel(channel_name, channel_options['domain_name'], channel_options['port'], channel_options['auth'], dirs['stream_dir'])


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

    # Chec kif a domain name should be used in the stream URLs
    domain_name = None
    if config.has_option('General', 'Domain Name'):
        domain_name = config.get('General', 'Domain Name')

    # Check if a port to use is set in the config
    port = None
    if config.has_option('General', 'Port'):
        port = config.get('General', 'Port')

    # Check if authentication parameters are set in the config
    auth_options = {}
    if (config.has_option('Authentication', 'Username') and config.has_option('Authentication', 'Password')):
        auth_options['Username'] = config.get('Authentication', 'Username')
        auth_options['Password'] = config.get('Authentication', 'Password')

    logo_directory = None
    if config.has_option('General', 'Logo Directory'):
        # Create the channel logo directory under the stream directory
        logo_directory = stream_directory
        if not logo_directory.endswith('/'):
            logo_directory = logo_directory + '/'
        logo_directory = logo_directory + 'logo'
        if not os.path.exists(logo_directory):
            os.mkdir(logo_directory)

        # Copy all the files from the user passed logo directory to the streams logo subdirectory
        input_logo_dir = config.get('General', 'Logo Directory')
        logo_paths = playlist_utils.list_files_with_path(input_logo_dir)
        for curr_path in logo_paths:
            shutil.copy2(curr_path, logo_directory)

    if config.has_option('General', 'Log Level'):
        logging_level = logging.getLevelName(config.get('General', 'Log Level'))
    else:
        logging_level = logging.INFO

    # Create a dictionary for all of the working directories
    directories = {
        'working_dir': working_directory,
        'stream_dir': stream_directory,
        'logo_dir': logo_directory,
        'playlist_dir': playlist_directory,
        'pid_dir': pid_directory,
        'log_dir': log_directory
    }

    setup_logger(logging_level, directories['log_dir'])
    db_utils.initialize_db(directories['working_dir'])

    # Read in any global default parameters if any and create a global default dict
    # for usage throughout the application
    GLOBAL_DEFAULTS = {}
    if config.has_section('Global Defaults'):
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

    # Stop and delete channels that have been removed from the config
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
            db_utils.delete_channel(pid_channel_name, directories['working_dir'])

            if check_pid_running(pid):
                logging.debug("Channel currently running but not in config. Stopping channel: " + pid_channel_name)
                kill_running_pid(pid)
            os.remove(pid_file_path)

    # Generate the parent m3u file if not exists
    m3u_path = directories['stream_dir']
    if not m3u_path.endswith('/'):
        m3u_path = m3u_path + '/'
    m3u_path = m3u_path + "tv.m3u"
    m3u.generate_m3u_if_not_exists(m3u_path)

    # Start any channels that are currently not running
    for channel in config.sections():
        if channel == 'General' or channel == 'Shows' or channel == 'Global Defaults' or channel == 'Authentication':
            continue

        logging.debug("Processing channel: " + channel)

        # Read all of the shows to be on the channel and trim whitespaces
        shows = config.get(channel, "Shows").split(',')
        shows = [x.strip() for x in shows]

        # Create dict to hold all options for channel creation and set default values if
        # parameter not present in config
        channel_opts = {}
        if config.has_option(channel, 'Order'):
            channel_opts['order'] = config.get(channel, 'Order')
        else:
            if "Order" in GLOBAL_DEFAULTS:
                channel_opts['order'] = GLOBAL_DEFAULTS["Order"]
            else:
                channel_opts['order'] = DEFAULT_ORDER
        if config.has_option(channel, 'Segment Runtime'):
            channel_opts['segment_runtime'] = int(config.get(channel, 'Segment Runtime'))
        else:
            if "Segment Runtime" in GLOBAL_DEFAULTS:
                channel_opts['segment_runtime'] = GLOBAL_DEFAULTS["Segment Runtime"]
            else:
                channel_opts['segment_runtime'] = DEFAULT_SEGMENT_RUNTIME
        if config.has_option(channel, 'Chunk Size'):
            channel_opts['chunk_size'] = int(config.get(channel, 'Chunk Size'))
        else:
            if "Chunk Size" in GLOBAL_DEFAULTS:
                channel_opts['chunk_size'] = GLOBAL_DEFAULTS["Chunk Size"]
            else:
                channel_opts['chunk_size'] = DEFAULT_CHUNK_SIZE
        if config.has_option(channel, 'Logo'):
            channel_opts['logo'] = config.get(channel, 'Logo')
        if "Username" in auth_options and "Password" in auth_options:
            channel_opts['auth'] = {}
            channel_opts['auth']['username'] = auth_options['Username']
            channel_opts['auth']['password'] = auth_options['Password']
        channel_opts['domain_name'] = domain_name
        channel_opts['port'] = port

        start_channel(channel, channel_opts, shows, file_xmltv, directories)

        logging.debug("Finished processing channel: " + channel)

    xmltv.remove_past_programmes(file_xmltv)
    xmltv.save_to_file(file_xmltv, xmltv_path)

    logging.info("Application has finished running. Exiting...")

except Exception as err:
    logging.exception("Error occurred in script")

sys.exit()
