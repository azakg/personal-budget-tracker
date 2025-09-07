import os
import io
import csv
import sqlite3
from datetime import date, datetime
from pathlib import Path
from calendar import monthrange

from flask import Flask, render_template, request, redirect, url_for, flash, Response
from flask_login import (
    LoginManager, UserMixin, login_user, login_required,
    logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from openpyxl import Workbook

APP_NAME = "Personal Budget Tracker"
DB_NAME = "budget.db"

app = Flask(__name__, instance_relative_config=True)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-key-change-me")

# Ensure instance folder exists and DB path set
Path(app.instance_path).mkdir(parents=True, exist_ok=True)
DB_PATH = os.path.join(app.instance_path, DB_NAME)

# ---------- DB helpers ----------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_db()
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tx_date TEXT NOT NULL,           -- ISO YYYY-MM-DD
            kind TEXT CHECK(kind IN ('income','expense')) NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount >= 0),
            note TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS budgets (
            user_id INTEGER NOT NULL,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            amount REAL NOT NULL CHECK(amount >= 0),
            PRIMARY KEY (user_id, year, month),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )
    conn.commit()
    conn.close()

def month_bounds(year: int, month: int):
    last = monthrange(year, month)[1]
    return date(year, month, 1).isoformat(), date(year, month, last).isoformat()

# ---------- Auth ----------
login_manager = LoginManager(app)
login_manager.login_view = "login"

class User(UserMixin):
    def __init__(self, row: sqlite3.Row):
        self.id = row["id"]
        self.email = row["email"]

def get_user_by_id(uid: int):
    conn = get_db()
    row = conn.execute("SELECT id, email FROM users WHERE id = ?", (uid,)).fetchone()
    conn.close()
    return User(row) if row else None

@login_manager.user_loader
def load_user(user_id: str):
    try:
        return get_user_by_id(int(user_id))
    except Exception:
        return None

# ---------- Auth routes ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        if not email or not password:
            flash("Email and password are required.", "danger")
            return redirect(url_for("register"))

        conn = get_db()
        exists = conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
        if exists:
            conn.close()
            flash("A user with this email already exists.", "warning")
            return redirect(url_for("register"))

        conn.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (email, generate_password_hash(password), datetime.utcnow().isoformat()),
        )
        conn.commit()
        row = conn.execute("SELECT id, email FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        login_user(User(row))
        flash("Registered and logged in!", "success")
        return redirect(url_for("index"))

    return render_template("register.html", app_name=APP_NAME)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        conn = get_db()
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if not row or not check_password_hash(row["password_hash"], password):
            flash("Invalid email or password.", "danger")
            return redirect(url_for("login"))

        login_user(User(row))
        flash("Logged in.", "success")
        return redirect(url_for("index"))

    return render_template("login.html", app_name=APP_NAME)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("login"))

# ---------- Helpers for filters ----------
def parse_filters(default_year: int, default_month: int):
    """Returns (date_from, date_to, category) derived from query args.
       If no custom range given, falls back to month bounds."""
    cat = (request.args.get("category") or "").strip()
    df = (request.args.get("date_from") or "").strip()
    dt = (request.args.get("date_to") or "").strip()
    # If not provided, use current month
    if not df or not dt:
        df, dt = month_bounds(default_year, default_month)
    return df, dt, cat

def add_filters_to_query(base_sql: str, have_where: bool = True):
    """Append SQL snippets for optional category filter."""
    sql = base_sql
    if request.args.get("category"):
        sql += " AND category = ?"
    return sql

def filter_params(user_id, date_from, date_to):
    params = [user_id, date_from, date_to]
    if request.args.get("category"):
        params.append(request.args.get("category"))
    return tuple(params)

