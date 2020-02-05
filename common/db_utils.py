import sqlite3


def connect_db():
    return sqlite3.connect('episode_info.db')


def initialize_tables():
    create_episode_table()
    create_channels_table()


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


def save_episode_info(series, season, episode, title, subtitle, desc, length, file_name, updated_date):
    conn = connect_db()
    c = conn.cursor()

    params = (series, season, episode, title, subtitle, desc, length, file_name, updated_date)
    c.execute('INSERT INTO episode_info VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', params)
    conn.commit()
    conn.close()

