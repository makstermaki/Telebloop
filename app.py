from tendo import singleton
import os


# Throw an exception if this script is already running
me = singleton.SingleInstance()

input_directory = '/media/TV/Steven Universe'

# This function accepts a list of strings and returns a new list with special characters escaped
def escape_special_characters(input_list):
    chars_to_escape = ['\'', '-', '(', ')']

    result = []
    for curr_file in input_list:
        curr_string = curr_file
        for curr_char in chars_to_escape:
            curr_string = curr_string.replace(curr_char, "'\\" + curr_char + "'")
        result.append(curr_string)
    return result

input_files = []

# Get the full paths for all files in the given directory
for path in os.listdir(input_directory):
    full_path = os.path.join(input_directory, path)
    input_files.append(full_path)

output_file = open("result.txt", 'w')

for curr in escape_special_characters(input_files):
    output_file.write(curr + '\n')
