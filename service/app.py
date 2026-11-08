"""FastAPI Command-Parsing Inference Service.

Endpoints:
  POST /parse   -> parses command, sets X-Model-Version and X-Served-By
  GET  /healthz -> liveness probe (200 OK)
  GET  /readyz  -> readiness probe (503 while loading, 200 once ready)
Configuration:
  MODEL_URI, MODEL_VERSION, S3_ENDPOINT, MAX_NEW_TOKENS, FAULT_INJECT
"""
import os
import json
import socket
import logging
from contextlib import asynccontextmanager

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import jsonschema
from fastapi import FastAPI, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("inference-service")

MODEL_URI = os.environ.get("MODEL_URI", "models/v1")
MODEL_VERSION = os.environ.get("MODEL_VERSION", "v1")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "")
MAX_NEW_TOKENS = int(os.environ.get("MAX_NEW_TOKENS", "64"))
FAULT_INJECT = os.environ.get("FAULT_INJECT", "0")
POD_NAME = os.environ.get("HOSTNAME", socket.gethostname())

SCHEMA_PATH = os.environ.get("SCHEMA_PATH", "data/schema.json")
with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
    SCHEMA_CONFIG = json.load(f)
JSON_SCHEMA = SCHEMA_CONFIG.get("json_schema")
REQUIRED_KEYS = set(SCHEMA_CONFIG.get("keys", ["intent", "date", "time", "place"]))

model = None
tokenizer = None
is_ready = False


def download_model_from_s3(endpoint: str, uri: str, target_dir: str):
    import boto3
    from urllib.parse import urlparse
    logger.info(f"Downloading model artifacts from {uri} using S3 endpoint {endpoint}...")
    os.makedirs(target_dir, exist_ok=True)

    if uri.startswith("s3://"):
        parsed = urlparse(uri)
        bucket = parsed.netloc
        prefix = parsed.path.lstrip("/")
    else:
        parts = uri.strip("/").split("/", 1)
        bucket = parts[0]
        prefix = parts[1] if len(parts) > 1 else ""

    s3_client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "seaweedfs"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "seaweedfs")
    )

    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            rel_path = os.path.relpath(key, prefix) if prefix else key
            local_file = os.path.join(target_dir, rel_path)
            os.makedirs(os.path.dirname(local_file), exist_ok=True)
            logger.info(f"Downloading {key} -> {local_file}")
            s3_client.download_file(bucket, key, local_file)


def load_artifacts():
    global model, tokenizer, is_ready
    local_dir = "/tmp/model" if os.name != "nt" else os.path.join(os.environ.get("TEMP", "C:/tmp"), "model")

    if S3_ENDPOINT and (MODEL_URI.startswith("s3://") or not os.path.exists(MODEL_URI)):
        download_model_from_s3(S3_ENDPOINT, MODEL_URI, local_dir)
        load_path = local_dir
    else:
        load_path = MODEL_URI

    logger.info(f"Loading model and tokenizer from {load_path}...")
    tokenizer = AutoTokenizer.from_pretrained(load_path)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        load_path,
        torch_dtype=torch.float32,
        low_cpu_mem_usage=True
    )
    model.eval()
    is_ready = True
    logger.info(f"Model {MODEL_VERSION} successfully loaded into memory and ready.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        load_artifacts()
    except Exception as e:
        logger.error(f"Failed to load model during startup: {e}")
    yield


app = FastAPI(title="Command Parser Service", lifespan=lifespan)


class ParseRequest(BaseModel):
    text: str


@app.get("/healthz")
def healthz():
    return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "healthy"})


@app.get("/readyz")
def readyz():
    if not is_ready:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"status": "initializing"})
    return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ready"})


@app.post("/parse")
def parse(req: ParseRequest, response: Response):
    headers = {
        "X-Model-Version": MODEL_VERSION,
        "X-Served-By": POD_NAME
    }

    if not is_ready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "model_not_ready"},
            headers=headers
        )

    fault_inject = os.environ.get("FAULT_INJECT", FAULT_INJECT)
    if fault_inject == "1":
        raw_text = "not json"
    else:
        prompt = f"Command: {req.text.strip()}\nJSON: "
        inputs = tokenizer(prompt, return_tensors="pt")
        input_ids = inputs["input_ids"]
        with torch.no_grad():
            output_tokens = model.generate(
                **inputs,
                max_new_tokens=MAX_NEW_TOKENS,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
                do_sample=False
            )
        generated = tokenizer.decode(output_tokens[0][input_ids.shape[1]:], skip_special_tokens=True)
        raw_text = generated.strip()

    try:
        parsed = json.loads(raw_text)
        if not isinstance(parsed, dict) or set(parsed.keys()) != REQUIRED_KEYS:
            raise ValueError("Keys do not match schema requirement")
        jsonschema.validate(instance=parsed, schema=JSON_SCHEMA)
    except Exception as e:
        logger.warning(f"Schema validation failed: {e}. Raw was: {raw_text[:100]}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "invalid_model_output"},
            headers=headers
        )

    return JSONResponse(status_code=status.HTTP_200_OK, content=parsed, headers=headers)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("service.app:app", host="0.0.0.0", port=8000, reload=False)
