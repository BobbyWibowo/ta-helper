import apprise
from distutils.util import strtobool
from dotenv import load_dotenv
import html2text
import logging
import os
import requests
import re
import sys
import time

# Configure logging.
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter(fmt='%(asctime)s %(filename)s:%(lineno)s %(levelname)-8s %(message)s',
                              datefmt='%d-%b-%y %H:%M:%S')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Pull configuration details from .env file.
load_dotenv()
NOTIFICATIONS_ENABLED = bool(strtobool(os.environ.get("NOTIFICATIONS_ENABLED", 'False')))
GENERATE_NFO = bool(strtobool(os.environ.get("GENERATE_NFO", 'False')))
SYMLINK_SUBS = bool(strtobool(os.environ.get("SYMLINK_SUBS", 'False')))
FROMADDR = str(os.environ.get("MAIL_USER"))
RECIPIENTS = str(os.environ.get("MAIL_RECIPIENTS"))
RECIPIENTS = RECIPIENTS.split(',')
TA_MEDIA_FOLDER = str(os.environ.get("TA_MEDIA_FOLDER"))
TA_SERVER = str(os.environ.get("TA_SERVER"))
TA_TOKEN = str(os.environ.get("TA_TOKEN"))
TA_CACHE = str(os.environ.get("TA_CACHE"))
TA_CACHE_DOCKER = bool(strtobool(os.environ.get("TA_CACHE_DOCKER", 'False')))
TARGET_FOLDER = str(os.environ.get("TARGET_FOLDER"))
APPRISE_LINK = str(os.environ.get("APPRISE_LINK"))
QUICK = bool(strtobool(os.environ.get("QUICK", 'True')))
CLEANUP_DELETED_VIDEOS = bool(strtobool(str(os.environ.get("CLEANUP_DELETED_VIDEOS"))))

logger.setLevel(os.environ.get("LOGLEVEL", "INFO"))

def cache_path(cache):
    if TA_CACHE_DOCKER:
        return TA_CACHE + cache.replace("/cache", "", 1)
    else:
        return TA_CACHE + cache

def xmlesc(s):
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    s = s.replace('"', "&quot;")
    s = s.replace("'", "&apos;")
    return s

def setup_new_channel_resources(chan_name, chan_data):
    logger.info("New channel \"%s\", setup resources.", chan_name)
    if TA_CACHE == "":
        logger.info("No TA_CACHE available so cannot setup symlinks to cache files.")
    else:
        # Link the channel logo from TA docker cache into target folder for media managers
        # and file explorers. Provide cover.jpg, poster.jpg and banner.jpg symlinks.
        channel_thumb_path = cache_path(chan_data['channel_thumb_url'])
        logger.info("Symlink cache %s thumb to poster, cover and folder.jpg files.", channel_thumb_path)
        os.symlink(channel_thumb_path, TARGET_FOLDER + "/" + chan_name + "/" + "poster.jpg")
        os.symlink(channel_thumb_path, TARGET_FOLDER + "/" + chan_name + "/" + "cover.jpg")
        folder_symlink = TARGET_FOLDER + "/" + chan_name + "/" + "folder.jpg"
        os.symlink(channel_thumb_path, folder_symlink)
        channel_banner_path = cache_path(chan_data['channel_banner_url'])
        os.symlink(channel_banner_path, TARGET_FOLDER + "/" + chan_name + "/" + "banner.jpg")

    # Generate tvshow.nfo for media managers, no TA_CACHE required.
    logger.info("Generating %s", TARGET_FOLDER + "/" + chan_name + "/" + "tvshow.nfo")
    f = open(TARGET_FOLDER + "/" + chan_name + "/" + "tvshow.nfo", "w+")
    f.write("<?xml version=\"1.0\" encoding=\"utf-8\" standalone=\"yes\"?>\n<tvshow>\n\t" +
            "<title>" + xmlesc(chan_data['channel_name'] or chan_data['channel_id']) + "</title>\n\t" +
            "<showtitle>" + xmlesc(chan_data['channel_name'] or chan_data['channel_id']) + "</showtitle>\n\t" +
            "<youtubemetadataid>" + chan_data['channel_id'] + "</youtubemetadataid>\n\t" +
            #"<lockdata>false</lockdata>\n\t" +
            "<plot>" + xmlesc(chan_data['channel_description'] or "") + "</plot>\n\t" +
            "<outline>" + xmlesc(chan_data['channel_description'] or "") + "</outline>\n\t" +
            "<art>\n\t\t<poster>" + folder_symlink + "</poster>\n\t</art>\n\t" +
            "<premiered>" + chan_data['channel_last_refresh'] + "</premiered>\n\t"+
            "<releasedate>" + chan_data['channel_last_refresh'] + "</releasedate></tvshow>")
    f.close()

