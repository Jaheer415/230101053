"""Evaluate trained student model on validation.jsonl."""
import json
import os
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

def main():
    os.makedirs('results', exist_ok=True)
    model_dir = "models/v1"
    print(f"Loading student model from {model_dir}...")
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(model_dir, torch_dtype=torch.float32)
    model.eval()

    with open('data/validation.jsonl', 'r', encoding='utf-8') as f:
        val_samples = [json.loads(line) for line in f if line.strip()]

    print(f"Generating predictions for {len(val_samples)} validation samples...")
    predictions = []
    for item in val_samples:
        prompt = f"Command: {item['text']}\nJSON: "
        inputs = tokenizer(prompt, return_tensors="pt")
        input_ids = inputs["input_ids"]
        with torch.no_grad():
            output_tokens = model.generate(
                input_ids=input_ids,
                max_new_tokens=64,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
                do_sample=False
            )
        generated = tokenizer.decode(output_tokens[0][input_ids.shape[1]:], skip_special_tokens=True)
        predictions.append({"id": item["id"], "prediction": generated.strip()})

    pred_file = "results/student_v1_predictions.jsonl"
    with open(pred_file, "w", encoding="utf-8") as f:
        for p in predictions:
            f.write(json.dumps(p) + "\n")
    print(f"Saved {len(predictions)} predictions to {pred_file}")

if __name__ == "__main__":
    main()

