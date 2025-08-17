#!/usr/bin/env python3
"""
MongoDB-specific analyzer for Jenkins build failures
Handles MongoDB connection issues and provides detailed solutions
"""

import re
from typing import Dict, List, Any

class MongoDBAnalyzer:
    """Specialized analyzer for MongoDB-related build failures"""
    
    def __init__(self):
        self.mongodb_error_patterns = [
            r'MongoServerSelectionError.*',
            r'MongoNetworkError.*',
            r'getaddrinfo ENOTFOUND.*',
            r'Connection refused.*',
            r'No primary available.*',
            r'Server selection timeout.*',
            r'Authentication failed.*',
            r'Network is unreachable.*'
        ]
    
    def analyze_mongodb_issue(self, log_content: str) -> Dict[str, Any]:
        """Analyze MongoDB-specific issues in build logs"""
        
        # Extract MongoDB-related errors
        mongodb_errors = []
        for pattern in self.mongodb_error_patterns:
            matches = re.findall(pattern, log_content, re.IGNORECASE)
            mongodb_errors.extend(matches)
        
        if not mongodb_errors:
            return {"is_mongodb_issue": False}
        
        # Analyze the specific MongoDB error
        analysis = self._analyze_specific_error(mongodb_errors, log_content)
        
        return {
            "is_mongodb_issue": True,
            "errors_found": mongodb_errors,
            "analysis": analysis
        }
    
    def _analyze_specific_error(self, errors: List[str], log_content: str) -> str:
        """Analyze specific MongoDB errors and provide solutions"""
        
        analysis = "## 🍃 MongoDB Connection Issue Analysis\n\n"
        
        # Check for DNS resolution issues
        if any("getaddrinfo ENOTFOUND" in error for error in errors):
            analysis += "**Root Cause**: DNS Resolution Failure\n"
            analysis += "- The application cannot resolve the MongoDB service hostname\n"
            analysis += "- This is typically a Kubernetes service discovery issue\n\n"
            
            analysis += "**Detailed Analysis**:\n"
            analysis += "1. **Service Discovery Issue**: The MongoDB service is not reachable via DNS\n"
            analysis += "2. **Network Policy**: There might be network policies blocking access\n"
            analysis += "3. **Service Configuration**: The MongoDB service might not be properly configured\n"
            analysis += "4. **Namespace Issues**: The service might be in a different namespace\n\n"
            
            analysis += "**Immediate Fix Steps**:\n"
            analysis += "```bash\n"
            analysis += "# 1. Check if MongoDB service exists\n"
            analysis += "kubectl get svc -n mongodb mongodb-central-stg-headless\n\n"
            analysis += "# 2. Check service endpoints\n"
            analysis += "kubectl get endpoints -n mongodb mongodb-central-stg-headless\n\n"
            analysis += "# 3. Test DNS resolution from a pod\n"
            analysis += "kubectl run test-dns --image=busybox --rm -it --restart=Never -- nslookup mongodb-central-stg-headless.mongodb.svc.cluster.local\n\n"
            analysis += "# 4. Check if MongoDB pods are running\n"
            analysis += "kubectl get pods -n mongodb -l app=mongodb\n\n"
            analysis += "# 5. Check network policies\n"
            analysis += "kubectl get networkpolicies -n mongodb\n"
            analysis += "```\n\n"
            
        # Check for authentication issues
        elif any("Authentication failed" in error for error in errors):
            analysis += "**Root Cause**: MongoDB Authentication Failure\n"
            analysis += "- The application cannot authenticate with MongoDB\n"
            analysis += "- This is typically a credentials or connection string issue\n\n"
            
            analysis += "**Fix Steps**:\n"
            analysis += "1. **Check Connection String**: Verify MongoDB connection string format\n"
            analysis += "2. **Verify Credentials**: Check username/password in environment variables\n"
            analysis += "3. **Check MongoDB Users**: Verify the user exists in MongoDB\n"
            analysis += "4. **Check Authentication Database**: Ensure correct auth database\n\n"
            
        # Check for connection timeout issues
        elif any("Server selection timeout" in error for error in errors):
            analysis += "**Root Cause**: MongoDB Connection Timeout\n"
            analysis += "- The application cannot establish connection to MongoDB within timeout\n"
            analysis += "- This could be due to network issues or MongoDB being overloaded\n\n"
            
            analysis += "**Fix Steps**:\n"
            analysis += "1. **Check MongoDB Health**: Verify MongoDB pods are healthy\n"
            analysis += "2. **Increase Timeout**: Adjust connection timeout settings\n"
            analysis += "3. **Check Network**: Verify network connectivity between pods\n"
            analysis += "4. **Check Resource Usage**: Ensure MongoDB has sufficient resources\n\n"
            
        # Check for network unreachable issues
        elif any("Network is unreachable" in error for error in errors):
            analysis += "**Root Cause**: Network Connectivity Issue\n"
            analysis += "- The application cannot reach the MongoDB network\n"
            analysis += "- This is typically a Kubernetes networking issue\n\n"
            
            analysis += "**Fix Steps**:\n"
            analysis += "1. **Check Pod Network**: Verify pod can reach other services\n"
            analysis += "2. **Check Service Mesh**: If using Istio/Linkerd, check policies\n"
            analysis += "3. **Check Network Policies**: Verify no blocking policies\n"
            analysis += "4. **Check DNS**: Verify DNS resolution works\n\n"
            
        else:
            analysis += "**Root Cause**: General MongoDB Connection Issue\n"
            analysis += "- The application cannot connect to MongoDB\n"
            analysis += "- This could be due to various network or configuration issues\n\n"
        
        # Add common troubleshooting steps
        analysis += "**Common Troubleshooting Steps**:\n"
        analysis += "```bash\n"
        analysis += "# 1. Check MongoDB service status\n"
        analysis += "kubectl get svc -n mongodb\n\n"
        analysis += "# 2. Check MongoDB pods\n"
        analysis += "kubectl get pods -n mongodb\n\n"
        analysis += "# 3. Check MongoDB logs\n"
        analysis += "kubectl logs -n mongodb <mongodb-pod-name>\n\n"
        analysis += "# 4. Test connectivity from application pod\n"
        analysis += "kubectl exec -it <app-pod-name> -- nc -zv mongodb-central-stg-headless.mongodb.svc.cluster.local 27017\n\n"
        analysis += "# 5. Check if MongoDB is accessible\n"
        analysis += "kubectl exec -it <app-pod-name> -- telnet mongodb-central-stg-headless.mongodb.svc.cluster.local 27017\n"
        analysis += "```\n\n"
        
        # Add prevention measures
        analysis += "**Prevention Measures**:\n"
        analysis += "1. **Health Checks**: Implement proper health checks for MongoDB\n"
        analysis += "2. **Connection Pooling**: Use connection pooling to handle connection issues\n"
        analysis += "3. **Retry Logic**: Implement retry logic with exponential backoff\n"
        analysis += "4. **Monitoring**: Set up monitoring for MongoDB connectivity\n"
        analysis += "5. **Documentation**: Document MongoDB connection requirements\n\n"
        
        analysis += "**Priority**: High\n"
        analysis += "**Estimated Time**: 30-60 minutes\n"
        analysis += "**Impact**: Critical - Application cannot function without database\n\n"
        
        analysis += "**Next Steps**:\n"
        analysis += "1. Immediately check MongoDB service status\n"
        analysis += "2. Verify network connectivity between application and MongoDB\n"
        analysis += "3. Check MongoDB pod logs for any errors\n"
        analysis += "4. Test connectivity from application pod\n"
        analysis += "5. Update connection string if needed\n"
        
        return analysis
    
    def get_mongodb_connection_test_commands(self) -> List[str]:
        """Get commands to test MongoDB connectivity"""
        return [
            "kubectl get svc -n mongodb",
            "kubectl get pods -n mongodb",
            "kubectl get endpoints -n mongodb mongodb-central-stg-headless",
            "kubectl exec -it <app-pod> -- nslookup mongodb-central-stg-headless.mongodb.svc.cluster.local",
            "kubectl exec -it <app-pod> -- nc -zv mongodb-central-stg-headless.mongodb.svc.cluster.local 27017",
            "kubectl logs -n mongodb <mongodb-pod-name>",
            "kubectl get networkpolicies -n mongodb",
            "kubectl describe svc mongodb-central-stg-headless -n mongodb"
        ] 