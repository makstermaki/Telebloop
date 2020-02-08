import os
import re
import subprocess


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


def get_length(filename):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                             "format=duration", "-of",
                             "default=noprint_wrappers=1:nokey=1", filename],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    return float(result.stdout)

