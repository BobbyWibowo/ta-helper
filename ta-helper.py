import apprise
from distutils.util import strtobool
from dotenv import load_dotenv
import html2text
import logging
import os
import re
import requests
import shutil
import subprocess
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
NOTIFICATIONS_ENABLED = bool(strtobool(os.environ.get("NOTIFICATIONS_ENABLED", "False")))
GENERATE_NFO = bool(strtobool(os.environ.get("GENERATE_NFO", "False")))
SYMLINK_SUBS = bool(strtobool(os.environ.get("SYMLINK_SUBS", "False")))
SUB_FORMAT = str(os.environ.get("SUB_FORMAT", ".en.vtt"))
GENERATE_SHOWS_NFO = bool(strtobool(os.environ.get("GENERATE_SHOWS_NFO", "False")))
FROMADDR = str(os.environ.get("MAIL_USER", ""))
RECIPIENTS = str(os.environ.get("MAIL_RECIPIENTS", ""))
RECIPIENTS = RECIPIENTS.split(',')
TA_MEDIA_FOLDER = str(os.environ.get("TA_MEDIA_FOLDER", ""))
TA_SERVER = str(os.environ.get("TA_SERVER", ""))
TA_TOKEN = str(os.environ.get("TA_TOKEN", ""))
TA_CACHE = str(os.environ.get("TA_CACHE", ""))
TA_CACHE_DOCKER = bool(strtobool(os.environ.get("TA_CACHE_DOCKER", "False")))
TARGET_FOLDER = str(os.environ.get("TARGET_FOLDER", ""))
APPRISE_LINK = str(os.environ.get("APPRISE_LINK", ""))
QUICK = bool(strtobool(os.environ.get("QUICK", "True")))
POSTPROCESS_COMMAND = str(os.environ.get("POSTPROCESS_COMMAND", ""))
CLEANUP_DELETED_VIDEOS = bool(strtobool(str(os.environ.get("CLEANUP_DELETED_VIDEOS", ""))))

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
    if not s:
        return ""
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    s = s.replace('"', "&quot;")
    s = s.replace("'", "&apos;")
    return s

def format_desc(s):
    if not s:
        return ""
    s = s.replace("\n", "<br>\n")
    return s

def setup_channel_thumb(chan_name, chan_data):
    if not TA_CACHE:
        return ''

    # Link the channel logo from TA docker cache into target folder for media managers
    # and file explorers. Provide cover.jpg, poster.jpg, folder.jpg and banner.jpg symlinks.
    channel_thumb_path = cache_path(chan_data['channel_thumb_url'])
    channel_banner_path = cache_path(chan_data['channel_banner_url'])

    channel_root = TARGET_FOLDER + "/" + chan_name
    target_filenames = ["poster.jpg", "cover.jpg", "folder.jpg", "banner.jpg"]
    for filename in target_filenames:
        try:
            os.remove(channel_root + "/" + filename)
        except FileNotFoundError:
            pass

        image_path = channel_banner_path if filename == "banner.jpg" else channel_thumb_path
        os.symlink(image_path, channel_root + "/" + filename)

    logger.debug("Symlink thumb \"%s\" to poster, cover, and folder.jpg files.", channel_thumb_path)
    return channel_root + "/folder.jpg"

def setup_new_channel_resources(chan_name, chan_data):
    logger.info("New channel \"%s\", setup resources.", chan_name)
    folder_symlink = setup_channel_thumb(chan_name, chan_data)
    if GENERATE_SHOWS_NFO:
        # Generate tvshow.nfo for media managers, no TA_CACHE required.
        logger.info("Generating tvshow.nfo for channel \"%s\".", chan_name)
        f = open(TARGET_FOLDER + "/" + chan_name + "/" + "tvshow.nfo", "w+")
        f.write("<?xml version=\"1.0\" encoding=\"utf-8\" standalone=\"yes\"?>\n" +
            "<tvshow>\n\t" +
            "<plot>" + xmlesc(format_desc(chan_data['channel_description'] or "")) + "</plot>\n\t" +
            "<outline>" + xmlesc(format_desc(chan_data['channel_description'] or "")) + "</outline>\n\t" +
            "<title>" + xmlesc(chan_data['channel_name']) + "</title>\n\t" +
            "<originaltitle>" + xmlesc(chan_name) + "</originaltitle>\n\t" +
            "<year>" + chan_data['channel_last_refresh'][:4] + "</year>\n\t" +
            "<premiered>" + chan_data['channel_last_refresh'][:10] + "</premiered>\n\t"+
            "<releasedate>" + chan_data['channel_last_refresh'][:10] + "</releasedate>\n\t" +
            "<art>\n\t\t<poster>" + folder_symlink + "</poster>\n\t</art>\n\t" +
            "<youtubemetadataid>" + chan_data['channel_id'] + "</youtubemetadataid>\n" +
            "</tvshow>")
        f.close()

