"""Main application routes."""
import io
import csv
from datetime import date, datetime
from flask import (
    render_template, request, redirect, url_for, flash,
    Response, current_app
)
from flask_login import login_required, current_user
from openpyxl import Workbook

from app.main import bp
from app.database import get_db, get_db_connection
from app.utils.helpers import month_bounds, prev_month, next_month


def parse_filters(default_year: int, default_month: int):
    """Parse filter parameters from request.

    Args:
        default_year: Default year if not provided
        default_month: Default month if not provided

    Returns:
        Tuple of (date_from, date_to, category)
    """
    cat = (request.args.get("category") or "").strip()
    df = (request.args.get("date_from") or "").strip()
    dt = (request.args.get("date_to") or "").strip()

    if not df or not dt:
        df, dt = month_bounds(default_year, default_month)

    return df, dt, cat


def add_filters_to_query(base_sql: str):
    """Add category filter to SQL query if present.

    Args:
        base_sql: Base SQL query

    Returns:
        SQL query with optional category filter
    """
    sql = base_sql
    if request.args.get("category"):
        sql += " AND category = ?"
    return sql


def filter_params(user_id, date_from, date_to):
    """Build parameter tuple for filtered queries.

    Args:
        user_id: User ID
        date_from: Start date
        date_to: End date

    Returns:
        Tuple of query parameters
    """
    params = [user_id, date_from, date_to]
    if request.args.get("category"):
        params.append(request.args.get("category"))
    return tuple(params)


def get_transactions_for_export(user_id, date_from, date_to, category=None):
    """Get transactions for export.

    Args:
        user_id: User ID
        date_from: Start date
        date_to: End date
        category: Optional category filter

    Returns:
        List of transaction rows
    """
    conn = get_db()
    sql = """
        SELECT tx_date, kind, category, amount, note
        FROM transactions
        WHERE user_id = ? AND tx_date BETWEEN ? AND ?
    """
    params = [user_id, date_from, date_to]
    if category:
        sql += " AND category = ?"
        params.append(category)
    sql += " ORDER BY tx_date ASC, id ASC"

    rows = conn.execute(sql, tuple(params)).fetchall()
    return rows


