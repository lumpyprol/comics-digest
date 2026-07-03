# Daily Comics Digest → Instapaper (Full API, private upload)

Every day this fetches the latest strip from each comic in `comics.yml`,
compiles them into one HTML digest, and uploads it directly to your
Instapaper account as a **private** article via the Full API. No email,
no public hosting — the content goes straight from the GitHub Actions
runner to Instapaper.

## One-time setup

1. **Apply for Instapaper API keys** at
   https://www.instapaper.com/main/request_oauth_consumer_token
   Describe it as a personal daily-digest tool. Once approved you'll
   receive an **OAuth consumer key** and **consumer secret**.
   (This is the only waiting step — everything else takes five minutes.)

2. **Create a GitHub repo** and push these files to it.

3. **Add repository secrets** (repo → Settings → Secrets and variables →
   Actions → New repository secret):

   | Secret | Value |
   |---|---|
   | `INSTAPAPER_CONSUMER_KEY` | from step 1 |
   | `INSTAPAPER_CONSUMER_SECRET` | from step 1 |
   | `INSTAPAPER_USERNAME` | your Instapaper username (usually your email) |
   | `INSTAPAPER_PASSWORD` | your Instapaper password |

4. **Test it:** repo → Actions → "Daily comics digest" → Run workflow.
   Today's digest should appear in your Instapaper queue within a minute.

It then runs automatically every day at 13:00 UTC. Change the `cron` line
in `.github/workflows/daily.yml` to adjust the time.

## Adding / removing comics

Edit `comics.yml`. Each comic is a name plus either a `feed` (RSS/Atom URL)
or a `page` (a web page whose metadata contains the day's strip):

```yaml
  - name: Nancy
    feed: https://someurl.example/nancy.rss

  - name: Heathcliff
    page: https://www.creators.com/read/heathcliff
```

Delete an entry's two lines to remove it. Commit the change and the next
run picks it up. Most indie webcomics have their own feed linked on their
site; for syndicated newspaper strips with no feed, use the strip's page
on its syndicate's site (e.g. creators.com) as a `page` entry — the
script grabs the strip from the page's `og:image` tag.

## How it works

1. `build_and_send.py` pulls the newest entry from each feed and builds
   one HTML document
2. It authenticates via xAuth (`oauth/access_token`) using your consumer
   keys + account credentials
3. It calls `bookmarks/add` with `is_private_from_source` and `content`,
   which tells Instapaper to store the supplied HTML directly as a
   private bookmark — no URL involved

## Notes

- Strip images are referenced from the comics' own servers, so Instapaper
  fetches them when it processes the article. If a particular comic shows
  up image-less, its feed probably doesn't embed the image — that's
  fixable per-comic with a small scraper.
- If a feed is down one day, the digest still uploads and lists what it
  couldn't fetch at the bottom.
- If the run fails with an auth error, re-check the four secrets; xAuth
  errors also occur if the consumer token hasn't been approved yet.