def setup_playlist_thumb(chan_name, playlist_name, playlist_data):
    if not TA_CACHE or playlist_data['playlist_name'] == 'Videos':
        return ''

    # Link the playlist thumb from TA docker cache into target folder for media managers
    # and file explorers. Provide folder.jpg symlink.
    playlist_thumb_path = cache_path(playlist_data['playlist_thumbnail'])
    folder_symlink = TARGET_FOLDER + "/" + chan_name + "/" + playlist_name + "/" + "folder.jpg"

    try:
        os.remove(folder_symlink)
    except FileNotFoundError:
        pass

    os.symlink(playlist_thumb_path, folder_symlink)

    logger.debug("Symlink thumb \"%s\" to folder.jpg file.", playlist_thumb_path)
    return folder_symlink

def setup_new_channel_playlist_resources(chan_name, playlist_name, playlist_data, season_num):
    logger.info("New playlist \"%s\", setup resources.", playlist_name)
    folder_symlink = setup_playlist_thumb(chan_name, playlist_name, playlist_data)
    if GENERATE_SHOWS_NFO:
        # Generate season.nfo for media managers, no TA_CACHE required.
        logger.info("Generating season.nfo for playlist \"%s\".", playlist_name)
        f = open(TARGET_FOLDER + "/" + chan_name + "/" + playlist_name + "/" + "season.nfo", "w+")
        f.write("<?xml version=\"1.0\" encoding=\"utf-8\" standalone=\"yes\"?>\n" +
            "<season>\n\t" +
            "<plot>" + xmlesc(format_desc(playlist_data['playlist_description'] or "")) + "</plot>\n\t" +
            "<outline>" + xmlesc(format_desc(playlist_data['playlist_description'] or "")) + "</outline>\n\t" +
            "<title>" + xmlesc(playlist_data['playlist_name']) + "</title>\n\t" +
            "<year>" + playlist_data['playlist_last_refresh'][:4] + "</year>\n\t" +
            "<premiered>" + playlist_data['playlist_last_refresh'][:10] + "</premiered>\n\t" +
            "<releasedate>" + playlist_data['playlist_last_refresh'][:10] + "</releasedate>\n\t" +
            "<art>\n\t\t<poster>" + folder_symlink + "</poster>\n\t</art>\n\t" +
            "<seasonnumber>" + str(season_num) + "</seasonnumber>\n\t" +
            "<youtubemetadataid>" + playlist_data['playlist_id'] + "</youtubemetadataid>\n" +
            "</season>")
        f.close()

def setup_video_thumb(chan_name, playlist_name, video_symlink_name, video_meta_data):
    if not TA_CACHE:
        return ''

    # Link the video thumb from TA docker cache into target folder for media managers
    # and file explorers. Provide -poster.jpg symlink.
    video_thumb_path = cache_path(video_meta_data['vid_thumb_url'])

    poster_title = video_symlink_name.replace('.mp4', '-poster.jpg')
    poster_symlink = TARGET_FOLDER + "/" + chan_name + "/" + playlist_name + "/" + poster_title

    try:
        os.remove(poster_symlink)
    except FileNotFoundError:
        pass

    os.symlink(video_thumb_path, poster_symlink)

    logger.debug("Symlink thumb \"%s\" to -poster.jpg file.", video_thumb_path)
    return poster_symlink

def generate_new_video_nfo(chan_name, playlist_name, video_symlink_name, video_meta_data, episode_num, season_num):
    logger.info("Generating .nfo file for %s.", video_meta_data['youtube_id'])
    poster_symlink = setup_video_thumb(chan_name, playlist_name, video_symlink_name, video_meta_data)
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
            "<premiered>" + video_meta_data['published'][:10] + "</premiered>\n\t" +
            "<releasedate>" + video_meta_data['published'][:10] + "</releasedate>\n\t" +
            "<youtubemetadataid>" + video_meta_data['youtube_id'] + "</youtubemetadataid>\n\t" +
            "<art>\n\t\t<poster>" + poster_symlink + "</poster>\n\t</art>\n\t" +
            "<episode>" + str(episode_num) + "</episode>\n\t" +
            "<season>" + str(season_num) + "</season>\n" +
            #"<showtitle>" + xmlesc(chan_name) + "</showtitle>\n" +
            "</" + nfo_tag + ">")
        f.close()