def setup_new_channel_playlist_resources(chan_name, chan_data, playlist_name, playlist_data, season_num):
    logger.info("New playlist \"%s\", setup resources.", playlist_name)
    if TA_CACHE == "":
        logger.info("No TA_CACHE available so cannot setup symlinks to cache files.")
    else:
        if 'no_playlist' in playlist_data and playlist_data['no_playlist'] == True:
            playlist_thumb_path = cache_path(chan_data['channel_thumb_url'])
        else:
            # Link the playlist thumb from TA docker cache into target folder for media managers
            # and file explorers.
            playlist_thumb_path = cache_path(playlist_data['playlist_thumbnail'])

        logger.info("Symlink cache %s thumb to poster.jpg file.", playlist_thumb_path)
        poster_symlink = TARGET_FOLDER + "/" + chan_name + "/" + playlist_name + "/" + "poster.jpg"
        os.symlink(playlist_thumb_path, poster_symlink)

    # Generate season.nfo for media managers, no TA_CACHE required.
    logger.info("Generating %s", TARGET_FOLDER + "/" + chan_name + "/" + playlist_name + "/" + "season.nfo")
    f = open(TARGET_FOLDER + "/" + chan_name + "/" + playlist_name + "/" + "season.nfo", "w+")
    f.write("<?xml version=\"1.0\" encoding=\"utf-8\" standalone=\"yes\"?>\n<season>\n\t" +
            "<title>" + xmlesc(playlist_name or playlist_data['playlist_id']) + "</title>\n\t" +
            "<showtitle>" + xmlesc(chan_data['channel_name'] or chan_data['channel_id']) + "</showtitle>\n\t" +
            "<youtubemetadataid>" + playlist_data['playlist_id'] + "</youtubemetadataid>\n\t" +
            #"<lockdata>false</lockdata>\n\t" +
            "<plot>" + xmlesc(playlist_data['playlist_description'] or "") + "</plot>\n\t" +
            "<outline>" + xmlesc(playlist_data['playlist_description'] or "") + "</outline>\n\t" +
            "<art>\n\t\t<poster>" + poster_symlink + "</poster>\n\t</art>\n\t" +
            "<premiered>" + playlist_data['playlist_last_refresh'] + "</premiered>\n\t" +
            "<releasedate>" + playlist_data['playlist_last_refresh'] + "</releasedate>\n\t" +
            "<seasonnumber>" + str(season_num) + "</seasonnumber>\n</season>")
    f.close()

def generate_new_video_nfo(chan_name, playlist_name, title, video_meta_data, episode_num, season_num):
    logger.info("Generating video NFO file for \"%s\": %s", video_meta_data['channel']['channel_name'], video_meta_data['title'])
    # TA has added a new video. Create an NFO file for media managers.
    title = title.replace('.mp4','.nfo')
    f = open(TARGET_FOLDER + "/" + chan_name + "/" + playlist_name + "/" + title, "w+")
    f.write("<?xml version=\"1.0\" encoding=\"utf-8\" standalone=\"yes\"?>\n<episodedetails>\n\t" +
        "<title>" + xmlesc(video_meta_data['title']) + "</title>\n\t" +
        "<showtitle>" + xmlesc(video_meta_data['channel']['channel_name']) + "</showtitle>\n\t" +
        "<youtubemetadataid>" + video_meta_data['youtube_id'] + "</youtubemetadataid>\n\t" +
        #"<lockdata>false</lockdata>\n\t" +
        "<plot>" + xmlesc(video_meta_data['description']) + "</plot>\n\t" +
        "<aired>" + video_meta_data['published'] + "</aired>\n\t" +
        "<season>" + str(season_num) + "</season>\n\t" +
        "<episode>" + str(episode_num) + "</episode>\n</episodedetails>")
    f.close()

