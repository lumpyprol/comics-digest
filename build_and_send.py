#!/usr/bin/env python3
"""
Daily webcomics digest -> Instapaper Full API, images on GitHub Pages.

build phase:
  Reads comics.yml, grabs the latest strip from each source, downloads
  the strip images into docs/img/<date>/ (served by GitHub Pages), and
  writes the article HTML (with rewritten image URLs) to digest_content.html.

save phase (after the workflow commits & Pages deploys):
  Waits until the rehosted images are live, authenticates via xAuth,
  and uploads the article as a private bookmark with bookmarks/add.

Required environment (GitHub Actions secrets/vars):
  INSTAPAPER_CONSUMER_KEY      from your Instapaper API application
  INSTAPAPER_CONSUMER_SECRET   from your Instapaper API application
  INSTAPAPER_USERNAME          your Instapaper username (usually your email)
  INSTAPAPER_PASSWORD          your Instapaper password
  PAGES_BASE_URL               e.g. https://<user>.github.io/<repo>
"""

import base64
import html
import mimetypes
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

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


def og_meta(page_html, prop):
    """Extract an Open Graph meta tag's content from raw HTML."""
    pattern = (
        r'<meta[^>]+(?:property|name)=["\']og:' + re.escape(prop) +
        r'["\'][^>]+content=["\']([^"\']+)["\']'
    )
    m = re.search(pattern, page_html, re.IGNORECASE)
    if not m:
        # attribute order can be reversed: content=... property=...
        pattern = (
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:'
            + re.escape(prop) + r'["\']'
        )
        m = re.search(pattern, page_html, re.IGNORECASE)
    return m.group(1) if m else None


def section_from_page(comic):
    """Comics without a feed: pull the strip from the page's og:image metadata."""
    req = urllib.request.Request(comic["page"], headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        page = resp.read().decode("utf-8", errors="replace")

    image = og_meta(page, "image")
    if not image:
        raise RuntimeError("no og:image found on page")
    title = og_meta(page, "title") or comic["name"]
    link = og_meta(page, "url") or comic["page"]

    return title, link, f'<img src="{html.escape(image)}" alt="{html.escape(title)}">'


def section_from_feed(comic):
    entry = latest_entry(comic["feed"])
    if entry is None:
        raise RuntimeError("feed returned no entries")
    title = getattr(entry, "title", comic["name"])
    link = getattr(entry, "link", comic["feed"])
    return title, link, entry_html(entry)


DOCS_DIR = Path(__file__).parent / "docs"


def rehost_images(body_html, referer, day_dir, base_url, saved):
    """Download every <img> into docs/img/<date>/ and rewrite its src to the
    GitHub Pages URL. Instapaper can always fetch from Pages, unlike some
    comic servers that block it."""

    def fetch(url):
        req = urllib.request.Request(url, headers={**HEADERS, "Referer": referer})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            mime = resp.headers.get_content_type()
        ext = mimetypes.guess_extension(mime) or Path(urllib.parse.urlparse(url).path).suffix or ".png"
        if ext == ".jpe":
            ext = ".jpg"
        name = f"{len(saved):02d}{ext}"
        out = DOCS_DIR / "img" / day_dir / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        saved.append(out)
        return f"{base_url}/img/{day_dir}/{name}"

    def replace(match):
        src = match.group(2)
        if src.startswith("//"):
            src = "https:" + src
        try:
            return match.group(1) + fetch(src) + match.group(3)
        except Exception as e:
            print(f"[warn] couldn't rehost image {src}: {e}", file=sys.stderr)
            return match.group(0)  # keep the original URL as a fallback

    return re.sub(
        r'(<img[^>]+src=["\'])([^"\']+)(["\'])',
        replace,
        body_html,
        flags=re.IGNORECASE,
    )


def build_digest(comics, base_url):
    today = date.today()
    pretty = today.strftime("%A, %B %-d, %Y")
    day_dir = today.isoformat()
    sections, failures, saved = [], [], []

    for comic in comics:
        name = comic["name"]
        try:
            if "page" in comic:
                title, link, body = section_from_page(comic)
            else:
                title, link, body = section_from_feed(comic)
        except Exception as e:
            print(f"[warn] {name}: {e}", file=sys.stderr)
            failures.append(name)
            continue

        body = rehost_images(body, link, day_dir, base_url, saved)

        sections.append(
            f"""
            <h2>{html.escape(name)}</h2>
            <p><em>{html.escape(title)}</em> &mdash; <a href="{html.escape(link)}">original</a></p>
            <div>{body}</div>
            <hr>
            """
        )

    if not sections:
        raise RuntimeError("No comics could be fetched; not sending an empty digest.")

    note = ""
    if failures:
        note = f"<p><small>Couldn't fetch today: {html.escape(', '.join(failures))}</small></p>"

    content = f"""<h1>Comics Digest — {pretty}</h1>
{''.join(sections)}
{note}"""

    # Stash the article body so the save phase (after the Pages deploy)
    # uploads exactly what was built, images already rewritten.
    (DOCS_DIR / "img" / day_dir).mkdir(parents=True, exist_ok=True)
    (Path("digest_content.html")).write_text(content, encoding="utf-8")
    print(f"Built digest with {len(saved)} rehosted images.")
    return saved


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


def wait_until_live(url, attempts=20, delay=15):
    import time
    for _ in range(attempts):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 200:
                    print(f"Pages deploy is live: {url}")
                    return
        except Exception:
            pass
        time.sleep(delay)
    raise RuntimeError(f"Rehosted image never became reachable: {url}")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "build"
    base_url = os.environ["PAGES_BASE_URL"].rstrip("/")
    pretty = date.today().strftime("%A, %B %-d, %Y")

    if mode == "build":
        build_digest(load_comics(), base_url)
        return

    if mode != "save":
        sys.exit(f"Unknown mode: {mode} (use 'build' or 'save')")

    content = Path("digest_content.html").read_text(encoding="utf-8")

    # Wait for the first rehosted image to be reachable before saving, so
    # Instapaper doesn't fetch the article while Pages is still deploying.
    m = re.search(re.escape(base_url) + r'[^"\']+', content)
    if m:
        wait_until_live(m.group(0))

    consumer_key = os.environ["INSTAPAPER_CONSUMER_KEY"]
    consumer_secret = os.environ["INSTAPAPER_CONSUMER_SECRET"]
    username = os.environ["INSTAPAPER_USERNAME"]
    password = os.environ["INSTAPAPER_PASSWORD"]

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