def generate_new_video_sub(chan_name, playlist_name, video_symlink_name, video_meta_data):
    # TA has added a new video. Create a symlink to subtitles.
    video_basename = os.path.splitext(video_meta_data['media_url'])[0]
    subtitle_path = TA_MEDIA_FOLDER + video_basename + SUB_FORMAT
    if os.path.exists(subtitle_path):
        subtitle_symlink = TARGET_FOLDER + "/" + chan_name + "/" + playlist_name + "/" + video_symlink_name.replace(".mp4", SUB_FORMAT)
        os.symlink(subtitle_path, subtitle_symlink)
        logger.debug("Symlink subtitle for %s.", video_meta_data['youtube_id'])
    else:
        logger.debug("%s does not have %s subtitle.", video_meta_data['youtube_id'], SUB_FORMAT)

def notify(video_meta_data):
    # Send a notification via apprise library.
    logger.debug("===")
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
    email_body += "\n<b>Video Desc.:</b>\n\n<pre>" + video_meta_data['description'] + '</pre></br>\n\n'
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
    logger.info("Checking for broken symlinks and hanging extra files\u2026")

    extras_pattern = re.compile(r"(\.nfo|-poster\.jpg|" + re.escape(SUB_FORMAT) + r")$", re.IGNORECASE)
    broken = []
    empty_subfolders = []
    for root, dirs, files in os.walk(TARGET_FOLDER):
        if root.startswith('./.git'):
            # Ignore the .git directory.
            continue

        has_working_symlink = False
        for filename in files:
            path = os.path.join(root, filename)
            # Check if the file is a video's extra file.
            if extras_pattern.search(filename):
                if filename in ["tvshow.nfo", "season.nfo"]:
                    continue
                # Check if there is a corresponding video file and if not, delete the extra file.
                expected_video = extras_pattern.sub(".mp4", path)
                if not os.path.exists(expected_video):
                    # Queue the hanging extra file for deletion.
                    broken.append(path)
            elif os.path.islink(path):
                # We've found a symlink.
                target_path = os.readlink(path)
                # Resolve relative symlinks
                if not os.path.isabs(target_path):
                    target_path = os.path.join(os.path.dirname(path), target_path)
                if os.path.exists(target_path):
                    has_working_symlink = True
                else:
                    # The symlink is broken.
                    broken.append(path)
            else:
                # If it's not a symlink or hanging extra file, we're not interested.
                logger.debug("No need to clean-up \"%s\".", path)

        if not len(dirs) and not has_working_symlink:
            empty_subfolders.append(root)

    if broken == []:
        logger.info("No broken files found.")
    else:
        logger.info('%d broken files found, cleaning up\u2026', len(broken))
        for link in broken:
            # Here we need to delete the NFO file and video and subtitle symlinks
            # associated with the deleted video.
            os.remove(link)
            logger.info("Deleted broken file: %s", link)

    if not shutil.rmtree.avoids_symlink_attacks:
        logger.info("Unable to clean-up empty folders due to unsafe shtuil.rmtree().")
        return False

    if empty_subfolders == []:
        logger.info("No empty sub-folders found.")
    else:
        logger.info("%d empty sub-folders found, cleaning up\u2026", len(empty_subfolders))
        for subfolder in empty_subfolders:
            shutil.rmtree(subfolder)
            logger.info("Deleted empty sub-folder: %s", subfolder)

    # Clean-up empty channel folders.
    for entry in os.scandir(TARGET_FOLDER):
        if not entry.is_dir() or entry.name.startswith('./.git'):
            continue

        has_subfolders = False
        for _entry in os.scandir(entry):
            if _entry.is_dir():
                has_subfolders = True
                break

        if not has_subfolders:
            shutil.rmtree(entry)
            logger.info("Deleted empty channel folder: %s", entry.path)

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

logger.info("Fetching all playlists and channels\u2026")

# Get all playlists from TA API.
playlist_url = TA_SERVER + '/api/playlist/'
logger.debug("Playlist API: %s", playlist_url)
playlist_req = requests.get(playlist_url, headers=headers, params={'page': 1})
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
chan_req = requests.get(chan_url, headers=headers, params={'page': 1})
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

logger.info("Data fetched, processing\u2026")

