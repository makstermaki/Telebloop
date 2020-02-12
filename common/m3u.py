import os
import socket


def generate_new_m3u(path):
    target_m3u_path = path
    if not target_m3u_path.endswith('/'):
        target_m3u_path = target_m3u_path + '/'
    target_m3u_path = target_m3u_path + 'streams.m3u'
    target_m3u = open(target_m3u_path, "w")
    target_m3u.write('#EXTM3U - Generated by Home Broadcaster')
    target_m3u.close()


def add_channel_if_not_exists(path, channel):
    target_m3u_path = path
    if not target_m3u_path.endswith('/'):
        target_m3u_path = target_m3u_path + '/'
    target_m3u_path = target_m3u_path + 'streams.m3u'
    with open(target_m3u_path) as f:
        if 'tvg-name=' + channel in f.read():
            # Channel already exists so leave m3u as is
            return
    target_m3u = open(target_m3u_path, "a")
    target_m3u.write('#EXTINF:-1 tvg-ID=' + channel + ' tvg-name=' + channel + ' tvg-logo= group-title=,' + channel + '\n')

    host_ip = socket.gethostbyname(socket.gethostname())
    target_m3u.write('http://' + host_ip + '/streams/' + channel + '.m3u8')
    target_m3u.close()