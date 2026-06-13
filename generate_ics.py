"""
St Mewan Parish Council Calendar Scraper

This script scrapes upcoming meeting dates from the St Mewan Parish Council
website and generates an iCalendar (.ics) file that can be imported into
calendar applications.
"""

import os
import re
import sys
import logging
import hashlib
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Tuple, List, Dict
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

# Constants
BASE_URL = "https://www.stmewanparishcouncil.gov.uk"
OUTPUT_DIR = "docs"
OUTPUT_FILE = "stmewan.ics"
SITE_URL = "https://evenwebb.github.io/stmewan-parish-council-calendar"
TIMEZONE = "Europe/London"
REQUEST_TIMEOUT = 20
REQUEST_RETRIES = 3
USER_AGENT = "StMewanCalendarScraper/1.0 (calendar automation; +https://github.com/evenwebb/stmewan-parish-council-calendar)"
INITIAL_RETRY_DELAY = 1
RETRY_MULTIPLIER = 2
DEFAULT_MEETING_DURATION_HOURS = 1
YEAR_THRESHOLD = 50  # For handling century rollovers in 2-digit years
ICAL_LINE_LENGTH = 75
ICAL_NEWLINE = "\r\n"

def discover_meeting_pages() -> List[Dict[str, str]]:
    """Scrape the council homepage to discover meeting type pages dynamically (#19).
    Falls back to hardcoded list if discovery fails."""
    try:
        resp = requests.get(
            BASE_URL,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        discovered = []
        seen_names = set()
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)
            if not text or len(text) < 3:
                continue
            # Look for links to meeting type ASPX pages
            if ".aspx" in href.lower() and any(
                kw in text.lower() for kw in ("full council", "planning", "rights of way", "finance, staffing", "playing fields", "polgooth playing fields", "extra ordinary")
            ):
                full_url = href if href.startswith("http") else BASE_URL + href
                if text not in seen_names:
                    seen_names.add(text)
                    discovered.append({"name": text, "url": full_url})
        if discovered:
            logging.info("Discovered %d meeting types from council page", len(discovered))
            return discovered
    except (requests.RequestException, Exception) as e:
        logging.warning("Meeting page discovery failed: %s — using hardcoded list", e)
    # Fallback to hardcoded list
    return HARDCODED_MEETING_TYPES


HARDCODED_MEETING_TYPES = [
    {
        "name": "Full Council",
        "url": f"{BASE_URL}/Full_Council_24620.aspx",
    },
    {
        "name": "Planning",
        "url": f"{BASE_URL}/Planning_24621.aspx",
    },
    {
        "name": "Extra Ordinary Council",
        "url": f"{BASE_URL}/Extra_Ordinary_Council_Meeting_30589.aspx",
    },
    {
        "name": "Finance, Staffing, General Purposes & Audit",
        "url": f"{BASE_URL}/Finance_Staffing_General_Purposes__and__Audit_24623.aspx",
    },
    {
        "name": "Playing Fields",
        "url": f"{BASE_URL}/Playing_Fields_24624.aspx",
    },
    {
        "name": "Rights of Way",
        "url": f"{BASE_URL}/Rights_of_Way_24622.aspx",
    },
    {
        "name": "Polgooth Playing Fields Trust",
        "url": f"{BASE_URL}/Polgooth_Playing_Fields_Trust_25013.aspx",
    },
]

