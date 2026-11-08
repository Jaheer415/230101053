.PHONY: up down train test lint clean

# Python executable
PYTHON ?= python

# Task 2: Student Model Training
train:
	@if [ -n "$(SUBSET)" ]; then \
		$(PYTHON) training/train.py --subset $(SUBSET); \
	else \
		$(PYTHON) training/train.py; \
	fi

# Task 6: Deploy entire stack in at most 3 commands from fresh clone
up:
	k3d cluster create --config cluster/k3d.yaml || true
	kubectl apply -f k8s/namespace.yaml -f k8s/secret.yaml -f k8s/seaweedfs.yaml
	kubectl apply -f k8s/deployment.yaml -f k8s/service.yaml -f k8s/ingress.yaml -f k8s/hpa.yaml

# Task 6: Tear down local cluster
down:
	k3d cluster delete cloud-cluster || true

# Automated Testing & Quality Checks
test:
	pytest tests/ -v

lint:
	flake8 service/ worker/ tests/

score-teacher:
	$(PYTHON) tools/score.py results/teacher_predictions.jsonl data/validation.jsonl --out results/teacher_validation.json

score-student:
	$(PYTHON) tools/score.py results/student_v1_predictions.jsonl data/validation.jsonl --out results/student_v1_validation.json

nacl-check:
	$(PYTHON) tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check

clean:
	rm -rf .pytest_cache __pycache__ service/__pycache__ worker/__pycache__ tests/__pycache__

# Task 7: Build single-file submission zip archive
zip:
	$(PYTHON) scripts/build_submission_zip.py


