"""Clean worker shard outputs and generate datasets/v1/train.jsonl and train.sha256.

Cleaning rules (applied in order):
(a) replies that are not valid JSON
(b) replies whose keys are not exactly intent, date, time, and place
(c) replies whose intent is not one of the eight allowed intents
(d) replies with a slot value that is neither null nor text appearing in the command
(e) duplicate commands (keep the one with the smallest id)
"""
import os
import glob
import json
import hashlib
import sys

ALLOWED_KEYS = {'intent', 'date', 'time', 'place'}
ALLOWED_INTENTS = {
    'alarm_set',
    'alarm_query',
    'calendar_set',
    'calendar_query',
    'calendar_remove',
    'weather_query',
    'datetime_query',
    'recommendation_events'
}


def clean_dataset(teacher_dir='datasets/teacher', out_dir='datasets/v1'):
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, 'train.jsonl')
    sha_file = os.path.join(out_dir, 'train.sha256')

    shard_files = sorted(glob.glob(os.path.join(teacher_dir, 'shard-*.jsonl')))
    if not shard_files:
        print(f"Error: No shard files found in {teacher_dir}", file=sys.stderr)
        return False

    records = []
    seen_shard_ids = set()
    for sf in shard_files:
        with open(sf, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                cid = obj['id']
                if cid in seen_shard_ids:
                    print(f"Warning: duplicate id across shards: {cid}", file=sys.stderr)
                seen_shard_ids.add(cid)
                records.append(obj)

    # Sort all records by id
    def sort_key(r):
        cid = r['id']
        num_part = ''.join(c for c in cid if c.isdigit())
        return int(num_part) if num_part else cid

    records.sort(key=sort_key)
    total_input = len(records)

    counts = {
        'input': total_input,
        'rejected_a_invalid_json': 0,
        'rejected_b_invalid_keys': 0,
        'rejected_c_invalid_intent': 0,
        'rejected_d_invalid_slots': 0,
        'rejected_e_duplicates': 0,
        'kept': 0
    }

    seen_command_texts = set()
    kept_records = []

    for r in records:
        text = r.get('text', '')
        raw = r.get('teacher_raw', '')

        # (a) Check valid JSON
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(parsed, dict):
                counts['rejected_a_invalid_json'] += 1
                continue
        except (json.JSONDecodeError, TypeError):
            counts['rejected_a_invalid_json'] += 1
            continue

        # (b) Check exact 4 keys
        if set(parsed.keys()) != ALLOWED_KEYS:
            counts['rejected_b_invalid_keys'] += 1
            continue

        # (c) Check intent
        intent = parsed.get('intent')
        if intent not in ALLOWED_INTENTS:
            counts['rejected_c_invalid_intent'] += 1
            continue

        # (d) Check slot values: either null or substring of command (case-insensitive)
        norm_text = ' '.join(text.lower().split())
        slots_valid = True
        for slot_key in ('date', 'time', 'place'):
            slot_val = parsed.get(slot_key)
            if slot_val is None:
                continue
            if not isinstance(slot_val, str):
                slots_valid = False
                break
            norm_val = ' '.join(slot_val.lower().split())
            if norm_val not in norm_text:
                slots_valid = False
                break

        if not slots_valid:
            counts['rejected_d_invalid_slots'] += 1
            continue

        # (e) Duplicate command text (keep smallest id)
        norm_cmd = norm_text
        if norm_cmd in seen_command_texts:
            counts['rejected_e_duplicates'] += 1
            continue

        seen_command_texts.add(norm_cmd)

        # Standardize teacher_raw to canonical compact JSON string for training
        cleaned_obj = {
            'id': r['id'],
            'text': text,
            'teacher_raw': json.dumps(parsed)
        }
        kept_records.append(cleaned_obj)

    counts['kept'] = len(kept_records)

    with open(out_file, 'w', encoding='utf-8') as f:
        for r in kept_records:
            f.write(json.dumps(r) + '\n')

    sha256_hash = hashlib.sha256()
    with open(out_file, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256_hash.update(chunk)
    digest = sha256_hash.hexdigest()

    with open(sha_file, 'w', encoding='utf-8') as f:
        f.write(digest + '\n')

    total_accounted = (counts['rejected_a_invalid_json']
                       + counts['rejected_b_invalid_keys']
                       + counts['rejected_c_invalid_intent']
                       + counts['rejected_d_invalid_slots']
                       + counts['rejected_e_duplicates']
                       + counts['kept'])

    print("=" * 60)
    print("CLEANING SUMMARY COUNTS:")
    print(f"  Input records:                 {counts['input']}")
    print(f"  (a) Rejected invalid JSON:     {counts['rejected_a_invalid_json']}")
    print(f"  (b) Rejected invalid keys:     {counts['rejected_b_invalid_keys']}")
    print(f"  (c) Rejected invalid intent:   {counts['rejected_c_invalid_intent']}")
    print(f"  (d) Rejected invalid slots:    {counts['rejected_d_invalid_slots']}")
    print(f"  (e) Rejected duplicates:       {counts['rejected_e_duplicates']}")
    print(f"  Kept records:                  {counts['kept']}")
    print("-" * 60)
    print(f"  Verification (Sum == Input):   {total_accounted} == {counts['input']}")
    print(f"  Dataset SHA-256:               {digest}")
    print("=" * 60)
    return True


if __name__ == '__main__':
    clean_dataset()
