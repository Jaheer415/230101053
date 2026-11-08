# Model Artifacts & GitHub Release Storage

In strict compliance with the assignment specification:
> *"Upload the trained model, tokenizer, version information, and checksums as GitHub Release assets. Do not commit model files to Git."*

All model weights (`model.safetensors`), tokenizers (`tokenizer.json`, `tokenizer_config.json`), configurations (`config.json`, `generation_config.json`), and SHA-256 checksums (`model.sha256`) are uploaded as GitHub Release assets under release tags `v1.0.0` (Production distilled student) and `v2.0.0` (Canary distilled student) at:
**https://github.com/Jaheer415/230101053/releases**

### Downloading Release Assets Locally:
```bash
# Download Student v1 (Release v1.0.0)
gh release download v1.0.0 --dir models/v1

# Download Student v2 (Release v2.0.0)
gh release download v2.0.0 --dir models/v2

# Verify Checksums
cd models/v1 && sha256sum -c model.sha256
cd ../models/v2 && sha256sum -c model.sha256
```
