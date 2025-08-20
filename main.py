#!/usr/bin/env python3
"""
Jenkins Build Analysis System
Automatically analyzes Jenkins build failures and provides solutions
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Any
import argparse

# Add backend to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from backend.core.jenkins import JenkinsFetcher
from backend.core.jenkins_fetch_and_vectorize import process_log_and_repos
from backend.models.rag_pipeline import JenkinsAnalyzer

class JenkinsAnalysisSystem:
    def __init__(self):
        self.fetcher = JenkinsFetcher()
        self.analyzer = JenkinsAnalyzer()
        
    def process_jenkins_url(self, jenkins_url: str) -> Dict[str, Any]:
        """Process Jenkins URL and return comprehensive analysis"""
        print(f"🚀 Starting analysis for: {jenkins_url}")
        
        # Step 1: Fetch logs from Jenkins
        print("\n📥 Fetching logs from Jenkins...")
        saved_logs = self.fetcher.process_jenkins_url(jenkins_url)
        
        if not saved_logs:
            return {
                "error": "No logs were fetched from Jenkins. Please check Jenkins credentials or use existing log files.",
                "suggestion": "Try: python main.py --log /path/to/existing/log/file.txt"
            }
        
        # Step 2: Process logs and repositories
        print("\n🔧 Processing logs and repositories...")
        
        # For single build URLs, we only have one log file
        if '/console' in jenkins_url:
            # Single build analysis
            log_path = saved_logs[0]
            print(f"🎯 Analyzing single build log: {log_path}")
            
            # Process the single log file
            try:
                process_log_and_repos(log_path, "analysis")
            except Exception as e:
                print(f"⚠️ Error processing {log_path}: {e}")
            
            # Analyze the single build
            print("\n🧠 Analyzing build...")
            analysis = self.analyzer.analyze_failure(log_path)
            
            return {
                "jenkins_url": jenkins_url,
                "saved_logs": saved_logs,
                "analysis_results": [analysis],
                "analysis_type": "single_build"
            }
        else:
            # Original logic for job URLs (multiple builds)
            failure_logs = []
            success_logs = []
            
            for log_path in saved_logs:
                if "failure" in log_path:
                    failure_logs.append(log_path)
                elif "success" in log_path:
                    success_logs.append(log_path)
            
            # Process each log file
            for log_path in saved_logs:
                tag = "failure" if "failure" in log_path else "success"
                try:
                    process_log_and_repos(log_path, tag)
                except Exception as e:
                    print(f"⚠️ Error processing {log_path}: {e}")
            
            # Step 3: Analyze failures
            print("\n🧠 Analyzing failures...")
            analysis_results = []
            
            for failure_log in failure_logs:
                # Find corresponding success log
                success_log = None
                if success_logs:
                    success_log = success_logs[0]  # Use first success log for comparison
                
                analysis = self.analyzer.analyze_failure(failure_log, success_log)
                analysis_results.append(analysis)
            
            return {
                "jenkins_url": jenkins_url,
                "saved_logs": saved_logs,
                "failure_logs": failure_logs,
                "success_logs": success_logs,
                "analysis_results": analysis_results,
                "analysis_type": "multiple_builds"
            }

    def analyze_specific_log(self, log_path: str) -> Dict[str, Any]:
        """Analyze a specific log file"""
        print(f"🔍 Analyzing specific log: {log_path}")
        
        # Process log and repositories
        try:
            process_log_and_repos(log_path, "failure")
        except Exception as e:
            print(f"⚠️ Error processing log: {e}")
        
        # Analyze the failure
        analysis = self.analyzer.analyze_failure(log_path)
        
        return {
            "log_path": log_path,
            "analysis": analysis
        }

def main():
    parser = argparse.ArgumentParser(description="Jenkins Build Analysis System")
    parser.add_argument("--url", help="Jenkins job URL to analyze")
    parser.add_argument("--log", help="Specific log file to analyze")
    parser.add_argument("--interactive", action="store_true", help="Run in interactive mode")

    args = parser.parse_args()

    system = JenkinsAnalysisSystem()

    if args.url:
        print(f"🚀 Starting analysis for: {args.url}")
        result = system.process_jenkins_url(args.url)
        
        if "error" in result:
            print(f"❌ {result['error']}")
            if "suggestion" in result:
                print(f"💡 {result['suggestion']}")
        else:
            print(f"✅ Processed {len(result['saved_logs'])} log files")
            
            # Handle different analysis types
            analysis_type = result.get('analysis_type', 'unknown')
            
            if analysis_type == 'single_build':
                print(f"🎯 Single build analysis completed")
            else:
                # Multiple builds analysis
                failure_logs = result.get('failure_logs', [])
                success_logs = result.get('success_logs', [])
                print(f"📊 Found {len(failure_logs)} failure logs and {len(success_logs)} success logs")
            
            print("\n" + "="*80)
            print("📊 ANALYSIS RESULTS")
            print("="*80)
            
            for i, analysis in enumerate(result['analysis_results']):
                print(f"\n🔍 Analysis {i+1}:")
                print("-" * 40)
                
                # Show build information
                if 'build_info' in analysis:
                    build_info = analysis['build_info']
                    print(f"📋 Build Information:")
                    print(f"   - File: {os.path.basename(analysis.get('failure_log_path', 'Unknown'))}")
                    print(f"   - Number: {build_info.get('build_number', 'Unknown')}")
                    print(f"   - Time: {build_info.get('build_time', 'Unknown')}")
                    print(f"   - Started by: {build_info.get('started_by', 'Unknown')}")
                    print(f"   - Status: {build_info.get('status', 'Unknown')}")
                
                # Show analysis type
                analysis_type = analysis.get('analysis_type', 'unknown')
                print(f"🤖 Analysis Type: {analysis_type}")
                
                # Show the analysis
                if 'analysis' in analysis:
                    print(f"\n📝 Analysis:")
                    print(analysis['analysis'])
                else:
                    print("❌ No analysis available")
                
                print("\n" + "="*80)
    
    elif args.log:
        result = system.analyze_specific_log(args.log)
        
        if "error" in result:
            print(f"❌ {result['error']}")
        else:
            analysis_data = result.get('analysis', {})
            if isinstance(analysis_data, dict):
                if 'error' in analysis_data:
                    print(f"❌ {analysis_data['error']}")
                elif 'analysis' in analysis_data:
                    print("\n" + "="*80)
                    print("📊 LOG ANALYSIS")
                    print("="*80)
                    print(analysis_data['analysis'])
                else:
                    print("Analysis completed but no detailed results available")
            else:
                print("Analysis completed")
    
    elif args.interactive:
        print("🔧 Interactive Mode")
        print("Enter 'quit' to exit")
        
        while True:
            try:
                user_input = input("\n🔗 Enter Jenkins URL or log file path: ").strip()
                
                if user_input.lower() == 'quit':
                    break
                elif user_input.startswith('http'):
                    result = system.process_jenkins_url(user_input)
                    if "error" in result:
                        print(f"❌ {result['error']}")
                        if "suggestion" in result:
                            print(f"💡 {result['suggestion']}")
                    else:
                        print(f"✅ Processed {len(result['saved_logs'])} log files")
                        for i, analysis in enumerate(result['analysis_results']):
                            print(f"\n🔍 Analysis {i+1}:")
                            if 'analysis' in analysis:
                                print(analysis['analysis'])
                elif os.path.exists(user_input):
                    result = system.analyze_specific_log(user_input)
                    if "error" in result:
                        print(f"❌ {result['error']}")
                    else:
                        analysis_data = result.get('analysis', {})
                        if isinstance(analysis_data, dict) and 'analysis' in analysis_data:
                            print(analysis_data['analysis'])
                else:
                    print("❌ Invalid input. Please enter a valid URL or file path.")
                    
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
    
    else:
        # Default: analyze the specific log mentioned in the user query
        log_path = "/Users/user/Documents/AIChatBotJenkins/jenkins_api/logs/failure/dev-ops-buddy-frontend-cicd_develop_build_230_20250731_125924.txt"
        result = system.analyze_specific_log(log_path)
        
        if "error" in result:
            print(f"❌ {result['error']}")
        else:
            analysis_data = result.get('analysis', {})
            if isinstance(analysis_data, dict):
                if 'error' in analysis_data:
                    print(f"❌ {analysis_data['error']}")
                elif 'analysis' in analysis_data:
                    print("\n" + "="*80)
                    print("📊 LOG ANALYSIS")
                    print("="*80)
                    print(analysis_data['analysis'])
                else:
                    print("Analysis completed but no detailed results available")
            else:
                print("Analysis completed")

if __name__ == "__main__":
    main()