import re
from typing import List, Dict
from pathlib import Path
from transformers import AutoTokenizer  # or your LLM-specific chunking lib

# Constants
MAX_TOKENS = 1024  # Adjust to your LLM window
LOG_DIR = Path("./logs/")  # Folder with raw Jenkins logs


def extract_repos(first_line: str) -> List[str]:
    """Extract repo names from the first line."""
    return [repo.strip() for repo in re.split(r'[,\[\]]+', first_line) if repo.strip()]


def chunk_log(log_body: str, max_tokens: int = MAX_TOKENS) -> List[str]:
    """Chunk logs using token limit."""
    tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")  # or your LLM tokenizer
    tokens = tokenizer.encode(log_body)
    chunks = []
    for i in range(0, len(tokens), max_tokens):
        chunk_tokens = tokens[i:i + max_tokens]
        chunk_text = tokenizer.decode(chunk_tokens, skip_special_tokens=True)
        chunks.append(chunk_text)
    return chunks

# jenkins_api/process_and_query.py

from transformers import AutoTokenizer
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
import os

tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")

def chunk_text_file(file_path: str) -> list[Document]:
    with open(file_path, "r") as f:
        text = f.read()

    splitter = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
        tokenizer, chunk_size=400, chunk_overlap=40
    )

    return splitter.create_documents([text])

def process_log_file(file_path: Path) -> Dict:
    """Parse one Jenkins log and prepare chunks with repo mapping."""
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if not lines:
        return {}

    repos = extract_repos(lines[0])
    log_body = "".join(lines[1:])
    chunks = chunk_log(log_body)

    return {
        "repos": repos,
        "chunks": [{"text": chunk, "repos": repos} for chunk in chunks]
    }


def process_all_logs(log_dir: Path) -> List[Dict]:
    """Process all Jenkins logs in a folder."""
    results = []
    for log_file in log_dir.glob("*.log"):
        parsed = process_log_file(log_file)
        if parsed:
            results.append(parsed)
    return results
