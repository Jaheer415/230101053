import json
import urllib.request
import concurrent.futures
import time

def evaluate_teacher():
    with open('prompts/teacher_prompt.txt', 'r', encoding='utf-8') as f:
        prompt_tpl = f.read()
    
    with open('data/validation.jsonl', 'r', encoding='utf-8') as f:
        val_samples = [json.loads(line) for line in f if line.strip()]

    print(f"Loaded {len(val_samples)} validation samples.")
    results = [None] * len(val_samples)

    def process_item(idx, item):
        cmd = item['text']
        prompt = prompt_tpl.replace('{command}', cmd)
        req_body = json.dumps({
            'model': 'phi3.5',
            'prompt': prompt,
            'stream': False,
            'format': 'json',
            'options': {
                'temperature': 0,
                'seed': 42,
                'num_predict': 80
            }
        }).encode('utf-8')
        req = urllib.request.Request(
            'http://127.0.0.1:11434/api/generate',
            data=req_body,
            headers={'Content-Type': 'application/json'}
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                raw = data.get('response', '')
                results[idx] = {'id': item['id'], 'prediction': raw}
        except Exception as e:
            print(f"Error for {item['id']}: {e}")
            results[idx] = {'id': item['id'], 'prediction': 'error'}

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(process_item, i, item) for i, item in enumerate(val_samples)]
        for f in concurrent.futures.as_completed(futures):
            pass
    print(f"Completed in {round(time.time() - t0, 2)}s.")

    with open('results/teacher_predictions.jsonl', 'w', encoding='utf-8') as f:
        for r in results:
            if r is not None:
                f.write(json.dumps(r) + '\n')
    print("Saved teacher predictions to results/teacher_predictions.jsonl")

if __name__ == '__main__':
    evaluate_teacher()

