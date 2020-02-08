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
                root.remove(child)
    return root


def add_channel(root, channel):
    channel_node = ET.Element('channel')
    channel_node.attrib['id'] = channel + '.tv'
    display_node = ET.Element('display-name')
    display_node.attrib['lang'] = 'en'
    display_node.text = channel + '.tv'
    channel_node.append(display_node)
    root.append(channel_node)


def add_programme(root, channel, start_time, stop_time, title, subtitle, desc):
    programme_node = ET.Element('programme')
    programme_node.attrib['channel'] = channel + '.tv'
    programme_node.attrib['start'] = start_time
    programme_node.attrib['stop'] = stop_time

    title_node = ET.Element('title')
    title_node.attrib['lang'] = 'en'
    title_node.text = title
    programme_node.append(title_node)

    subtitle_node = ET.Element('sub-title')
    subtitle_node.attrib['lang'] = 'en'
    subtitle_node.text = subtitle
    programme_node.append(subtitle_node)

    desc_node = ET.Element('desc')
    desc_node.attrib['lang'] = 'en'
    desc_node.text = desc
    programme_node.append(desc_node)

    root.append(programme_node)


tree = ET.parse('/Users/andrew/Desktop/xmltv.xml')
xml_root = tree.getroot()
remove_past_episodes(xml_root)
add_channel(xml_root, 'NEW_CHANNEL')
add_programme(xml_root, 'NEW_CHANNEL', 'START_TIME', 'STOP_TIME', 'TITLE', 'SUBTITLE', 'DESC DESC DESC DESC')
tree.write('/Users/andrew/Desktop/NEW_xmltv.xml')