# ---------- App routes ----------
@app.route("/")
@login_required
def index():
    # Month nav (still works even if custom range used)
    try:
        y = int(request.args.get("year", date.today().year))
        m = int(request.args.get("month", date.today().month))
    except ValueError:
        y, m = date.today().year, date.today().month

    date_from, date_to, category = parse_filters(y, m)

    conn = get_db()

    # category list for dropdown (from user's data in the selected range)
    cats = conn.execute(
        """
        SELECT DISTINCT category
        FROM transactions
        WHERE user_id = ? AND tx_date BETWEEN ? AND ?
        ORDER BY category COLLATE NOCASE
        """,
        (current_user.id, date_from, date_to),
    ).fetchall()
    categories = [r["category"] for r in cats]

    # sums
    sums_sql = """
        SELECT
          COALESCE(SUM(CASE WHEN kind='income'  THEN amount END), 0) AS income,
          COALESCE(SUM(CASE WHEN kind='expense' THEN amount END), 0) AS expense
        FROM transactions
        WHERE user_id = ? AND tx_date BETWEEN ? AND ?
    """
    sums_sql = add_filters_to_query(sums_sql)
    sums = conn.execute(sums_sql, filter_params(current_user.id, date_from, date_to)).fetchone()
    income = float(sums["income"])
    expense = float(sums["expense"])
    balance = income - expense

    # transactions
    tx_sql = """
        SELECT id, tx_date, kind, category, amount, note
        FROM transactions
        WHERE user_id = ? AND tx_date BETWEEN ? AND ?
    """
    tx_sql = add_filters_to_query(tx_sql) + " ORDER BY tx_date DESC, id DESC"
    txs = conn.execute(tx_sql, filter_params(current_user.id, date_from, date_to)).fetchall()

    # budget (by month y/m only)
    b = conn.execute(
        "SELECT amount FROM budgets WHERE user_id = ? AND year = ? AND month = ?",
        (current_user.id, y, m),
    ).fetchone()
    budget = float(b["amount"]) if b else 0.0
    remaining = budget - expense if budget > 0 else None
    progress_pct = int(min(100, (expense / budget) * 100)) if budget > 0 else None

    # category totals (expenses)
    cat_sql = """
        SELECT category, COALESCE(SUM(CASE WHEN kind='expense' THEN amount END), 0) AS total
        FROM transactions
        WHERE user_id = ? AND tx_date BETWEEN ? AND ?
    """
    cat_sql = add_filters_to_query(cat_sql) + " GROUP BY category HAVING total > 0 ORDER BY total DESC"
    cat_rows = conn.execute(cat_sql, filter_params(current_user.id, date_from, date_to)).fetchall()
    cat_labels = [r["category"] for r in cat_rows]
    cat_values = [float(r["total"]) for r in cat_rows]
    cat_pairs = list(zip(cat_labels, cat_values))

    conn.close()

    # prev/next month (for month navigation controls)
    def prev_month(y, m): return (y - 1, 12) if m == 1 else (y, m - 1)
    def next_month(y, m): return (y + 1, 1) if m == 12 else (y, m + 1)
    py, pm = prev_month(y, m)
    ny, nm = next_month(y, m)

    return render_template(
        "index.html",
        app_name=APP_NAME,
        year=y, month=m,
        prev_year=py, prev_month=pm,
        next_year=ny, next_month=nm,
        income=income, expense=expense, balance=balance,
        budget=budget, remaining=remaining, progress_pct=progress_pct,
        txs=txs, cat_pairs=cat_pairs,
        categories=categories, selected_category=category or "",
        date_from=date_from, date_to=date_to,
        today=date.today().isoformat(),
    )

