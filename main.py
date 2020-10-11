#!/bin/python
import json
import os
import pickle
import re
import sys
import logging as log
import time

from pathlib import Path
from typing import Set

import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
import praw

REDDIT_UA = "python:com.cloventt.r2y_scraper:2.0.0 (by /u/cloventt)"
CONFIG_DIR = Path("~/.config/youddit/").expanduser()
MAX_VIDEOS = 20

log.getLogger().setLevel(log.INFO)
log.getLogger('googleapicliet.discovery_cache').setLevel(log.ERROR)


def reddit_retrieve_submissions(subreddit_name: str, reddit_client: praw.Reddit) -> Set[str]:
    """Returns a list of submission URLs from your chosen subreddit."""
    submissions = set()
    youtube_re = \
        r'^((?:https?:)?\/\/)?((?:www|m)\.)?((?:youtube\.com|youtu.be))(\/(?:[\w\-]+\?v=|embed\/|v\/)?)([\w\-]+)(\S+)?$'

    log.info("Retrieving URLS from subreddit: " + subreddit_name)
    # get the list of hot submissions from this subreddit
    for submission_object in reddit_client.subreddit(subreddit_name).hot(limit=MAX_VIDEOS):
        match = re.match(youtube_re, submission_object.url)
        if match:
            submissions.add(match.group(5))
    log.info(f"Retrieved {len(submissions)} URLs from subreddit: {subreddit_name}")
    return submissions


def create_reddit_client() -> praw.Reddit:
    creds_file = CONFIG_DIR / "reddit.json"
    try:
        with open(creds_file, "r") as reddit_creds_file:
            creds = json.load(reddit_creds_file)
            log.info("Using reddit CLIENT_ID: ", creds["clientId"])

        client = praw.Reddit(user_agent=REDDIT_UA,
                             client_id=creds["clientId"],
                             client_secret=creds["clientSecret"])
        client.read_only = True
        return client
    except (IOError, FileNotFoundError):
        log.error(f"Failed to open reddit creds from '{creds_file}', please ensure this is correctly configured.")
        sys.exit(1)


def create_youtube_client():
    api_service_name = "youtube"
    api_version = "v3"
    client_secrets_file = CONFIG_DIR / "youtube.json"
    creds_file = CONFIG_DIR / "youtube-creds.pickle"
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # hack to suppress a warning
    if os.path.exists(creds_file):
        with open(creds_file, 'rb') as f:
            credentials = pickle.load(f)
    else:
        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(client_secrets_file, [
            "https://www.googleapis.com/auth/youtube.force-ssl"])
        credentials = flow.run_console()
        with open(creds_file, 'wb') as f:
            pickle.dump(credentials, f)
    return googleapiclient.discovery.build(
        api_service_name, api_version, credentials=credentials)


def get_current_playlist_videos(playlist_id: str, youtube_client) -> Set[str]:
    values = set()
    first_call = youtube_client.playlistItems().list(
        part="contentDetails",
        maxResults=50,
        playlistId=playlist_id
    ).execute()
    values.update({video["contentDetails"]["videoId"] for video in first_call["items"]})
    next_page_token = first_call.get("nextPageToken")
    while next_page_token:
        api_call = youtube_client.playlistItems().list(
            part="contentDetails",
            maxResults=50,
            playlistId=playlist_id,
            pageToken=next_page_token,
        ).execute()
        values.update({video["contentDetails"]["videoId"] for video in api_call["items"]})
        next_page_token = api_call.get("nextPageToken")
        print("getting page")
        time.sleep(1)
    return values


def insert_playlist_videos(playlist_id: str, video_id: str, youtube_client):
    try:
        youtube_client.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "position": 0,
                    "resourceId": {
                        "kind": "youtube#video",
                        "videoId": video_id
                    }
                }
            }
        ).execute()
        time.sleep(2)
    except googleapiclient.errors.HttpError as e:
        log.warning(f"Failed to add '{video_id}' to playlist: {e}")
        if e.resp.status == 403 and 'quota' in e._get_reason().strip():
            log.info("Hit a quota limit, so that's all we can do for today")
            sys.exit(1)


def build_playlist(playlist_id: str, subreddit: str, youtube_client, reddit_client):
    current_playlist_items = get_current_playlist_videos(playlist_id, youtube_client)
    log.info(f"Found {len(current_playlist_items)} items in the Youtube playlist")
    candidate_reddit_submissions = reddit_retrieve_submissions(subreddit, reddit_client)
    log.info(f"Found {len(candidate_reddit_submissions)} candidate submissions")

    submissions_to_add = candidate_reddit_submissions - current_playlist_items
    log.info(f"Found {len(submissions_to_add)} videos to add")

    for video in submissions_to_add:
        log.info(f"Adding video '{video}' to playlist")
        #insert_playlist_videos(playlist_id, video, youtube_client)
    log.info("Finished adding videos")


if __name__ == '__main__':
    reddit = create_reddit_client()
    youtube = create_youtube_client()
    build_playlist("PLHpihp9SFjsasQ-VNyQYL4GorCijAL7oy", "youtubehaiku", youtube, reddit)
