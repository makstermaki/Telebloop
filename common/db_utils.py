import sqlite3


def connect_db():
    return sqlite3.connect('episode_info.db')


def initialize_tables():
    create_episode_table()
    create_channels_table()
    create_series_lookup_table()


def create_episode_table():
    conn = connect_db()
    c = conn.cursor()

    c.execute('''
        CREATE TABLE episode_info (
            series text,
            season integer,
            episode integer,
            title text,
            subtitle text,
            description text,
            length real,
            file_name text, 
            last_updated_date integer
        )
    ''')
    conn.commit()
    conn.close()


def save_tv_maze_episode_info(series, season, episode, title, subtitle, desc, file_name, updated_date):
    conn = connect_db()
    c = conn.cursor()

    if table_exists('episode_info') == 0:
        create_episode_table()

    # params = (series, season, episode, title, subtitle, desc, length, file_name, updated_date)
    # c.execute('INSERT INTO episode_info VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', params)
    conn.commit()
    conn.close()


def create_series_lookup_table():
    conn = connect_db()
    c = conn.cursor()

    # The local series name field is the series name as found in the video files
    c.execute('''
                CREATE TABLE series_lookup (
                    series_id int,
                    local_series_name text
                )
            ''')
    conn.commit()
    conn.close()


def save_series_id(series_id, series):
    conn = connect_db()
    c = conn.cursor()

    if table_exists('series_lookup') == 0:
        create_series_lookup_table()

    params = (series_id, series,)
    c.execute('INSERT INTO series_lookup VALUES (?, ?)', params)
    conn.commit()
    conn.close()


def create_channels_table():
    conn = connect_db()
    c = conn.cursor()

# Channel type is sequential or random
# Next episode season and num will be the next episode to start streaming from. (Remember, attempt to only create streams for 24 hr intervals)
    c.execute('''
            CREATE TABLE channel_state (
                channel text,
                type text,
                next_episode_season int,
                next_episode_num int
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
