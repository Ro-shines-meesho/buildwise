#!/usr/bin/env python3
"""
Jenkins Log Processing and Repository Vectorization
Processes Jenkins logs and creates vector embeddings for repository code.
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List

# Add backend to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.services.vector_indexer import chunk_and_store_to_vector_db

def extract_repos_from_log(log_path: str) -> list[str]:
    """Extract repository URLs from Jenkins log file"""
    repos = []
    
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Extract repositories from first line (comma-separated)
        lines = content.split('\n')
        if lines:
            first_line = lines[0].strip()
            if first_line and ',' in first_line:
                repos.extend([repo.strip() for repo in first_line.split(',')])
        
        # Also extract repositories mentioned in the log content
        github_pattern = r'https://github\.com/[^\s]+\.git'
        github_matches = re.findall(github_pattern, content)
        repos.extend(github_matches)
        
        # Extract from "Cloning repository" patterns
        cloning_pattern = r'Cloning repository (https://github\.com/[^\s]+)'
        cloning_matches = re.findall(cloning_pattern, content)
        repos.extend(cloning_matches)
        
        # Remove duplicates and filter invalid URLs
        repos = list(set(repos))
        valid_repos = []
        for repo in repos:
            if (repo.startswith('https://github.com/') and 
                repo.endswith('.git') and 
                len(repo.split('/')) >= 5 and
                'api.git' not in repo):
                valid_repos.append(repo)
        
        # Add additional repositories for better context
        additional_repos = [
            "https://github.com/Meesho/devops-lib.git",
            "https://github.com/Meesho/ringmaster-backend.git", 
            "https://github.com/Meesho/ringmaster-frontend.git"
        ]
        for repo in additional_repos:
            if repo not in valid_repos:
                valid_repos.append(repo)
        
        return valid_repos
        
    except Exception as e:
        print(f"⚠️ Error extracting repos from {log_path}: {e}")
        return []

def clone_repository(repo_url: str, target_dir: str) -> bool:
    """Clone a Git repository"""
    try:
        if os.path.exists(target_dir):
            print(f"📁 Repository already exists: {target_dir}")
            return True
        
        print(f"📥 Cloning {repo_url} to {target_dir}")
        result = subprocess.run(
            ['git', 'clone', repo_url, target_dir],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            print(f"✅ Successfully cloned: {repo_url}")
            return True
        else:
            print(f"❌ Failed to clone {repo_url}: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"⏰ Timeout cloning {repo_url}")
        return False
    except Exception as e:
        print(f"❌ Error cloning {repo_url}: {e}")
        return False

def process_log_and_repos(log_path: str, tag: str = "analysis"):
    """Process a log file and its associated repositories"""
    print(f"🔧 Processing log: {log_path}")
    
    # Extract repository URLs
    repos = extract_repos_from_log(log_path)
    print(f"📦 Found {len(repos)} repositories")
    
    # Clone repositories
    cloned_repos = []
    for repo_url in repos:
        repo_name = repo_url.rstrip('.git').split('/')[-1]
        target_dir = f"cloned_repos/{repo_name}"
        
        if clone_repository(repo_url, target_dir):
            cloned_repos.append(target_dir)
    
    print(f"✅ Cloned {len(cloned_repos)} repositories")
    
    # Process each cloned repository
    for repo_dir in cloned_repos:
        try:
            print(f"🔍 Processing repository: {repo_dir}")
            chunk_and_store_to_vector_db(repo_dir, tag)
        except Exception as e:
            print(f"⚠️ Error processing {repo_dir}: {e}")
    
    # Also process the log file itself
    try:
        print(f"📄 Processing log file: {log_path}")
        chunk_and_store_to_vector_db(log_path, tag)
    except Exception as e:
        print(f"⚠️ Error processing log file {log_path}: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python jenkins_fetch_and_vectorize.py <log_file_path>")
        sys.exit(1)
    
    log_path = sys.argv[1]
    process_log_and_repos(log_path)
