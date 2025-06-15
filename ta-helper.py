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
formatter = logging.Formatter(
    fmt='%(asctime)s %(filename)s:%(lineno)s %(levelname)-8s %(message)s',
    datefmt='%d-%b-%y %H:%M:%S'
)
handler.setFormatter(formatter)
logger.addHandler(handler)

# Pull configuration details from .env file.
load_dotenv()
NOTIFICATIONS_ENABLED = bool(strtobool(os.environ.get("NOTIFICATIONS_ENABLED", 'False')))
GENERATE_NFO = bool(strtobool(os.environ.get("GENERATE_NFO", 'False')))
SYMLINK_SUBS = bool(strtobool(os.environ.get("SYMLINK_SUBS", 'False')))
SUB_FORMAT = str(os.environ.get("SUB_FORMAT", ".en.vtt"))
GENERATE_SHOWS_NFO = bool(strtobool(os.environ.get("GENERATE_SHOWS_NFO", 'False')))
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

if TA_CACHE == "":
    logger.info("No TA_CACHE available so cannot setup symlinks to cache files.")

if not NOTIFICATIONS_ENABLED:
    logger.debug("NOTIFICATIONS_ENABLED is set to False in .env settings.")

if not GENERATE_SHOWS_NFO:
    logger.debug("GENERATE_SHOWS_NFO is set to False in .env settings.")

if not GENERATE_NFO:
    logger.debug("GENERATE_NFO is et to False in .env settings.")

if not SYMLINK_SUBS:
    logger.debug("SYMLINK_SUBS is et to False in .env settings.")

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

def format_desc(s):
    s = s.replace("\n", "<br>\n")
    return s

def setup_new_channel_resources(chan_name, chan_data):
    logger.info("New channel \"%s\", setup resources.", chan_name)
    if TA_CACHE:
        # Link the channel logo from TA docker cache into target folder for media managers
        # and file explorers. Provide cover.jpg, poster.jpg, folder.jpg and banner.jpg symlinks.
        channel_thumb_path = cache_path(chan_data['channel_thumb_url'])
        os.symlink(channel_thumb_path, TARGET_FOLDER + "/" + chan_name + "/" + "poster.jpg")
        os.symlink(channel_thumb_path, TARGET_FOLDER + "/" + chan_name + "/" + "cover.jpg")
        folder_symlink = TARGET_FOLDER + "/" + chan_name + "/" + "folder.jpg"
        os.symlink(channel_thumb_path, folder_symlink)
        channel_banner_path = cache_path(chan_data['channel_banner_url'])
        os.symlink(channel_banner_path, TARGET_FOLDER + "/" + chan_name + "/" + "banner.jpg")
        logger.debug("Symlink thumb \"%s\" to poster, cover, and folder.jpg files.", channel_thumb_path)

    if GENERATE_SHOWS_NFO:
        # Generate tvshow.nfo for media managers, no TA_CACHE required.
        logger.info("Generating tvshow.nfo for channel %s.", chan_data['channel_id'])
        f = open(TARGET_FOLDER + "/" + chan_name + "/" + "tvshow.nfo", "w+")
        f.write("<?xml version=\"1.0\" encoding=\"utf-8\" standalone=\"yes\"?>\n" +
            "<tvshow>\n\t" +
            "<plot>" + xmlesc(format_desc(chan_data['channel_description'] or "")) + "</plot>\n\t" +
            "<outline>" + xmlesc(format_desc(chan_data['channel_description'] or "")) + "</outline>\n\t" +
            #"<lockdata>false</lockdata>\n\t" +
            "<title>" + xmlesc(chan_name) + "</title>\n\t" +
            "<originaltitle>" + xmlesc(chan_name) + "</originaltitle>\n\t" +
            "<year>" + chan_data['channel_last_refresh'][:4] + "</year>\n\t" +
            "<premiered>" + chan_data['channel_last_refresh'] + "</premiered>\n\t"+
            "<releasedate>" + chan_data['channel_last_refresh'] + "</releasedate>\n" +
            "<art>\n\t\t<poster>" + folder_symlink + "</poster>\n\t</art>\n\t" +
            "<youtubemetadataid>" + chan_data['channel_id'] + "</youtubemetadataid>\n\t" +
            #"<showtitle>" + xmlesc(chan_name) + "</showtitle>\n\t" +
            "</tvshow>")
        f.close()