@app.route("/add", methods=["POST"])
@login_required
def add():
    tx_date = request.form.get("tx_date") or date.today().isoformat()
    kind = request.form.get("kind")
    category = (request.form.get("category") or "").strip() or "General"
    amount_raw = request.form.get("amount")
    note = (request.form.get("note") or "").strip()

    try:
        amount = round(float(amount_raw), 2)
        if amount < 0:
            raise ValueError
    except (TypeError, ValueError):
        flash("Amount must be a non-negative number.", "danger")
        return redirect(url_for("index"))

    if kind not in ("income", "expense"):
        flash("Invalid type selected.", "danger")
        return redirect(url_for("index"))

    conn = get_db()
    conn.execute(
        """
        INSERT INTO transactions (user_id, tx_date, kind, category, amount, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (current_user.id, tx_date, kind, category, amount, note, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()

    flash("Transaction added!", "success")
    return redirect(url_for("index", year=tx_date[:4], month=int(tx_date[5:7])))

@app.route("/edit/<int:tx_id>", methods=["GET", "POST"])
@login_required
def edit(tx_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM transactions WHERE id = ? AND user_id = ?",
        (tx_id, current_user.id),
    ).fetchone()

    if not row:
        conn.close()
        flash("Not found.", "warning")
        return redirect(url_for("index"))

    if request.method == "POST":
        tx_date = request.form.get("tx_date") or row["tx_date"]
        kind = request.form.get("kind") or row["kind"]
        category = (request.form.get("category") or row["category"]).strip() or "General"
        amount_raw = request.form.get("amount") or str(row["amount"])
        note = (request.form.get("note") or row["note"] or "").strip()

        try:
            amount = round(float(amount_raw), 2)
            if amount < 0:
                raise ValueError
        except (TypeError, ValueError):
            flash("Amount must be a non-negative number.", "danger")
            return redirect(url_for("edit", tx_id=tx_id))

        if kind not in ("income", "expense"):
            flash("Invalid type selected.", "danger")
            return redirect(url_for("edit", tx_id=tx_id))

        conn.execute(
            """
            UPDATE transactions
            SET tx_date = ?, kind = ?, category = ?, amount = ?, note = ?
            WHERE id = ? AND user_id = ?
            """,
            (tx_date, kind, category, amount, note, tx_id, current_user.id),
        )
        conn.commit()
        conn.close()

        flash("Transaction updated.", "success")
        return redirect(url_for("index", year=tx_date[:4], month=int(tx_date[5:7])))

    conn.close()
    return render_template("edit.html", app_name=APP_NAME, tx=row)

@app.route("/delete/<int:tx_id>", methods=["POST"])
@login_required
def delete(tx_id):
    conn = get_db()
    row = conn.execute(
        "SELECT user_id, tx_date FROM transactions WHERE id = ?",
        (tx_id,),
    ).fetchone()
    if not row or row["user_id"] != current_user.id:
        conn.close()
        flash("Not found.", "warning")
        return redirect(url_for("index"))
    conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    conn.commit()
    tx_date = row["tx_date"]
    conn.close()

    flash("Transaction removed.", "info")
    return redirect(url_for("index", year=tx_date[:4], month=int(tx_date[5:7])))

@app.route("/set-budget", methods=["POST"])
@login_required
def set_budget():
    try:
        y = int(request.form.get("year", date.today().year))
        m = int(request.form.get("month", date.today().month))
        amount = round(float(request.form.get("budget_amount", "0") or 0), 2)
        if amount < 0:
            raise ValueError
    except ValueError:
        flash("Budget must be a non-negative number.", "danger")
        return redirect(url_for("index"))

    conn = get_db()
    conn.execute(
        """
        INSERT INTO budgets (user_id, year, month, amount)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, year, month) DO UPDATE SET amount = excluded.amount
        """,
        (current_user.id, y, m, amount),
    )
    conn.commit()
    conn.close()

    flash("Budget saved.", "success")
    return redirect(url_for("index", year=y, month=m))

def current_filters_or_month(y, m):
    """Helper for export: reuse current filters if present; else month bounds."""
    df = (request.args.get("date_from") or "").strip()
    dt = (request.args.get("date_to") or "").strip()
    if not df or not dt:
        df, dt = month_bounds(y, m)
    return df, dt

@app.route("/export.csv")
@login_required
def export_csv():
    try:
        y = int(request.args.get("year", date.today().year))
        m = int(request.args.get("month", date.today().month))
    except ValueError:
        y, m = date.today().year, date.today().month

    date_from, date_to = current_filters_or_month(y, m)
    category = (request.args.get("category") or "").strip()

    conn = get_db()
    sql = """
        SELECT tx_date, kind, category, amount, note
        FROM transactions
        WHERE user_id = ? AND tx_date BETWEEN ? AND ?
    """
    params = [current_user.id, date_from, date_to]
    if category:
        sql += " AND category = ?"
        params.append(category)
    sql += " ORDER BY tx_date ASC, id ASC"
    rows = conn.execute(sql, tuple(params)).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["tx_date", "kind", "category", "amount", "note"])
    for r in rows:
        writer.writerow([r["tx_date"], r["kind"], r["category"], f"{float(r['amount']):.2f}", r["note"] or ""])

    csv_bytes = output.getvalue().encode("utf-8")
    filename = f"transactions_{y}-{m:02d}.csv"
    return Response(csv_bytes, mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})

@app.route("/export.xlsx")
@login_required
def export_xlsx():
    try:
        y = int(request.args.get("year", date.today().year))
        m = int(request.args.get("month", date.today().month))
    except ValueError:
        y, m = date.today().year, date.today().month

    date_from, date_to = current_filters_or_month(y, m)
    category = (request.args.get("category") or "").strip()

    conn = get_db()
    sql = """
        SELECT tx_date, kind, category, amount, note
        FROM transactions
        WHERE user_id = ? AND tx_date BETWEEN ? AND ?
    """
    params = [current_user.id, date_from, date_to]
    if category:
        sql += " AND category = ?"
        params.append(category)
    sql += " ORDER BY tx_date ASC, id ASC"
    rows = conn.execute(sql, tuple(params)).fetchall()
    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = f"{y}-{m:02d}"
    ws.append(["tx_date", "kind", "category", "amount", "note"])
    for r in rows:
        ws.append([r["tx_date"], r["kind"], r["category"], float(r["amount"]), r["note"] or ""])

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    filename = f"transactions_{y}-{m:02d}.xlsx"
    return Response(stream.read(),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})

if __name__ == "__main__":
    init_db()
    port = int(os.getenv("PORT", "5000"))
    app.run(debug=True, port=port)
