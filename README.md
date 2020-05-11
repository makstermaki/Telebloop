# Telebloop

Telebloop is an application for hosting your own IPTV service at home. The application takes directories of video files and
creates HLS video streams from them. A XMLTV file will be generated for each channel which contains the TV guide
information.

### Usage

In order for Telebloop to run, a config file needs to be passed as the first argument when running. An example
config file can be found in the repo. The config file contains comments describing the different fields but before
editing the config, the terms segment and chunk need to be defined.

**Chunk** - A grouping of segments ordered in airing order

**Segment** - A grouping of episodes in airing order with a minimum runtime

The purpose of these 2 parameters is to be able to cleanly switch between multiple shows on the same channel which may
have different episodes lengths while replicating the standard TV channel experience. 

As an example, lets say you have 2 shows on the same channel. One show has an episode length of around 12 minutes
(E.g. a cartoon where 2 episodes play in a 30 min block) and the other has an episode length of around 23 minutes
(E.g. a standard show where a single episode plays in a 30 min block). If you wanted to replicate
the standard TV experience, you would want to play 2 of the 12 minute episodes for every 1 of the 23 minute episodes.
To achieve this, a segment size of 20 minutes would be set along size a chunk size of 1. What this means is that
episodes will be added to a segment until a runtime of 20 minutes is reached. The segments are then added
to a chunk until the chunk size is reached, in this case its 1 so there is a single segment. This means for the first
show, 2 episodes will exist in the chunk while for the second show, only 1 episode will be in a chunk. The application
will then alternate between playing a chunk from show one and the a chunk of show two, thus replicating the TV
experience.

### Media structure requirements
All of the episodes for a show need to be kept in a single directory with no subdirectories. The name of the show set
in the config file will then be used to look up the episodes details on TV Maze.

The episode files themselves must have season and episode numbers denoted in the format of SxEy where x is the season
number and y is the episode number. Zero padding for these numbers is not necessary, the parsing will work either way.
The media files that have been tested with this application have all been in the format of **Series Name - SxxEyy - Episode Name**