def setup_new_channel_playlist_resources(chan_name, chan_data, playlist_name, playlist_data, season_num):
    logger.info("New playlist \"%s\", setup resources.", playlist_name)
    if TA_CACHE:
        if 'no_playlist' in playlist_data and playlist_data['no_playlist'] == True:
            playlist_thumb_path = cache_path(chan_data['channel_thumb_url'])
        else:
            # Link the playlist thumb from TA docker cache into target folder for media managers
            # and file explorers. Provide folder.jpg symlink.
            playlist_thumb_path = cache_path(playlist_data['playlist_thumbnail'])

        folder_symlink = TARGET_FOLDER + "/" + chan_name + "/" + playlist_name + "/" + "folder.jpg"
        os.symlink(playlist_thumb_path, folder_symlink)
        logger.debug("Symlink thumb \"%s\" to folder.jpg file.", playlist_thumb_path)

    if GENERATE_SHOWS_NFO:
        # Generate season.nfo for media managers, no TA_CACHE required.
        logger.info("Generating season.nfo for playlist %s.", playlist_data['playlist_id'])
        f = open(TARGET_FOLDER + "/" + chan_name + "/" + playlist_name + "/" + "season.nfo", "w+")
        f.write("<?xml version=\"1.0\" encoding=\"utf-8\" standalone=\"yes\"?>\n" +
            "<season>\n\t" +
            "<plot>" + xmlesc(format_desc(playlist_data['playlist_description'] or "")) + "</plot>\n\t" +
            "<outline>" + xmlesc(format_desc(playlist_data['playlist_description'] or "")) + "</outline>\n\t" +
            #"<lockdata>false</lockdata>\n\t" +
            "<title>" + xmlesc(playlist_name) + "</title>\n\t" +
            "<year>" + playlist_data['playlist_last_refresh'][:4] + "</year>\n\t" +
            "<premiered>" + playlist_data['playlist_last_refresh'] + "</premiered>\n\t" +
            "<releasedate>" + playlist_data['playlist_last_refresh'] + "</releasedate>\n\t" +
            "<art>\n\t\t<poster>" + folder_symlink + "</poster>\n\t</art>\n\t" +
            "<seasonnumber>" + str(season_num) + "</seasonnumber>\n" +
            "<youtubemetadataid>" + playlist_data['playlist_id'] + "</youtubemetadataid>\n\t" +
            #"<showtitle>" + xmlesc(chan_name) + "</showtitle>\n\t" +
            "</season>")
        f.close()

def generate_new_video_nfo(chan_name, playlist_name, video_symlink_name, video_meta_data, episode_num, season_num):
    logger.info("Generating .nfo file for %s.", video_meta_data['youtube_id'])
    if TA_CACHE:
        # Link the video thumb from TA docker cache into target folder for media managers
        # and file explorers. Provide -poster.jpg symlink.
        video_thumb_path = cache_path(video_meta_data['vid_thumb_url'])

        poster_title = video_symlink_name.replace('.mp4', '-poster.jpg')
        poster_symlink = TARGET_FOLDER + "/" + chan_name + "/" + playlist_name + "/" + poster_title
        os.symlink(video_thumb_path, poster_symlink)
        logger.debug("Symlink thumb \"%s\" to -poster.jpg file.", video_thumb_path)

    nfo_tag = "episodedetails" if GENERATE_SHOWS_NFO else "musicvideo"

    if GENERATE_NFO:
        # TA has added a new video. Create an NFO file for media managers.
        nfo_filename = video_symlink_name.replace('.mp4', '.nfo')
        f = open(TARGET_FOLDER + "/" + chan_name + "/" + playlist_name + "/" + nfo_filename, "w+")
        f.write("<?xml version=\"1.0\" encoding=\"utf-8\" standalone=\"yes\"?>\n" +
            "<" + nfo_tag + ">\n\t" +
            "<plot>" + xmlesc(format_desc(video_meta_data['description'])) + "</plot>\n\t" +
            #"<lockdata>false</lockdata>\n\t" +
            "<title>" + xmlesc(video_meta_data['title']) + "</title>\n\t" +
            "<director>" + xmlesc(video_meta_data['channel']['channel_name']) + "</director>\n\t" +
            "<year>" + video_meta_data['published'][:4] + "</year>\n\t" +
            "<premiered>" + video_meta_data['published'] + "</premiered>\n\t" +
            "<releasedate>" + video_meta_data['published'] + "</releasedate>\n\t" +
            "<youtubemetadataid>" + video_meta_data['youtube_id'] + "</youtubemetadataid>\n\t" +
            "<art>\n\t\t<poster>" + poster_symlink + "</poster>\n\t</art>\n\t" +
            "<episode>" + str(episode_num) + "</episode>\n" +
            "<season>" + str(season_num) + "</season>\n\t" +
            #"<showtitle>" + xmlesc(chan_name) + "</showtitle>\n\t" +
            "</" + nfo_tag + ">")
        f.close()

