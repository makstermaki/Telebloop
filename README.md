# Home Broadcaster - PLACEHOLDER
*Name To Be Determined*

This application is for hosting your own IPTV service at home. The application takes a list of
video files as an input and will create a continuous stream that runs 24/7.

This project is heavily inspired by deanochips own project found here: https://github.com/deanochips/HLS-XMLTV---Home-Broadcasting

Essentially I have started this project to recreate what deanochips has created but in Python. This
is meant to be a learning experience while also fixing some of the issues I ran into in the original
source code.

### Media structure requirements
The directory for a TV show must be named the series name. This directory name will called against the TV Maze API to get a matching series. Note that adding the same show from two different directories has not been tested and the outcome is unknown.

The episode files themselves must have season and episode numbers denoted in the format of SxEy where x is the season number and y is the episode number. Zero padding for these numbers is not necessary, the parsing will work either way. The media files that have been tested with this application have all been in the format of **Series Name - SxxEyy - Episode Name**
