# vector_ingestor.py

import os
import json
import uuid
import chromadb
from chromadb.utils import embedding_functions

from pathlib import Path
from typing import List

# Azure OpenAI config
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")

# Use OpenAI Embedding Function
openai_ef = embedding_functions.OpenAIEmbeddingFunction(
    api_key=AZURE_OPENAI_KEY,
    api_base=AZURE_OPENAI_ENDPOINT,
    model_name="text-embedding-ada-002",
)

client = chromadb.PersistentClient(path="./vector_store")
collection = client.get_or_create_collection(name="jenkins_logs", embedding_function=openai_ef)

def parse_log_file(filepath: str):
    with open(filepath) as f:
        lines = f.readlines()

    if not lines:
        return None

    # First line is comma-separated list of repositories
    repo_line = lines[0].strip()
    repos = [r.strip() for r in repo_line.split(",") if r.strip()]
    log_content = "".join(lines[1:]).strip()

    return {
        "repos": repos,
        "log": log_content
    }

def chunk_and_embed(filepath: str):
    parsed = parse_log_file(filepath)
    if not parsed:
        return

    repo_chunks = parsed["repos"]
    log_chunk = parsed["log"]

    # Add each repo separately
    for repo in repo_chunks:
        collection.add(
            documents=[repo],
            metadatas=[{"type": "repo", "source_file": filepath}],
            ids=[str(uuid.uuid4())]
        )

    # Add log body
    collection.add(
        documents=[log_chunk],
        metadatas=[{"type": "log", "source_file": filepath}],
        ids=[str(uuid.uuid4())]
    )

def ingest_all_logs(log_dir: str):
    for path in Path(log_dir).glob("*.log"):
        chunk_and_embed(str(path))

if __name__ == "__main__":
    log_dir = "jenkins_logs"  # directory with .log files
    ingest_all_logs(log_dir)
