import os
import re
import subprocess


def generate_concat_playlist(files, playlist_directory, channel_name):
    target_file_path = playlist_directory
    if not target_file_path.endswith('/'):
        target_file_path = target_file_path + '/'
    target_file_path = target_file_path + channel_name + '.txt'
    escaped_files = escape_special_chars(files)

    # If a playlist already exists, delete it so a new one can be created
    if os.path.exists(target_file_path):
        os.remove(target_file_path)

    target_file = open(target_file_path, "w")
    for file in escaped_files:
        target_file.write("file '" + file + "'\n")
    target_file.close()


# Returns a list of all files with full paths in a given directory
def list_files_with_path(directory):
    result = []

    for path in os.listdir(directory):
        full_path = os.path.join(directory, path)
        result.append(full_path)

    return result


# Accepts a file name and returns a tuple of (season, episode)
def parse_season_episode(file_name):
    match = re.search('S(\\d*)E(\\d*)', file_name)
    return match.group(1), match.group(2)


# This function accepts a list of strings and returns a new list with special characters escaped.
# Used to escape special characters in an ffmpeg playlist
def escape_special_chars(input_list):
    chars_to_escape = ['\'', '-', '(', ')']

    result = []
    for curr_file in input_list:
        curr_string = curr_file
        for curr_char in chars_to_escape:
            curr_string = curr_string.replace(curr_char, "'\\" + curr_char + "'")
        result.append(curr_string)
    return result


def get_video_length(filename):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                             "format=duration", "-of",
                             "default=noprint_wrappers=1:nokey=1", filename],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    return float(result.stdout)

