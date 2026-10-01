# Taipei 591 Rent Watcher

This project scrapes 591 rental listings, filters for a Taipei personal search, and sends only new matches to a Discord channel through a webhook.

Current default filters:
- Price `<= 35000`
- Keywords: `大安`, `東門`, `大安森林公園`, `中山`, `中正`, `大同`
- Must include `電梯` (can be disabled with `REQUIRE_ELEVATOR=false`)
- Allowed property types: `整層住家` (configurable with `ALLOWED_KINDS`)
- 591 URL can additionally restrict districts, MRT stations, cooking, floor range, and rooftop exclusion

### Searching more than one property type (e.g. 整層住家 + 獨立套房)

591 only lets a single 類型 (property type) be selected per search — both in the
website UI and in the URL (`kind=1,2` is silently treated as `kind=1`). To watch two
types at once, give the `URL` variable **two URLs** separated by a space or newline —
one per type — and the watcher fetches both, merges, and de-duplicates them. Set
`ALLOWED_KINDS` so the code-side filter keeps both types:

```bash
export URL='https://rent.591.com.tw/list?...&kind=1&... https://rent.591.com.tw/list?...&kind=2&...'
export ALLOWED_KINDS='整層住家,獨立套房'
```

591 `kind` values: `1`=整層住家, `2`=獨立套房, `3`=分租套房, `4`=雅房.

The script stores notified listing IDs in `seen_ids.json` so it does not send the same house twice.

## Repo structure

- [main.py](./main.py): scraping, filtering, dedupe, formatting, Discord notification
- [.github/workflows/python-package.yml](./.github/workflows/python-package.yml): scheduled GitHub Actions run
- [requirements.txt](./requirements.txt): Python dependencies

## How it works

1. Open the 591 search page and collect listing IDs.
2. Fetch each listing detail from the 591 detail API.
3. Normalize each listing into a simple structure.
4. Filter by price, keywords, elevator, and whole-unit requirement.
5. Skip already-seen listing IDs from `seen_ids.json`.
6. Send clean Discord messages for brand new matches.

## Step 1: Create a Discord webhook

1. Open Discord.
2. Create a server or use an existing one.
3. Create a channel like `rent-alerts`.
4. Open the channel settings.
5. Go to `Integrations`.
6. Click `Webhooks`.
7. Create a new webhook.
8. Copy the webhook URL.

This webhook URL is the only thing you need for notifications.

## Step 2: Install Python dependencies

```bash
pip install -r requirements.txt
```

## Step 3: Set environment variables

Use your own 591 URL(s). The example below watches the 板南線 MRT search for both
整層住家 and 獨立套房 within 1000m of 國父紀念館 / 忠孝敦化 / 忠孝復興 / 忠孝新生 / 善導寺,
`20000-30000` 元, 電梯大樓, excluding rooftop additions:

```bash
export URL='https://rent.591.com.tw/list?region=1&metro=168&mrt_distance=1000&station=4267,4221,4187,4264,4263&kind=1&price=20000_30000&shape=2&notice=not_cover https://rent.591.com.tw/list?region=1&metro=168&mrt_distance=1000&station=4267,4221,4187,4264,4263&kind=2&price=20000_30000&shape=2&notice=not_cover'
export DISCORD_WEBHOOK_URL='paste_your_discord_webhook_url_here'
export MAX_PRICE='30000'
export ALLOWED_KINDS='整層住家,獨立套房'
export KEYWORDS=''          # empty = trust the URL (MRT-based search, no district keywords)
export REQUIRE_ELEVATOR='false'   # shape=2 already restricts to 電梯大樓
export WANTED_PAGES='2'
export SEND_EMPTY_STATUS='true'
```

Environment variables:
- `URL` — one or more 591 search URLs (space/newline separated). Each extra URL is
  merged and de-duplicated, which is how you combine property types.
- `MAX_PRICE` — hard upper bound applied in code on top of the URL filter.
- `ALLOWED_KINDS` — comma-separated property types to keep (default `整層住家`). Empty = keep all.
- `KEYWORDS` — comma-separated text that must appear in a listing. Empty = no keyword filter.
- `REQUIRE_ELEVATOR` — require `電梯` in the listing (default `true`).
- `WANTED_PAGES` — how many result pages to scan per URL.
- `SEND_EMPTY_STATUS` — post a heartbeat when a run finds nothing new.

## Step 4: Test locally first

Run in dry mode first so nothing gets posted while you verify matches.

```bash
export DRY_RUN='true'
python main.py
```

Expected result:
- matching listings print to the terminal
- no Discord messages are sent
- `seen_ids.json` is not updated during dry run
- each printed result shows title, price, location, and link

If the printed matches look correct, turn off dry run:

```bash
unset DRY_RUN
python main.py
```

That run will post new matches to your Discord channel and save their IDs in `seen_ids.json`.

## Step 5: Use GitHub Actions for automatic checks

Add these GitHub repository secrets:

- `URL` — the first 591 search URL (e.g. the `kind=1` / 整層住家 search)
- `URL2` — the second 591 search URL (e.g. the `kind=2` / 獨立套房 search); optional
- `DISCORD_WEBHOOK_URL`

The workflow combines `URL` and `URL2` into one multi-URL search, so each secret holds
a single URL. If you only want one property type, leave `URL2` unset.

Then:

1. Go to the `Actions` tab (if you see a banner, click **"I understand my workflows, go ahead and enable them"**).
2. Open the `Rent591Watcher` workflow (if it shows **"Enable workflow"**, click it).
3. Click **Run workflow** to run it once manually and confirm it works.

Once the workflow file is on the `main` branch and Actions are enabled, the hourly
schedule runs automatically — no further action needed.

The workflow commits `seen_ids.json` back to the repo, so duplicate notifications are avoided across scheduled runs too.
The default workflow schedule is hourly from `09:00` to `04:00` Taipei time.
The default workflow also sends `No new listing found / 未找到新房源` when a run finishes without any new matches.

## Local development notes

- Change filters in `main.py` if your search changes later.
- `KEYWORDS` can also be changed without code edits by setting the environment variable.
- If you want to trust the 591 URL only, set `KEYWORDS` to an empty string locally and remove the workflow `KEYWORDS` value.
- `WANTED_PAGES=2` means the script checks the first 2 result pages.
- `SEND_EMPTY_STATUS=true` posts a heartbeat message when no new listings are found.

## Quick troubleshooting

If Discord does not receive messages:
- make sure the webhook URL is correct
- make sure the channel still has that webhook enabled
- make sure `DRY_RUN` is turned off

If nothing matches:
- run with `DRY_RUN=true`
- widen the 591 URL filters
- check whether the listings actually contain `大安`, `東門`, `大安森林公園`, `電梯`, and `整層住家`

If 591 changes their site:
- the scraper may need small adjustments
- the most likely places to update are listing extraction in `get_house_ids()` and field parsing in `normalize_listing()`
