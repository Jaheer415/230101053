"""PyTorch + HuggingFace Transformers fine-tuning on CPU for Pythia-70M.

Sequence-level knowledge distillation for command parsing.
Reads configuration strictly from training/config.yaml.
Supports --subset / SUBSET=N (e.g. SUBSET=50).
Saves loss per epoch to training/loss.csv.
Saves model, tokenizer, and computes SHA-256 checksums.
"""
import os
import sys
import csv
import glob
import random
import hashlib
import argparse
import yaml
import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, AutoModelForCausalLM

CONFIG_PATH = os.environ.get("CONFIG_PATH", "training/config.yaml")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


class DistillationDataset(Dataset):
    def __init__(self, records, tokenizer, max_length=128):
        self.samples = []
        eos = tokenizer.eos_token or "<|endoftext|>"
        for r in records:
            cmd = r["text"].strip()
            raw = r["teacher_raw"].strip()

            prompt_ids = tokenizer.encode(f"Command: {cmd}\nJSON: ", add_special_tokens=False)
            target_ids = tokenizer.encode(f"{raw}{eos}", add_special_tokens=False)

            full_ids = prompt_ids + target_ids
            if len(full_ids) > max_length:
                full_ids = full_ids[:max_length]

            # Mask prompt tokens: loss is computed only on predicting teacher JSON
            labels = [-100] * min(len(prompt_ids), len(full_ids)) + full_ids[len(prompt_ids):]

            self.samples.append({
                "input_ids": torch.tensor(full_ids, dtype=torch.long),
                "labels": torch.tensor(labels, dtype=torch.long)
            })

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        return self.samples[idx]


def collate_fn(batch, pad_token_id):
    max_len = max(len(x["input_ids"]) for x in batch)
    input_ids = []
    labels = []
    attention_mask = []
    for x in batch:
        seq_len = len(x["input_ids"])
        pad_len = max_len - seq_len
        inp = torch.cat([x["input_ids"], torch.full((pad_len,), pad_token_id, dtype=torch.long)])
        lbl = torch.cat([x["labels"], torch.full((pad_len,), -100, dtype=torch.long)])
        mask = torch.cat([torch.ones(seq_len, dtype=torch.long), torch.zeros(pad_len, dtype=torch.long)])
        input_ids.append(inp)
        labels.append(lbl)
        attention_mask.append(mask)

    return {
        "input_ids": torch.stack(input_ids),
        "labels": torch.stack(labels),
        "attention_mask": torch.stack(attention_mask)
    }


def compute_checksums(model_dir):
    checksum_file = os.path.join(model_dir, "model.sha256")
    files = sorted(glob.glob(os.path.join(model_dir, "*")))
    lines = []
    for fpath in files:
        fname = os.path.basename(fpath)
        if fname == "model.sha256" or os.path.isdir(fpath):
            continue
        h = hashlib.sha256()
        with open(fpath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        lines.append(f"{h.hexdigest()}  {fname}")

    with open(checksum_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Saved model checksums to {checksum_file}")


def train():
    parser = argparse.ArgumentParser(description="Pythia-70M Distillation Training")
    parser.add_argument("--subset", type=int, default=None, help="Train on first N records only")
    parser.add_argument("--output_dir", type=str, default="models/v1", help="Output model directory")
    parser.add_argument("--epochs", type=int, default=None, help="Override epochs")
    parser.add_argument("--seed", type=int, default=None, help="Override seed")
    args = parser.parse_args()

    cfg = load_config()
    seed = args.seed if args.seed is not None else cfg.get("seed", 42)
    lr = float(cfg.get("learning_rate", 5e-4))
    batch_size = int(cfg.get("batch_size", 16))
    epochs = args.epochs if args.epochs is not None else int(cfg.get("epochs", 3))
    max_seq_len = int(cfg.get("max_seq_length", 128))
    output_dir = args.output_dir

    subset = args.subset
    if subset is None and "SUBSET" in os.environ and os.environ["SUBSET"].strip():
        subset = int(os.environ["SUBSET"].strip())

    set_seed(seed)
    device = torch.device("cpu")
    print(f"Training on device: {device} | Seed: {seed} | LR: {lr} | Epochs: {epochs} | Batch: {batch_size}")

    dataset_path = "datasets/v1/train.jsonl"
    if not os.path.exists(dataset_path):
        sys.exit(f"Dataset not found at {dataset_path}. Run worker/clean.py first.")

    import json
    with open(dataset_path, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    if subset:
        records = records[:subset]
        print(f"Training on SUBSET of {len(records)} records.")
    else:
        records = records[:1500]
        print(f"Training on first {len(records)} records (max 1500 limit).")

    base_model_name = "EleutherAI/pythia-70m"
    print(f"Loading base model {base_model_name}...")
    tokenizer = AutoTokenizer.from_pretrained(base_model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(base_model_name, torch_dtype=torch.float32)
    model.to(device)
    model.train()

    dataset = DistillationDataset(records, tokenizer, max_length=max_seq_len)
    dataloader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=True,
        collate_fn=lambda b: collate_fn(b, tokenizer.pad_token_id)
    )

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)

    loss_records = []
    print("Starting training loop...")
    for epoch in range(1, epochs + 1):
        total_loss = 0.0
        steps = 0
        for batch in dataloader:
            optimizer.zero_grad()
            input_ids = batch["input_ids"].to(device)
            labels = batch["labels"].to(device)
            attention_mask = batch["attention_mask"].to(device)

            outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
            loss = outputs.loss
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            steps += 1

        avg_loss = round(total_loss / max(1, steps), 4)
        loss_records.append({"epoch": epoch, "loss": avg_loss})
        print(f"Epoch {epoch}/{epochs} - Loss: {avg_loss}")

    loss_csv_path = "training/loss.csv"
    with open(loss_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["epoch", "loss"])
        writer.writeheader()
        writer.writerows(loss_records)
    print(f"Saved epoch losses to {loss_csv_path}")

    os.makedirs(output_dir, exist_ok=True)
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    print(f"Saved model and tokenizer to {output_dir}")

    compute_checksums(output_dir)
    print("Training completed successfully.")


if __name__ == "__main__":
    train()
