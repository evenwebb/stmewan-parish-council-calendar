# Parish Council Calendar

This repository contains a Python script that scrapes upcoming meeting dates from the St Mewan Parish Council website and builds an iCalendar (`.ics`) file. The generated calendar can be imported into any calendar application that supports the iCalendar format.

## Requirements

- Python 3
- `requests`
- `beautifulsoup4`

Install the dependencies using `pip`:

```bash
pip install -r requirements.txt
```

## Usage

Run the script to fetch the meeting information and generate `stmewan.ics`:

```bash
python generate_ics.py
```

The script downloads the meeting pages, extracts upcoming dates and associated links (agenda and minutes when available) and writes them into `stmewan.ics`.

## Calendar file

An example `stmewan.ics` is included in this repository. After running the script you can import the file into your preferred calendar application to view upcoming Parish Council meetings.

