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
    if result[0] is None:
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
                next_episode string
            )
        ''')
    conn.commit()
    conn.close()


def save_channel(channel, order, shows, db_dir):
    next_episode_string = ""
    for i in range(len(shows)):
        next_episode_string += "0,"
    next_episode_string = next_episode_string[:-1]

    conn = connect_db(db_dir)
    c = conn.cursor()

    params = (channel, order, shows, next_episode_string)
    c.execute('''
        INSERT INTO channels (channel, playback_order, shows, next_episode)
        VALUES (?, ?, ?, ?)
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


def get_channel(channel, db_dir):
    conn = connect_db(db_dir)
    c = conn.cursor()
    c.execute('''
        SELECT *
        FROM channels
        WHERE channel = ?
    ''', (channel, ))
    result = c.fetchone()
    conn.commit()
    conn.close()
    if not (result is None):
        return {
            'channel': result[0],
            'playbackOrder': result[1],
            'shows': result[2],
            'nextEpisode': str(result[3])
        }
    return None


def table_exists(table_name, db_dir):
    conn = connect_db(db_dir)
    c = conn.cursor()
    c.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    is_exists = False
    if c.fetchall()[0][0] == 1:
        is_exists = True
    conn.close()
    return is_exists
