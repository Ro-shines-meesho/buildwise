#!/usr/bin/env python3
"""
Jenkins Log Extractor - Enhanced Multi-Project Version
Fetches console logs from Jenkins with success/failure categorization.
"""

import requests
import sys
import os
import json
import re
from datetime import datetime
from urllib.parse import urlparse
import argparse

# Try to load .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()  # Load .env file from current directory
except ImportError:
    pass  # python-dotenv not installed, skip

def create_directories():
    """Create necessary directory structure"""
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    dirs = ['logs', 'logs/success', 'logs/failure']
    for dir_name in dirs:
        dir_path = os.path.join(script_dir, dir_name)
        os.makedirs(dir_path, exist_ok=True)
    print(f"Created directories in {script_dir}: {', '.join(dirs)}")

def is_job_url(url):
    """Check if URL is a job URL (not a console URL)"""
    return '/consoleText' not in url and '/job/' in url

def extract_repository_urls(logs_content):
    """Extract repository URLs from Jenkins logs"""
    repo_urls = []
    
    # Search for lines containing "Cloning repository"
    cloning_pattern = r'\[.*?\] Cloning repository (https://github\.com/[^\s]+)'
    matches = re.findall(cloning_pattern, logs_content)
    
    repo_urls.extend(matches)
    
    return repo_urls

def get_job_builds(job_url, username, token, count=50):
    """
    Get build information from Jenkins job
    
    Args:
        job_url (str): Jenkins job URL (without /consoleText)
        username (str): Jenkins username
        token (str): Jenkins API token
        count (int): Number of builds to fetch
    
    Returns:
        list: List of build info dictionaries
    """
    try:
        print(f"Fetching build information from: {job_url}")
        
        # First get job info to determine total builds
        job_info_url = f"{job_url}/api/json?tree=nextBuildNumber"
        job_response = requests.get(job_info_url, auth=(username, token), timeout=30)
        
        if job_response.status_code == 401:
            print(f"Authentication failed for job API")
            return []
        elif job_response.status_code == 403:
            print(f"Access forbidden for job API")
            return []
        elif job_response.status_code == 404:
            print(f"Job not found: {job_url}")
            return []
            
        job_response.raise_for_status()
        job_data = job_response.json()
        next_build_number = job_data.get('nextBuildNumber', 1)
        total_builds = next_build_number - 1 if next_build_number > 1 else 0
        
        # Now get the builds list
        api_url = f"{job_url}/api/json?tree=builds[number,result,url]{{0,{count}}}"
        response = requests.get(api_url, auth=(username, token), timeout=30)
        response.raise_for_status()
        
        data = response.json()
        builds = data.get('builds', [])
        print(f"Found {total_builds} total builds")
        return builds
    
    except Exception as e:
        print(f"Error fetching job builds: {e}")
        return []

def extract_single_log(console_url, output_file, username, token):
    """Extract logs from a single console URL"""
    try:
        response = requests.get(console_url, auth=(username, token), timeout=30)
        
        if response.status_code == 401:
            print(f"Authentication failed for: {console_url}")
            return False
        elif response.status_code == 403:
            print(f"Access forbidden for: {console_url}")
            return False
        elif response.status_code == 404:
            print(f"Build not found: {console_url}")
            return False
        
        response.raise_for_status()
        logs_content = response.text
        
        # Check if we got HTML instead of logs
        if '<html' in logs_content.lower() and len(logs_content) < 10000:
            print(f"Received HTML page instead of logs: {console_url}")
            return False
        
        # Ensure output file is relative to script directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if not os.path.isabs(output_file):
            output_file = os.path.join(script_dir, output_file)
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        # Extract repository URLs from logs
        repo_urls = extract_repository_urls(logs_content)
        
        # Save logs to file
        with open(output_file, 'w', encoding='utf-8') as f:
            # Write repository URLs as first line if found
            if repo_urls:
                f.write(f"{','.join(repo_urls)}\n\n")
            
            f.write(logs_content)
        
        return True
        
    except Exception as e:
        print(f"Error extracting log: {e}")
        return False

def process_job_for_builds(job_url, username, token, success_count=5, failure_count=5):
    """
    Process a job URL to extract success and failure builds
    
    Args:
        job_url (str): Jenkins job URL
        username (str): Jenkins username  
        token (str): Jenkins API token
        success_count (int): Number of successful builds to extract
        failure_count (int): Number of failed builds to extract
    """
    print(f"\nProcessing job: {job_url}")
    
    # Get job name for file naming
    parsed_url = urlparse(job_url)
    path_parts = [part for part in parsed_url.path.split('/') if part and part != 'job']
    job_name = '_'.join(path_parts) if path_parts else 'unknown_job'
    
    # Get build information
    builds = get_job_builds(job_url, username, token, count=50)
    
    if not builds:
        print(f"No builds found for: {job_url}")
        return False
    
    success_builds = []
    failure_builds = []
    
    # Categorize builds by result (latest first)
    for build in builds:
        result = build.get('result', '').upper()
        if result == 'SUCCESS' and len(success_builds) < success_count:
            success_builds.append(build)
        elif result in ['FAILURE', 'ABORTED', 'UNSTABLE'] and len(failure_builds) < failure_count:
            failure_builds.append(build)
        
        # Stop if we have enough of both types
        if len(success_builds) >= success_count and len(failure_builds) >= failure_count:
            break
    
    print(f"Found {len(success_builds)} success builds, {len(failure_builds)} failure builds to extract")
    
    # Get script directory for output files
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Extract success builds
    if success_builds:
        print(f"\nExtracting {len(success_builds)} SUCCESS builds:")
        for i, build in enumerate(success_builds, 1):
            build_num = build['number']
            console_url = f"{build['url']}consoleText"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(script_dir, f"logs/success/{job_name}_build_{build_num}_{timestamp}.txt")
            
            print(f"  Extracting success build #{build_num} ({i}/{len(success_builds)})")
            if extract_single_log(console_url, output_file, username, token):
                print(f"    Saved: {output_file}")
            else:
                print(f"    Failed to extract build #{build_num}")
    else:
        print(f"No successful builds found")
    
    # Extract failure builds
    if failure_builds:
        print(f"\nExtracting {len(failure_builds)} FAILURE builds:")
        for i, build in enumerate(failure_builds, 1):
            build_num = build['number']
            console_url = f"{build['url']}consoleText"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(script_dir, f"logs/failure/{job_name}_build_{build_num}_{timestamp}.txt")
            
            print(f"  Extracting failure build #{build_num} ({i}/{len(failure_builds)})")
            if extract_single_log(console_url, output_file, username, token):
                print(f"    Saved: {output_file}")
            else:
                print(f"    Failed to extract build #{build_num}")
    else:
        print(f"No failed builds found")
    
    return True

