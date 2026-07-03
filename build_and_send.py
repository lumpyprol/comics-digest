#!/usr/bin/env python3
"""
Daily webcomics digest -> Instapaper Full API (private content upload).

1. Reads comics.yml and grabs the latest entry from each feed.
2. Compiles a single HTML digest.
3. Authenticates with Instapaper via xAuth (OAuth 1.0a).
4. Uploads the digest directly with bookmarks/add using
   is_private_from_source + content — no hosting, no email,
   and the article is private to your account.

Required environment variables (GitHub Actions secrets):
  INSTAPAPER_CONSUMER_KEY      from your approved API application
  INSTAPAPER_CONSUMER_SECRET   from your approved API application
  INSTAPAPER_USERNAME          your Instapaper username (usually your email)
  INSTAPAPER_PASSWORD          your Instapaper password
"""

import html
import os
import sys
import urllib.parse
from datetime import date

import feedparser
import yaml
from requests_oauthlib import OAuth1Session

BASE = "https://www.instapaper.com/api/1"
HEADERS = {"User-Agent": "Mozilla/5.0 (comics-digest; personal use)"}


# ---------- digest building ----------

def load_comics(path="comics.yml"):
    with open(path) as f:
        return yaml.safe_load(f)["comics"]


def latest_entry(feed_url):
    parsed = feedparser.parse(feed_url, request_headers=HEADERS)
    return parsed.entries[0] if parsed.entries else None


def entry_html(entry):
    """Prefer full content, fall back to summary. Feeds usually embed the strip image."""
    if getattr(entry, "content", None):
        return entry.content[0].value
    return getattr(entry, "summary", "")


def build_digest(comics):
    pretty = date.today().strftime("%A, %B %-d, %Y")
    sections, failures = [], []

    for comic in comics:
        name = comic["name"]
        try:
            entry = latest_entry(comic["feed"])
        except Exception as e:
            entry = None
            print(f"[warn] {name}: {e}", file=sys.stderr)

        if entry is None:
            failures.append(name)
            continue

        title = html.escape(getattr(entry, "title", name))
        link = getattr(entry, "link", comic["feed"])
        sections.append(
            f"""
            <h2>{html.escape(name)}</h2>
            <p><em>{title}</em> &mdash; <a href="{html.escape(link)}">original</a></p>
            <div>{entry_html(entry)}</div>
            <hr>
            """
        )

    if not sections:
        raise RuntimeError("No comics could be fetched; not sending an empty digest.")

    note = ""
    if failures:
        note = f"<p><small>Couldn't fetch today: {html.escape(', '.join(failures))}</small></p>"

    body = f"""<h1>Comics Digest — {pretty}</h1>
{''.join(sections)}
{note}"""
    return pretty, body


# ---------- Instapaper Full API ----------

def get_access_token(consumer_key, consumer_secret, username, password):
    """xAuth: exchange username/password for an OAuth access token."""
    session = OAuth1Session(consumer_key, client_secret=consumer_secret)
    resp = session.post(
        f"{BASE}/oauth/access_token",
        data={
            "x_auth_username": username,
            "x_auth_password": password,
            "x_auth_mode": "client_auth",
        },
    )
    if resp.status_code != 200:
        raise RuntimeError(f"xAuth failed ({resp.status_code}): {resp.text}")
    creds = dict(urllib.parse.parse_qsl(resp.text))
    return creds["oauth_token"], creds["oauth_token_secret"]


def add_private_bookmark(consumer_key, consumer_secret, token, token_secret,
                         title, content):
    session = OAuth1Session(
        consumer_key,
        client_secret=consumer_secret,
        resource_owner_key=token,
        resource_owner_secret=token_secret,
    )
    resp = session.post(
        f"{BASE}/bookmarks/add",
        data={
            "title": title,
            "content": content,
            "is_private_from_source": "Comics Digest",
        },
    )
    if resp.status_code != 200:
        raise RuntimeError(f"bookmarks/add failed ({resp.status_code}): {resp.text}")
    print(f"Saved to Instapaper: {title}")


def main():
    consumer_key = os.environ["INSTAPAPER_CONSUMER_KEY"]
    consumer_secret = os.environ["INSTAPAPER_CONSUMER_SECRET"]
    username = os.environ["INSTAPAPER_USERNAME"]
    password = os.environ["INSTAPAPER_PASSWORD"]

    pretty, content = build_digest(load_comics())

    token, token_secret = get_access_token(
        consumer_key, consumer_secret, username, password
    )
    add_private_bookmark(
        consumer_key, consumer_secret, token, token_secret,
        title=f"Comics Digest — {pretty}",
        content=content,
    )


if __name__ == "__main__":
    main()