# Show containers for all channels.
for channel in channels_data:
    logger.debug("===")

    chan_name = str(channel['channel_name'])
    chan_desc = str(channel['channel_description'])
    if (len(chan_name) < 1):
        chan_name = channel['channel_id']

    logger.info("Channel: %s", chan_name)
    logger.debug("Channel Desc.: %s", strmaxlen(chan_desc, 32))

    chan_name = sanitize(chan_name)
    chan_path = TARGET_FOLDER + "/" + chan_name
    if os.path.exists(chan_path):
        setup_channel_thumb(chan_name, channel)
    else:
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
    logger.debug("Playlist: %s", playlist_name)
    logger.debug("Playlist Description: %s", playlist_desc)

    videos_path = TARGET_FOLDER + "/" + chan_name + "/" + playlist_name
    if not os.path.exists(videos_path):
        try:
            os.makedirs(videos_path)
            playlist_data = {
                'playlist_name': playlist_name,
                'playlist_description': playlist_desc,
                'playlist_last_refresh': "",
                'playlist_id': ""
            }
            setup_new_channel_playlist_resources(chan_name, playlist_name, playlist_data, season_num)
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
        for video_data in chan_videos_data:
            video_chan = video_data['channel']['channel_name'] or video_data['channel']['channel_id']
            custom_name = urlify(sanitize(video_chan)) + " - " + simplify_date(video_data['published']) + " - [" + video_data['youtube_id'] + "]"
            video_symlink_name = custom_name + ".mp4"

            # Try to clean-up old symlink if video is assigned to playlist.
            if 'playlist' in video_data and len(video_data['playlist']) > 0:
                video_path = TA_MEDIA_FOLDER + video_data['media_url'].replace('/youtube', '')
                video_symlink = TARGET_FOLDER + "/" + chan_name + "/" + playlist_name + "/" + video_symlink_name

                if os.path.exists(video_symlink):
                    os.remove(video_symlink)
                    logger.info("Video %s is now assigned to playlist, deleted: %s", video_data['youtube_id'], video_symlink)

                # Continue to next video.
                continue

            episode_num += 1
            try:
                process_video(chan_name, playlist_name, video_symlink_name, video_data, episode_num, season_num)
            except FileExistsError:
                # This means we already had processed the video, completely normal.
                logger.debug("Symlink exists for \"%s\".", video_symlink_name)
                if (QUICK): break
                setup_video_thumb(chan_name, playlist_name, video_symlink_name, video_data)

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
        logger.debug("Playlist: %s", str(playlist_name))
        logger.debug("Playlist Desc.: %s", strmaxlen(playlist_desc, 32))

        if (len(playlist_name) < 1):
            playlist_name = playlist['playlist_id']

        playlist_folder = TARGET_FOLDER + "/" + chan_name + "/" + playlist_name
        if os.path.exists(playlist_folder):
            setup_playlist_thumb(chan_name, playlist_name, playlist)
        else:
            try:
                os.makedirs(TARGET_FOLDER + "/" + chan_name + "/" + playlist_name)
                setup_new_channel_playlist_resources(chan_name, playlist_name, playlist, season_num)
            except OSError as error:
                logger.error(error)

        episode_num = 0
        for video in playlist['playlist_entries']:
            video_url = TA_SERVER + '/api/video/' + video['youtube_id'] + "/"
            logger.debug("Video API: %s", video_url)
            video_req = requests.get(video_url, headers=headers)
            video_data = video_req.json() if video_req and video_req.status_code == 200 else None

            if video_data is None:
                logger.debug("Missing video data for %s.", video['youtube_id'])
                continue

            video_chan = video_data['channel']['channel_name'] or video_data['channel']['channel_id']
            custom_name = urlify(sanitize(video_chan)) + " - " + simplify_date(video_data['published']) + " - [" + video['youtube_id'] + "]"
            video_symlink_name = custom_name + ".mp4"

            episode_num += 1
            try:
                process_video(chan_name, playlist_name, video_symlink_name, video_data, episode_num, season_num)
            except FileExistsError:
                # This means we already had processed the video, completely normal.
                logger.debug("Symlink exists for \"%s\".", video_symlink_name)
                if (QUICK): break
                setup_video_thumb(chan_name, playlist_name, video_symlink_name, video_data)

        logger.debug("Valid videos assigned to this playlist: %s / %s", episode_num, len(playlist['playlist_entries']))

# If enabled, check for deleted video and if found cleanup video NFO file and video and subtitle symlinks.
if CLEANUP_DELETED_VIDEOS:
    cleanup_after_deleted_videos()

if POSTPROCESS_COMMAND:
    logger.info("Running: \"%s\"", POSTPROCESS_COMMAND)
    subprocess.run(POSTPROCESS_COMMAND)
