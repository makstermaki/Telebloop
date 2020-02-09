import common.tv_maze as tv_maze

import sqlite3
import time


def connect_db():
    return sqlite3.connect('episode_info.db')


def initialize_db():
    if table_exists('episode_info') == 0:
        create_episode_table()
    if table_exists('series_lookup') == 0:
        create_series_lookup_table()


def create_episode_table():
    conn = connect_db()
    c = conn.cursor()

    c.execute('''
        CREATE TABLE episode_info (
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


def save_tv_maze_episode_info(series_id, season, episode, title, subtitle, desc):
    conn = connect_db()
    c = conn.cursor()
    params = (series_id, season, episode, title, subtitle, desc)
    c.execute('INSERT INTO episode_info (series_id, season, episode, title, subtitle, description) VALUES (?, ?, ?, ?, ?, ?)', params)
    conn.commit()
    conn.close()


def save_local_episode_info(series_id, season, episode, length, file_path):
    conn = connect_db()
    c = conn.cursor()
    params = (length, file_path, series_id, season, episode,)
    c.execute('''
        UPDATE episode_info
        SET length = ?,
            file_path = ?
        WHERE
            series_id = ? AND
            season = ? AND
            episode = ?
    ''', params)
    conn.commit()
    conn.close()


def get_episode_info_by_season_episode(series_id, season, episode):
    conn = connect_db()
    c = conn.cursor()
    params = (series_id, season, episode)
    c.execute('''
        SELECT *
        FROM episode_info
        WHERE
            series_id = ? AND
            season = ? AND
            episode = ?
    ''', params)
    row = c.fetchone()

    if row is not None:
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


# This function will populate the absolute order column for all episodes in a given series.
# This order will be used to determine playback order for an in order series
def populate_series_absolute_order(series_id):
    conn = connect_db()
    c = conn.cursor()

    c.execute('''
        SELECT season, episode
        FROM episode_info
        WHERE series_id = ?
        ORDER BY season ASC, episode ASC
    ''', (series_id,))

    rows = c.fetchall()
    counter = 0
    for row in rows:
        params = (counter, series_id, row[0], row[1],)
        print("Counter: " + str(counter) + ", Series ID: " + str(series_id) + ", Season: " + str(row[0]) + ', Episode: ' + str(row[1]))
        c.execute('''
            UPDATE episode_info
            SET absolute_order = ?
            WHERE
                series_id = ? AND
                season = ? AND
                episode = ?
        ''', params)
        counter = counter + 1

    conn.commit()
    conn.close()


def create_series_lookup_table():
    conn = connect_db()
    c = conn.cursor()

    # The local series name field is the series name as found in the video files
    c.execute('''
                CREATE TABLE series_lookup (
                    series_id int,
                    local_series_name text,
                    last_updated_date int
                )
            ''')
    conn.commit()
    conn.close()


def save_series_id(series_id, series):
    conn = connect_db()
    c = conn.cursor()

    params = (series_id, series,)
    c.execute('INSERT INTO series_lookup (series_id, local_series_name) VALUES (?, ?)', params)
    conn.commit()
    conn.close()


# Retrieves the TV Maze series ID for a show.
def get_series_id(local_series_name):
    conn = connect_db()
    c = conn.cursor()
    result = c.execute('SELECT series_id FROM series_lookup WHERE local_series_name = ?', (local_series_name,))
    rows = result.fetchall()
    conn.close()
    if len(rows) == 1:
        return rows[0][0]

    # DB doesn't have the series ID so populate it from the TV Maze API
    show_single_search_response = tv_maze.show_single_search(local_series_name)
    series_id = show_single_search_response['id']
    save_series_id(series_id, local_series_name)
    return series_id


def is_series_metadata_loaded(local_series_name):
    conn = connect_db()
    c = conn.cursor()
    c.execute('''
        SELECT last_updated_date
        FROM series_lookup
        WHERE local_series_name = ?
    ''', (local_series_name,))
    result = c.fetchone()
    conn.close()
    if result is None:
        return False
    return True


def update_series_last_updated_time(local_series_name):
    conn = connect_db()
    c = conn.cursor()
    c.execute('''
        UPDATE series_lookup
        SET last_updated_date = ?
        WHERE local_series_name = ?
    ''', (time.time(), local_series_name,))
    conn.commit()
    conn.close()


def create_channels_table():
    conn = connect_db()
    c = conn.cursor()

# Channel type is sequential or random
# Next episode season and num will be the next episode to start streaming from. (Remember, attempt to only create streams for 24 hr intervals)
    c.execute('''
            CREATE TABLE channel (
                channel text,
                order text,
                next_episode int
            )
        ''')
    conn.commit()
    conn.close()


def table_exists(table_name):
    conn = connect_db()
    c = conn.cursor()
    result = c.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    is_exists = False
    if result.fetchall()[0][0] == 1 :
        is_exists = True
    conn.commit()
    conn.close()
    return is_exists
