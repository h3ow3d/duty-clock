# Duty Clock

A lightweight time-tracker web application for monitoring how you spend your working day across different duties.

Built with **Python / Flask / SQLite** – no external front-end frameworks, no ORM.

---

## Features

- Create and manage **duties** (Dev work, Meetings, Admin, Support, …)
- **Start / Stop** a timer against any duty with a single click
- Starting a new timer **automatically stops** the previous one
- **Dashboard** shows today's total, per-duty breakdown, and a live percentage bar chart
- **Reports** page with today's detailed entries and a weekly summary grouped by duty
- **Edit or delete** any time entry
- **CSV export** of all time entries

---

## Project structure

```
time-tracker/
  app.py               # Flask application (routes, DB helpers, utilities)
  requirements.txt     # Python dependencies
  README.md            # This file
  instance/
    time_tracker.db    # SQLite database (auto-created on first run)
  templates/
    base.html          # Shared layout
    index.html         # Dashboard
    report.html        # Reports & weekly summary
    edit_entry.html    # Edit a time entry
  static/
    styles.css         # Custom CSS (no Bootstrap)
```

---

## Setup & running locally

### 1. Prerequisites

- Python 3.10 or newer
- `pip`

### 2. Install dependencies

```bash
cd time-tracker
pip install -r requirements.txt
```

### 3. Run the app

```bash
python app.py
```

To enable debug/auto-reload during development:

```bash
FLASK_DEBUG=1 python app.py
```

To set a custom secret key (recommended for any non-local deployment):

```bash
SECRET_KEY=your-random-secret python app.py
```

The database is created automatically on the first run inside `instance/time_tracker.db`.

### 4. Open in your browser

```
http://localhost:5000
```

---

## Database initialisation

The SQLite database and both tables (`duties` and `time_entries`) are created automatically when you start the app for the first time.  You do **not** need to run any migration commands.

If you ever want to reset to a clean state, just delete `instance/time_tracker.db` and restart the app.

---

## Example usage

1. Open the dashboard at `http://localhost:5000`.
2. Type a duty name (e.g. *Dev work*) and click **+ Add**.
3. Click **▶ Start** next to a duty to begin tracking.
4. Click **⏹ Stop** or **▶ Start** on a different duty to switch tasks.
5. Visit `/report` to see today's entries and the weekly summary.
6. Click **⬇ Download CSV** (or visit `/export/csv`) to export all entries.

---

## Routes

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Dashboard |
| POST | `/duties/create` | Create a new duty |
| POST | `/duties/<id>/deactivate` | Deactivate a duty |
| POST | `/duties/<id>/activate` | Re-activate a duty |
| POST | `/duties/<id>/delete` | Delete a duty and all its entries |
| POST | `/start/<duty_id>` | Start a timer (stops any current timer) |
| POST | `/stop` | Stop the active timer |
| GET | `/report` | Reports & weekly summary |
| GET/POST | `/entries/<id>/edit` | Edit a time entry |
| POST | `/entries/<id>/delete` | Delete a time entry |
| GET | `/export/csv` | Download all entries as CSV |
