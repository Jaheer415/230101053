# Cloud Computing (CS3081) Mini Project
## Knowledge Distillation and Deployment of a Lightweight Command-Parsing Language Model on a Local Cloud

**Student Name**: UDAYA  
**Roll Number**: 230101053  
**GitHub Repository**: `https://github.com/Jaheer415/230101053`  
**Git Submission Tag**: `final`  

---

## 1. Project Overview
This project demonstrates sequence-level knowledge distillation and cloud-native deployment of a lightweight command-parsing language model (`EleutherAI/pythia-70m`, 70M parameters) distilled from a larger teacher model (`phi3.5`, 3.8B parameters via Ollama). The model parses natural language voice-assistant commands into a structured 4-key JSON object (`intent`, `date`, `time`, `place`) across 8 predefined intents from the SLURP benchmark.

The distilled model is containerized into a lightweight, CPU-optimized container (< 2.0 GB) and deployed onto a local Kubernetes cloud cluster with automated scaling (HPA), rolling updates, health probes, and stateless network access control (NACL).

---

## 2. Repository Structure
```
230101053/
├── cluster/
│   └── k3d.yaml                  # k3d cluster configuration with port mappings
├── data/
│   ├── commands_pool.jsonl       # 3,000 raw input commands (CC BY 4.0)
│   ├── validation.jsonl          # 100 gold labelled validation commands
│   ├── schema.json               # JSON schema and intent/slot rules
│   └── rate_card.json            # Hypothetical cloud billing rates
├── datasets/
│   ├── teacher/
│   │   ├── shard-0.jsonl         # Worker 0 raw teacher outputs
│   │   └── shard-1.jsonl         # Worker 1 raw teacher outputs
│   └── v1/
│       ├── train.jsonl           # Cleaned distillation training dataset
│       └── train.sha256          # SHA-256 checksum of train.jsonl
├── models/
│   ├── v1/                       # Trained student model v1 & tokenizer
│   │   └── model.sha256          # SHA-256 checksum of model artifacts
│   └── v2/                       # Trained student model v2 (for rolling update)
│       └── model.sha256          # SHA-256 checksum of v2 artifacts
├── k8s/
│   ├── namespace.yaml            # 'app' namespace definition
│   ├── secret.yaml               # S3 storage credentials Secret
│   ├── seaweedfs.yaml            # SeaweedFS object storage in 'data' namespace
│   ├── seaweedfs-init.yaml       # Bucket creation & dataset upload Job
│   ├── deployment.yaml           # Service deployment (2 replicas, limits, probes)
│   ├── service.yaml              # ClusterIP Service routing to port 8000
│   ├── ingress.yaml              # Traefik Ingress routing /parse
│   └── hpa.yaml                  # Horizontal Pod Autoscaler (min 1, max 2, 70% CPU)
├── network/
│   ├── nacl.json                 # Public subnet stateless Network Access Control List
│   ├── subnets.md                # Subnetting calculations, table, and NACL reasoning
│   └── packets_sample.jsonl      # Test packet traces for NACL simulation
├── prompts/
│   └── teacher_prompt.txt        # Teacher prompt for phi3.5 (temperature=0, seed=42)
├── results/
│   ├── teacher_predictions.jsonl # Raw teacher predictions on validation.jsonl
│   ├── teacher_validation.json   # Teacher score report (score.py output)
│   ├── pythia_untrained_predictions.jsonl # Untrained baseline predictions
│   ├── pythia_untrained_validation.json   # Untrained baseline score report
│   ├── student_v1_predictions.jsonl       # Distilled student v1 predictions
│   ├── student_v1_validation.json         # Distilled student v1 score report
│   ├── loadtest_stats.csv        # Locust 2-minute load test summary statistics
│   ├── loadtest_headers.json     # Per-replica & per-model-version header distribution
│   ├── peak_memory.txt           # 50-request memory limit verification evidence
│   ├── cold_start.txt            # Cold-start measurements across 3 runs and median
│   ├── rolling_update.txt        # Rolling update (v1->v2->v1) evidence & failure rate
│   ├── recovery.txt              # Pod failure recovery evidence & failure rate
│   ├── hpa_scaling.txt           # HPA scaling dynamics report under load
│   └── nacl_simulation.txt       # NACL packet simulation test output
├── service/
│   ├── app.py                    # FastAPI service (/parse, /healthz, /readyz, FAULT_INJECT)
│   ├── Dockerfile                # CPU-only PyTorch container build (< 2 GB, no weights)
│   └── requirements.txt          # Pinned dependency versions
├── tests/
│   ├── test_api.py               # Unit tests for endpoints and response headers
│   ├── test_validation.py        # Unit tests for schema enforcement and FAULT_INJECT
│   └── test_clean.py             # Unit tests for dataset cleaner rules
├── tools/
│   ├── score.py                  # Evaluation scoring script
│   ├── locustfile.py             # Locust load test script
│   └── nacl_sim.py               # Stateless NACL simulation tool
├── training/
│   ├── config.yaml               # Training hyperparameters & library versions
│   ├── train.py                  # PyTorch CPU fine-tuning script
│   └── loss.csv                  # Per-epoch training loss records
├── worker/
│   ├── worker.py                 # Resumable, parallel teacher worker
│   ├── clean.py                  # Data cleaning script (rules a-e)
│   └── job.yaml                  # Kubernetes Job manifest for workers in 'pipeline'
├── .github/workflows/
│   └── ci.yml                    # CI pipeline (lint, test, eval, quality gate, secret scan)
├── report/
│   └── report.pdf                # Technical report (Task 1 to Task 7)
├── 230101053.pdf                 # Scanned reflection document (3 pages)
├── Makefile                      # Build, deploy, test, and teardown automation
├── AI_USE.md                     # Disclosure of AI tools, verification, and audit trail
└── README.md                     # Project documentation and instructions
```