def generate_new_video_sub(chan_name, playlist_name, title, video_meta_data):
    logger.info("Symlink subtitle for \"%s\": %s", video_meta_data['channel']['channel_name'], video_meta_data['title'])
    # TA has added a new video. Create a symlink to subtitles.
    video_basename = os.path.splitext(video_meta_data['media_url'])[0]
    os.symlink(TA_MEDIA_FOLDER + video_basename + ".en.vtt", TARGET_FOLDER + "/" + chan_name + "/" + playlist_name + "/" + title.replace(".mp4",".eng.vtt"))

def notify(video_meta_data):

    # Send a notification via apprise library.
    logger.info("Sending new video notification \"%s\": %s", video_meta_data['channel']['channel_name'],
                video_meta_data['title'])

    email_body = '<!DOCTYPE PUBLIC “-//W3C//DTD XHTML 1.0 Transitional//EN” '
    email_body += '“https://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd”>' + '\n'
    email_body += '<html xmlns="http://www.w3.org/1999/xhtml">' + '\n'
    email_body += '<head>' + '\n\t'
    email_body += '<title>' + video_meta_data['title'] + '</title>' + '\n'
    email_body += '</head>' + '\n'
    email_body += '<body>'

    video_url = TA_SERVER + "/video/" + video_meta_data['youtube_id']
    email_body += "\n\n<b>Video Title:</b> " + video_meta_data['title']  + "<br>" + '\n'
    email_body += "\n<b>Video Date:</b> " + video_meta_data['published'] + "<br>" + '\n'
    email_body += "\n<b>Video Views:</b> " + str(video_meta_data['stats']['view_count']) + "<br>" + '\n'
    email_body += "\n<b>Video Likes:</b> " + str(video_meta_data['stats']['like_count']) + "<br>" + '\n\n'
    email_body += "\n<b>Video Link:</b> <a href=\"" + video_url + "\">" + video_url + "</a><br>" + '\n'
    email_body += "\n<b>Video Description:</b>\n\n<pre>" + video_meta_data['description'] + '</pre></br>\n\n'
    email_body += '\n</body>\n</html>'

    # Dump for local debug viewing
    pretty_text = html2text.HTML2Text()
    pretty_text.ignore_links = True
    pretty_text.body_width = 200
    logger.debug(pretty_text.handle(email_body))
    logger.debug(email_body)

    video_title = "[TA] New video from " + video_meta_data['channel']['channel_name']

    apobj = apprise.Apprise()
    apobj.add(APPRISE_LINK)
    apobj.notify(body=email_body,title=video_title)

def cleanup_after_deleted_videos():
    logger.info("Check for broken symlinks and NFO files without videos in our target folder.")
    broken = []
    for root, dirs, files in os.walk(TARGET_FOLDER):
        if root.startswith('./.git'):
            # Ignore the .git directory.
            continue
        for filename in files:
            path = os.path.join(root,filename)
            file_info = os.path.splitext(path)
            # Check if the file is a video's nfo file
            if not filename == "tvshow.nfo" and not filename == "season.nfo" and file_info[1] == ".nfo" :
                # Check if there is a corresponding video file and if not, delete the nfo file.
                expected_video = path.replace('.nfo','.mp4')
                if not os.path.exists(expected_video):
                    logger.info("Found hanging .nfo file: %s", path)
                    # Queue the hanging nfo file for deletion.
                    broken.append(path)
            elif os.path.islink(path):
                # We've found a symlink.
                target_path = os.readlink(path)
                # Resolve relative symlinks
                if not os.path.isabs(target_path):
                    target_path = os.path.join(os.path.dirname(path),target_path)
                if not os.path.exists(target_path):
                    # The symlink is broken.
                    broken.append(path)
            else:
                # If it's not a symlink or hanging nfo file, we're not interested.
                logger.debug("No need to clean-up  %s", path)
                continue
        for dir in dirs:
            logger.debug("Found channel folder: %s", dir)

    if broken == []:
        logger.info("No deleted videos found, no cleanup required.")
    else:
        logger.info('%d Broken symlinks found...', len(broken))
        for link in broken:
            logger.info("Deleting file: %s", link )
            # Here we need to delete the NFO file and video and subtitle symlinks
            # associated with the deleted video.
            os.remove(link)
            # TBD Also check TA if channel target folder should be deleted?