def extract_jenkins_logs(url, output_file=None, username=None, token=None):
    """
    Extract logs from Jenkins console output URL using basic auth
    (For single console URL)
    """
    try:
        print(f"Fetching logs from: {url}")
        
        if not username or not token:
            print("Missing username or token!")
            return False
        
        # Make the request with basic auth
        response = requests.get(url, auth=(username, token), timeout=30)
        
        # Check for authentication/permission errors
        if response.status_code == 401:
            print("Authentication failed! Check your credentials.")
            return False
        elif response.status_code == 403:
            print("Access forbidden! You don't have permission to access this job.")
            return False
        elif response.status_code == 404:
            print("Job or build not found! Check the URL.")
            return False
        
        response.raise_for_status()
        
        # Get the content
        logs_content = response.text
        
        # Check if we got HTML instead of logs
        if '<html' in logs_content.lower() and len(logs_content) < 10000:
            print("Received HTML page instead of logs. Check your permissions.")
            return False
        
        # Get script directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Generate output filename if not provided
        if not output_file:
            parsed_url = urlparse(url)
            job_info = parsed_url.path.replace('/consoleText', '').replace('/job/', '_').replace('/', '_').strip('_')
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(script_dir, f"logs/{job_info}_{timestamp}.txt")
        else:
            output_file = os.path.join(script_dir, f"logs/{output_file}")
        
        # Create logs directory
        os.makedirs(os.path.join(script_dir, 'logs'), exist_ok=True)
        
        # Extract repository URLs from logs
        repo_urls = extract_repository_urls(logs_content)
        
        # Save logs to file
        with open(output_file, 'w', encoding='utf-8') as f:
            # Write repository URLs as first line if found
            if repo_urls:
                f.write(f"# Repository URLs: {', '.join(repo_urls)}\n\n")
            
            f.write(logs_content)
        
        print(f"Logs saved successfully to: {output_file}")
        print(f"Log size: {len(logs_content)} characters")
        print(f"Lines: {len(logs_content.splitlines())} lines")
        if repo_urls:
            print(f"Repository URLs found: {', '.join(repo_urls)}")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching logs: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False

def load_credentials():
    """Load Jenkins credentials from .env file"""
    username = os.getenv('JENKINS_USERNAME')
    token = os.getenv('JENKINS_TOKEN')
    return username, token

def main():
    """Main function"""
    
    parser = argparse.ArgumentParser(description='Extract Jenkins console logs')
    parser.add_argument('url', nargs='?', help='Jenkins job URL or console URL')
    parser.add_argument('-o', '--output', help='Output file path (for single console URL only)')
    parser.add_argument('--success-count', type=int, default=5, help='Number of success builds to extract (default: 5)')
    parser.add_argument('--failure-count', type=int, default=5, help='Number of failure builds to extract (default: 5)')
    
    args = parser.parse_args()
    
    print("Jenkins Log Extractor - Enhanced")
    print("=" * 45)
    
    # Load credentials from .env file
    username, token = load_credentials()
    
    if not username or not token:
        print("No credentials found in .env file!")
        print("Please ensure your .env file contains:")
        print("  JENKINS_USERNAME=your_username")
        print("  JENKINS_TOKEN=your_api_token")
        sys.exit(1)
    
    print(f"Loaded credentials for user: {username}")
    
    # Create directory structure
    create_directories()
    
    # Get URL
    url = args.url or os.getenv('JENKINS_URL')
    
    if not url:
        print("No URL provided!")
        print("Usage:")
        print("  python script.py <job_url>           # Extract 5 success + 5 failure builds")
        print("  python script.py <console_url>       # Extract single console log")
        print("  python script.py <job_url> --success-count 3 --failure-count 3")
        sys.exit(1)
    
    # Determine if this is a job URL or console URL
    if is_job_url(url):
        print(f"Detected JOB URL - will extract {args.success_count} success + {args.failure_count} failure builds")
        
        success = process_job_for_builds(
            job_url=url,
            username=username,
            token=token,
            success_count=args.success_count,
            failure_count=args.failure_count
        )
        
        if success:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            print(f"\nJob processing complete!")
            print(f"Check {os.path.join(script_dir, 'logs/success/')} and {os.path.join(script_dir, 'logs/failure/')} directories")
        else:
            print(f"\nJob processing failed!")
            sys.exit(1)
    
    else:
        print(f"Detected CONSOLE URL - will extract single log")
        
        # Extract single console log
        success = extract_jenkins_logs(
            url=url,
            output_file=args.output,
            username=username,
            token=token
        )
        
        if success:
            print("\nLog extraction completed successfully!")
        else:
            print("\nLog extraction failed!")
            sys.exit(1)

if __name__ == "__main__":
    main()