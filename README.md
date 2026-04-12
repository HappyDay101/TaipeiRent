# Taipei 591 Rent Watcher

This project scrapes 591 rental listings, filters for a Taipei personal search, and sends only new matches to a Discord channel through a webhook.

Current default filters:
- Price `<= 35000`
- Keywords: `大安`, `東門`, `大安森林公園`, `中山`, `中正`, `大同`
- Must include `電梯`
- Must be `整層住家`
- 591 URL can additionally restrict districts, cooking, floor range, and rooftop exclusion

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

Use your own 591 URL or the one you already shared.

```bash
export URL='https://rent.591.com.tw/list?region=1&section=5,1,2,3&price=25000$_35000$&other=lift,cook&floor=2_6,6_12,13_&notice=not_cover'
export DISCORD_WEBHOOK_URL='paste_your_discord_webhook_url_here'
export MAX_PRICE='35000'
export KEYWORDS='大安,東門,大安森林公園,中山,中正,大同'
export WANTED_PAGES='2'
```

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

- `URL`
- `DISCORD_WEBHOOK_URL`

Then:

1. Go to the `Actions` tab.
2. Open the `Rent591Watcher` workflow.
3. Run it once manually.

The workflow commits `seen_ids.json` back to the repo, so duplicate notifications are avoided across scheduled runs too.
The default workflow schedule is hourly from `09:00` to `04:00` Taipei time.

## Local development notes

- Change filters in `main.py` if your search changes later.
- `KEYWORDS` can also be changed without code edits by setting the environment variable.
- If you want to trust the 591 URL only, set `KEYWORDS` to an empty string locally and remove the workflow `KEYWORDS` value.
- `WANTED_PAGES=2` means the script checks the first 2 result pages.

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
