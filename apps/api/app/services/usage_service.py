from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models.usage import DailyUsageCounter, UsageEvent

LOCAL = timezone(timedelta(hours=8))


def utc_now():
    return datetime.now(timezone.utc)


def usage_day(now):
    return now.astimezone(LOCAL).date()


def quota_reset_at(now):
    local = now.astimezone(LOCAL)
    return (
        local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    ).astimezone(timezone.utc)


def normalize_token_usage(raw):
    raw = raw if isinstance(raw, dict) else {}
    values = {
        key: value
        for key, value in raw.items()
        if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
        and type(value) is int
        and 0 <= value <= 2**53 - 1
    }
    total = values.get("total_tokens")
    parts = sum(values.get(key, 0) for key in ("prompt_tokens", "completion_tokens"))
    consistent = total is not None and total >= parts
    if {"prompt_tokens", "completion_tokens"}.issubset(values) and total is not None:
        consistent = total == parts
    if total is not None and not consistent:
        values.pop("total_tokens")
    return {**values, "known_tokens": total if consistent else parts, "complete": consistent}


def reserve_operation(
    db,
    user_id,
    operation,
    run_id,
    request_id,
    settings,
    *,
    knowledge_base_id=None,
    conversation_id=None,
    document_id=None,
    now=None,
):
    now = now or utc_now()
    if operation not in {"chat", "index"}:
        raise ValueError("Invalid operation")
    if db.scalar(
        select(UsageEvent.id).where(
            UsageEvent.operation == operation, UsageEvent.operation_run_id == run_id
        )
    ):
        raise HTTPException(409, "这个请求已提交，请刷新后确认")
    day = usage_day(now)
    limit = settings.daily_chat_limit if operation == "chat" else settings.daily_index_limit
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    db.execute(
        insert(DailyUsageCounter)
        .values(
            id=uuid4(),
            user_id=user_id,
            quota_day=day,
            operation=operation,
            used_count=0,
            updated_at=now,
        )
        .on_conflict_do_nothing(index_elements=["user_id", "quota_day", "operation"])
    )
    changed = db.execute(
        update(DailyUsageCounter)
        .where(
            DailyUsageCounter.user_id == user_id,
            DailyUsageCounter.quota_day == day,
            DailyUsageCounter.operation == operation,
            DailyUsageCounter.used_count < limit,
        )
        .values(used_count=DailyUsageCounter.used_count + 1, updated_at=now)
    )
    if changed.rowcount != 1:
        reset = quota_reset_at(now).isoformat()
        label = "问答" if operation == "chat" else "索引"
        raise HTTPException(
            429,
            f"今日{label}次数已用完，将于 "
            f"{quota_reset_at(now).astimezone(LOCAL).strftime('%m-%d %H:%M')}"
            "（UTC+08:00）重置",
            headers={
                "X-Error-Code": "daily_quota_exceeded",
                "X-Quota-Operation": operation,
                "X-Quota-Reset-At": reset,
            },
        )
    event = UsageEvent(
        user_id=user_id,
        request_id=request_id,
        operation=operation,
        operation_run_id=run_id,
        knowledge_base_id=knowledge_base_id,
        conversation_id=conversation_id,
        document_id=document_id,
        quota_day=day,
        quota_charged=True,
        started_at=now,
    )
    db.add(event)
    db.flush()
    return event


def persist_attempt(factory, event_id, metrics):
    with factory() as db:
        changed = db.execute(
            update(UsageEvent)
            .where(UsageEvent.id == event_id, UsageEvent.status == "running")
            .values(attempts=dict(metrics.attempts), models=dict(metrics.models))
        )
        db.commit()
        return changed.rowcount == 1


