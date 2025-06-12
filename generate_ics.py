import re
import datetime
from bs4 import BeautifulSoup

def parse_event_date(date_str):
    # e.g. '8 Jan 25' -> 2025-01-08
    day, month, year = re.match(r'(\d{1,2}) (\w{3}) (\d{2})', date_str).groups()
    month_number = datetime.datetime.strptime(month, "%b").month
    year_full = 2000 + int(year)
    return datetime.date(year_full, month_number, int(day))

def parse_time_range(time_str):
    # '19:00 to 21:00' -> ('19:00', '21:00')
    match = re.match(r'(\d{1,2}:\d{2}) to (\d{1,2}:\d{2})', time_str)
    if match:
        return match.group(1), match.group(2)
    # Sometimes time is just one time (start), e.g. '18:00'
    match = re.match(r'(\d{1,2}:\d{2})', time_str)
    if match:
        return match.group(1), None
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

def extract_events(filename, meeting_type, base_url):
    with open(filename, "r", encoding="utf-8") as f:
        html = f.read()
    soup = BeautifulSoup(html, "html.parser")
    today = datetime.date.today()
    ics_events = []

    for minutes_div in soup.find_all("div", class_="minutes"):
        h4 = minutes_div.find("h4")
        if not h4: continue
        date_str = h4.get_text(strip=True)
        try:
            event_date = parse_event_date(date_str)
        except Exception:
            continue
        if event_date < today:
            continue

        # Time: handle possible multiple <p> tags (first is time, next are agenda/minutes)
        p_tags = minutes_div.find_all("p")
        if len(p_tags) == 0:
            continue
        time_str = p_tags[0].get_text(strip=True)
        start_time_str, end_time_str = parse_time_range(time_str)
        if not start_time_str:
            continue

        # Title: e.g. "Full Council Meeting" or "Planning Meeting"
        summary = f"{meeting_type} Meeting"

        # Links to Agenda/Minutes
        description = ""
        for a in minutes_div.find_all("a"):
            if "Agenda" in a.get_text():
                description += f"Agenda: {base_url}{a['href']}\n"
            if "Minutes" in a.get_text():
                description += f"Minutes: {base_url}{a['href']}\n"

        # Combine date and time
        try:
            start_dt = datetime.datetime.strptime(f"{event_date} {start_time_str}", "%Y-%m-%d %H:%M")
        except Exception:
            continue
        if end_time_str:
            try:
                end_dt = datetime.datetime.strptime(f"{event_date} {end_time_str}", "%Y-%m-%d %H:%M")
            except Exception:
                end_dt = start_dt + datetime.timedelta(hours=1)
        else:
            end_dt = start_dt + datetime.timedelta(hours=1)

        ics_events.append(make_ics_event(start_dt, end_dt, summary, description.strip()))

    return ics_events

# Scrape both meetings
full_council_events = extract_events(
    "Full Council - St Mewan Parish Council.html",
    "Full Council",
    "https://www.stmewanparishcouncil.gov.uk"
)
planning_events = extract_events(
    "Planning - St Mewan Parish Council.html",
    "Planning",
    "https://www.stmewanparishcouncil.gov.uk"
)

ical_content = (
    "BEGIN:VCALENDAR\n"
    "VERSION:2.0\n"
    "PRODID:-//St Mewan Parish Council//EN\n"
    "CALSCALE:GREGORIAN\n"
    "METHOD:PUBLISH\n"
    "X-WR-TIMEZONE:Europe/London\n"
    + "".join(full_council_events)
    + "".join(planning_events)
    + "END:VCALENDAR\n"
)

with open("st_mewan_combined.ics", "w", encoding="utf-8") as f:
    f.write(ical_content)

print("Combined iCal file created: st_mewan_combined.ics")