def generate_new_video_sub(chan_name, playlist_name, video_symlink_name, video_meta_data):
    # TA has added a new video. Create a symlink to subtitles.
    video_basename = os.path.splitext(video_meta_data['media_url'])[0]
    subtitle_path = TA_MEDIA_FOLDER + video_basename + SUB_FORMAT
    if os.path.exists(subtitle_path):
        subtitle_symlink = TARGET_FOLDER + "/" + chan_name + "/" + playlist_name + "/" + video_symlink_name.replace(".mp4", ".eng.vtt")
        os.symlink(subtitle_path, subtitle_symlink)
        logger.debug("Symlink subtitle for %s.", video_meta_data['youtube_id'])
    else:
        logger.debug("%s does not have %s subtitle.", video_meta_data['youtube_id'], SUB_FORMAT)

def notify(video_meta_data):

    # Send a notification via apprise library.
    logger.info("Sending new video notification %s.", video_meta_data['youtube_id'])

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
    apobj.notify(body=email_body, title=video_title)

def cleanup_after_deleted_videos():
    logger.debug("===")
    logger.info("Checking for broken symlinks and .nfo files without videos in our target folder\u2026")
    broken = []
    folders = []
    for root, dirs, files in os.walk(TARGET_FOLDER):
        if root.startswith('./.git'):
            # Ignore the .git directory.
            continue
        for filename in files:
            path = os.path.join(root, filename)
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
                    target_path = os.path.join(os.path.dirname(path), target_path)
                if not os.path.exists(target_path):
                    # The symlink is broken.
                    broken.append(path)
            else:
                # If it's not a symlink or hanging nfo file, we're not interested.
                logger.debug("No need to clean-up \"%s\".", path)
                continue

        for dir in dirs:
            folders.append(os.path.join(root, dir))

    if broken == []:
        logger.info("No broken symlinks found.")
    else:
        logger.info('%d broken symlinks found, cleaning up\u2026', len(broken))
        for link in broken:
            # Here we need to delete the NFO file and video and subtitle symlinks
            # associated with the deleted video.
            os.remove(link)
            logger.info("Deleted broken symlink: %s", link)

    empty_dirs = 0

    if folders != []:
        for path in folders:
            if len(os.listdir(path)) == 0:
                os.rmdir(path)
                logger.info("Deleted empty folder: %s", path)
                empty_dirs += 1

    if empty_dirs == 0:
        logger.info("No empty folders found.")

def process_video(chan_name, playlist_name, video_symlink_name, video, episode_num, season_num):
    video['media_url'] = video['media_url'].replace('/youtube', '')
    video_path = TA_MEDIA_FOLDER + video['media_url']
    video_symlink = TARGET_FOLDER + "/" + chan_name + "/" + playlist_name + "/" + video_symlink_name

    os.symlink(video_path, video_symlink)
    logger.debug("Symlink video \"%s\" to \"%s\".", video_path, video_symlink)

    # Getting here means a new video.
    logger.info("Processing new video from \"%s\": \"%s\".", chan_name, video['title'])

    if NOTIFICATIONS_ENABLED:
        notify(video)

    generate_new_video_nfo(chan_name, playlist_name, video_symlink_name, video, episode_num, season_num)

    if SYMLINK_SUBS:
        generate_new_video_sub(chan_name, playlist_name, video_symlink_name, video)

def urlify(s):
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", "_", s)
    return s

def sanitize(s):
    s = re.sub(r"[/\\?%*:|\"<>\x7F\x00-\x1F]", "_", s)
    return s

def simplify_date(s):
    s = s[:10].replace("-", "")
    return s

def strmaxlen(s, maxlen):
    l = maxlen - 1
    return (s[:l] + '\u2026') if len(s) > maxlen else s

os.makedirs(TARGET_FOLDER, exist_ok = True)

headers = {'Authorization': 'Token ' + TA_TOKEN}

