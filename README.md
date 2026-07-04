# Daily Comics Digest → Instapaper (Full API + Pages-hosted images)

Every day this fetches the latest strip from each comic in `comics.yml`,
downloads the strip images, hosts them on GitHub Pages, and uploads the
digest article itself directly (and privately) to your Instapaper account
via the Full API. The article text never touches public hosting; only
the strip images do, because Instapaper needs a reliably fetchable URL
for images (it strips embedded data URIs and some comic servers block
its image fetcher).

## One-time setup

1. **Get Instapaper API keys** at
   https://www.instapaper.com/main/request_oauth_consumer_token
   (fill in title/description/URL/email; keys appear immediately;
   "Owner Only" is fine).

2. **Create a GitHub repo** and push these files to it.

3. **Turn on GitHub Pages:** repo → Settings → Pages → under "Build and
   deployment", set Source to **Deploy from a branch**, branch `main`,
   folder `/docs`. Save.

4. **Add a repository variable** (Settings → Secrets and variables →
   Actions → **Variables** tab):

   | Variable | Value |
   |---|---|
   | `PAGES_BASE_URL` | `https://<your-username>.github.io/<repo-name>` |

5. **Add repository secrets** (same page, **Secrets** tab):

   | Secret | Value |
   |---|---|
   | `INSTAPAPER_CONSUMER_KEY` | from step 1 |
   | `INSTAPAPER_CONSUMER_SECRET` | from step 1 |
   | `INSTAPAPER_USERNAME` | your Instapaper username (usually your email) |
   | `INSTAPAPER_PASSWORD` | your Instapaper password |

6. **Test it:** repo → Actions → "Daily comics digest" → Run workflow.

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

1. `build_and_send.py build` pulls the newest strip from each source,
   downloads every strip image into `docs/img/<date>/`, and writes the
   article HTML (pointing at the Pages URLs) to `digest_content.html`
2. The workflow commits `docs/`; GitHub Pages serves the images
3. `build_and_send.py save` waits until the images are live, then
   authenticates via xAuth and calls `bookmarks/add` with
   `is_private_from_source` + `content` — the article itself is private

## Notes

- **The strip images are public** at obscure Pages URLs (that's what
  makes them reliably fetchable by Instapaper). The digest article and
  your reading list stay private.
- If a feed is down one day, the digest still uploads and lists what it
  couldn't fetch at the bottom. If a single image fails to download, the
  original comic-server URL is kept as a fallback for that image.
- Old daily image folders accumulate in `docs/img/`; harmless, but you
  can delete them whenever.
- If the run fails with an auth error, re-check the four secrets.
