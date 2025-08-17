import requests
import re
import json
import os
from requests.auth import HTTPBasicAuth
import os
from dotenv import load_dotenv
from pathlib import Path
import time

load_dotenv()  # loads .env file from current directory

username = os.getenv("JENKINS_USERNAME")
api_token = os.getenv("JENKINS_API_TOKEN")

class JenkinsFetcher:
    def __init__(self, username=None, api_token=None):
        self.username = username or os.getenv("JENKINS_USERNAME")
        self.api_token = api_token or os.getenv("JENKINS_API_TOKEN")
        self.auth = HTTPBasicAuth(self.username, self.api_token) if self.username and self.api_token else None
        
        if not self.auth:
            print("⚠️ No Jenkins credentials found. Set JENKINS_USERNAME and JENKINS_API_TOKEN environment variables.")
            print("💡 The system will work with existing log files in jenkins_api/logs/")
        
    def fetch_jenkins_console_text(self, url):
        """Fetch console text from Jenkins URL"""
        try:
            response = requests.get(url, auth=self.auth, timeout=60)  # Increased timeout
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching console text: {e}")
            return None

    def get_latest_builds(self, jenkins_url):
        """Get latest success and failure builds from Jenkins URL"""
        
        if not self.auth:
            print("❌ Cannot fetch from Jenkins without authentication")
            print("💡 Please set JENKINS_USERNAME and JENKINS_API_TOKEN environment variables")
            print("💡 Or use existing log files in jenkins_api/logs/")
            return None, None
            
        try:
            # Convert job URL to API URL
            if jenkins_url.endswith('/'):
                jenkins_url = jenkins_url[:-1]
            
            api_url = f"{jenkins_url}/api/json"
            print(f"🔗 Fetching from: {api_url}")
            
            response = requests.get(api_url, auth=self.auth, timeout=60)  # Increased timeout
            response.raise_for_status()
            
            job_data = response.json()
            builds = job_data.get('builds', [])
            
            print(f"📊 Found {len(builds)} builds in Jenkins")
            
            if not builds:
                print("❌ No builds found")
                return None, None
            
            # Get latest builds and fetch their details
            latest_builds = builds[:10]  # Get last 10 builds
            
            latest_failure = None
            latest_success = None
            
            for build in latest_builds:
                build_url = build['url']
                build_number = build['number']
                
                # Fetch individual build details to get the result
                build_api_url = f"{build_url}api/json"
                try:
                    build_response = requests.get(build_api_url, auth=self.auth, timeout=30)
                    if build_response.status_code == 200:
                        build_details = build_response.json()
                        result = build_details.get('result')
                        
                        print(f"🔍 Build {build_number}: {result}")
                        
                        if result == 'SUCCESS' and not latest_success:
                            latest_success = {
                                'url': f"{build_url}consoleText",
                                'number': build_number,
                                'result': result
                            }
                        elif result == 'FAILURE' and not latest_failure:
                            latest_failure = {
                                'url': f"{build_url}consoleText",
                                'number': build_number,
                                'result': result
                            }
                        
                        if latest_success and latest_failure:
                            break
                    else:
                        print(f"⚠️ Could not fetch details for build {build_number}")
                        
                except Exception as e:
                    print(f"⚠️ Error fetching build {build_number} details: {e}")
                    continue
            
            if not latest_success and not latest_failure:
                print("⚠️ Could not determine build results, using latest builds")
                # Fallback: use the latest builds without result
                if builds:
                    latest_build = builds[0]
                    latest_failure = {
                        'url': f"{latest_build['url']}consoleText",
                        'number': latest_build['number'],
                        'result': 'UNKNOWN'
                    }
            
            return latest_failure, latest_success
            
        except requests.exceptions.Timeout:
            print("❌ Timeout connecting to Jenkins API")
            return None, None
        except requests.exceptions.ConnectionError:
            print("❌ Connection error to Jenkins API")
            return None, None
        except Exception as e:
            print(f"❌ Error getting latest builds: {e}")
            return None, None

    def save_build_logs(self, failure_build=None, success_build=None):
        """Save build logs to files"""
        logs_dir = Path("jenkins_api/logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "failure").mkdir(exist_ok=True)
        (logs_dir / "success").mkdir(exist_ok=True)
        
        saved_logs = []
        
        if failure_build:
            print(f"📥 Fetching failure log for build {failure_build['number']}...")
            failure_content = self.fetch_jenkins_console_text(failure_build['url'])
            if failure_content:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"build_{failure_build['number']}_{timestamp}.txt"
                filepath = logs_dir / "failure" / filename
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(failure_content)
                
                print(f"✅ Saved failure log: {filepath}")
                saved_logs.append(str(filepath))
            else:
                print(f"❌ Failed to fetch failure log for build {failure_build['number']}")
        
        if success_build:
            print(f"📥 Fetching success log for build {success_build['number']}...")
            success_content = self.fetch_jenkins_console_text(success_build['url'])
            if success_content:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"build_{success_build['number']}_{timestamp}.txt"
                filepath = logs_dir / "success" / filename
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(success_content)
                
                print(f"✅ Saved success log: {filepath}")
                saved_logs.append(str(filepath))
            else:
                print(f"❌ Failed to fetch success log for build {success_build['number']}")
        
        return saved_logs

    def process_specific_build_url(self, build_url):
        """Process a specific build URL with build number"""
        print(f"🔗 Processing specific build URL: {build_url}")
        
        # Extract build information from URL
        build_info = self._extract_build_info_from_url(build_url)
        if not build_info:
            print("❌ Invalid build URL format")
            return []
        
        # Fetch console text for this specific build
        console_content = self.fetch_jenkins_console_text(build_url)
        if not console_content:
            print("❌ Failed to fetch console text for the specified build")
            return []
        
        # Save the log
        saved_logs = self._save_single_build_log(build_info, console_content)
        
        return saved_logs
    
    def _extract_build_info_from_url(self, build_url):
        """Extract build information from a specific build URL"""
        # Pattern: https://jenkins-dev.meeshogcp.in/job/dev-ops-buddy-frontend-cicd/job/develop/210/console
        pattern = r'https://[^/]+/job/([^/]+)/job/([^/]+)/(\d+)/console'
        match = re.match(pattern, build_url)
        
        if match:
            job_name = match.group(1)
            branch_name = match.group(2)
            build_number = match.group(3)
            
            return {
                'job_name': job_name,
                'branch_name': branch_name,
                'build_number': build_number,
                'full_url': build_url
            }
        
        return None
    
    def _save_single_build_log(self, build_info, console_content):
        """Save a single build log"""
        logs_dir = Path("jenkins_api/logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "failure").mkdir(exist_ok=True)
        (logs_dir / "success").mkdir(exist_ok=True)
        
        # Determine if this is a success or failure build
        # Look for success/failure indicators in the console content
        is_success = self._determine_build_status(console_content)
        
        # Create filename
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"build_{build_info['build_number']}_{timestamp}.txt"
        
        # Save to appropriate directory
        if is_success:
            filepath = logs_dir / "success" / filename
            print(f"📥 Saving success log for build {build_info['build_number']}...")
        else:
            filepath = logs_dir / "failure" / filename
            print(f"📥 Saving failure log for build {build_info['build_number']}...")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(console_content)
        
        print(f"✅ Saved log: {filepath}")
        return [str(filepath)]
    
    def _determine_build_status(self, console_content):
        """Determine if a build was successful or failed based on console content"""
        # Look for success indicators
        success_indicators = [
            'Finished: SUCCESS',
            'SUCCESS',
            'Build completed successfully',
            'Pipeline completed successfully'
        ]
        
        # Look for failure indicators
        failure_indicators = [
            'Finished: FAILURE',
            'FAILURE',
            'Build failed',
            'Pipeline failed',
            'ERROR:',
            'Exception:',
            'Failed to'
        ]
        
        content_lower = console_content.lower()
        
        # Check for success indicators
        for indicator in success_indicators:
            if indicator.lower() in content_lower:
                return True
        
        # Check for failure indicators
        for indicator in failure_indicators:
            if indicator.lower() in content_lower:
                return False
        
        # Default to failure if we can't determine
        return False

    def process_jenkins_url(self, jenkins_url):
        """Process Jenkins URL and return saved log paths"""
        print(f"🔗 Processing Jenkins URL: {jenkins_url}")
        
        # Check if this is a specific build URL
        if '/console' in jenkins_url:
            print("🎯 Detected specific build URL - processing single build")
            return self.process_specific_build_url(jenkins_url)
        
        # Original logic for job URLs
        print("📋 Detected job URL - fetching latest builds")
        
        # Get latest builds from Jenkins
        failure_build, success_build = self.get_latest_builds(jenkins_url)
        
        if not failure_build and not success_build:
            print("❌ No builds found or could not fetch build details")
            print("💡 Check Jenkins credentials or network connectivity")
            
            # Only fallback to existing logs if we can't fetch from Jenkins
            logs_dir = Path("jenkins_api/logs")
            if logs_dir.exists():
                failure_logs = list(logs_dir.glob("failure/*.txt"))
                success_logs = list(logs_dir.glob("success/*.txt"))
                
                if failure_logs or success_logs:
                    print(f"📁 Falling back to existing logs: {len(failure_logs)} failure, {len(success_logs)} success")
                    return [str(log) for log in failure_logs + success_logs]
            
            return []
        
        # Save logs from Jenkins
        saved_logs = self.save_build_logs(failure_build, success_build)
        
        return saved_logs

def parse_jenkins_console(log_text):
    """Parse Jenkins console output for key information"""
    data = {}

    build_num_match = re.search(r'build #(\d+)', log_text)
    if build_num_match:
        data['build_number'] = int(build_num_match.group(1))

    user_match = re.search(r'Started by user (.+)', log_text)
    if user_match:
        data['started_by'] = user_match.group(1)

    status_match = re.search(r'Finished: (\w+)', log_text)
    if status_match:
        data['status'] = status_match.group(1)

    pod_name_match = re.search(r'name:\s*"([^"]+)"', log_text)
    if pod_name_match:
        data['pod_name'] = pod_name_match.group(1)

    env_vars = re.findall(r'- name: "([^"]+)"\s+value: "([^"]+)"', log_text)
    data['env_vars'] = {name: val for name, val in env_vars}

    package_install_count = len(re.findall(r'Unpacking ', log_text))
    data['packages_installed'] = package_install_count

    return data

def validate_url(url):
    """Validate Jenkins URL format"""
    return url.startswith("http") and "jenkins" in url

if __name__ == "__main__":
    url = input("🔗 Enter Jenkins job URL: ").strip()
    if not validate_url(url):
        print("❌ Invalid URL. Must be a Jenkins job URL.")
    else:
        username = input("👤 Enter Jenkins username (or press Enter to skip): ").strip()
        api_token = input("🔑 Enter Jenkins API token (or press Enter to skip): ").strip()

        try:
            fetcher = JenkinsFetcher(username or None, api_token or None)
            saved_logs = fetcher.process_jenkins_url(url)
            
            if saved_logs:
                print(f"\n✅ Successfully saved {len(saved_logs)} log files")
                for log in saved_logs:
                    print(f"📄 {log}")
            else:
                print("❌ No logs were saved")
                
        except Exception as e:
            print(f"❌ Error: {e}")