---

## 3. Quick Start & Setup Instructions

### Prerequisites
- Python 3.11+
- Git
- k3d & kubectl (for Kubernetes tasks)
- Ollama (for teacher model inference)

### Step 1: Install Dependencies
```bash
pip install -r service/requirements.txt
pip install flake8 pytest locust boto3 pyyaml
```

---

## 4. Build, Training & Deployment Commands

### A. Dataset Labelling & Cleaning (Task 1)
1. Launch parallel teacher workers:
   ```bash
   # Terminal 1: Worker 0
   SHARD_INDEX=0 SHARD_COUNT=2 python worker/worker.py

   # Terminal 2: Worker 1
   SHARD_INDEX=1 SHARD_COUNT=2 python worker/worker.py
   ```
2. Run dataset cleaner and generate SHA-256 checksum:
   ```bash
   python worker/clean.py
   ```

### B. Student Model Training (Task 2)
1. **Verification run on 50 records**:
   ```bash
   make train SUBSET=50
   ```
2. **Full training run**:
   ```bash
   make train
   ```
   *Reads hyperparameters from `training/config.yaml`, saves model artifacts to `models/v1/`, and computes `models/v1/model.sha256`.*

### C. Build Inference Container Image (Task 3)
Build lightweight CPU-only image (< 2 GB, no weights):
```bash
docker build -t parser-service:latest -f service/Dockerfile .
```

### D. Deploy to Kubernetes Cloud (Task 4)
Deploy entire system from fresh clone in 3 commands:
```bash
make up
```
*(Equivalent to: `k3d cluster create --config cluster/k3d.yaml`, followed by applying SeaweedFS and application manifests).*

Verify running resources:
```bash
kubectl get pods -n app
kubectl get svc -n app
kubectl get ingress -n app
kubectl get hpa -n app
```

---

## 5. Testing & Verification

### A. Run Automated Unit Tests & Linting (Task 6)
```bash
make test     # Executes pytest tests/ -v (all 6 tests passing)
make lint     # Executes flake8 service/ worker/ tests/ (zero errors)
```

### B. Run Stateless NACL Verification (Task 5)
```bash
python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check
```
*Outputs: 6 / 6 packets decided correctly (100.0%).*

### C. Run Resource Limits Verification (Task 3)
```bash
python scripts/test_memory_limit.py
```
*Completes 50 sequential requests under 1 CPU / 1 GiB limit, recording peak RSS in `results/peak_memory.txt`.*

### D. Run Locust Performance & Load Balancing Test (Task 4 & Task 7)
```bash
locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m \
       --host http://localhost:8080 --csv results/loadtest
```
*Results stored in `results/loadtest_stats.csv` and `results/loadtest_headers.json`.*

### E. Run Full Resilience & Cold Start Suite
```bash
python scripts/run_experiments.py
```

---

## 6. Teardown / Shutdown Instructions
Tear down the local Kubernetes cluster and all cloud resources with one command:
```bash
make down
```

---

## 7. Model Artifacts & GitHub Release
Model weights, tokenizer, and checksums are published as GitHub Release assets for release tag `v1.0.0`:
- `models/v1/model.safetensors`
- `models/v1/config.json`
- `models/v1/tokenizer.json`
- `models/v1/tokenizer_config.json`
- `models/v1/model.sha256`
*(No model binary files are committed directly to Git).*
