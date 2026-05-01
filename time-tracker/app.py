"""
Duty Clock – a simple time-tracker for daily work duties.
Flask + SQLite, no external ORM required.
"""

import csv
import io
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from flask import (
    Flask,
    g,
    redirect,
    render_template,
    request,
    Response,
    url_for,
    flash,
)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__, instance_relative_config=True)

# Load secret key from environment; fall back to a development default (not for production).
app.secret_key = os.environ.get("SECRET_KEY", "duty-clock-dev-secret-change-me")

# Ensure the instance folder exists so SQLite can create the DB file there.
Path(app.instance_path).mkdir(parents=True, exist_ok=True)

DATABASE = Path(app.instance_path) / "time_tracker.db"


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    """Return a per-request SQLite connection stored on Flask's `g` object."""
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables if they don't already exist."""
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS duties (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            name   TEXT    NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS time_entries (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            duty_id    INTEGER NOT NULL,
            started_at TEXT    NOT NULL,
            ended_at   TEXT,
            notes      TEXT,
            FOREIGN KEY (duty_id) REFERENCES duties (id)
        );
        """
    )
    db.commit()


# ---------------------------------------------------------------------------
# Time / duration utilities
# ---------------------------------------------------------------------------

def now_iso() -> str:
    """Return the current local time as an ISO-8601 string (no timezone suffix)."""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def parse_dt(iso_str: str) -> datetime:
    """Parse an ISO-8601 string (without timezone) into a datetime object."""
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(iso_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {iso_str!r}")


def format_duration(seconds: float) -> str:
    """Convert a number of seconds into a human-readable string like '2h 15m'."""
    if seconds < 0:
        seconds = 0
    total_minutes = int(seconds) // 60
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


def entry_duration_seconds(entry) -> float:
    """Return the duration in seconds for a time-entry row.

    Uses *now* as the end time when the entry is still running.
    """
    start = parse_dt(entry["started_at"])
    end = parse_dt(entry["ended_at"]) if entry["ended_at"] else datetime.now()
    return (end - start).total_seconds()


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def week_start_str() -> str:
    """Return the ISO date of Monday of the current week."""
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    return monday.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_active_entry(db):
    """Return the currently running time entry (ended_at IS NULL), or None."""
    return db.execute(
        """
        SELECT te.*, d.name AS duty_name
        FROM   time_entries te
        JOIN   duties d ON d.id = te.duty_id
        WHERE  te.ended_at IS NULL
        ORDER  BY te.started_at DESC
        LIMIT  1
        """
    ).fetchone()


def get_today_entries(db):
    """Return all time entries that started today, newest first."""
    return db.execute(
        """
        SELECT te.*, d.name AS duty_name
        FROM   time_entries te
        JOIN   duties d ON d.id = te.duty_id
        WHERE  date(te.started_at) = ?
        ORDER  BY te.started_at DESC
        """,
        (today_str(),),
    ).fetchall()


def build_duty_totals(entries) -> list[dict]:
    """Aggregate total seconds per duty from a list of entry rows."""
    totals: dict[str, float] = {}
    for e in entries:
        totals[e["duty_name"]] = totals.get(e["duty_name"], 0) + entry_duration_seconds(e)

    overall = sum(totals.values()) or 1  # avoid division by zero
    result = []
    for duty_name, secs in sorted(totals.items()):
        result.append(
            {
                "duty_name": duty_name,
                "total_seconds": secs,
                "duration": format_duration(secs),
                "percentage": round(secs / overall * 100),
            }
        )
    return result


# ---------------------------------------------------------------------------
# Routes – Dashboard (index)
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    db = get_db()
    init_db()

    duties = db.execute("SELECT * FROM duties ORDER BY name").fetchall()
    active_entry = get_active_entry(db)
    today_entries = get_today_entries(db)

    # Total tracked time today
    total_seconds = sum(entry_duration_seconds(e) for e in today_entries)

    duty_totals = build_duty_totals(today_entries)

    return render_template(
        "index.html",
        duties=duties,
        active_entry=active_entry,
        today_entries=today_entries,
        total_duration=format_duration(total_seconds),
        duty_totals=duty_totals,
        format_duration=format_duration,
        entry_duration_seconds=entry_duration_seconds,
    )


# ---------------------------------------------------------------------------
# Routes – Duties
# ---------------------------------------------------------------------------

@app.route("/duties/create", methods=["POST"])
def create_duty():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Duty name cannot be empty.", "error")
        return redirect(url_for("index"))
    db = get_db()
    db.execute("INSERT INTO duties (name) VALUES (?)", (name,))
    db.commit()
    flash(f"Duty '{name}' created.", "success")
    return redirect(url_for("index"))


@app.route("/duties/<int:duty_id>/deactivate", methods=["POST"])
def deactivate_duty(duty_id: int):
    db = get_db()
    db.execute("UPDATE duties SET active = 0 WHERE id = ?", (duty_id,))
    db.commit()
    flash("Duty deactivated.", "success")
    return redirect(url_for("index"))


@app.route("/duties/<int:duty_id>/activate", methods=["POST"])
def activate_duty(duty_id: int):
    db = get_db()
    db.execute("UPDATE duties SET active = 1 WHERE id = ?", (duty_id,))
    db.commit()
    flash("Duty activated.", "success")
    return redirect(url_for("index"))


@app.route("/duties/<int:duty_id>/delete", methods=["POST"])
def delete_duty(duty_id: int):
    db = get_db()
    # Remove related time entries first to respect FK integrity
    db.execute("DELETE FROM time_entries WHERE duty_id = ?", (duty_id,))
    db.execute("DELETE FROM duties WHERE id = ?", (duty_id,))
    db.commit()
    flash("Duty and its time entries deleted.", "success")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Routes – Time tracking
# ---------------------------------------------------------------------------

@app.route("/start/<int:duty_id>", methods=["POST"])
def start_timer(duty_id: int):
    db = get_db()

    # Stop any currently running entry first
    active = get_active_entry(db)
    if active:
        db.execute(
            "UPDATE time_entries SET ended_at = ? WHERE id = ?",
            (now_iso(), active["id"]),
        )

    # Start a new entry
    db.execute(
        "INSERT INTO time_entries (duty_id, started_at) VALUES (?, ?)",
        (duty_id, now_iso()),
    )
    db.commit()
    return redirect(url_for("index"))


@app.route("/stop", methods=["POST"])
def stop_timer():
    db = get_db()
    active = get_active_entry(db)
    if active:
        db.execute(
            "UPDATE time_entries SET ended_at = ? WHERE id = ?",
            (now_iso(), active["id"]),
        )
        db.commit()
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Routes – Edit / Delete time entries
# ---------------------------------------------------------------------------

@app.route("/entries/<int:entry_id>/edit", methods=["GET", "POST"])
def edit_entry(entry_id: int):
    db = get_db()
    entry = db.execute("SELECT * FROM time_entries WHERE id = ?", (entry_id,)).fetchone()
    if entry is None:
        flash("Time entry not found.", "error")
        return redirect(url_for("index"))

    duties = db.execute("SELECT * FROM duties ORDER BY name").fetchall()

    if request.method == "POST":
        duty_id = request.form.get("duty_id")
        started_at = request.form.get("started_at", "").strip()
        ended_at = request.form.get("ended_at", "").strip() or None
        notes = request.form.get("notes", "").strip() or None

        # Basic validation
        if not duty_id or not started_at:
            flash("Duty and start time are required.", "error")
            return render_template("edit_entry.html", entry=entry, duties=duties)

        try:
            parse_dt(started_at)
            if ended_at:
                parse_dt(ended_at)
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("edit_entry.html", entry=entry, duties=duties)

        db.execute(
            """
            UPDATE time_entries
            SET    duty_id    = ?,
                   started_at = ?,
                   ended_at   = ?,
                   notes      = ?
            WHERE  id = ?
            """,
            (duty_id, started_at, ended_at, notes, entry_id),
        )
        db.commit()
        flash("Time entry updated.", "success")
        return redirect(url_for("report"))

    return render_template("edit_entry.html", entry=entry, duties=duties)


@app.route("/entries/<int:entry_id>/delete", methods=["POST"])
def delete_entry(entry_id: int):
    db = get_db()
    db.execute("DELETE FROM time_entries WHERE id = ?", (entry_id,))
    db.commit()
    flash("Time entry deleted.", "success")
    return redirect(url_for("report"))


# ---------------------------------------------------------------------------
# Routes – Reports
# ---------------------------------------------------------------------------

@app.route("/report")
def report():
    db = get_db()

    today_entries = get_today_entries(db)

    # Weekly entries (Mon → today)
    week_start = week_start_str()
    weekly_entries = db.execute(
        """
        SELECT te.*, d.name AS duty_name
        FROM   time_entries te
        JOIN   duties d ON d.id = te.duty_id
        WHERE  date(te.started_at) >= ?
        ORDER  BY te.started_at DESC
        """,
        (week_start,),
    ).fetchall()

    weekly_totals = build_duty_totals(weekly_entries)
    weekly_total_seconds = sum(t["total_seconds"] for t in weekly_totals)

    return render_template(
        "report.html",
        today_entries=today_entries,
        weekly_totals=weekly_totals,
        weekly_total_duration=format_duration(weekly_total_seconds),
        format_duration=format_duration,
        entry_duration_seconds=entry_duration_seconds,
        week_start=week_start,
    )


@app.route("/export/csv")
def export_csv():
    """Download all time entries as a CSV file."""
    db = get_db()
    entries = db.execute(
        """
        SELECT te.id,
               d.name  AS duty,
               te.started_at,
               te.ended_at,
               te.notes
        FROM   time_entries te
        JOIN   duties d ON d.id = te.duty_id
        ORDER  BY te.started_at DESC
        """
    ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "duty", "started_at", "ended_at", "duration", "notes"])

    for e in entries:
        if e["ended_at"]:
            duration = format_duration(
                (parse_dt(e["ended_at"]) - parse_dt(e["started_at"])).total_seconds()
            )
        else:
            duration = "ongoing"
        writer.writerow(
            [e["id"], e["duty"], e["started_at"], e["ended_at"] or "", duration, e["notes"] or ""]
        )

    csv_bytes = output.getvalue().encode("utf-8")
    filename = f"time_entries_{today_str()}.csv"
    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Ensure DB is set up before the first request
    with app.app_context():
        init_db()
    # Enable debug mode only when explicitly requested (e.g. FLASK_DEBUG=1)
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, host="0.0.0.0", port=5000)
