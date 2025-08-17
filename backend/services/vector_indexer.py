# vector_indexer.py
import os
import glob
import shutil
import json
import hashlib
import subprocess
from tqdm import tqdm
from pathlib import Path

from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import SentenceTransformerEmbeddings

from langchain.docstore.document import Document

from dotenv import load_dotenv
load_dotenv()

# Use local embeddings to avoid API key issues
embeddings = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")

REPO_DIR = "cloned_repos"
VECTOR_STORE_DIR = "vectorstore"
vectorstore_path = "vectorstore"

text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)

def extract_repos_from_log(log_path):
    """Extract repo URLs from first line of the log file"""
    with open(log_path, "r", encoding="utf-8") as f:
        first_line = f.readline().strip()
        if first_line.startswith("http") or "github.com" in first_line:
            return first_line.split(",")
    return []

def clone_repo(url):
    """Clone a repo only if not already cloned"""
    if not os.path.exists(REPO_DIR):
        os.makedirs(REPO_DIR)
    repo_name = url.split("/")[-1].replace(".git", "")
    repo_path = os.path.join(REPO_DIR, repo_name)
    if not os.path.exists(repo_path):
        subprocess.run(["git", "clone", url, repo_path], check=True)
    return repo_path

def load_texts_from_repo(repo_path):
    """Load all .py, .md, .js, .ts, .json, .yaml, .yml files as documents"""
    docs = []
    extensions = ("**/*.py", "**/*.md", "**/*.txt", "**/*.js", "**/*.ts", "**/*.json", "**/*.yaml", "**/*.yml", "**/*.Jenkinsfile", "**/*.Dockerfile")
    for ext in extensions:
        for file_path in glob.glob(os.path.join(repo_path, ext), recursive=True):
            try:
                loader = TextLoader(file_path)
                loaded_docs = loader.load()
                docs.extend(loaded_docs)
            except Exception as e:
                print(f"Failed to load {file_path}: {e}")
                pass
    return docs

def chunk_and_store_to_vector_db(directory_path: str, vectorstore_path: str, metadata=None):
    """Chunk and store documents to vector database"""
    documents = []
    
    # Load all relevant files
    for ext in ("**/*.py", "**/*.md", "**/*.txt", "**/*.js", "**/*.ts", "**/*.json", "**/*.yaml", "**/*.yml", "**/*.Jenkinsfile", "**/*.Dockerfile"):
        for file in Path(directory_path).rglob(ext):
            try:
                loader = TextLoader(str(file))
                docs = loader.load()
                split_docs = text_splitter.split_documents(docs)
                if metadata:
                    for d in split_docs:
                        d.metadata.update(metadata)
                documents.extend(split_docs)
            except Exception as e:
                print(f"Failed to process {file}: {e}")
                continue

    if not documents:
        print(f"⚠️ No documents found in {directory_path}")
        return

    # Create vectorstore from documents and save it
    try:
        vectorstore = FAISS.from_documents(documents, embeddings)
        vectorstore.save_local(vectorstore_path)
        print(f"✅ Vector store saved to: {vectorstore_path} with {len(documents)} chunks")
    except Exception as e:
        print(f"❌ Error creating vector store: {e}")

def load_logs(log_dir):
    """Load all logs and parse into LangChain Documents"""
    log_docs = []
    for log_file in glob.glob(os.path.join(log_dir, "*.txt")):
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                content = f.read()
                doc = Document(page_content=content, metadata={"source": log_file})
                log_docs.append(doc)
        except Exception as e:
            print(f"Failed to load log {log_file}: {e}")
    return log_docs

def build_vectorstore():
    """Build comprehensive vector store from logs and repositories"""
    all_docs = []

    print("📝 Loading logs...")
    all_docs.extend(load_logs("logs/success"))
    all_docs.extend(load_logs("logs/failure"))

    print("🔗 Extracting repos and cloning...")
    repo_urls_set = set()
    for log_file in glob.glob("logs/success/*.txt") + glob.glob("logs/failure/*.txt"):
        repo_urls = extract_repos_from_log(log_file)
        repo_urls_set.update(repo_urls)

    for repo_url in tqdm(repo_urls_set, desc="Processing repositories"):
        try:
            repo_path = clone_repo(repo_url)
            repo_docs = load_texts_from_repo(repo_path)
            all_docs.extend(repo_docs)
            print(f"✅ Processed {repo_url}: {len(repo_docs)} documents")
        except Exception as e:
            print(f"❌ Failed to process {repo_url}: {e}")

    print(f"📊 Total documents before splitting: {len(all_docs)}")
    docs = text_splitter.split_documents(all_docs)

    print(f"💾 Storing {len(docs)} chunks in FAISS vectorstore...")
    try:
        vectorstore = FAISS.from_documents(docs, embeddings)
        vectorstore.save_local(VECTOR_STORE_DIR)
        print(f"✅ Vector store saved to: {VECTOR_STORE_DIR}")
    except Exception as e:
        print(f"❌ Error building vector store: {e}")

if __name__ == "__main__":
    build_vectorstore()
