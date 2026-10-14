"""Africa/Lagos reporting windows for Hospital Admin analytics.

OpenMRS stores datetimes in UTC. Odoo Date fields are calendar dates as stored.
Callers must not mix a UTC calendar day with a Lagos calendar day.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from server import ApiError

HOSPITAL_TZ = ZoneInfo("Africa/Lagos")
PERIODS = (
    "today",
    "yesterday",
    "this_week",
    "last_week",
    "this_month",
    "last_month",
    "custom",
)
MAX_CUSTOM_DAYS = 366
WEEKDAY_MONDAY = 0


def hospital_today(now: datetime | None = None) -> date:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(HOSPITAL_TZ).date()


def parse_iso_date(value: str, *, field: str) -> date:
    text = (value or "").strip()
    try:
        parsed = date.fromisoformat(text)
    except ValueError as error:
        raise ApiError(422, "invalid_period", f"Enter a valid {field} date.") from error
    return parsed


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday() - WEEKDAY_MONDAY)


def month_start(day: date) -> date:
    return date(day.year, day.month, 1)


def add_months(day: date, months: int) -> date:
    month_index = day.year * 12 + (day.month - 1) + months
    year, month = divmod(month_index, 12)
    return date(year, month + 1, 1)


def lagos_range_utc(
    start_day: date, end_day_exclusive: date
) -> tuple[datetime, datetime]:
    start = datetime(
        start_day.year, start_day.month, start_day.day, tzinfo=HOSPITAL_TZ
    ).astimezone(timezone.utc)
    end = datetime(
        end_day_exclusive.year,
        end_day_exclusive.month,
        end_day_exclusive.day,
        tzinfo=HOSPITAL_TZ,
    ).astimezone(timezone.utc)
    return start, end


def utc_naive(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


def resolve_period(
    period: str,
    *,
    start: str = "",
    end: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    selected = (period or "today").strip().lower().replace("-", "_")
    if selected not in PERIODS:
        raise ApiError(422, "invalid_period", "Choose a valid date range.")
    today = hospital_today(now)
    if selected == "today":
        start_day = today
        end_exclusive = today + timedelta(days=1)
        label = "Today"
    elif selected == "yesterday":
        start_day = today - timedelta(days=1)
        end_exclusive = today
        label = "Yesterday"
    elif selected == "this_week":
        start_day = week_start(today)
        end_exclusive = start_day + timedelta(days=7)
        label = "This week"
    elif selected == "last_week":
        start_day = week_start(today) - timedelta(days=7)
        end_exclusive = start_day + timedelta(days=7)
        label = "Last week"
    elif selected == "this_month":
        start_day = month_start(today)
        end_exclusive = add_months(start_day, 1)
        label = "This month"
    elif selected == "last_month":
        start_day = add_months(month_start(today), -1)
        end_exclusive = month_start(today)
        label = "Last month"
    else:
        if not start or not end:
            raise ApiError(
                422,
                "invalid_period",
                "Enter a start date and an end date for a custom range.",
            )
        start_day = parse_iso_date(start, field="start")
        last_day = parse_iso_date(end, field="end")
        if last_day < start_day:
            raise ApiError(422, "invalid_period", "The end date cannot be before the start date.")
        if (last_day - start_day).days + 1 > MAX_CUSTOM_DAYS:
            raise ApiError(422, "invalid_period", "Choose a custom range of one year or less.")
        end_exclusive = last_day + timedelta(days=1)
        label = f"{start_day.isoformat()} to {last_day.isoformat()}"

    utc_start, utc_end = lagos_range_utc(start_day, end_exclusive)
    last_inclusive = end_exclusive - timedelta(days=1)
    return {
        "period": selected,
        "label": label,
        "timezone": "Africa/Lagos",
        "startDate": start_day.isoformat(),
        "endDate": last_inclusive.isoformat(),
        "endDateExclusive": end_exclusive.isoformat(),
        "utcStart": utc_start,
        "utcEnd": utc_end,
        "utcStartNaive": utc_naive(utc_start),
        "utcEndNaive": utc_naive(utc_end),
        "weekStartsOn": "Monday",
    }
