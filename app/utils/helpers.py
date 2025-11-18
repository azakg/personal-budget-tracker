"""Utility helper functions."""
import re
from datetime import date
from calendar import monthrange


def to_amount(val) -> float:
    """Convert various amount formats to float.

    Examples:
        '38.70' -> 38.70
        '$ 38.70' -> 38.70
        'USD 38,70' -> 38.70
    """
    s = str(val) if val is not None else ""
    s = s.replace(",", "")
    m = re.search(r'(\d+(?:\.\d{1,2})?)', s)
    return float(m.group(1)) if m else 0.0


def to_iso_date(val: str, fallback: str) -> str:
    """Convert various date formats to ISO format (YYYY-MM-DD).

    Accepts:
        - ISO format: '2025-10-12'
        - US format: '10/12/25' or '10/12/2025'

    Args:
        val: Date string to parse
        fallback: Fallback date if parsing fails

    Returns:
        ISO formatted date string (YYYY-MM-DD)
    """
    s = (val or "").strip()

    # Already in ISO format
    if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
        return s

    # MM/DD/YY or MM/DD/YYYY
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{2,4})$', s)
    if m:
        mm, dd, yy = m.groups()
        yy = int(yy)
        if yy < 100:
            yy += 2000
        return f"{yy:04d}-{int(mm):02d}-{int(dd):02d}"

    return fallback


def month_bounds(year: int, month: int) -> tuple[str, str]:
    """Get first and last day of month in ISO format.

    Args:
        year: Year
        month: Month (1-12)

    Returns:
        Tuple of (first_day, last_day) in ISO format
    """
    last_day = monthrange(year, month)[1]
    return (
        date(year, month, 1).isoformat(),
        date(year, month, last_day).isoformat()
    )


def prev_month(year: int, month: int) -> tuple[int, int]:
    """Get previous month's year and month.

    Args:
        year: Current year
        month: Current month (1-12)

    Returns:
        Tuple of (prev_year, prev_month)
    """
    return (year - 1, 12) if month == 1 else (year, month - 1)


def next_month(year: int, month: int) -> tuple[int, int]:
    """Get next month's year and month.

    Args:
        year: Current year
        month: Current month (1-12)

    Returns:
        Tuple of (next_year, next_month)
    """
    return (year + 1, 1) if month == 12 else (year, month + 1)


def allowed_file(filename: str, allowed_extensions: set) -> bool:
    """Check if filename has allowed extension.

    Args:
        filename: Filename to check
        allowed_extensions: Set of allowed extensions (without dots)

    Returns:
        True if file extension is allowed
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions
