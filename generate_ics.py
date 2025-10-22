"""
St Mewan Parish Council Calendar Scraper

This script scrapes upcoming meeting dates from the St Mewan Parish Council
website and generates an iCalendar (.ics) file that can be imported into
calendar applications.
"""

import re
import sys
import logging
from datetime import date, datetime, timedelta
from typing import Optional, Tuple, List, Dict
import requests
from bs4 import BeautifulSoup

# Constants
BASE_URL = "https://www.stmewanparishcouncil.gov.uk"
OUTPUT_FILE = "stmewan.ics"
TIMEZONE = "Europe/London"
REQUEST_TIMEOUT = 20
DEFAULT_MEETING_DURATION_HOURS = 1
YEAR_THRESHOLD = 50  # For handling century rollovers in 2-digit years

MEETING_TYPES = [
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
    }
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
    match = re.match(r'(\d{1,2}) (\w{3}) (\d{2})', date_str)
    if not match:
        logging.warning(f"Failed to parse date: '{date_str}'")
        return None

    day, month, year = match.groups()

    try:
        month_number = datetime.strptime(month, "%b").month
    except ValueError as e:
        logging.error(f"Invalid month format '{month}' in date '{date_str}': {e}")
        return None

    # Infer century from current year to handle century rollovers correctly
    year_2digit = int(year)
    current_year = date.today().year
    current_century = (current_year // 100) * 100
    current_2digit = current_year % 100

    # If parsed year is much less than current year, assume next century
    # e.g., in 2099, year "01" should be 2101, not 2001
    if year_2digit < current_2digit - YEAR_THRESHOLD:
        year_full = current_century + 100 + year_2digit
    else:
        year_full = current_century + year_2digit

    try:
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
    # Try to match time range first
    match = re.match(r'(\d{1,2}:\d{2}) to (\d{1,2}:\d{2})', time_str)
    if match:
        return match.group(1), match.group(2)

    # Try to match single time
    match = re.match(r'(\d{1,2}:\d{2})', time_str)
    if match:
        return match.group(1), None

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
    return (
        "BEGIN:VEVENT\n"
        f"DTSTART;TZID={TIMEZONE}:{dtstart.strftime('%Y%m%dT%H%M%S')}\n"
        f"DTEND;TZID={TIMEZONE}:{dtend.strftime('%Y%m%dT%H%M%S')}\n"
        f"SUMMARY:{summary}\n"
        f"DESCRIPTION:{description}\n"
        "END:VEVENT\n"
    )

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
            logging.debug(f"Skipping past event for {meeting_type}: {event_date}")
            continue

        p_tags = minutes_div.find_all("p")
        if len(p_tags) == 0:
            logging.warning(f"No time information found for {meeting_type} on {event_date}")
            continue

        time_str = p_tags[0].get_text(strip=True)
        start_time_str, end_time_str = parse_time_range(time_str)
        if not start_time_str:
            logging.warning(f"Could not parse time for {meeting_type} on {event_date}: '{time_str}'")
            continue

        summary = f"St Mewan Parish - {meeting_type} Meeting"

        # Extract agenda and minutes links
        description = ""
        for a in minutes_div.find_all("a"):
            link_text = a.get_text()
            link_url = a.get("href")
            if not link_url:
                continue
            if not link_url.startswith("http"):
                link_url = BASE_URL + link_url
            if "Agenda" in link_text:
                description += f"Agenda: {link_url}\n"
            if "Minutes" in link_text:
                description += f"Minutes: {link_url}\n"

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
        response = requests.get(meeting["url"], timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
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


def generate_ical_content(events: List[str]) -> str:
    """
    Generate complete iCalendar file content from event strings.

    Args:
        events: List of VEVENT strings

    Returns:
        Complete iCalendar file content
    """
    return (
        "BEGIN:VCALENDAR\n"
        "VERSION:2.0\n"
        "PRODID:-//St Mewan Parish Council//EN\n"
        "CALSCALE:GREGORIAN\n"
        "METHOD:PUBLISH\n"
        f"X-WR-TIMEZONE:{TIMEZONE}\n"
        + "".join(events)
        + "END:VCALENDAR\n"
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

    # Fetch events from all meeting types
    for meeting in MEETING_TYPES:
        events, success = fetch_meeting_events(meeting)
        all_events.extend(events)
        if not success:
            failed_meetings.append(meeting['name'])

    # Validate that we found at least some events
    if len(all_events) == 0:
        logging.error("CRITICAL: Zero events found across all meeting types!")
        logging.error("This likely indicates:")
        logging.error("  1. The website structure has changed")
        logging.error("  2. All meetings are in the past")
        logging.error("  3. Network or parsing errors occurred")
        if failed_meetings:
            logging.error(f"Failed to fetch: {', '.join(failed_meetings)}")
        logging.error("The generated calendar file will be empty.")
        sys.exit(1)

    if failed_meetings:
        logging.warning(f"Failed to fetch some meetings: {', '.join(failed_meetings)}")
        logging.warning("Calendar will be incomplete")

    logging.info(f"Total events collected: {len(all_events)}")

    # Generate and write calendar file
    ical_content = generate_ical_content(all_events)
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(ical_content)
        logging.info(f"Successfully created {OUTPUT_FILE} with {len(all_events)} upcoming meetings")
    except IOError as e:
        logging.error(f"Failed to write calendar file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
