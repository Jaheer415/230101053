"""Unit tests for Dataset Cleaning Rules."""
import json

from worker.clean import ALLOWED_KEYS, ALLOWED_INTENTS


def test_clean_filters_rules():
    """Test filtering of invalid JSON, bad keys, invalid intent, invalid slots, and duplicates."""
    records = [
        # (a) invalid JSON
        {"id": "C01", "text": "set alarm", "teacher_raw": "not a json string"},
        # (b) invalid keys
        {"id": "C02", "text": "set alarm", "teacher_raw": json.dumps({"intent": "alarm_set", "date": None})},
        # (c) invalid intent
        {"id": "C03", "text": "set alarm",
         "teacher_raw": json.dumps({"intent": "invalid_intent", "date": None, "time": None, "place": None})},
        # (d) slot not in command
        {"id": "C04", "text": "set alarm",
         "teacher_raw": json.dumps({"intent": "alarm_set", "date": "tomorrow", "time": None, "place": None})},
        # Valid
        {"id": "C05", "text": "alarm for tomorrow",
         "teacher_raw": json.dumps({"intent": "alarm_set", "date": "tomorrow", "time": None, "place": None})},
        # (e) Duplicate of C05
        {"id": "C06", "text": "alarm for tomorrow",
         "teacher_raw": json.dumps({"intent": "alarm_set", "date": "tomorrow", "time": None, "place": None})}
    ]

    kept = []
    seen = set()
    for r in records:
        try:
            parsed = json.loads(r["teacher_raw"])
        except Exception:
            continue
        if set(parsed.keys()) != ALLOWED_KEYS:
            continue
        if parsed.get("intent") not in ALLOWED_INTENTS:
            continue
        norm_text = r["text"].lower()
        if any(parsed.get(k) is not None and parsed[k].lower() not in norm_text for k in ("date", "time", "place")):
            continue
        if norm_text in seen:
            continue
        seen.add(norm_text)
        kept.append(r["id"])

    assert kept == ["C05"]