def process_video(chan_name, playlist_name, title, video, episode_num, season_num):
    logger.debug(custom_name + ", " + video['media_url'])
    video['media_url'] = video['media_url'].replace('/media', '')

    # Getting here means a new video.
    logger.info("Processing new video from \"%s\": %s", chan_name, title)
    os.symlink(TA_MEDIA_FOLDER + video['media_url'], TARGET_FOLDER + "/" + chan_name + "/" + playlist_name + "/" + title)

    if NOTIFICATIONS_ENABLED:
        notify(video)
    else:
        logger.debug("Notification not sent for \"%s\": %s as NOTIFICATIONS_ENABLED is set to False in .env settings.", chan_name, title)

    if GENERATE_NFO:
        generate_new_video_nfo(chan_name, playlist_name, title, video, episode_num, season_num)
    else:
        logger.debug("Not generating video NFO file for \"%s\": %s as GENERATE_NFO is et to False in .env settings.", chan_name, title)

    if SYMLINK_SUBS:
        generate_new_video_sub(chan_name, playlist_name, title, video)
    else:
        logger.debug("Not generating subtitle symlink for \"%s\": %s as SYMLINK_SUBS is et to False in .env settings.", chan_name, title)

def urlify(s):
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", "_", s)
    return s

def sanitize(s):
    s = re.sub(r"[/\\?%*:|\"<>\x7F\x00-\x1F]", "_", s)
    return s

def simplify_date(s):
    s = s.replace("-", "")
    return s

def strmaxlen(s, maxlen):
    l = maxlen - 1
    return (s[:l] + '\u2026') if len(s) > maxlen else s

os.makedirs(TARGET_FOLDER, exist_ok = True)

headers = {'Authorization': 'Token ' + TA_TOKEN}

# Get all playlists from TA API.
playlist_url = TA_SERVER + '/api/playlist/'
logger.debug("Playlist API: " + playlist_url)
playlist_req = requests.get(playlist_url, headers=headers)
if playlist_req and playlist_req.status_code == 200:
    playlists_json = playlist_req.json()
    playlists_data = playlists_json['data']
else:
    logger.info("No playlists in TA, exiting\u2026")
    # Bail from program as we have no playlists in TA.
    sys.exit()

while playlists_json['paginate']['last_page']:
    playlists_json = requests.get(playlist_url, headers=headers, params={'page': playlists_json['paginate']['current_page'] + 1}).json()
    playlists_data.extend(playlists_json['data'])

# Get all channels from TA API.
chan_url = TA_SERVER + '/api/channel/'
logger.debug("Channel API: " + chan_url)
chan_req = requests.get(chan_url, headers=headers)
if chan_req and chan_req.status_code == 200:
    channels_json = chan_req.json()
    channels_data = channels_json['data']
else:
    logger.info("No channels in TA, exiting\u2026")
    # Bail from program as we have no channels in TA.
    sys.exit()

while channels_json['paginate']['last_page']:
    channels_json = requests.get(chan_url, headers=headers, params={'page': channels_json['paginate']['current_page'] + 1}).json()
    channels_data.extend(channels_json['data'])

