import common.tv_maze as tv_maze

import sqlite3
import time


def connect_db(db_dir):
    return sqlite3.connect(db_dir + 'data.db')


def initialize_db(db_dir):
    if table_exists('episodes', db_dir) == 0:
        create_episode_table(db_dir)
    if table_exists('series', db_dir) == 0:
        create_series_table(db_dir)
    if table_exists('channels', db_dir) == 0:
        create_channels_table(db_dir)


def create_episode_table(db_dir):
    conn = connect_db(db_dir)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE episodes (
            series_id int,
            absolute_order int,
            season integer,
            episode integer,
            title text,
            subtitle text,
            description text,
            length real,
            file_path text
        )
    ''')
    conn.commit()
    conn.close()


def save_tv_maze_episode(series_id, season, episode, title, subtitle, desc, db_dir):
    conn = connect_db(db_dir)
    c = conn.cursor()
    params = (series_id, season, episode, title, subtitle, desc)
    c.execute('INSERT INTO episodes (series_id, season, episode, title, subtitle, description) VALUES (?, ?, ?, ?, ?, ?)', params)
    conn.commit()
    conn.close()


def save_local_episode(series_id, season, episode, length, file_path, db_dir):
    conn = connect_db(db_dir)
    c = conn.cursor()
    params = (length, file_path, series_id, season, episode,)
    c.execute('''
        UPDATE episodes
        SET length = ?,
            file_path = ?
        WHERE
            series_id = ? AND
            season = ? AND
            episode = ?
    ''', params)
    conn.commit()
    conn.close()


def get_episode_by_season_episode(series_id, season, episode, db_dir):
    conn = connect_db(db_dir)
    c = conn.cursor()
    params = (series_id, season, episode)
    c.execute('''
        SELECT *
        FROM episodes
        WHERE
            series_id = ? AND
            season = ? AND
            episode = ?
    ''', params)
    row = c.fetchone()

    if not (row is None):
        result = {
            'seriesID': row[0],
            'absoluteOrder': row[1],
            'season': row[2],
            'episode': row[3],
            'title': row[4],
            'subtitle': row[5],
            'description': row[6],
            'length': row[7],
            'filePath': row[8]
        }
    else:
        result = None

    conn.close()
    return result


def get_episode_by_absolute_order(series_id, absolute_order, db_dir):
    conn = connect_db(db_dir)
    c = conn.cursor()
    params = (series_id, absolute_order)
    c.execute('''
        SELECT *
        FROM episodes
        WHERE
            series_id = ? AND
            absolute_order = ?
    ''', params)
    row = c.fetchone()

    if not (row is None):
        result = {
            'seriesID': row[0],
            'absoluteOrder': row[1],
            'season': row[2],
            'episode': row[3],
            'title': row[4],
            'subtitle': row[5],
            'description': row[6],
            'length': row[7],
            'filePath': row[8]
        }
    else:
        result = None

    conn.close()
    return result


def get_episodes_in_order(series_id, absolute_order, db_dir):
    conn = connect_db(db_dir)
    c = conn.cursor()
    c.execute('''
        SELECT *
        FROM episodes
        WHERE
            series_id = ? AND
            absolute_order >= ? AND
            file_path IS NOT NULL
        ORDER BY
            absolute_order asc
    ''', (series_id, absolute_order))
    rows = c.fetchall()

    result = []
    for row in rows:
        result.append({
            'seriesID': row[0],
            'absoluteOrder': row[1],
            'season': row[2],
            'episode': row[3],
            'title': row[4],
            'subtitle': row[5],
            'description': row[6],
            'length': row[7],
            'filePath': row[8]
        })
    return result


# This function will populate the absolute order column for all episodes in a given series.
# This order will be used to determine playback order for an in order series
def populate_series_absolute_order(series_id, db_dir):
    conn = connect_db(db_dir)
    c = conn.cursor()

    c.execute('''
        SELECT season, episode
        FROM episodes
        WHERE series_id = ?
        ORDER BY season ASC, episode ASC
    ''', (series_id,))

    rows = c.fetchall()
    counter = 0
    for row in rows:
        params = (counter, series_id, row[0], row[1],)
        c.execute('''
            UPDATE episodes
            SET absolute_order = ?
            WHERE
                series_id = ? AND
                season = ? AND
                episode = ?
        ''', params)
        counter = counter + 1

    conn.commit()
    conn.close()


def create_series_table(db_dir):
    conn = connect_db(db_dir)
    c = conn.cursor()

    # The local series name field is the series name as found in the video files
    c.execute('''
                CREATE TABLE series (
                    series_id int,
                    local_series_name text,
                    last_updated_date int
                )
            ''')
    conn.commit()
    conn.close()


def save_series(local_series_name, db_dir):
    get_series_id(local_series_name, db_dir)


def save_series_id(series_id, series, db_dir):
    conn = connect_db(db_dir)
    c = conn.cursor()
    params = (series_id, series,)
    c.execute('INSERT INTO series (series_id, local_series_name) VALUES (?, ?)', params)
    conn.commit()
    conn.close()


# Retrieves the TV Maze series ID for a show.
def get_series_id(local_series_name, db_dir):
    conn = connect_db(db_dir)
    c = conn.cursor()
    result = c.execute('SELECT series_id FROM series WHERE local_series_name = ?', (local_series_name,))
    rows = result.fetchall()
    conn.close()
    if len(rows) == 1:
        return rows[0][0]

    # DB doesn't have the series ID so populate it from the TV Maze API
    show_single_search_response = tv_maze.show_single_search(local_series_name)
    series_id = show_single_search_response['id']
    save_series_id(series_id, local_series_name, db_dir)
    return series_id


def is_series_metadata_loaded(local_series_name, db_dir):
    conn = connect_db(db_dir)
    c = conn.cursor()
    c.execute('''
        SELECT last_updated_date
        FROM series
        WHERE local_series_name = ?
    ''', (local_series_name,))
    result = c.fetchone()
    conn.close()
    if result is None or result[0] is None:
        return False
    return True


def update_series_last_updated_time(local_series_name, db_dir):
    conn = connect_db(db_dir)
    c = conn.cursor()
    c.execute('''
        UPDATE series
        SET last_updated_date = ?
        WHERE local_series_name = ?
    ''', (time.time(), local_series_name,))
    conn.commit()
    conn.close()


def create_channels_table(db_dir):
    conn = connect_db(db_dir)
    c = conn.cursor()

# Channel type is sequential or random
# Next episode season and num will be the next episode to start streaming from. (Remember, attempt to only create streams for 24 hr intervals)
    c.execute('''
            CREATE TABLE channels (
                channel text,
                playback_order text,
                shows text,
                next_episode text,
                played_chunks text,
                chunk_offset int
            )
        ''')
    conn.commit()
    conn.close()


def save_channel(channel, order, shows, db_dir):
    conn = connect_db(db_dir)
    c = conn.cursor()

    params = (channel, order, shows)
    c.execute('''
        INSERT INTO channels (channel, playback_order, shows)
        VALUES (?, ?, ?)
    ''', params)
    conn.commit()
    conn.close()


def delete_channel(channel, db_dir):
    conn = connect_db(db_dir)
    c = conn.cursor()

    params = (channel,)
    c.execute('''
        DELETE FROM channels
        WHERE channel = ?
    ''', params)

    conn.commit()
    conn.close()


def update_channel_next_episode(channel, next_episode, db_dir):
    conn = connect_db(db_dir)
    c = conn.cursor()
    c.execute('''
        UPDATE channels
        SET next_episode = ?
        WHERE channel = ?
    ''', (next_episode, channel))
    conn.commit()
    conn.close()


def update_channel_chunks(channel, played_chunks, chunk_offsets, db_dir):
    conn = connect_db(db_dir)
    c = conn.cursor()
    c.execute('''
        UPDATE channels
        SET played_chunks = ?,
            chunk_offset = ?
        WHERE channel = ?
    ''', (played_chunks, chunk_offsets, channel))
    conn.commit()
    conn.close()


def get_channel(channel, db_dir):
    conn = connect_db(db_dir)
    c = conn.cursor()
    c.execute('''
        SELECT *
        FROM channels
        WHERE channel = ?
    ''', (channel, ))
    result = c.fetchone()
    conn.close()
    if not (result is None):
        return {
            'channel': result[0],
            'playbackOrder': result[1],
            'shows': result[2],
            'nextEpisode': str(result[3]),
            'playedChunks': result[4],
            'chunkOffset': result[5]
        }
    return None


""" Retrieves all episodes for a show split into chunks.
    
    A chunk is made up of a number of segments.
    A segment is a grouping of the minimum number of episodes with a runtime greater than
        the user defined runtime
"""
def get_show_in_chunks(series_id, chunk_offset, segments_per_chunk, segment_runtime, db_dir):

    # First get all the episodes in order
    db_episodes = get_episodes_in_order(series_id, 0, db_dir)

    # Separate the list of episodes into chunks
    chunks_list = []
    curr_chunk = []
    curr_segment = []
    curr_segment_runtime = 0
    curr_chunk_segment_count = 0

    # First if a non-zero chunk offset is set, create a chunk up to the offset
    if chunk_offset != 0:
        chunks_list.append(db_episodes[:chunk_offset])
        db_episodes = db_episodes[chunk_offset:]

    for idx, episode in enumerate(db_episodes):

        curr_segment.append(episode)
        curr_segment_runtime += episode['length']
        # Keep adding to the current segment until the minimum segment runtime is reached
        if curr_segment_runtime < segment_runtime:
            continue

        # The current segment has now passed the minimum segment runtime and can be added to the current chunk
        curr_chunk.extend(curr_segment)
        curr_chunk_segment_count += 1
        curr_segment = []
        curr_segment_runtime = 0

        # If the current chunk has the minimum number of segments required, add the chunk to
        # the list of chunks
        if curr_chunk_segment_count >= segments_per_chunk:
            chunks_list.append(curr_chunk)
            curr_chunk = []
            curr_chunk_segment_count = 0

    # Add any partial chunk or segment which may have been generated at the end
    if curr_segment:
        curr_chunk.extend(curr_segment)
    if curr_chunk:
        chunks_list.append(curr_chunk)

    return chunks_list


def table_exists(table_name, db_dir):
    conn = connect_db(db_dir)
    c = conn.cursor()
    c.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    is_exists = False
    if c.fetchall()[0][0] == 1:
        is_exists = True
    conn.close()
    return is_exists