def parse_event_date(date_str: str) -> Optional[date]:
    """
    Parse a date string in the format 'DD MMM YY' to a date object.

    Handles century rollovers intelligently. For example, in 2025:
    - '8 Jan 25' becomes 2025-01-08
    - '8 Jan 75' becomes 2075-01-08
    - '8 Jan 74' becomes 2074-01-08

    Args:
        date_str: Date string in format like '8 Jan 25'

    Returns:
        Parsed date object, or None if parsing fails
    """
    # The site date formats have changed over time; accept a few common variants.
    # Examples observed/expected:
    # - "8 Jan 25"
    # - "8 Jan 2026"
    # - "08 January 2026"
    cleaned = re.sub(r"\s+", " ", date_str.strip())
    cleaned = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", cleaned)  # Strip ordinals: "8th" → "8"

    # Try strict known formats first (fast path)
    for fmt in ("%d %b %y", "%d %b %Y", "%d %B %Y"):
        try:
            parsed = datetime.strptime(cleaned, fmt).date()
            # Handle century rollover only for 2-digit years
            if fmt == "%d %b %y":
                year_2digit = parsed.year % 100
                current_year = date.today().year
                current_century = (current_year // 100) * 100
                current_2digit = current_year % 100
                if year_2digit < current_2digit - YEAR_THRESHOLD:
                    return date(current_century + 100 + year_2digit, parsed.month, parsed.day)
                if year_2digit > current_2digit + YEAR_THRESHOLD:
                    return date(current_century - 100 + year_2digit, parsed.month, parsed.day)
                return date(current_century + year_2digit, parsed.month, parsed.day)
            return parsed
        except ValueError:
            pass

    # Fallback: "DD <month> <year>" where month may be abbreviated or full
    match = re.match(r"^(\d{1,2}) ([A-Za-z]{3,}) (\d{2}|\d{4})$", cleaned)
    if not match:
        logging.warning(f"Failed to parse date: '{date_str}'")
        return None

    day, month, year = match.groups()
    try:
        try:
            month_number = datetime.strptime(month[:3], "%b").month
        except ValueError:
            month_number = datetime.strptime(month, "%B").month
    except ValueError as e:
        logging.error(f"Invalid month format '{month}' in date '{date_str}': {e}")
        return None

    try:
        if len(year) == 4:
            year_full = int(year)
        else:
            year_2digit = int(year)
            current_year = date.today().year
            current_century = (current_year // 100) * 100
            current_2digit = current_year % 100
            if year_2digit < current_2digit - YEAR_THRESHOLD:
                year_full = current_century + 100 + year_2digit
            else:
                year_full = current_century + year_2digit
        return date(year_full, month_number, int(day))
    except ValueError as e:
        logging.error(f"Invalid date components in '{date_str}': {e}")
        return None

def parse_time_range(time_str: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse a time range string to extract start and end times.

    Supports both single times and time ranges:
    - '19:00 to 21:00' returns ('19:00', '21:00')
    - '18:00' returns ('18:00', None)

    Args:
        time_str: Time string in formats like '19:00 to 21:00' or '18:00'

    Returns:
        Tuple of (start_time, end_time) as strings, or (None, None) if parsing fails
    """
    cleaned = re.sub(r"\s+", " ", time_str.strip().lower())
    cleaned = cleaned.replace(".", ":")

    # Try to match time range first
    match = re.match(r"^(\d{1,2}:\d{2})\s*(?:to|-)\s*(\d{1,2}:\d{2})$", cleaned)
    if match:
        return match.group(1), match.group(2)

    # Try to match single time (possibly with am/pm)
    match = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", cleaned)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or "00")
        ampm = match.group(3)
        if ampm:
            if ampm == "pm" and hour != 12:
                hour += 12
            if ampm == "am" and hour == 12:
                hour = 0
        return f"{hour:02d}:{minute:02d}", None

    logging.warning(f"Failed to parse time range: '{time_str}'")
    return None, None

def make_ics_event(dtstart: datetime, dtend: datetime, summary: str, description: str = "") -> str:
    """
    Generate an iCalendar event string in VEVENT format.

    Args:
        dtstart: Event start datetime
        dtend: Event end datetime
        summary: Event title/summary
        description: Optional event description (may include URLs)

    Returns:
        Formatted VEVENT string for inclusion in an iCalendar file
    """
    uid_seed = f"{dtstart.isoformat()}|{dtend.isoformat()}|{summary}|{description}"
    uid = f"{hashlib.sha1(uid_seed.encode('utf-8')).hexdigest()}@stmewan-calendar"
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART;TZID={TIMEZONE}:{dtstart.strftime('%Y%m%dT%H%M%S')}",
        f"DTEND;TZID={TIMEZONE}:{dtend.strftime('%Y%m%dT%H%M%S')}",
        _escape_and_fold_ical_text(summary, "SUMMARY:"),
        _escape_and_fold_ical_text(description, "DESCRIPTION:"),
        "SEQUENCE:0",
        "END:VEVENT",
        "",
    ]
    return ICAL_NEWLINE.join(lines)


def _escape_and_fold_ical_text(text: str, prefix: str = "") -> str:
    escaped = (
        text.replace("\\", "\\\\")
        .replace(";", r"\;")
        .replace(",", r"\,")
        .replace("\n", r"\n")
    )
    full_line = prefix + escaped
    if len(full_line) <= ICAL_LINE_LENGTH:
        return full_line
    chunks = [full_line[:ICAL_LINE_LENGTH]]
    remaining = full_line[ICAL_LINE_LENGTH:]
    while remaining:
        chunks.append(" " + remaining[:ICAL_LINE_LENGTH - 1])
        remaining = remaining[ICAL_LINE_LENGTH - 1:]
    return ICAL_NEWLINE.join(chunks)

def extract_events_from_html(html: str, meeting_type: str) -> List[str]:
    """
    Extract upcoming meeting events from HTML content.

    Parses HTML to find meeting dates, times, and associated documents
    (agendas and minutes), then generates iCalendar event strings.

    Args:
        html: HTML content of the meeting page
        meeting_type: Type of meeting (e.g., "Full Council", "Planning")

    Returns:
        List of iCalendar VEVENT strings for upcoming meetings
    """
    soup = BeautifulSoup(html, "html.parser")
    today = date.today()
    ics_events = []

    minutes_divs = soup.find_all("div", class_="minutes")
    logging.info(f"Found {len(minutes_divs)} potential event divs for {meeting_type}")

    for minutes_div in minutes_divs:
        h4 = minutes_div.find("h4")
        if not h4:
            logging.debug(f"Skipping div without h4 tag for {meeting_type}")
            continue

        date_str = h4.get_text(strip=True)
        event_date = parse_event_date(date_str)
        if not event_date:
            logging.warning(f"Could not parse date for {meeting_type}: '{date_str}'")
            continue

        if event_date < today:
            logging.debug(f"Skipping past event for {meeting_type}: {event_date} (raw='{date_str}')")
            continue

        p_tags = minutes_div.find_all("p")
        if len(p_tags) == 0:
            logging.warning(f"No time information found for {meeting_type} on {event_date}")
            continue

        # Find the first <p> that looks like a time (site markup varies)
        time_str = None
        for p in p_tags:
            candidate = p.get_text(strip=True)
            if re.search(r"\b\d{1,2}([:.]\d{2})?\s*(am|pm)?\b", candidate, flags=re.IGNORECASE):
                time_str = candidate
                break
        if not time_str:
            time_str = p_tags[0].get_text(strip=True)
        start_time_str, end_time_str = parse_time_range(time_str)
        if not start_time_str:
            logging.warning(f"Could not parse time for {meeting_type} on {event_date}: '{time_str}'")
            continue

        # Extract meeting sub-type and venue from p tags
        meeting_subtype = ""
        venue = ""
        for p in p_tags:
            pt = p.get_text(strip=True)
            # Skip time strings and standalone "Agenda"/"Minutes" labels
            if re.search(r"\b\d{1,2}([:.]\d{2})?\s*(am|pm|to)?\b", pt, flags=re.IGNORECASE):
                continue
            if pt.lower() in ("agenda", "minutes", "agenda (pdf)", "minutes (pdf)"):
                continue
            if not meeting_subtype and any(
                kw in pt.lower() for kw in ("ordinary", "annual", "extra", "parish", "assembly", "meeting")
            ):
                meeting_subtype = pt
            elif not venue and not re.search(r"\d", pt):
                venue = pt

        # Build summary with subtype and venue
        if meeting_subtype:
            summary = f"St Mewan Parish - {meeting_subtype}"
        else:
            summary = f"St Mewan Parish - {meeting_type} Meeting"

        # Extract agenda and minutes links
        description = ""
        if venue:
            description += f"Location: {venue}\n"
        for a in minutes_div.find_all("a"):
            link_text = a.get_text()
            link_url = a.get("href")
            if not link_url:
                continue
            if not link_url.startswith("http"):
                link_url = urljoin(BASE_URL, link_url)
            doc_title = link_text.strip()
            if "Agenda" in link_text:
                description += f"Agenda ({doc_title}): {link_url}\n"
            if "Minutes" in link_text:
                description += f"Minutes ({doc_title}): {link_url}\n"

        # Parse start datetime
        try:
            start_dt = datetime.strptime(f"{event_date} {start_time_str}", "%Y-%m-%d %H:%M")
        except ValueError as e:
            logging.error(f"Failed to parse start time for {meeting_type} on {event_date}: {e}")
            continue

        # Parse or calculate end datetime
        if end_time_str:
            try:
                end_dt = datetime.strptime(f"{event_date} {end_time_str}", "%Y-%m-%d %H:%M")
            except ValueError as e:
                logging.warning(
                    f"Failed to parse end time for {meeting_type}, "
                    f"using default {DEFAULT_MEETING_DURATION_HOURS}-hour duration: {e}"
                )
                end_dt = start_dt + timedelta(hours=DEFAULT_MEETING_DURATION_HOURS)
        else:
            end_dt = start_dt + timedelta(hours=DEFAULT_MEETING_DURATION_HOURS)

        ics_events.append(make_ics_event(start_dt, end_dt, summary, description.strip()))
        logging.info(f"Added event: {meeting_type} on {event_date} at {start_time_str}")

    return ics_events

def fetch_meeting_events(meeting: Dict[str, str]) -> Tuple[List[str], bool]:
    """
    Fetch and extract events for a specific meeting type.

    Args:
        meeting: Dictionary containing meeting 'name' and 'url'

    Returns:
        Tuple of (list of event strings, success boolean)
    """
    logging.info(f"Fetching {meeting['name']} page from {meeting['url']}")
    try:
        response = fetch_with_retries(meeting["url"])
    except requests.exceptions.Timeout:
        logging.error(f"Timeout fetching {meeting['name']} page after {REQUEST_TIMEOUT} seconds")
        return [], False
    except requests.exceptions.HTTPError as e:
        logging.error(f"HTTP error fetching {meeting['name']} page: {e}")
        return [], False
    except requests.exceptions.RequestException as e:
        logging.error(f"Request failed for {meeting['name']}: {e}")
        return [], False

    events = extract_events_from_html(response.text, meeting["name"])
    logging.info(f"Extracted {len(events)} upcoming events from {meeting['name']}")
    return events, True


def fetch_with_retries(url: str) -> requests.Response:
    delay = INITIAL_RETRY_DELAY
    for attempt in range(REQUEST_RETRIES):
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            logging.warning("Attempt %d failed for %s: %s", attempt + 1, url, exc)
            if attempt == REQUEST_RETRIES - 1:
                raise
            time.sleep(delay)
            delay *= RETRY_MULTIPLIER
    raise requests.RequestException("All retries exhausted")  # safety net for retries=0


def generate_ical_content(events: List[str]) -> str:
    """
    Generate complete iCalendar file content from event strings.

    Args:
        events: List of VEVENT strings

    Returns:
        Complete iCalendar file content
    """
    return (
        ICAL_NEWLINE.join(
            [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//St Mewan Parish Council//EN",
                "CALSCALE:GREGORIAN",
                "METHOD:PUBLISH",
                f"X-WR-TIMEZONE:{TIMEZONE}",
                "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
                "X-PUBLISHED-TTL:PT12H",
            ]
        )
        + ICAL_NEWLINE
        + "".join(events)
        + f"END:VCALENDAR{ICAL_NEWLINE}"
    )


def configure_logging() -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )


def main() -> None:
    """
    Main function to scrape parish council meetings and generate iCalendar file.

    Fetches meeting information from all configured meeting types,
    extracts upcoming events, and writes them to an .ics file.

    Exits with status code 1 if no events are found or file write fails.
    """
    configure_logging()
    logging.info("Starting St Mewan Parish Council calendar scraper")

    all_events = []
    failed_meetings = []

    # Fetch events from all meeting types (discovered dynamically, fallback to hardcoded)
    meeting_types = discover_meeting_pages()
    for meeting in meeting_types:
        events, success = fetch_meeting_events(meeting)
        all_events.extend(events)
        if not success:
            failed_meetings.append(meeting['name'])

    # If there are no upcoming events, keep the last published calendar file.
    # This avoids breaking subscribers just because the site has no future meetings listed
    # (or because markup temporarily changed).
    if len(all_events) == 0:
        logging.warning("No upcoming events found across all meeting types.")
        logging.warning("Leaving existing calendar file as-is and exiting successfully.")
        sys.exit(1)
        if failed_meetings:
            logging.warning(f"Some meeting pages failed to fetch: {', '.join(failed_meetings)}")
        return

    if failed_meetings:
        logging.warning(f"Failed to fetch some meetings: {', '.join(failed_meetings)}")
        logging.warning("Calendar will be incomplete")

    logging.info(f"Total events collected: {len(all_events)}")

    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Generate and write calendar file
    ical_content = generate_ical_content(all_events)
    ics_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    try:
        tmp = ics_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(ical_content)
        os.replace(tmp, ics_path)
        logging.info(f"Successfully created {ics_path} with {len(all_events)} upcoming meetings")
    except IOError as e:
        logging.error(f"Failed to write calendar file: {e}")
        sys.exit(1)

    # Generate HTML landing page
    try:
        html = _build_index_html(len(all_events), meeting_types)
        html_path = os.path.join(OUTPUT_DIR, "index.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        logging.info(f"Created {html_path}")
    except Exception as e:
        logging.warning(f"HTML generation failed (non-fatal): {e}")


def _build_index_html(event_count: int, meeting_types: list) -> str:
    now = datetime.now().strftime("%d %B %Y at %H:%M")
    ics_url = f"{SITE_URL}/{OUTPUT_FILE}"
    webcal_url = ics_url.replace("https://", "webcal://")
    gcal_url = f"https://calendar.google.com/calendar/render?cid={webcal_url}"

    meeting_list = ""
    for mt in meeting_types[:15]:
        meeting_list += f"<li>{mt['name']}</li>\n"

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>St Mewan Parish Council — Meeting Calendar</title>
    <meta name="description" content="Subscribe to the St Mewan Parish Council meeting calendar. Stay informed about Full Council, Planning, Finance, and committee meetings.">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🏛️</text></svg>">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <style>
        :root{{--bg:#0a0a12;--surface:#12121e;--surface2:#1a1a2c;--border:rgba(139,157,181,0.18);--text:#e4e8f0;--muted:#8b9db5;--accent:#818cf8;--accent-dim:rgba(129,140,248,0.12);--green:#4ade80;--amber:#fbbf24;--radius:14px;--radius-sm:8px}}
        [data-theme="light"]{{--bg:#f8fafc;--surface:#ffffff;--surface2:#f1f5f9;--border:rgba(100,116,139,0.15);--text:#1e293b;--muted:#64748b;--accent:#4f46e5;--accent-dim:rgba(79,70,229,0.1);--green:#16a34a;--amber:#d97706}}
        *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
        body{{font-family:'Outfit',system-ui,sans-serif;background:var(--bg);color:var(--text);line-height:1.6;transition:background .2s,color .2s}}
        .container{{max-width:800px;margin:0 auto;padding:2rem 1.5rem 4rem}}
        .header{{text-align:center;padding:3rem 0 2.5rem}}
        .header h1{{font-size:2.2rem;font-weight:700;letter-spacing:-0.02em;margin-bottom:0.5rem}}
        .header .badge{{display:inline-block;font-size:0.8rem;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:var(--accent);background:var(--accent-dim);padding:0.3rem 0.85rem;border-radius:100px;margin-bottom:1rem}}
        .header p{{color:var(--muted);font-size:1.05rem;max-width:500px;margin:0 auto}}
        .theme-toggle{{position:fixed;top:1rem;right:1rem;background:var(--surface);border:1px solid var(--border);color:var(--text);cursor:pointer;padding:0.45rem 0.8rem;border-radius:8px;font-size:0.85rem;transition:background .15s;z-index:10}}
        .theme-toggle:hover{{background:var(--surface2)}}

        .subscribe-card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:2rem;margin-bottom:2rem;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.2)}}
        .subscribe-card h2{{font-size:1.3rem;margin-bottom:1.25rem}}
        .sub-buttons{{display:flex;flex-wrap:wrap;gap:0.75rem;justify-content:center;margin-bottom:1.5rem}}
        .sub-btn{{display:inline-flex;align-items:center;gap:0.5rem;padding:0.7rem 1.4rem;border-radius:100px;font-weight:600;font-size:0.9rem;text-decoration:none;transition:all .15s;border:1px solid var(--border);background:var(--surface2);color:var(--text)}}
        .sub-btn:hover{{transform:translateY(-1px);box-shadow:0 4px 12px rgba(0,0,0,.25);border-color:var(--accent)}}
        .sub-btn.primary{{background:var(--accent);color:#fff;border-color:var(--accent)}}
        .sub-url{{font-family:'JetBrains Mono',monospace;font-size:0.82rem;color:var(--muted);word-break:break-all;background:var(--surface2);padding:0.6rem 1rem;border-radius:var(--radius-sm);margin-top:1rem}}

        .instructions{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1.25rem;margin-bottom:2.5rem}}
        .inst-card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:1.5rem}}
        .inst-card h3{{font-size:1rem;margin-bottom:0.6rem;display:flex;align-items:center;gap:0.5rem}}
        .inst-card p,.inst-card ol{{font-size:0.88rem;color:var(--muted);line-height:1.7}}
        .inst-card ol{{padding-left:1.25rem}}
        .inst-card li{{margin-bottom:0.3rem}}

        .meetings-card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:1.5rem;margin-bottom:2rem}}
        .meetings-card h2{{font-size:1.2rem;margin-bottom:1rem}}
        .meeting-types{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:0.75rem}}
        .meeting-type{{background:var(--surface2);padding:0.8rem 1rem;border-radius:var(--radius-sm);border:1px solid var(--border);font-size:0.9rem;font-weight:500}}
        .stat-badge{{display:inline-flex;align-items:center;gap:0.4rem;font-size:0.85rem;color:var(--green);background:rgba(74,222,128,0.12);padding:0.3rem 0.75rem;border-radius:100px;margin:1rem 0}}

        footer{{text-align:center;padding:2rem 0;color:var(--muted);font-size:0.85rem;border-top:1px solid var(--border);margin-top:2rem}}
        footer a{{color:var(--accent)}}
        @media(max-width:600px){{.header h1{{font-size:1.6rem}}.container{{padding:1rem}}.sub-buttons{{flex-direction:column}}.sub-btn{{justify-content:center}}}}
    </style>
</head>
<body>
    <button class="theme-toggle" onclick="toggleTheme()" aria-label="Toggle theme">☀️ 🌙</button>
    <div class="container">
        <div class="header">
            <div class="badge">Cornwall · Local Government</div>
            <h1>St Mewan Parish<br>Council Meetings</h1>
            <p>Subscribe to stay informed about upcoming parish council meetings. Calendar includes Full Council, Planning, Finance, and committee meetings with agenda and minutes links.</p>
        </div>

        <div class="subscribe-card">
            <h2>📅 Subscribe to the Calendar</h2>
            <div class="sub-buttons">
                <a href="{webcal_url}" class="sub-btn primary">📱 Add to Apple / iOS</a>
                <a href="{gcal_url}" class="sub-btn" target="_blank" rel="noopener">🔗 Add to Google Calendar</a>
                <a href="{OUTPUT_FILE}" class="sub-btn" download>💾 Download .ics File</a>
            </div>
            <div class="sub-url">{ics_url}</div>
        </div>

        <div class="instructions">
            <div class="inst-card">
                <h3>📱 iPhone / iPad</h3>
                <ol><li>Tap <strong>Add to Apple / iOS</strong> above</li><li>Tap <strong>Subscribe</strong> when prompted</li><li>The calendar appears in your Calendar app</li></ol>
            </div>
            <div class="inst-card">
                <h3>🔗 Google Calendar</h3>
                <ol><li>Tap <strong>Add to Google Calendar</strong> above</li><li>Sign in if needed</li><li>Confirm to add the calendar</li></ol>
            </div>
            <div class="inst-card">
                <h3>💻 Outlook / Desktop</h3>
                <ol><li>Click <strong>Download .ics File</strong> above</li><li>Open the downloaded file</li><li>Your calendar app will import it</li></ol>
            </div>
            <div class="inst-card">
                <h3>🔄 Auto-Updates</h3>
                <p>This calendar checks for new meetings every 24 hours. Subscribe via Apple or Google above for automatic updates — no manual re-downloading needed.</p>
            </div>
        </div>

        <div class="meetings-card">
            <h2>📋 Meeting Types Tracked</h2>
            <div class="stat-badge">📌 {event_count} upcoming meeting{'s' if event_count != 1 else ''} in the calendar</div>
            <div class="meeting-types">
                {meeting_list or '<div class="meeting-type">Meeting types will appear after the first successful scrape</div>'}
            </div>
        </div>

        <footer>
            <p>St Mewan Parish Council Meeting Calendar · Updated {now}</p>
            <p style="margin-top:0.5rem">An open-source community project. <a href="https://github.com/evenwebb/stmewan-parish-council-calendar">Source on GitHub</a> · <a href="{BASE_URL}">Council Website</a></p>
        </footer>
    </div>
    <script>
    (function(){{var t=localStorage.getItem('stmewan-theme')||(window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');document.documentElement.setAttribute('data-theme',t)}})();
    function toggleTheme(){{var c=document.documentElement.getAttribute('data-theme');var n=c==='dark'?'light':'dark';document.documentElement.setAttribute('data-theme',n);localStorage.setItem('stmewan-theme',n)}}
    </script>
</body>
</html>"""


if __name__ == "__main__":
    main()