def finish_operation(factory, event_id, status, metrics, error_code=None, *, finished_at=None):
    if status not in {"completed", "local_completed", "failed", "cancelled", "interrupted"}:
        raise ValueError("Invalid terminal status")
    with factory() as db:
        event = db.scalar(select(UsageEvent).where(UsageEvent.id == event_id).with_for_update())
        if event is None:
            return False
        values = {
            name: {**getattr(event, name), **getattr(metrics, name)}
            for name in ("durations_ms", "models", "attempts", "token_usage")
        }
        values["attempts"] = {
            key: max(event.attempts.get(key, 0), metrics.attempts.get(key, 0))
            for key in event.attempts.keys() | metrics.attempts.keys()
        }
        values["token_usage"] = dict(event.token_usage)
        for phase, incoming in metrics.token_usage.items():
            existing = event.token_usage.get(phase, {})
            newer = metrics.attempts.get(phase, 0) > event.attempts.get(phase, 0)
            improves = incoming.get("known_tokens", 0) > existing.get("known_tokens", 0)
            completes = incoming.get("complete", False) and not existing.get("complete", False)
            if newer or improves or completes or not existing:
                values["token_usage"][phase] = incoming
        if event.status != "running":
            # A remote worker can cancel before the producer flushes validated usage.
            # Preserve observations without resurrecting the task or changing its end time.
            db.execute(
                update(UsageEvent)
                .where(UsageEvent.id == event_id, UsageEvent.status == event.status)
                .values(
                    models=values["models"],
                    attempts=values["attempts"],
                    token_usage=values["token_usage"],
                )
            )
            db.commit()
            return False
        changed = db.execute(
            update(UsageEvent)
            .where(UsageEvent.id == event_id, UsageEvent.status == "running")
            .values(
                status=status, finished_at=finished_at or utc_now(), error_code=error_code, **values
            )
        )
        db.commit()
        return changed.rowcount == 1


def expire_usage_events(db, user_id, now, settings):
    count = 0
    for operation, seconds in [
        ("chat", settings.chat_timeout_seconds + 180),
        ("index", settings.indexing_timeout_seconds + 300),
    ]:
        result = db.execute(
            update(UsageEvent)
            .where(
                UsageEvent.user_id == user_id,
                UsageEvent.operation == operation,
                UsageEvent.status == "running",
                UsageEvent.started_at <= now - timedelta(seconds=seconds),
            )
            .values(status="interrupted", error_code="interrupted", finished_at=now)
        )
        count += result.rowcount
    return count


def get_usage_summary(db, user_id, settings, now=None):
    now = now or utc_now()
    expire_usage_events(db, user_id, now, settings)
    db.commit()
    day = usage_day(now)
    used = {
        row.operation: row.used_count
        for row in db.scalars(
            select(DailyUsageCounter).where(
                DailyUsageCounter.user_id == user_id, DailyUsageCounter.quota_day == day
            )
        )
    }
    quota = {
        operation: {
            "limit": limit,
            "used": used.get(operation, 0),
            "remaining": max(0, limit - used.get(operation, 0)),
        }
        for operation, limit in [
            ("chat", settings.daily_chat_limit),
            ("index", settings.daily_index_limit),
        ]
    }
    start = datetime.combine(day - timedelta(days=6), datetime.min.time(), LOCAL).astimezone(
        timezone.utc
    )
    counts = {
        name: 0
        for name in (
            "running",
            "completed",
            "local_completed",
            "failed",
            "cancelled",
            "interrupted",
        )
    }
    total = known = unknown = samples = duration = 0
    for event in db.scalars(
        select(UsageEvent)
        .where(
            UsageEvent.user_id == user_id,
            UsageEvent.started_at >= start,
            UsageEvent.started_at <= now,
        )
        .execution_options(yield_per=200)
    ):
        total += 1
        counts[event.status] += 1
        known += sum(item.get("known_tokens", 0) for item in event.token_usage.values())
        unknown += int(
            any(
                count and not event.token_usage.get(phase, {}).get("complete", False)
                for phase, count in event.attempts.items()
            )
        )
        value = event.durations_ms.get("total")
        if event.status != "running" and type(value) is int and value >= 0:
            samples += 1
            duration += value
    ended = total - counts["running"]
    return {
        "today": day.isoformat(),
        "reset_at": quota_reset_at(now),
        "quota": quota,
        "recording_started_at": db.scalar(
            select(func.min(UsageEvent.started_at)).where(UsageEvent.user_id == user_id)
        ),
        "recent": {
            "total": total,
            "ended": ended,
            **counts,
            "success_rate": (counts["completed"] + counts["local_completed"]) / ended
            if ended
            else None,
            "avg_duration_ms": duration / samples if samples else None,
            "sample_count": samples,
            "known_tokens": known,
            "unknown_usage_count": unknown,
        },
    }


def list_usage_events(db, user_id, *, operation=None, status=None, limit=20, offset=0):
    query = select(UsageEvent).where(UsageEvent.user_id == user_id)
    if operation:
        query = query.where(UsageEvent.operation == operation)
    if status:
        query = query.where(UsageEvent.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    return {
        "items": db.scalars(
            query.order_by(UsageEvent.started_at.desc(), UsageEvent.id.desc())
            .limit(limit)
            .offset(offset)
        ).all(),
        "total": total,
        "limit": limit,
        "offset": offset,
    }
