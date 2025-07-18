# ta-helper

Python script to post process Tube Archivist products, generate human readable folders and files, support NFO files and new per video notifications using apprise library.  
Various functions can be enabled/disabled.  
Nothing is touched in your Tube Archivist media folders.

> This fork is intended to optimize support for Jellyfin, and [jellyfin-youtube-metadata](https://github.com/ankenyr/jellyfin-youtube-metadata-plugin) plugin.  
> If `GENERATE_NFO` is set to `"True"`, most fields that are already stored by TA will be mapped to fields expected by the plugin, including the video IDs.  
> This ensures the plugin will be able to pull any additional data if necessary.  
> Those data will only be stored in your Jellyfin database, leaving your TA untouched.  
> Be advised that if you choose to explicitly refresh images of the Jellyfin library, it will also attempt to replace thumbnails of the videos, which will also replace the ones in TA because the images are symlinked.  
> More details can be found in [https://github.com/BobbyWibowo/ta-helper/issues/1](https://github.com/BobbyWibowo/ta-helper/issues/1).

The image below shows your original obfuscated naming on the left and new, human readable folders on the right.

![Screenshot from 2023-08-12 16-56-04](https://github.com/RoninTech/ta-helper/assets/226861/4cf31133-8d40-4a93-b363-cf8f26054f25)

Here is how your NFO file supporting media manager (Kodi, Emby, Jellyfin etc.) can look after you add your new YouTube videos folder:

![screenshot00000](https://github.com/RoninTech/ta-helper/assets/226861/b2625c9f-c600-43ac-9b72-cdacc9f6ea7f)

![screenshot00002](https://github.com/RoninTech/ta-helper/assets/226861/ad2a539a-3b84-4045-9c98-4e78886ae3db)

## Using It

Copy `.example.env` to `.env` in the same folder as the script and edit to put in your own settings.  
`.example.env` has detailed comments that explain how to use each setting.

## What exactly does it do?

It iterates through the Tube Archivist video folders and does several things:

1. Creates a mirror set of folders via symbolic links with the actual channel names and video titles for human readability.
2. If `GENERATE_NFO` is set to `"True"` it will generate .nfo files for each new channel and/or video which allows media managers such as Kodi, Emby, Jellyfin etc. to show meta info.
3. If `TA_CACHE` is not `""` it can generate symbolic links to subtitles, poster, cover and banner jpg's inside TA cache for media managers.
4. If `NOTIFICATIONS_ENABLED` is set to `"True"` in your .env, apprise will be used to notify of new videos using the apprise URL you provide, also in .env, based off the [apprise documentation](https://github.com/caronc/apprise/wiki). Here is an example of an apprise link to send notification via Gmail: `"mailto://<username>:<password>@gmail.com"`.
5. If `CLEANUP_DELETED_VIDEOS` is set to `"True"`, any broken symlinks or hanging nfo files (nfo file with no corresponding video) will be deleted from `TARGET_FOLDER`.  
So if TA is configured to delete watched videos, this will clean-up any leftovers.

**NOTE:** When apprise is setup to send emails via gmail, each notification takes approx 3s on a Raspberry Pi4.  
So if you are doing an initial run on a large library, temporarily setting `NOTIFICATIONS_ENABLED` to `"False"` will save a lot of time.

## Triggering ta-helper to run

To kickstart the ta-helper when TA adds new videos to the archive we have 3 options:

1. Manually run the script when you know new videos have been added via `python ta-helper.py`.

2. Use a cron job to periodically run the script, say every half an hour.  
Using crontab -e to add a cron job.  
This would trigger it every 30 minutes: `30 * * * * python /home/me/projects/ta-helper/ta-helper.py`.

3. Use apprise notifications from TA server as event driven triggers to run the script only when needed.  
More efficient than cron polling described in (2) above. We use apprise via the Settings page.  
Save a new task with type "Downloading", and set its apprise notification URL to `json://<IP/Hostname>:<PORT>/ta-helper-trigger`.  
For example I use: `json://192.168.1.11:8001/ta-helper-trigger`.
To process these notifications and trigger the script, simply run `python ta-helper-trigger.py` on the machine where your TA archive is.  
Make sure the PORT value in `ta-helper-trigger.py` matches the PORT you used in the TA apprise link mentioned above.

For the 3rd option, you can add the following line as a cron job (using crontab -e): `@reboot python /home/me/src/ta-helper/ta-helper-trigger.py > /home/me/Desktop/ta-trigger.log`.

Alternatively, you can create a systemd service file:
```
[Unit]
Description=ta-helper-trigger service

[Service]
Type=simple
WorkingDirectory=%h/src/ta-helper
ExecStart=%h/.cache/pypoetry/virtualenvs/ta-helper-0fQqOb5a-py3.13/bin/python %h/src/ta-helper/ta-helper-trigger.py

[Install]
WantedBy=graphical-session.target
```
Change the paths to match your own config.

---

Upstream of this fork can be found on [https://github.com/RoninTech/ta-helper](https://github.com/RoninTech/ta-helper).

Script originally created by user GordonFreeman on the [Tube Archivist discord server](https://www.tubearchivist.com/discord).
