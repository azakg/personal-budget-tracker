import os
import sqlite3
from datetime import date, datetime
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash

APP_NAME = "Budget Tracker"
DB_NAME = "budget.db"

app = Flask(__name__, instance_relative_config=True)
app.config['SECRET_KEY'] = 'dev-key-change-me'

Path(app.instance_path).mkdir(parents=True, exist_ok=True)
DB_PATH = os.path.join(app.instance_path, DB_NAME)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_date TEXT NOT NULL,
            kind TEXT CHECK(kind IN ('income','expense')) NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount >= 0),
            note TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()

#@app.before_first_request
def startup():
    init_db()

def month_bounds(year: int, month: int):
    from calendar import monthrange
    last_day = monthrange(year, month)[1]
    first = date(year, month, 1).isoformat()
    last = date(year, month, last_day).isoformat()
    return first, last

@app.route('/')
def index():
    try:
        y = int(request.args.get('year', date.today().year))
        m = int(request.args.get('month', date.today().month))
    except ValueError:
        y, m = date.today().year, date.today().month

    first, last = month_bounds(y, m)

    conn = get_db()
    sums = conn.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN kind='income'  THEN amount END), 0) AS income,
            COALESCE(SUM(CASE WHEN kind='expense' THEN amount END), 0) AS expense
        FROM transactions
        WHERE tx_date BETWEEN ? AND ?
        """,
        (first, last)
    ).fetchone()

    balance = float(sums['income']) - float(sums['expense'])

    txs = conn.execute(
        """
        SELECT id, tx_date, kind, category, amount, note
        FROM transactions
        WHERE tx_date BETWEEN ? AND ?
        ORDER BY tx_date DESC, id DESC
        """,
        (first, last)
    ).fetchall()
    conn.close()

    def prev_month(y, m):
        if m == 1:
            return y - 1, 12
        return y, m - 1

    def next_month(y, m):
        if m == 12:
            return y + 1, 1
        return y, m + 1

    py, pm = prev_month(y, m)
    ny, nm = next_month(y, m)

    return render_template(
        'index.html',
        app_name=APP_NAME,
        year=y, month=m,
        prev_year=py, prev_month=pm,
        next_year=ny, next_month=nm,
        income=sums['income'], expense=sums['expense'], balance=balance,
        txs=txs,
        today=date.today().isoformat()
    )

@app.route('/add', methods=['POST'])
def add():
    tx_date = request.form.get('tx_date') or date.today().isoformat()
    kind = request.form.get('kind')
    category = (request.form.get('category') or '').strip() or 'General'
    amount_raw = request.form.get('amount')
    note = (request.form.get('note') or '').strip()

    try:
        amount = round(float(amount_raw), 2)
    except (TypeError, ValueError):
        flash('Amount must be a number.', 'danger')
        return redirect(url_for('index'))

    if kind not in ('income', 'expense'):
        flash('Invalid type selected.', 'danger')
        return redirect(url_for('index'))

    if amount < 0:
        flash('Amount cannot be negative.', 'danger')
        return redirect(url_for('index'))

    conn = get_db()
    conn.execute(
        """
        INSERT INTO transactions (tx_date, kind, category, amount, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (tx_date, kind, category, amount, note, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

    flash('Transaction added!', 'success')
    return redirect(url_for('index', year=tx_date[:4], month=int(tx_date[5:7])))

@app.route('/delete/<int:tx_id>', methods=['POST'])
def delete(tx_id):
    conn = get_db()
    conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    conn.commit()
    conn.close()
    flash('Transaction removed.', 'warning')
    return redirect(url_for('index'))

if __name__ == '__main__':
    startup()
    app.run(debug=True)
