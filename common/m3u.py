import os
import socket


def generate_new_m3u(m3u_path):
    target_m3u = open(m3u_path, "w")
    target_m3u.write('#EXTM3U - Generated by Home Broadcaster\n')
    target_m3u.close()


def add_channel_if_not_exists(m3u_dir, channel):
    target_m3u_path = m3u_dir
    if not target_m3u_path.endswith('/'):
        target_m3u_path = target_m3u_path + '/'
    target_m3u_path = target_m3u_path + 'tv.m3u'
    if not os.path.exists(target_m3u_path):
        generate_new_m3u(target_m3u_path)

    with open(target_m3u_path) as f:
        if 'tvg-name=' + channel in f.read():
            # Channel already exists so leave m3u as is
            return
    target_m3u = open(target_m3u_path, "a")
    target_m3u.write('\n#EXTINF:-1 tvg-ID=' + channel + '.tv' + ' tvg-name=' + channel + ' tvg-logo= group-title=,' + channel)

    host_ip = socket.gethostbyname(socket.gethostname())
    target_m3u.write('\nhttp://192.168.1.79/tv/' + channel + '.m3u8') # TODO Must dynamically generate the IP address
    target_m3u.close()