# Get all playlists from TA API.
playlist_url = TA_SERVER + '/api/playlist/'
logger.debug("Playlist API: %s", playlist_url)
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
logger.debug("Channel API: %s", chan_url)
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
    logger.debug("===")

    chan_name = sanitize(channel['channel_name'])
    chan_desc = str(channel['channel_description'])
    logger.debug("Channel Name: %s", str(chan_name))
    logger.debug("Channel Description: %s", strmaxlen(chan_desc, 32))

    if (len(chan_name) < 1):
        chan_name = channel['channel_id']

    chan_path = TARGET_FOLDER + "/" + chan_name
    if not os.path.exists(chan_path):
        try:
            os.makedirs(chan_path)
            setup_new_channel_resources(chan_name, channel)
        except OSError as error:
            logger.error(error)

    logger.debug("---")

    # Season container for videos not assigned to playlists.
    season_num = 1

    playlist_name = "Videos"
    playlist_desc = "Channel's videos not assigned to playlists."
    logger.debug("Playlist Name: %s", playlist_name)
    logger.debug("Playlist Description: %s", playlist_desc)

    videos_path = TARGET_FOLDER + "/" + chan_name + "/" + playlist_name
    if not os.path.exists(videos_path):
        try:
            os.makedirs(videos_path)
            playlist_data = {
                'no_playlist': True,
                'playlist_name': playlist_name,
                'playlist_description': playlist_desc,
                'playlist_last_refresh': "",
                'playlist_id': ""
            }
            setup_new_channel_playlist_resources(chan_name, channel, playlist_name, playlist_data, season_num)
        except OSError as error:
            logger.error(error)

    chan_videos_url = TA_SERVER + '/api/video/?channel=' + channel['channel_id']
    logger.debug("Channel Videos API: %s", chan_videos_url)
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
            if 'playlist' in video and len(video['playlist']) > 0:
                continue

            episode_num += 1
            video_chan = video['channel']['channel_name'] or video['channel']['channel_id']
            custom_name = urlify(sanitize(video_chan)) + " - " + simplify_date(video['published']) + " - " + urlify(sanitize(video['title']))[:64] + " [" + video['youtube_id'] + "]"
            title = custom_name + ".mp4"
            try:
                process_video(chan_name, playlist_name, title, video, episode_num, season_num)
            except FileExistsError:
                # This means we already had processed the video, completely normal.
                logger.debug("Symlink exists for \"%s\".", title)
                if (QUICK):
                    time.sleep(.5)
                    break;

        logger.debug("Valid videos not assigned to playlists: %s / %s", episode_num, len(chan_videos_data))

    # Season containers for all playlists by this channel.
    for playlist in playlists_data:
        # Continue to next playlist if it is by another channel.
        if playlist['playlist_channel_id'] != channel['channel_id']:
            continue

        logger.debug('---')

        season_num += 1
        playlist_name = sanitize(playlist['playlist_name'])
        playlist_desc = str(playlist['playlist_description'])
        logger.debug("Playlist Name: %s", str(playlist_name))
        logger.debug("Playlist Description: %s", strmaxlen(playlist_desc, 32))

        if (len(playlist_name) < 1):
            playlist_name = playlist['playlist_id']

        playlist_folder = TARGET_FOLDER + "/" + chan_name + "/" + playlist_name
        if not os.path.exists(playlist_folder):
            try:
                os.makedirs(TARGET_FOLDER + "/" + chan_name + "/" + playlist_name)
                setup_new_channel_playlist_resources(chan_name, channel, playlist_name, playlist, season_num)
            except OSError as error:
                logger.error(error)

        episode_num = 0
        for video in playlist['playlist_entries']:
            video_url = TA_SERVER + '/api/video/' + video['youtube_id'] + "/"
            logger.debug("Video API: %s", video_url)
            video_req = requests.get(video_url, headers=headers)
            video_json = video_req.json() if video_req and video_req.status_code == 200 else None

            if video_json is None:
                logger.warning("Missing video data for %s.", video['youtube_id'])
                continue

            episode_num += 1
            video_data = video_json
            video_chan = video_data['channel']['channel_name'] or video_data['channel']['channel_id']
            custom_name = urlify(sanitize(video_chan)) + " - " + simplify_date(video_data['published']) + " - " + urlify(sanitize(video_data['title']))[:64] + " [" + video['youtube_id'] + "]"
            video_symlink_name = custom_name + ".mp4"
            try:
                process_video(chan_name, playlist_name, video_symlink_name, video_data, episode_num, season_num)
            except FileExistsError:
                # This means we already had processed the video, completely normal.
                logger.debug("Symlink exists for \"%s\".", video_symlink_name)
                if (QUICK):
                    time.sleep(.5)
                    break;

        logger.debug("Valid videos assigned to this playlist: %s / %s", episode_num, len(playlist['playlist_entries']))

# If enabled, check for deleted video and if found cleanup video NFO file and video and subtitle symlinks.
if CLEANUP_DELETED_VIDEOS:
    cleanup_after_deleted_videos()
