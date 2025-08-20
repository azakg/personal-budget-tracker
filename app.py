import os
import io
import csv
import sqlite3
from datetime import date, datetime
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, Response

APP_NAME = "Budget Tracker"
DB_NAME = "budget.db"

app = Flask(__name__, instance_relative_config=True)
app.config['SECRET_KEY'] = 'dev-key-change-me'

# Ensure instance folder exists
Path(app.instance_path).mkdir(parents=True, exist_ok=True)
DB_PATH = os.path.join(app.instance_path, DB_NAME)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_date TEXT NOT NULL,           -- ISO YYYY-MM-DD
            kind TEXT CHECK(kind IN ('income','expense')) NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount >= 0),
            note TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS budgets (
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            amount REAL NOT NULL CHECK(amount >= 0),
            PRIMARY KEY (year, month)
        );
        """
    )
    conn.commit()
    conn.close()


def startup():
    init_db()


def month_bounds(year: int, month: int):
    from calendar import monthrange
    last_day = monthrange(year, month)[1]
    first = date(year, month, 1).isoformat()
    last = date(year, month, last_day).isoformat()
    return first, last


def get_budget(conn, y: int, m: int) -> float:
    row = conn.execute(
        "SELECT amount FROM budgets WHERE year = ? AND month = ?",
        (y, m)
    ).fetchone()
    return float(row['amount']) if row else 0.0


@app.route('/')
def index():
    # Parse optional ?year=YYYY&month=MM
    try:
        y = int(request.args.get('year', date.today().year))
        m = int(request.args.get('month', date.today().month))
    except ValueError:
        y, m = date.today().year, date.today().month

    first, last = month_bounds(y, m)

    conn = get_db()

    # Monthly summary (income / expense)
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

    income = float(sums['income'])
    expense = float(sums['expense'])
    balance = income - expense

    # Transactions list (this month)
    txs = conn.execute(
        """
        SELECT id, tx_date, kind, category, amount, note
        FROM transactions
        WHERE tx_date BETWEEN ? AND ?
        ORDER BY tx_date DESC, id DESC
        """,
        (first, last)
    ).fetchall()

    # Budget
    budget = get_budget(conn, y, m)
    remaining = budget - expense if budget > 0 else None
    progress_pct = int(min(100, (expense / budget) * 100)) if budget > 0 else None

    # Category report (expenses by category)
    cat_rows = conn.execute(
        """
        SELECT category, COALESCE(SUM(CASE WHEN kind='expense' THEN amount END), 0) AS total
        FROM transactions
        WHERE tx_date BETWEEN ? AND ?
        GROUP BY category
        HAVING total > 0
        ORDER BY total DESC
        """,
        (first, last)
    ).fetchall()

    cat_labels = [r['category'] for r in cat_rows]
    cat_values = [float(r['total']) for r in cat_rows]

    conn.close()

    # Prev/next month helpers
    def prev_month(y, m):
        return (y - 1, 12) if m == 1 else (y, m - 1)

    def next_month(y, m):
        return (y + 1, 1) if m == 12 else (y, m + 1)

    py, pm = prev_month(y, m)
    ny, nm = next_month(y, m)

    return render_template(
        'index.html',
        app_name=APP_NAME,
        year=y, month=m,
        prev_year=py, prev_month=pm,
        next_year=ny, next_month=nm,
        income=income, expense=expense, balance=balance,
        budget=budget, remaining=remaining, progress_pct=progress_pct,
        txs=txs,
        cat_labels=cat_labels, cat_values=cat_values,
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


@app.route('/set-budget', methods=['POST'])
def set_budget():
    try:
        y = int(request.form.get('year', date.today().year))
        m = int(request.form.get('month', date.today().month))
        amount = round(float(request.form.get('budget_amount', '0') or 0), 2)
        if amount < 0:
            raise ValueError
    except ValueError:
        flash('Budget must be a non-negative number.', 'danger')
        return redirect(url_for('index'))

    conn = get_db()
    conn.execute(
        """
        INSERT INTO budgets (year, month, amount)
        VALUES (?, ?, ?)
        ON CONFLICT(year, month) DO UPDATE SET amount = excluded.amount
        """,
        (y, m, amount)
    )
    conn.commit()
    conn.close()

    flash('Budget saved.', 'success')
    return redirect(url_for('index', year=y, month=m))


@app.route('/export.csv')
def export_csv():
    try:
        y = int(request.args.get('year', date.today().year))
        m = int(request.args.get('month', date.today().month))
    except ValueError:
        y, m = date.today().year, date.today().month

    first, last = month_bounds(y, m)

    conn = get_db()
    rows = conn.execute(
        """
        SELECT tx_date, kind, category, amount, note
        FROM transactions
        WHERE tx_date BETWEEN ? AND ?
        ORDER BY tx_date ASC, id ASC
        """,
        (first, last)
    ).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['tx_date', 'kind', 'category', 'amount', 'note'])
    for r in rows:
        writer.writerow([r['tx_date'], r['kind'], r['category'], f"{float(r['amount']):.2f}", r['note'] or ''])

    csv_bytes = output.getvalue().encode('utf-8')
    filename = f"transactions_{y}-{m:02d}.csv"
    return Response(csv_bytes, mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={filename}'})


if __name__ == '__main__':
    startup()
    app.run(debug=True)