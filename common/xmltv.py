from datetime import datetime, date
from dateutil.parser import parse
import time
import xml.etree.ElementTree as ET


# This function removes all programme nodes where the stop time is before the current time
def remove_past_episodes(root):
    for child in root:
        if child.tag == 'programme':
            stop_time = parse(child.attrib['stop'], fuzzy=True).timestamp()
            curr_time = int(time.time())
            if curr_time > stop_time:
                print(child.attrib['stop'])
                root.remove(child)
    tree.write('/Users/andrew/Desktop/NEW_xmltv.xml')



tree = ET.parse('/Users/andrew/Desktop/xmltv.xml')
root = tree.getroot()
remove_past_episodes(root)