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
NAME_OF_DB = "budget.db"

app = Flask(__name__, instance_relative_config=True)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-key-change-me")

# instance folder и база
Path(app.instance_path).mkdir(parents=True, exist_ok=True)
DB_PATH = os.path.join(app.instance_path, NAME_OF_DB)


# получение соединения с БД
def get_db():
    # каждый раз открываем соединение
    conn_db = sqlite3.connect(DB_PATH)
    conn_db.row_factory = sqlite3.Row
    conn_db.execute("PRAGMA foreign_keys = ON;")
    return conn_db


def init_db():
    conn_init = get_db()
    conn_init.executescript("""
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
            tx_date TEXT NOT NULL,
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
    """)
    conn_init.commit()
    conn_init.close()


def month_bounds(y, m):
    last = monthrange(y, m)[1]
    return date(y, m, 1).isoformat(), date(y, m, last).isoformat()


# Это для логинна----
login_manager = LoginManager(app)
login_manager.login_view = "login"


class User(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.email = row["email"]


def get_user_by_id(uid):
    conn = get_db()
    row = conn.execute("SELECT id, email FROM users WHERE id = ?", (uid,)).fetchone()
    conn.close()
    if row:
        return User(row)
    return None


@login_manager.user_loader
def load_user(user_id):
    try:
        return get_user_by_id(int(user_id))
    except Exception:
        return None


#
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if email == "" or password == "":
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

        if (not row) or (not check_password_hash(row["password_hash"], password)):
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


# --фльтры
def parse_filters(default_year, default_month):
    category = (request.args.get("category") or "").strip()
    date_from = (request.args.get("date_from") or "").strip()
    date_to = (request.args.get("date_to") or "").strip()


    if date_from == "" or date_to == "":
        date_from, date_to = month_bounds(default_year, default_month)

    return date_from, date_to, category


def current_filters_or_month(y, m):
    df = (request.args.get("date_from") or "").strip()
    dt = (request.args.get("date_to") or "").strip()
    if df == "" or dt == "":
        df, dt = month_bounds(y, m)
    return df, dt


# ---------- Main page ----------
@app.route("/")
@login_required
def index():
    # берем год/месяц для навигации
    try:
        y = int(request.args.get("year", date.today().year))
        m = int(request.args.get("month", date.today().month))
    except ValueError:
        y = date.today().year
        m = date.today().month

    date_from, date_to, selected_category = parse_filters(y, m)

    conn = get_db()

    # список категорий для dropdown
    cats = conn.execute("""
        SELECT DISTINCT category
        FROM transactions
        WHERE user_id = ? AND tx_date BETWEEN ? AND ?
        ORDER BY category COLLATE NOCASE
    """, (current_user.id, date_from, date_to)).fetchall()
    categories = [r["category"] for r in cats]

    # суммы
    if selected_category:
        sums = conn.execute("""
            SELECT
              COALESCE(SUM(CASE WHEN kind='income'  THEN amount END), 0) AS income,
              COALESCE(SUM(CASE WHEN kind='expense' THEN amount END), 0) AS expense
            FROM transactions
            WHERE user_id = ? AND tx_date BETWEEN ? AND ? AND category = ?
        """, (current_user.id, date_from, date_to, selected_category)).fetchone()
    else:
        sums = conn.execute("""
            SELECT
              COALESCE(SUM(CASE WHEN kind='income'  THEN amount END), 0) AS income,
              COALESCE(SUM(CASE WHEN kind='expense' THEN amount END), 0) AS expense
            FROM transactions
            WHERE user_id = ? AND tx_date BETWEEN ? AND ?
        """, (current_user.id, date_from, date_to)).fetchone()

    income = float(sums["income"])
    expense = float(sums["expense"])
    balance = income - expense

    # транзакции
    if selected_category:
        txs = conn.execute("""
            SELECT id, tx_date, kind, category, amount, note
            FROM transactions
            WHERE user_id = ? AND tx_date BETWEEN ? AND ? AND category = ?
            ORDER BY tx_date DESC, id DESC
        """, (current_user.id, date_from, date_to, selected_category)).fetchall()
    else:
        txs = conn.execute("""
            SELECT id, tx_date, kind, category, amount, note
            FROM transactions
            WHERE user_id = ? AND tx_date BETWEEN ? AND ?
            ORDER BY tx_date DESC, id DESC
        """, (current_user.id, date_from, date_to)).fetchall()

    # бюджет только по месяцу y/m
    b = conn.execute(
        "SELECT amount FROM budgets WHERE user_id = ? AND year = ? AND month = ?",
        (current_user.id, y, m),
    ).fetchone()
    budget = float(b["amount"]) if b else 0.0

    remaining = None
    progress_pct = None
    if budget > 0:
        remaining = budget - expense
        try:
            progress_pct = int(min(100, (expense / budget) * 100))
        except Exception:
            progress_pct = 0

    # категории по расходам (для графика/таблички)
    if selected_category:
        cat_rows = conn.execute("""
            SELECT category, COALESCE(SUM(CASE WHEN kind='expense' THEN amount END), 0) AS total
            FROM transactions
            WHERE user_id = ? AND tx_date BETWEEN ? AND ? AND category = ?
            GROUP BY category
            HAVING total > 0
            ORDER BY total DESC
        """, (current_user.id, date_from, date_to, selected_category)).fetchall()
    else:
        cat_rows = conn.execute("""
            SELECT category, COALESCE(SUM(CASE WHEN kind='expense' THEN amount END), 0) AS total
            FROM transactions
            WHERE user_id = ? AND tx_date BETWEEN ? AND ?
            GROUP BY category
            HAVING total > 0
            ORDER BY total DESC
        """, (current_user.id, date_from, date_to)).fetchall()

    cat_pairs = [(r["category"], float(r["total"])) for r in cat_rows]

    conn.close()

    # prev/next month (простая навигация)
    if m == 1:
        prev_year, prev_month = y - 1, 12
    else:
        prev_year, prev_month = y, m - 1

    if m == 12:
        next_year, next_month = y + 1, 1
    else:
        next_year, next_month = y, m + 1

    return render_template(
        "index.html",
        app_name=APP_NAME,
        year=y, month=m,
        prev_year=prev_year, prev_month=prev_month,
        next_year=next_year, next_month=next_month,
        income=income, expense=expense, balance=balance,
        budget=budget, remaining=remaining, progress_pct=progress_pct,
        txs=txs,
        cat_pairs=cat_pairs,
        categories=categories,
        selected_category=selected_category,
        date_from=date_from, date_to=date_to,
        today=date.today().isoformat(),
    )


@app.route("/add", methods=["POST"])
@login_required
def add():
    tx_date = request.form.get("tx_date") or date.today().isoformat()
    kind = request.form.get("kind") or ""
    category = (request.form.get("category") or "").strip()
    amount_raw = request.form.get("amount")
    note = (request.form.get("note") or "").strip()

    if category == "":
        category = "General"

    # простая валидация
    try:
        amount = round(float(amount_raw), 2)
        if amount < 0:
            raise ValueError("negative")
    except Exception:
        flash("Amount must be a non-negative number.", "danger")
        return redirect(url_for("index"))

    if kind not in ("income", "expense"):
        flash("Invalid type selected.", "danger")
        return redirect(url_for("index"))

    conn = get_db()
    conn.execute("""
        INSERT INTO transactions (user_id, tx_date, kind, category, amount, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (current_user.id, tx_date, kind, category, amount, note, datetime.utcnow().isoformat()))
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
        category = (request.form.get("category") or row["category"]).strip()
        amount_raw = request.form.get("amount") or str(row["amount"])
        note = (request.form.get("note") or (row["note"] or "")).strip()

        if category == "":
            category = "General"

        try:
            amount = round(float(amount_raw), 2)
            if amount < 0:
                raise ValueError("negative")
        except Exception:
            flash("Amount must be a non-negative number.", "danger")
            return redirect(url_for("edit", tx_id=tx_id))

        if kind not in ("income", "expense"):
            flash("Invalid type selected.", "danger")
            return redirect(url_for("edit", tx_id=tx_id))

        conn.execute("""
            UPDATE transactions
            SET tx_date = ?, kind = ?, category = ?, amount = ?, note = ?
            WHERE id = ? AND user_id = ?
        """, (tx_date, kind, category, amount, note, tx_id, current_user.id))
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
            raise ValueError("negative")
    except Exception:
        flash("Budget must be a non-negative number.", "danger")
        return redirect(url_for("index"))

    conn = get_db()
    conn.execute("""
        INSERT INTO budgets (user_id, year, month, amount)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, year, month) DO UPDATE SET amount = excluded.amount
    """, (current_user.id, y, m, amount))
    conn.commit()
    conn.close()

    flash("Budget saved.", "success")
    return redirect(url_for("index", year=y, month=m))


# --- export CSV ---
@app.route("/export.csv")
@login_required
def export_csv():
    try:
        y = int(request.args.get("year", date.today().year))
        m = int(request.args.get("month", date.today().month))
    except Exception:
        y = date.today().year
        m = date.today().month

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
        writer.writerow([
            r["tx_date"],
            r["kind"],
            r["category"],
            f"{float(r['amount']):.2f}",
            r["note"] or ""
        ])

    filename = f"transactions_{y}-{m:02d}.csv"
    return Response(
        output.getvalue().encode("utf-8"),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# --- export XLSX ---
@app.route("/export.xlsx")
@login_required
def export_xlsx():
    try:
        y = int(request.args.get("year", date.today().year))
        m = int(request.args.get("month", date.today().month))
    except Exception:
        y = date.today().year
        m = date.today().month

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
    return Response(
        stream.read(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


if __name__ == "__main__":
    init_db()
    port = int(os.getenv("PORT", "5001"))
    app.run(debug=True, port=port)