@bp.route("/")
@login_required
def index():
    """Main dashboard page."""
    # Get month navigation parameters
    try:
        y = int(request.args.get("year", date.today().year))
        m = int(request.args.get("month", date.today().month))
    except ValueError:
        y, m = date.today().year, date.today().month

    date_from, date_to, category = parse_filters(y, m)

    conn = get_db()

    # Get categories for dropdown
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

    # Get income/expense sums
    sums_sql = """
        SELECT
          COALESCE(SUM(CASE WHEN kind='income'  THEN amount END), 0) AS income,
          COALESCE(SUM(CASE WHEN kind='expense' THEN amount END), 0) AS expense
        FROM transactions
        WHERE user_id = ? AND tx_date BETWEEN ? AND ?
    """
    sums_sql = add_filters_to_query(sums_sql)
    sums = conn.execute(
        sums_sql,
        filter_params(current_user.id, date_from, date_to)
    ).fetchone()

    income = float(sums["income"])
    expense = float(sums["expense"])
    balance = income - expense

    # Get transactions
    tx_sql = """
        SELECT id, tx_date, kind, category, amount, note
        FROM transactions
        WHERE user_id = ? AND tx_date BETWEEN ? AND ?
    """
    tx_sql = add_filters_to_query(tx_sql) + " ORDER BY tx_date DESC, id DESC"
    txs = conn.execute(
        tx_sql,
        filter_params(current_user.id, date_from, date_to)
    ).fetchall()

    # Get budget
    b = conn.execute(
        "SELECT amount FROM budgets WHERE user_id = ? AND year = ? AND month = ?",
        (current_user.id, y, m),
    ).fetchone()
    budget = float(b["amount"]) if b else 0.0
    remaining = budget - expense if budget > 0 else None
    progress_pct = int(min(100, (expense / budget) * 100)) if budget > 0 else None

    # Get category totals for expenses
    cat_sql = """
        SELECT category, COALESCE(SUM(CASE WHEN kind='expense' THEN amount END), 0) AS total
        FROM transactions
        WHERE user_id = ? AND tx_date BETWEEN ? AND ?
    """
    cat_sql = add_filters_to_query(cat_sql) + \
        " GROUP BY category HAVING total > 0 ORDER BY total DESC"
    cat_rows = conn.execute(
        cat_sql,
        filter_params(current_user.id, date_from, date_to)
    ).fetchall()

    cat_labels = [r["category"] for r in cat_rows]
    cat_values = [float(r["total"]) for r in cat_rows]
    cat_pairs = list(zip(cat_labels, cat_values))

    # Calculate prev/next month
    py, pm = prev_month(y, m)
    ny, nm = next_month(y, m)

    return render_template(
        "index.html",
        app_name=current_app.config['APP_NAME'],
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


@bp.route("/add", methods=["POST"])
@login_required
def add():
    """Add a new transaction."""
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
        return redirect(url_for("main.index"))

    if kind not in ("income", "expense"):
        flash("Invalid type selected.", "danger")
        return redirect(url_for("main.index"))

    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO transactions (user_id, tx_date, kind, category, amount, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (current_user.id, tx_date, kind, category, amount, note,
             datetime.utcnow().isoformat()),
        )

    flash("Transaction added!", "success")
    return redirect(url_for("main.index", year=tx_date[:4], month=int(tx_date[5:7])))


@bp.route("/edit/<int:tx_id>", methods=["GET", "POST"])
@login_required
def edit(tx_id):
    """Edit an existing transaction."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM transactions WHERE id = ? AND user_id = ?",
        (tx_id, current_user.id),
    ).fetchone()

    if not row:
        flash("Transaction not found.", "warning")
        return redirect(url_for("main.index"))

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
            return redirect(url_for("main.edit", tx_id=tx_id))

        if kind not in ("income", "expense"):
            flash("Invalid type selected.", "danger")
            return redirect(url_for("main.edit", tx_id=tx_id))

        with get_db_connection() as conn:
            conn.execute(
                """
                UPDATE transactions
                SET tx_date = ?, kind = ?, category = ?, amount = ?, note = ?
                WHERE id = ? AND user_id = ?
                """,
                (tx_date, kind, category, amount, note, tx_id, current_user.id),
            )

        flash("Transaction updated.", "success")
        return redirect(url_for("main.index", year=tx_date[:4], month=int(tx_date[5:7])))

    return render_template(
        "edit.html",
        app_name=current_app.config['APP_NAME'],
        tx=row
    )


@bp.route("/delete/<int:tx_id>", methods=["POST"])
@login_required
def delete(tx_id):
    """Delete a transaction."""
    conn = get_db()
    row = conn.execute(
        "SELECT user_id, tx_date FROM transactions WHERE id = ?",
        (tx_id,),
    ).fetchone()

    if not row or row["user_id"] != current_user.id:
        flash("Transaction not found.", "warning")
        return redirect(url_for("main.index"))

    tx_date = row["tx_date"]

    with get_db_connection() as conn:
        conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))

    flash("Transaction removed.", "info")
    return redirect(url_for("main.index", year=tx_date[:4], month=int(tx_date[5:7])))


@bp.route("/set-budget", methods=["POST"])
@login_required
def set_budget():
    """Set monthly budget."""
    try:
        y = int(request.form.get("year", date.today().year))
        m = int(request.form.get("month", date.today().month))
        amount = round(float(request.form.get("budget_amount", "0") or 0), 2)
        if amount < 0:
            raise ValueError
    except ValueError:
        flash("Budget must be a non-negative number.", "danger")
        return redirect(url_for("main.index"))

    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO budgets (user_id, year, month, amount)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, year, month) DO UPDATE SET amount = excluded.amount
            """,
            (current_user.id, y, m, amount),
        )

    flash("Budget saved.", "success")
    return redirect(url_for("main.index", year=y, month=m))


@bp.route("/export.csv")
@login_required
def export_csv():
    """Export transactions to CSV."""
    try:
        y = int(request.args.get("year", date.today().year))
        m = int(request.args.get("month", date.today().month))
    except ValueError:
        y, m = date.today().year, date.today().month

    df = (request.args.get("date_from") or "").strip()
    dt = (request.args.get("date_to") or "").strip()
    if not df or not dt:
        df, dt = month_bounds(y, m)

    category = (request.args.get("category") or "").strip()
    rows = get_transactions_for_export(current_user.id, df, dt, category or None)

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

    csv_bytes = output.getvalue().encode("utf-8")
    filename = f"transactions_{y}-{m:02d}.csv"

    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@bp.route("/export.xlsx")
@login_required
def export_xlsx():
    """Export transactions to Excel."""
    try:
        y = int(request.args.get("year", date.today().year))
        m = int(request.args.get("month", date.today().month))
    except ValueError:
        y, m = date.today().year, date.today().month

    df = (request.args.get("date_from") or "").strip()
    dt = (request.args.get("date_to") or "").strip()
    if not df or not dt:
        df, dt = month_bounds(y, m)

    category = (request.args.get("category") or "").strip()
    rows = get_transactions_for_export(current_user.id, df, dt, category or None)

    wb = Workbook()
    ws = wb.active
    ws.title = f"{y}-{m:02d}"
    ws.append(["tx_date", "kind", "category", "amount", "note"])
    for r in rows:
        ws.append([
            r["tx_date"],
            r["kind"],
            r["category"],
            float(r["amount"]),
            r["note"] or ""
        ])

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    filename = f"transactions_{y}-{m:02d}.xlsx"

    return Response(
        stream.read(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
