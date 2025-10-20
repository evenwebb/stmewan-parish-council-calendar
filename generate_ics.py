import re
import datetime
import logging
import sys
import requests
from bs4 import BeautifulSoup

MEETING_TYPES = [
    {
        "name": "Full Council",
        "url": "https://www.stmewanparishcouncil.gov.uk/Full_Council_24620.aspx",
        "base_url": "https://www.stmewanparishcouncil.gov.uk"
    },
    {
        "name": "Planning",
        "url": "https://www.stmewanparishcouncil.gov.uk/Planning_24621.aspx",
        "base_url": "https://www.stmewanparishcouncil.gov.uk"
    },
    {
        "name": "Extra Ordinary Council",
        "url": "https://www.stmewanparishcouncil.gov.uk/Extra_Ordinary_Council_Meeting_30589.aspx",
        "base_url": "https://www.stmewanparishcouncil.gov.uk"
    },
    {
        "name": "Finance, Staffing, General Purposes & Audit",
        "url": "https://www.stmewanparishcouncil.gov.uk/Finance_Staffing_General_Purposes__and__Audit_24623.aspx",
        "base_url": "https://www.stmewanparishcouncil.gov.uk"
    },
    {
        "name": "Playing Fields",
        "url": "https://www.stmewanparishcouncil.gov.uk/Playing_Fields_24624.aspx",
        "base_url": "https://www.stmewanparishcouncil.gov.uk"
    },
    {
        "name": "Rights of Way",
        "url": "https://www.stmewanparishcouncil.gov.uk/Rights_of_Way_24622.aspx",
        "base_url": "https://www.stmewanparishcouncil.gov.uk"
    }
]

def parse_event_date(date_str):
    # Example: '8 Jan 25' → 2025-01-08
    match = re.match(r'(\d{1,2}) (\w{3}) (\d{2})', date_str)
    if not match:
        logging.warning(f"Failed to parse date: '{date_str}'")
        return None

    day, month, year = match.groups()

    try:
        month_number = datetime.datetime.strptime(month, "%b").month
    except ValueError as e:
        logging.error(f"Invalid month format '{month}' in date '{date_str}': {e}")
        return None

    # Infer century from current year to handle century rollovers correctly
    year_2digit = int(year)
    current_year = datetime.date.today().year
    current_century = (current_year // 100) * 100
    current_2digit = current_year % 100

    # If parsed year is much less than current year, assume next century
    # e.g., in 2099, year "01" should be 2101, not 2001
    if year_2digit < current_2digit - 50:
        year_full = current_century + 100 + year_2digit
    else:
        year_full = current_century + year_2digit

    try:
        return datetime.date(year_full, month_number, int(day))
    except ValueError as e:
        logging.error(f"Invalid date components in '{date_str}': {e}")
        return None

def parse_time_range(time_str):
    # Example: '19:00 to 21:00' → (19:00, 21:00), or '18:00' → (18:00, None)
    match = re.match(r'(\d{1,2}:\d{2}) to (\d{1,2}:\d{2})', time_str)
    if match:
        return match.group(1), match.group(2)
    match = re.match(r'(\d{1,2}:\d{2})', time_str)
    if match:
        return match.group(1), None

    logging.warning(f"Failed to parse time range: '{time_str}'")
    return None, None

def make_ics_event(dtstart, dtend, summary, description=""):
    return (
        "BEGIN:VEVENT\n"
        f"DTSTART;TZID=Europe/London:{dtstart.strftime('%Y%m%dT%H%M%S')}\n"
        f"DTEND;TZID=Europe/London:{dtend.strftime('%Y%m%dT%H%M%S')}\n"
        f"SUMMARY:{summary}\n"
        f"DESCRIPTION:{description}\n"
        "END:VEVENT\n"
    )

def extract_events_from_html(html, meeting_type, base_url):
    soup = BeautifulSoup(html, "html.parser")
    today = datetime.date.today()
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

        description = ""
        for a in minutes_div.find_all("a"):
            link_text = a.get_text()
            link_url = a.get("href")
            if not link_url: continue
            if not link_url.startswith("http"):
                link_url = base_url + link_url
            if "Agenda" in link_text:
                description += f"Agenda: {link_url}\n"
            if "Minutes" in link_text:
                description += f"Minutes: {link_url}\n"

        try:
            start_dt = datetime.datetime.strptime(f"{event_date} {start_time_str}", "%Y-%m-%d %H:%M")
        except ValueError as e:
            logging.error(f"Failed to parse start time for {meeting_type} on {event_date}: {e}")
            continue

        if end_time_str:
            try:
                end_dt = datetime.datetime.strptime(f"{event_date} {end_time_str}", "%Y-%m-%d %H:%M")
            except ValueError as e:
                logging.warning(f"Failed to parse end time for {meeting_type}, using default 1-hour duration: {e}")
                end_dt = start_dt + datetime.timedelta(hours=1)
        else:
            end_dt = start_dt + datetime.timedelta(hours=1)

        ics_events.append(make_ics_event(start_dt, end_dt, summary, description.strip()))
        logging.info(f"Added event: {meeting_type} on {event_date} at {start_time_str}")

    return ics_events

def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

    logging.info("Starting St Mewan Parish Council calendar scraper")
    all_events = []
    failed_meetings = []

    for meeting in MEETING_TYPES:
        logging.info(f"Fetching {meeting['name']} page from {meeting['url']}")
        try:
            response = requests.get(meeting["url"], timeout=20)
            response.raise_for_status()
        except requests.exceptions.Timeout:
            logging.error(f"Timeout fetching {meeting['name']} page after 20 seconds")
            failed_meetings.append(meeting['name'])
            continue
        except requests.exceptions.HTTPError as e:
            logging.error(f"HTTP error fetching {meeting['name']} page: {e}")
            failed_meetings.append(meeting['name'])
            continue
        except requests.exceptions.RequestException as e:
            logging.error(f"Request failed for {meeting['name']}: {e}")
            failed_meetings.append(meeting['name'])
            continue

        events = extract_events_from_html(response.text, meeting["name"], meeting["base_url"])
        all_events.extend(events)
        logging.info(f"Extracted {len(events)} upcoming events from {meeting['name']}")

    # Validation: Check if we found any events
    if len(all_events) == 0:
        logging.error("CRITICAL: Zero events found across all meeting types!")
        logging.error("This likely indicates:")
        logging.error("  1. The website structure has changed")
        logging.error("  2. All meetings are in the past")
        logging.error("  3. Network or parsing errors occurred")
        if failed_meetings:
            logging.error(f"Failed to fetch: {', '.join(failed_meetings)}")
        logging.error("The generated calendar file will be empty.")
        # Exit with error code if zero events found
        sys.exit(1)

    if failed_meetings:
        logging.warning(f"Failed to fetch some meetings: {', '.join(failed_meetings)}")
        logging.warning("Calendar will be incomplete")

    logging.info(f"Total events collected: {len(all_events)}")

    ical_content = (
        "BEGIN:VCALENDAR\n"
        "VERSION:2.0\n"
        "PRODID:-//St Mewan Parish Council//EN\n"
        "CALSCALE:GREGORIAN\n"
        "METHOD:PUBLISH\n"
        "X-WR-TIMEZONE:Europe/London\n"
        + "".join(all_events)
        + "END:VCALENDAR\n"
    )

    try:
        with open("stmewan.ics", "w", encoding="utf-8") as f:
            f.write(ical_content)
        logging.info(f"Successfully created stmewan.ics with {len(all_events)} upcoming meetings")
    except IOError as e:
        logging.error(f"Failed to write calendar file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
