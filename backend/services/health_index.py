"""Dream Health Index — compute emotional trends, nightmare frequency, anomaly detection."""

from datetime import date, datetime, timedelta
from collections import Counter

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models.dream import DreamRecord, DreamStatus
from models.entities import DreamHealthSnapshot, PeriodType


async def compute_health_index(
    user_id: str, period_start: date, period_end: date, db: AsyncSession
) -> dict:
    """Compute health index for a user over a date range."""
    result = await db.execute(
        select(DreamRecord).where(
            and_(
                DreamRecord.user_id == user_id,
                DreamRecord.created_at >= datetime.combine(period_start, datetime.min.time()),
                DreamRecord.created_at <= datetime.combine(period_end, datetime.max.time()),
                DreamRecord.status == DreamStatus.completed,
            )
        ).order_by(DreamRecord.created_at)
    )
    dreams = result.scalars().all()

    total = len(dreams)
    if total == 0:
        return {"health_score": 100, "total_dreams": 0, "message": "No dreams in this period"}

    # Nightmare count
    nightmare_count = sum(1 for d in dreams if d.nightmare_flag)
    nightmare_freq = nightmare_count / total if total > 0 else 0

    # Emotion trend
    emotion_trend = []
    for d in dreams:
        if d.emotion_valence is not None:
            emotion_trend.append({
                "date": d.created_at.isoformat(),
                "valence": d.emotion_valence,
                "arousal": d.emotion_arousal or 0.5,
            })

    # Dominant emotions
    all_emotions = []
    for d in dreams:
        all_emotions.extend(d.emotion_tags or [])
    emotion_counter = Counter(all_emotions)
    dominant = [{"emotion": k, "count": v, "pct": round(v / total * 100)} for k, v in emotion_counter.most_common(5)]

    # Recurring symbols
    all_symbols = []
    for d in dreams:
        all_symbols.extend(d.symbol_tags or [])
    symbol_counter = Counter(all_symbols)
    recurring_symbols = [{"symbol": k, "count": v} for k, v in symbol_counter.most_common(10)]

    # Recurring characters
    all_chars = []
    for d in dreams:
        all_chars.extend(d.character_tags or [])
    char_counter = Counter(all_chars)
    recurring_chars = [{"character": k, "count": v} for k, v in char_counter.most_common(10)]

    # Anomaly detection
    anomalies = []
    if nightmare_freq > 0.4:
        anomalies.append({"type": "nightmare_spike", "description": f"Nightmare frequency at {nightmare_freq:.0%}", "severity": "high"})
    if emotion_trend:
        recent_valence = [e["valence"] for e in emotion_trend[-5:]]
        avg_recent = sum(recent_valence) / len(recent_valence) if recent_valence else 0
        if avg_recent < -0.3:
            anomalies.append({"type": "negative_trend", "description": f"Recent emotion valence averaging {avg_recent:.2f}", "severity": "medium"})

    # Composite score
    score = 100.0
    score -= nightmare_freq * 30  # High nightmares penalize
    if emotion_trend:
        avg_valence = sum(e["valence"] for e in emotion_trend) / len(emotion_trend)
        if avg_valence < 0:
            score += avg_valence * 20  # Negative emotions penalize
    score -= len(anomalies) * 10
    score = max(0, min(100, score))

    return {
        "health_score": round(score, 1),
        "total_dreams": total,
        "nightmare_count": nightmare_count,
        "nightmare_frequency": round(nightmare_freq, 3),
        "dominant_emotions": dominant,
        "emotion_trend": emotion_trend,
        "recurring_symbols": recurring_symbols,
        "recurring_characters": recurring_chars,
        "anomalies": anomalies,
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
    }


async def detect_anomalies(user_id: str, db: AsyncSession) -> list[dict]:
    """Quick anomaly scan comparing last 2 weeks to previous month.

    Single DB fetch spanning the union range; partition in Python. Previously
    two independent scans of the dreams table (each with its own WHERE+JOIN).
    """
    now = date.today()
    recent_start = now - timedelta(days=14)
    baseline_start = now - timedelta(days=45)

    # One scan covering baseline_start → now; partition locally below.
    result = await db.execute(
        select(DreamRecord).where(and_(
            DreamRecord.user_id == user_id,
            DreamRecord.created_at >= datetime.combine(baseline_start, datetime.min.time()),
            DreamRecord.created_at <= datetime.combine(now, datetime.max.time()),
            DreamRecord.status == DreamStatus.completed,
        )).order_by(DreamRecord.created_at)
    )
    all_dreams = result.scalars().all()
    recent_cutoff_dt = datetime.combine(recent_start, datetime.min.time())
    recent_dreams = [d for d in all_dreams if d.created_at >= recent_cutoff_dt]
    baseline_dreams = [d for d in all_dreams if d.created_at < recent_cutoff_dt]

    def _summary(dreams: list) -> dict:
        n = len(dreams)
        if n == 0:
            return {"total_dreams": 0, "nightmare_frequency": 0.0, "anomalies": []}
        nm = sum(1 for d in dreams if d.nightmare_flag)
        freq = nm / n
        a = []
        if freq > 0.4:
            a.append({"type": "nightmare_spike", "description": f"Nightmare frequency at {freq:.0%}", "severity": "high"})
        return {"total_dreams": n, "nightmare_frequency": freq, "anomalies": a}

    recent = _summary(recent_dreams)
    baseline = _summary(baseline_dreams)
    anomalies = list(recent.get("anomalies", []))

    # Compare nightmare frequency
    if baseline.get("total_dreams", 0) > 0 and recent.get("total_dreams", 0) > 0:
        baseline_freq = baseline.get("nightmare_frequency", 0)
        recent_freq = recent.get("nightmare_frequency", 0)
        if baseline_freq > 0 and recent_freq > baseline_freq * 2:
            anomalies.append({
                "type": "nightmare_increase",
                "description": f"Nightmare rate doubled: {baseline_freq:.0%} → {recent_freq:.0%}",
                "severity": "high",
            })

    return anomalies
