<div align="center">

# 🏛️ St Mewan Parish Council Calendar Scraper

Automatically fetches upcoming St Mewan Parish Council meeting dates and generates an iCalendar (`.ics`) feed for Apple Calendar, Google Calendar, Outlook, and other calendar apps.

</div>

---

## 📚 Table of Contents

- [⚡ Quick Start](#-quick-start)
- [✨ Features](#-features)
- [📦 Installation](#-installation)
- [🚀 Usage](#-usage)
- [⚙️ Configuration](#️-configuration)
- [🤖 GitHub Actions Automation](#-github-actions-automation)
- [📲 Subscribe in Calendar Apps](#-subscribe-in-calendar-apps)
- [🧩 Dependencies](#-dependencies)
- [🛠️ Troubleshooting](#️-troubleshooting)
- [⚠️ Known Limitations](#️-known-limitations)
- [📄 License](#-license)

---

## ⚡ Quick Start

```bash
git clone https://github.com/evenwebb/stmewan-parish-council-calendar.git
cd stmewan-parish-council-calendar
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 generate_ics.py
```

✅ Output file: `stmewan.ics`

---

## ✨ Features

| Feature | Description |
|---|---|
| `🏛️ Multi-Page Meeting Scrape` | Collects upcoming events across configured St Mewan meeting page types. |
| `🕒 Date/Time Parsing` | Supports single times and explicit time ranges per meeting entry. |
| `🔗 Agenda & Minutes Links` | Adds available agenda/minutes URLs into event descriptions automatically. |
| `📆 Upcoming-Only Focus` | Filters out past events and keeps future meetings in output. |
| `📅 Stable Calendar Sync` | Uses deterministic UIDs + `DTSTAMP` and RFC 5545-compatible line escaping/folding. |
| `🌐 Retry-Hardened Fetching` | Includes retry/backoff logic for network calls and workflow execution. |
| `🤖 GitHub Actions Ready` | Daily automation updates `stmewan.ics` and can open failure issues. |

---

## 📦 Installation

```bash
git clone https://github.com/evenwebb/stmewan-parish-council-calendar.git
cd stmewan-parish-council-calendar
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 🚀 Usage

```bash
python3 generate_ics.py
```

The script fetches configured meeting pages, extracts future events, and writes `stmewan.ics`.

---

## ⚙️ Configuration

Settings are defined at the top of `generate_ics.py`.

| Option | Default | Description |
|---|---|---|
| `BASE_URL` | `https://www.stmewanparishcouncil.gov.uk` | Base URL for meeting pages and links. |
| `OUTPUT_FILE` | `stmewan.ics` | Output calendar file path/name. |
| `TIMEZONE` | `Europe/London` | Timezone for calendar events. |
| `REQUEST_TIMEOUT` | `20` | HTTP timeout in seconds. |
| `REQUEST_RETRIES` | `3` | Number of request retries per URL. |
| `INITIAL_RETRY_DELAY` | `1` | Initial request retry delay (seconds). |
| `RETRY_MULTIPLIER` | `2` | Backoff multiplier between retries. |
| `DEFAULT_MEETING_DURATION_HOURS` | `1` | Default duration when end time is missing. |
| `MEETING_TYPES` | list in script | Meeting pages to scrape. |

---

## 🤖 GitHub Actions Automation

This repo includes `.github/workflows/scrape.yml`:

- `⏰` Runs daily at `11:00 UTC`
- `🖱️` Supports manual runs (`workflow_dispatch`)
- `🔁` Retries scraper runs before failing (`SCRAPER_RUN_ATTEMPTS`, default `2`)
- `✅` Validates that `stmewan.ics` was generated
- `📝` Commits output only when changed
- `🚨` Optionally opens or updates a GitHub issue on failure (`CREATE_FAILURE_ISSUE=true`)

Configure these repository secrets if needed:

- `CREATE_FAILURE_ISSUE` (`true`/`false`)
- `SCRAPER_RUN_ATTEMPTS` (integer)

---

## 📲 Subscribe in Calendar Apps

Use the raw GitHub `.ics` URL as a subscription URL:

`https://raw.githubusercontent.com/<github-user>/stmewan-parish-council-calendar/<branch>/stmewan.ics`

### 🗓️ Google Calendar

1. Open Google Calendar on web.
2. Click **+** next to **Other calendars**.
3. Select **From URL**.
4. Paste the raw `.ics` URL.

### 🍎 iPhone / iPad

1. Open **Settings**.
2. Go to **Calendar** -> **Accounts** -> **Add Account** -> **Other**.
3. Tap **Add Subscribed Calendar**.
4. Paste the raw `.ics` URL.

### 🤖 Android

1. Add the subscription in Google Calendar web using **From URL**.
2. Ensure that calendar is enabled in your Android calendar app sync settings.

---

## 🧩 Dependencies

| Package | Purpose |
|---|---|
| `requests` | HTTP requests to meeting pages |
| `beautifulsoup4` | HTML parsing and event extraction |

---

## 🛠️ Troubleshooting

- `🧱` If no events are returned, source HTML structure may have changed.
- `📣` Enable more verbose logs by adjusting logging config in `generate_ics.py`.
- `🔁` If scraper failures are intermittent, raise `SCRAPER_RUN_ATTEMPTS` in secrets.

---

## ⚠️ Known Limitations

- `🌐` Extraction relies on current page structure and class names.
- `📄` Event details are limited to what is available in meeting listings.

---

## 📄 License

[GPL-3.0](LICENSE)