# Show containers for all channels.
for channel in channels_data:
    chan_name = sanitize(channel['channel_name'])
    chan_desc = str(channel['channel_description'])
    logger.debug("Channel Name: " + str(chan_name))
    logger.debug("Channel Description: " + strmaxlen(chan_desc, 32))
    if (len(chan_name) < 1): chan_name = channel['channel_id']
    try:
        os.makedirs(TARGET_FOLDER + "/" + chan_name, exist_ok = False)
        setup_new_channel_resources(chan_name, channel)
    except OSError as error:
        logger.debug("We already have %s channel folder", chan_name)

    # Season container for videos not assigned to playlists.
    season_num = 1

    playlist_name = "Videos"
    playlist_desc = "Channel's videos not assigned to any playlists."
    logger.debug(playlist_name)
    logger.debug(playlist_desc)
    try:
        os.makedirs(TARGET_FOLDER + "/" + chan_name + "/" + playlist_name, exist_ok = False)
        playlist_data = {
            'no_playlist': True,
            'playlist_description': playlist_desc,
            'playlist_last_refresh': "",
            'playlist_id': ""
        }
        setup_new_channel_playlist_resources(chan_name, channel, playlist_name, playlist_data, season_num)
    except OSError as error:
        logger.debug("We already have \"%s\" playlist folder", playlist_desc)

    chan_videos_url = chan_url + channel['channel_id'] + "/video/"
    logger.debug("Channel Videos API: " + chan_videos_url)
    chan_videos = requests.get(chan_videos_url, headers=headers)
    chan_videos_json = chan_videos.json() if chan_videos and chan_videos.status_code == 200 else None

    if chan_videos_json is not None:
        chan_videos_data = chan_videos_json['data']
        while chan_videos_json['paginate']['last_page']:
            chan_videos_json = requests.get(chan_videos_url, headers=headers, params={'page': chan_videos_json['paginate']['current_page'] + 1}).json()
            chan_videos_data.extend(chan_videos_json['data'])

        episode_num = 0
        for video in chan_videos_data:
            # Continue to next video if it is assigned to a playlist.
            if 'playlist' in video:
                continue

            episode_num += 1
            video_chan = video['channel']['channel_name'] or video['channel']['channel_id']
            custom_name = urlify(sanitize(video_chan)) + " - " + simplify_date(video['published']) + " - " + urlify(sanitize(video['title']))[:64] + " [" + video['youtube_id'] + "]"
            title = custom_name + ".mp4"
            try:
                process_video(chan_name, playlist_name, title, video, episode_num, season_num)
            except FileExistsError:
                # This means we already had processed the video, completely normal.
                logger.debug("Symlink exists for " + title)
                if (QUICK):
                    time.sleep(.5)
                    break;

    # Season containers for all playlists by this channel.
    for playlist in playlists_data:
        # Continue to next playlist if it is by another channel.
        if playlist['playlist_channel_id'] != channel['channel_id']:
            continue

        season_num += 1
        playlist_name = sanitize(playlist['playlist_name'])
        playlist_desc = str(playlist['playlist_description'])
        logger.debug("Playlist Name: " + str(playlist_name))
        logger.debug("Playlist Description: " + strmaxlen(playlist_desc, 32))
        if (len(playlist_name) < 1): playlist_name = playlist['playlist_id']
        try:
            os.makedirs(TARGET_FOLDER + "/" + chan_name + "/" + playlist_name, exist_ok = False)
            setup_new_channel_playlist_resources(chan_name, channel, playlist_name, playlist, season_num)
        except OSError as error:
            logger.debug("We already have \"%s\" playlist folder", playlist_name)

        episode_num = 0
        for video in playlist['playlist_entries']:
            video_url = TA_SERVER + '/api/video/' + video['youtube_id'] + "/"
            logger.debug("Video API: " + video_url)
            video_data = requests.get(video_url, headers=headers)
            video_json = video_data.json() if video_data and video_data.status_code == 200 else None

            if video_json is None:
                continue

            episode_num += 1
            video = video_json['data']
            video_chan = video['channel']['channel_name'] or video['channel']['channel_id']
            custom_name = urlify(sanitize(video_chan)) + " - " + simplify_date(video['published']) + " - " + urlify(sanitize(video['title']))[:64] + " [" + video['youtube_id'] + "]"
            title = custom_name + ".mp4"
            try:
                process_video(chan_name, playlist_name, title, video, episode_num, season_num)
            except FileExistsError:
                # This means we already had processed the video, completely normal.
                logger.debug("Symlink exists for " + title)
                if (QUICK):
                    time.sleep(.5)
                    break;

# If enabled, check for deleted video and if found cleanup video NFO file and video and subtitle symlinks.
if CLEANUP_DELETED_VIDEOS:
    cleanup_after_deleted_videos()
