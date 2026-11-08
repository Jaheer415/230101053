"""Worker for parallel teacher labelling.

Reads SHARD_INDEX and SHARD_COUNT from environment variables.
Filters commands_pool.jsonl by: line_index % SHARD_COUNT == SHARD_INDEX.
Queries teacher model (phi3.5 via Ollama) with prompts/teacher_prompt.txt.
Thread-safe, resumable, writes raw output to datasets/teacher/shard-<SHARD_INDEX>.jsonl.
"""
import os
import sys
import json
import time
import threading
import concurrent.futures
import urllib.request
import urllib.error

SHARD_INDEX = int(os.environ.get('SHARD_INDEX', '0'))
SHARD_COUNT = int(os.environ.get('SHARD_COUNT', '2'))
CONCURRENCY = int(os.environ.get('CONCURRENCY', '2'))
TEACHER_URL = os.environ.get('TEACHER_URL', 'http://127.0.0.1:11434/api/generate')
INPUT_PATH = os.environ.get('INPUT_PATH', 'data/commands_pool.jsonl')
PROMPT_PATH = os.environ.get('PROMPT_PATH', 'prompts/teacher_prompt.txt')
OUTPUT_DIR = os.environ.get('OUTPUT_DIR', 'datasets/teacher')
OUTPUT_PATH = os.environ.get('OUTPUT_PATH', os.path.join(OUTPUT_DIR, f'shard-{SHARD_INDEX}.jsonl'))

file_lock = threading.Lock()


def query_teacher(prompt, retries=5):
    req_body = json.dumps({
        'model': 'phi3.5',
        'prompt': prompt,
        'stream': False,
        'format': 'json',
        'options': {
            'temperature': 0,
            'seed': 42,
            'num_predict': 70
        }
    }).encode('utf-8')

    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                TEACHER_URL,
                data=req_body,
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data.get('response', '')
        except Exception as e:
            time.sleep(1 + attempt * 2)
            if attempt == retries - 1:
                return f'{{"error": "{str(e)}"}}'


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(PROMPT_PATH, 'r', encoding='utf-8') as f:
        prompt_tpl = f.read()

    existing_ids = set()
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        record = json.loads(line)
                        if 'id' in record:
                            existing_ids.add(record['id'])
                    except json.JSONDecodeError:
                        pass
        print(f"[Worker {SHARD_INDEX}/{SHARD_COUNT}] Found {len(existing_ids)} existing records.")

    all_commands = []
    with open(INPUT_PATH, 'r', encoding='utf-8') as f:
        for idx, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            all_commands.append((idx, json.loads(line)))

    shard_items = [(idx, cmd) for idx, cmd in all_commands if idx % SHARD_COUNT == SHARD_INDEX]
    remaining_items = [item for item in shard_items if item[1]['id'] not in existing_ids]
    print(f"[Worker {SHARD_INDEX}/{SHARD_COUNT}] Assigned: {len(shard_items)}, Remaining: {len(remaining_items)}.")

    if not remaining_items:
        print(f"[Worker {SHARD_INDEX}] All assigned commands already processed.")
        return

    out_file = open(OUTPUT_PATH, 'a', encoding='utf-8')
    processed_count = len(existing_ids)
    total_assigned = len(shard_items)

    def process_command(item):
        nonlocal processed_count
        idx, cmd = item
        cid = cmd['id']
        text = cmd['text']
        prompt = prompt_tpl.replace('{command}', text)
        raw_reply = query_teacher(prompt)
        record = {
            'id': cid,
            'text': text,
            'teacher_raw': raw_reply
        }
        with file_lock:
            out_file.write(json.dumps(record) + '\n')
            out_file.flush()
            processed_count += 1
            if processed_count % 25 == 0 or processed_count == total_assigned:
                pct = round(100.0 * processed_count / total_assigned, 1)
                print(f"[Worker {SHARD_INDEX}] Progress: {processed_count}/{total_assigned} ({pct}%)")

    t_start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = [executor.submit(process_command, item) for item in remaining_items]
        for f in concurrent.futures.as_completed(futures):
            try:
                f.result()
            except Exception as e:
                print(f"[Worker {SHARD_INDEX}] Error: {e}", file=sys.stderr)

    out_file.close()
    elapsed = round(time.time() - t_start, 2)
    print(f"[Worker {SHARD_INDEX}] Finished in {elapsed}s. Total records: {processed_count}/{total_assigned}")


if __name__ == '__main__':
    main()
