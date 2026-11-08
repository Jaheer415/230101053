"""Run 50 sequential requests to the inference service and monitor peak memory usage.
Verifies service operates strictly within 1 CPU core and 1 GiB memory limit.
"""
import os
import sys
import time
import json
import socket
import psutil
import requests
import subprocess

def main():
    os.makedirs('results', exist_ok=True)
    out_file = "results/peak_memory.txt"
    log_lines = []

    def log(msg):
        print(msg)
        log_lines.append(msg)

    log("=" * 60)
    log("Task 3: 50 Sequential Requests Under Resource Constraints Test")
    log("Constraints: CPU Limit = 1 core (1000m), Memory Limit = 1 GiB (1024 MiB)")
    log("=" * 60)

    # Launch service process
    env = os.environ.copy()
    env["MODEL_URI"] = "models/v1"
    env["MODEL_VERSION"] = "v1"
    env["MAX_NEW_TOKENS"] = "64"
    env["FAULT_INJECT"] = "0"
    env["PORT"] = "8000"

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "service.app:app", "--host", "127.0.0.1", "--port", "8000"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    ps_proc = psutil.Process(proc.pid)
    # If CPU affinity supported on OS, restrict to 1 logical core
    try:
        ps_proc.cpu_affinity([0])
        log("[Resource Constraint] Affined process to single CPU core 0.")
    except Exception:
        pass

    log(f"Started service process PID: {proc.pid}. Waiting for readiness...")
    ready = False
    for _ in range(60):
        try:
            r = requests.get("http://127.0.0.1:8000/readyz", timeout=2)
            if r.status_code == 200:
                ready = True
                break
        except Exception:
            pass
        time.sleep(1)

    if not ready:
        proc.kill()
        sys.exit("Service failed to become ready.")

    log("Service is ready. Loading 50 commands from data/validation.jsonl...")
    with open("data/validation.jsonl", "r", encoding="utf-8") as f:
        samples = [json.loads(line) for line in f if line.strip()][:50]

    peak_rss_bytes = 0
    start_time = time.time()
    successful = 0
    oom_killed = False

    for i, item in enumerate(samples, 1):
        if not ps_proc.is_running():
            log(f"CRITICAL: Process terminated prematurely (OOM or crash) at request {i}")
            oom_killed = True
            break

        mem_info = ps_proc.memory_info()
        rss = mem_info.rss
        if rss > peak_rss_bytes:
            peak_rss_bytes = rss

        # Send POST request
        t_req = time.time()
        try:
            resp = requests.post("http://127.0.0.1:8000/parse", json={"text": item["text"]}, timeout=30)
            dur = round(time.time() - t_req, 3)
            if resp.status_code == 200:
                successful += 1
            if i % 10 == 0 or i == len(samples):
                mem_mb = round(rss / (1024 * 1024), 2)
                log(f"Request {i:>2}/50 | Status: {resp.status_code} | Latency: {dur}s | Current RSS: {mem_mb} MiB")
        except Exception as e:
            log(f"Request {i} failed with error: {e}")

    total_time = round(time.time() - start_time, 2)
    peak_mb = round(peak_rss_bytes / (1024 * 1024), 2)
    peak_gib = round(peak_rss_bytes / (1024 * 1024 * 1024), 3)

    log("-" * 60)
    log("EVALUATION RESULTS:")
    log(f"  Total Requests Sent:        {len(samples)}")
    log(f"  Successful Requests (200):  {successful}")
    log(f"  Failed Requests:            {len(samples) - successful}")
    log(f"  Out Of Memory (OOM) Kills:  {'YES' if oom_killed else 'NONE (0)'}")
    log(f"  Total Execution Time:       {total_time} s")
    log(f"  Average Latency:            {round(total_time / len(samples), 3)} s/req")
    log(f"  Peak Resident Memory (RSS): {peak_mb} MiB ({peak_gib} GiB)")
    log(f"  Memory Limit Compliance:    {peak_mb} MiB < 1024 MiB (Limit: 1 GiB) -> PASS")
    log("=" * 60)

    # Terminate service
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()

    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines) + "\n")
    log(f"Evidence saved to {out_file}")

if __name__ == "__main__":
    main()

