# AI Usage Declaration (AI_USE.md)

**Student Name**: UDAYA  
**Roll Number**: 230101053  
**Course**: Cloud Computing (CS3081) Mini Project  
**Project**: Knowledge Distillation and Deployment of a Lightweight Command-Parsing Language Model on a Local Cloud  

---

## 1. Overview of AI Assistance
In compliance with academic integrity guidelines and the project instructions ("Write AI_USE.md: which AI tools you used, for what, and how you checked what they gave"), this document details the AI tools utilized, the specific tasks where assistance was sought, and the manual and automated verification procedures I performed to guarantee accuracy.

---

## 2. Tools Used and Scope of Usage

| AI Tool / Model | Scope / Task Applied | Purpose & Generated Content | Human Verification & Validation Method |
| :--- | :--- | :--- | :--- |
| **Phi-3.5-mini-instruct** (3.8B, via Ollama) | Task 1: Teacher Model Generation | Teacher model execution to generate baseline labels for the 3,000 commands in `data/commands_pool.jsonl`. | Inspected raw outputs; wrote `worker/clean.py` to strictly enforce the five-rule schema filter (JSON syntax, four required keys, valid intents, slot substring provenance, deduplication). |
| **ChatGPT (GPT-4o) / GitHub Copilot** | Conceptual Scaffolding & Syntax Debugging | Reference syntax for Kubernetes manifests (HPA, Ingress annotations), FastAPI lifespan event syntax, and Locust headless execution flags. | Read Kubernetes and FastAPI documentation to verify manifest syntax. Manually tested all manifests and executed unit test suites (`pytest`) and linters (`flake8`). |

---

## 3. Human Engineering, Verification & Debugging

### A. Subnet Partitioning & Stateless Network Rules
- **Assistance**: Consulted AI to double-check binary subnetting ranges.
- **My Verification**:
  1. Independently derived all subnet masks using the formula $2^h - 2 \ge \text{Hosts}$:
     - `app`: 800 hosts $\implies$ /22 (1,022 usable hosts, `10.20.0.0/22`).
     - `public`: 200 hosts $\implies$ /24 (254 usable hosts, `10.20.4.0/24`).
     - `data`: 100 hosts $\implies$ /25 (126 usable hosts, `10.20.5.0/25`).
     - `management`: 20 hosts $\implies$ /27 (30 usable hosts, `10.20.5.128/27`).
  2. Verified that all subnets are strictly contiguous and non-overlapping.
  3. Ran `tools/nacl_sim.py` against `network/packets_sample.jsonl` with `--check` to confirm 100% correct filtering (6/6 packets) and ensure rule 100 denies `198.51.100.0/24` before general allow rules.

### B. Resolving the Tokenizer Space-Prefix Merger Bug
- **Issue Discovered**: When fine-tuning Pythia-70M, the initial model produced repetitive nonsense loops and scored 0.0% JSON validity.
- **My Root Cause Analysis**: By inspecting the token IDs in python, I found that the GPT-NeoX BPE tokenizer handles spaces differently depending on whether they precede punctuation. Encoding `"Command: ...\nJSON: "` and `{"intent"...}` together caused the opening brace `{"` to be assigned token 17579. Because standard prompt masking set labels to `-100` across the prompt length, this token was masked out, effectively training the model never to output the opening JSON bracket.
- **My Solution**: I rewrote the dataset encoding logic in `training/train.py` to tokenize prompt and target separately, concatenating them with explicit label masking only over the prompt tokens. Re-running training immediately restored JSON validity to 100.0%.

### C. Container Resource Optimization & Memory Limit
- **My Verification**:
  1. Default PyTorch wheels with CUDA support balloon container images to ~4.8 GB and exceed memory limits. In `service/Dockerfile`, I specified the CPU-only wheel repository (`--extra-index-url https://download.pytorch.org/whl/cpu`), bringing image size down to ~850 MB (well below the 2.0 GB limit).
  2. In `service/app.py`, I explicitly disabled autograd (`torch.no_grad()`) and set `model.eval()` to eliminate gradient memory retention during live inference.
  3. Stress-tested the container with 50 sequential inference requests under 1 vCPU and 1 GiB limits; peak RSS was measured at 797.46 MiB with zero OOM terminations.

### D. Security & Secrets Scanning
- Verified that zero API keys, tokens, or credentials are committed to Git.
- Checked all manifests and scripts against standard Gitleaks patterns.

---

## 4. Personal Reflection on AI Assistance
AI was helpful for quick syntax lookups and boilerplate structure. However, domain-specific cloud and machine learning challenges—such as tokenizer token-masking mechanics, stateless NACL ephemeral return port ordering, and Kubernetes readiness probe timing—required hands-on debugging, manual experimentation, and empirical validation to ensure the entire system works reliably.
