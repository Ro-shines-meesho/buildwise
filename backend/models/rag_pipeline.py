import os
from typing import List, Dict, Any
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain.chains import RetrievalQA
from langchain_openai import AzureChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.schema import Document
import json
import re

# Import MongoDB analyzer
from .mongodb_analyzer import MongoDBAnalyzer

class JenkinsAnalyzer:
    def __init__(self):
        # Use local embeddings to avoid API key issues
        self.embeddings = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")
        self.mongodb_analyzer = MongoDBAnalyzer()
        self.llm = None
        try:
            # Try Azure OpenAI first
            azure_api_key = os.getenv("AZURE_OPENAI_API_KEY")
            azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
            azure_deployment = os.getenv("AZURE_OPENAI_API_DEPLOYMENT_NAME")
            azure_version = os.getenv("AZURE_OPENAI_API_VERSION")
            
            if azure_api_key and azure_endpoint and azure_deployment:
                self.llm = AzureChatOpenAI(
                    model="gpt-4o",
                    temperature=0.1,
                    max_tokens=4096,
                    max_retries=2,
                    top_p=1,
                    api_key=azure_api_key,
                    azure_endpoint=azure_endpoint,
                    azure_deployment=azure_deployment,
                    api_version=azure_version,
                )
                print("✅ Azure OpenAI configured successfully")
            else:
                # Fallback to regular OpenAI
                openai_api_key = os.getenv("OPENAI_API_KEY")
                if openai_api_key:
                    from langchain_openai import ChatOpenAI
                    self.llm = ChatOpenAI(
                        temperature=0.1,
                        model="gpt-4",
                        openai_api_key=openai_api_key
                    )
                    print("✅ OpenAI configured successfully")
                else:
                    print("⚠️ No OpenAI API keys found, using local analysis only")
                    self.llm = None
        except Exception as e:
            print(f"⚠️ OpenAI configuration failed: {e}")
            self.llm = None
        
    def get_rag_chain(self, vectorstore_path: str) -> RetrievalQA:
        """Get RAG chain for vector store"""
        try:
            # Load vector store with dangerous deserialization enabled for local files
            vectorstore = FAISS.load_local(
                vectorstore_path, 
                self.embeddings,
                allow_dangerous_deserialization=True  # Enable for local trusted files
            )
            
            # Create custom prompt template
            prompt_template = """Use the following pieces of context to answer the question at the end. 
            If you don't know the answer, just say that you don't know, don't try to make up an answer.
            
            Context: {context}
            
            Question: {question}
            
            Answer:"""
            
            prompt = PromptTemplate(
                template=prompt_template,
                input_variables=["context", "question"]
            )
            
            # Create RAG chain
            qa_chain = RetrievalQA.from_chain_type(
                llm=self.llm,
                chain_type="stuff",
                retriever=vectorstore.as_retriever(search_kwargs={"k": 5}),
                chain_type_kwargs={"prompt": prompt}
            )
            
            return qa_chain
            
        except Exception as e:
            print(f"Error creating RAG chain: {e}")
            return None

    def analyze_failure(self, failure_log_path: str, success_log_path: str = None) -> Dict[str, Any]:
        """Analyze Jenkins build failure with comprehensive analysis using repository context"""
        
        # Load failure log
        with open(failure_log_path, 'r') as f:
            failure_content = f.read()
        
        # Load success log for comparison if available
        success_content = ""
        if success_log_path and os.path.exists(success_log_path):
            with open(success_log_path, 'r') as f:
                success_content = f.read()
        
        # Extract repository URLs
        failure_repos = self._extract_repos_from_log(failure_log_path)
        success_repos = self._extract_repos_from_log(success_log_path) if success_log_path else []
        
        # Check for MongoDB-specific issues first
        mongodb_analysis = self.mongodb_analyzer.analyze_mongodb_issue(failure_content)
        if mongodb_analysis.get("is_mongodb_issue", False):
            # Add build-specific information to MongoDB analysis
            build_info = self._extract_build_info(failure_log_path, failure_content)
            enhanced_analysis = mongodb_analysis["analysis"]
            enhanced_analysis += f"\n\n**Build Information**:\n"
            enhanced_analysis += f"- Build File: {os.path.basename(failure_log_path)}\n"
            enhanced_analysis += f"- Build Number: {build_info.get('build_number', 'Unknown')}\n"
            enhanced_analysis += f"- Build Time: {build_info.get('build_time', 'Unknown')}\n"
            enhanced_analysis += f"- Repositories: {', '.join(failure_repos)}\n"
            
            return {
                "analysis": enhanced_analysis,
                "failure_repos": failure_repos,
                "success_repos": success_repos,
                "failure_log_path": failure_log_path,
                "success_log_path": success_log_path,
                "analysis_type": "mongodb_specialized",
                "build_info": build_info
            }
        
        # If OpenAI is not available, use local analysis
        if not self.llm:
            print("⚠️ Using local analysis (no LLM available)")
            return self._local_analysis(failure_content, success_content, failure_repos, success_repos)
        
        # Create analysis prompt with repository context
        build_info = self._extract_build_info(failure_log_path, failure_content)
        
        # Get repository context from vector stores
        repo_context = self._get_repository_context(failure_repos, failure_content)
        
        analysis_prompt = f"""
        Analyze this Jenkins build failure and provide a comprehensive solution using the repository context.
        
        BUILD INFORMATION:
        - Build File: {os.path.basename(failure_log_path)}
        - Build Number: {build_info.get('build_number', 'Unknown')}
        - Build Time: {build_info.get('build_time', 'Unknown')}
        
        REPOSITORIES INVOLVED:
        Failure repos: {failure_repos}
        Success repos: {success_repos}
        
        FAILURE LOG (first 2000 chars):
        {failure_content[:2000]}...
        
        SUCCESS LOG (for comparison, first 1000 chars):
        {success_content[:1000] if success_content else "No success log available"}...
        
        REPOSITORY CONTEXT:
        {repo_context}
        
        Please provide a comprehensive analysis using the repository context:
        1. **Root Cause Analysis**: What caused the build to fail? Use repository context to understand the codebase.
        2. **Error Details**: Specific error messages and their meaning in the context of the codebase.
        3. **Fix Instructions**: Step-by-step solution based on the repository structure and code.
        4. **Code Changes**: Specific code modifications needed, referencing actual files and functions.
        5. **Configuration Changes**: Any configuration or environment changes needed.
        6. **Prevention**: How to prevent this in future builds based on the codebase patterns.
        7. **Priority**: High/Medium/Low priority for fixing.
        8. **Estimated Time**: How long the fix will take.
        9. **Build-Specific Notes**: Any notes specific to this build and codebase.
        
        Use the repository context to provide specific, actionable solutions that are relevant to this codebase.
        """
        
        try:
            print("🤖 Using Azure OpenAI with repository context for enhanced analysis...")
            response = self.llm.invoke(analysis_prompt)
            return {
                "analysis": response.content,
                "failure_repos": failure_repos,
                "success_repos": success_repos,
                "failure_log_path": failure_log_path,
                "success_log_path": success_log_path,
                "analysis_type": "azure_openai_with_context",
                "build_info": build_info,
                "repository_context_used": True
            }
        except Exception as e:
            print(f"⚠️ OpenAI analysis failed, falling back to local analysis: {e}")
            return self._local_analysis(failure_content, success_content, failure_repos, success_repos)

    def _get_repository_context(self, repos: List[str], failure_content: str) -> str:
        """Get relevant context from repository vector stores"""
        context_parts = []
        
        # Get vector store directory
        vectorstore_dir = "vectorstore"
        
        for repo_url in repos:
            try:
                # Extract repo name from URL
                repo_name = repo_url.rstrip('.git').split('/')[-1]
                vectorstore_path = os.path.join(vectorstore_dir, f"{repo_name}_vectorstore")
                
                if os.path.exists(vectorstore_path):
                    print(f"🔍 Querying vector store for {repo_name}...")
                    
                    # Create RAG chain for this repository
                    rag_chain = self.get_rag_chain(vectorstore_path)
                    if rag_chain:
                        # Query with failure content to get relevant context
                        query = f"Find relevant code and configuration related to: {failure_content[:500]}"
                        try:
                            result = rag_chain.run(query)
                            if result and len(result) > 50:  # Only add if we got meaningful results
                                context_parts.append(f"=== {repo_name} Repository Context ===\n{result}\n")
                        except Exception as e:
                            print(f"⚠️ Error querying {repo_name} vector store: {e}")
                else:
                    print(f"⚠️ Vector store not found for {repo_name}: {vectorstore_path}")
                    
            except Exception as e:
                print(f"⚠️ Error processing repository {repo_url}: {e}")
        
        if context_parts:
            return "\n".join(context_parts)
        else:
            return "No repository context available - vector stores may not be created or accessible."

    def _local_analysis(self, failure_content: str, success_content: str, failure_repos: List[str], success_repos: List[str]) -> Dict[str, Any]:
        """Perform local analysis without OpenAI API"""
        
        # Extract key error patterns
        error_patterns = [
            r'ERROR.*',
            r'Exception.*',
            r'Failed.*',
            r'Error.*',
            r'AuthenticationError.*',
            r'401.*',
            r'403.*',
            r'500.*',
            r'Build.*failed.*',
            r'Step.*failed.*',
            r'MongoDB.*',
            r'MongoServerSelectionError.*',
            r'MongoNetworkError.*',
            r'getaddrinfo ENOTFOUND.*',
            r'Docker.*Error.*',
            r'ECR.*Error.*'
        ]
        
        errors_found = []
        for pattern in error_patterns:
            matches = re.findall(pattern, failure_content, re.IGNORECASE)
            errors_found.extend(matches)
        
        # Analyze common patterns
        analysis = "## 🔍 Local Analysis Results\n\n"
        
        if "MongoServerSelectionError" in failure_content or "MongoNetworkError" in failure_content or "getaddrinfo ENOTFOUND" in failure_content:
            # Use specialized MongoDB analysis
            mongodb_analysis = self.mongodb_analyzer.analyze_mongodb_issue(failure_content)
            if mongodb_analysis.get("is_mongodb_issue", False):
                return {
                    "analysis": mongodb_analysis["analysis"],
                    "failure_repos": failure_repos,
                    "success_repos": success_repos,
                    "analysis_type": "mongodb_specialized"
                }
            
            analysis += "**Root Cause**: MongoDB Connection Issue\n"
            analysis += "- The build failed due to MongoDB connection problems\n"
            analysis += "- Error: `getaddrinfo ENOTFOUND mongodb-central-stg-headless.mongodb.svc.cluster.local`\n"
            analysis += "- This indicates DNS resolution failure for MongoDB service\n\n"
            analysis += "**Fix Instructions**:\n"
            analysis += "1. Check if MongoDB service is running in the cluster\n"
            analysis += "2. Verify DNS resolution for MongoDB service\n"
            analysis += "3. Check network connectivity between pods\n"
            analysis += "4. Verify MongoDB service configuration\n"
            analysis += "5. Check if the MongoDB service name is correct\n\n"
            analysis += "**Specific MongoDB Fix**:\n"
            analysis += "1. Check if MongoDB service exists: `kubectl get svc -n mongodb`\n"
            analysis += "2. Verify DNS resolution: `nslookup mongodb-central-stg-headless.mongodb.svc.cluster.local`\n"
            analysis += "3. Check pod connectivity: `kubectl exec -it <pod-name> -- nslookup mongodb-central-stg-headless.mongodb.svc.cluster.local`\n"
            analysis += "4. Verify MongoDB service configuration in Kubernetes\n"
            analysis += "5. Check if MongoDB pods are running: `kubectl get pods -n mongodb`\n"
            analysis += "6. Check MongoDB service endpoints: `kubectl get endpoints -n mongodb mongodb-central-stg-headless`\n"
            analysis += "7. Verify network policies: `kubectl get networkpolicies -n mongodb`\n"
            analysis += "8. Check if MongoDB is accessible from the build pod\n\n"
        elif "AuthenticationError" in failure_content or "401" in failure_content:
            analysis += "**Root Cause**: Authentication/API Key Error\n"
            analysis += "- The build failed due to an authentication error\n"
            analysis += "- This is likely related to API keys or credentials\n"
            analysis += "- Check environment variables and API key configuration\n\n"
        elif "npm" in failure_content.lower() or "node" in failure_content.lower():
            analysis += "**Root Cause**: Node.js/npm Dependency Issue\n"
            analysis += "- The build failed during npm install or node execution\n"
            analysis += "- Check package.json and node_modules\n"
            analysis += "- Verify all dependencies are properly specified\n\n"
        elif "docker" in failure_content.lower() or "ecr" in failure_content.lower():
            analysis += "**Root Cause**: Docker/Container Issue\n"
            analysis += "- The build failed during Docker operations\n"
            analysis += "- Check Dockerfile and container configuration\n"
            analysis += "- Verify Docker daemon is running\n"
            analysis += "- Check ECR access and permissions\n\n"
        elif "git" in failure_content.lower():
            analysis += "**Root Cause**: Git Repository Issue\n"
            analysis += "- The build failed during Git operations\n"
            analysis += "- Check repository access and credentials\n"
            analysis += "- Verify branch names and commit hashes\n\n"
        else:
            analysis += "**Root Cause**: General Build Failure\n"
            analysis += "- The build failed for an unknown reason\n"
            analysis += "- Check the error logs for specific details\n\n"
        
        # Add repository information
        analysis += f"**Repositories Involved**:\n"
        analysis += f"- Failure repos: {', '.join(failure_repos)}\n"
        analysis += f"- Success repos: {', '.join(success_repos)}\n\n"
        
        # Add error details
        if errors_found:
            analysis += "**Error Details**:\n"
            for error in errors_found[:5]:  # Show first 5 errors
                analysis += f"- {error}\n"
            analysis += "\n"
        
        # Add fix suggestions
        analysis += "**General Fix Suggestions**:\n"
        analysis += "1. Check environment variables and API keys\n"
        analysis += "2. Verify repository access and permissions\n"
        analysis += "3. Review build configuration files\n"
        analysis += "4. Check for dependency conflicts\n"
        analysis += "5. Verify network connectivity\n\n"
        
        analysis += "**Priority**: High\n"
        analysis += "**Estimated Time**: 30-60 minutes\n\n"
        
        analysis += "*Note: This is a local analysis. For more detailed AI-powered analysis, please set up Azure OpenAI API key.*"
        
        return {
            "analysis": analysis,
            "failure_repos": failure_repos,
            "success_repos": success_repos,
            "analysis_type": "local"
        }

    def _extract_repos_from_log(self, log_path: str) -> List[str]:
        """Extract repository URLs from log file"""
        repos = []
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # First check if first line contains comma-separated repos (like frontend logs)
                lines = content.split('\n')
                if lines and ("github.com" in lines[0] or "http" in lines[0]):
                    first_line_repos = [repo.strip() for repo in lines[0].split(",") if repo.strip()]
                    repos.extend(first_line_repos)
                
                # Also extract repositories mentioned in the log content
                import re
                
                # Pattern for GitHub URLs
                github_pattern = r'https://github\.com/[^\s]+\.git'
                github_matches = re.findall(github_pattern, content)
                repos.extend(github_matches)
                
                # Pattern for general repository URLs
                repo_pattern = r'https://[^\s]+\.git'
                repo_matches = re.findall(repo_pattern, content)
                repos.extend(repo_matches)
                
                # Pattern for "Cloning repository" mentions
                cloning_pattern = r'Cloning repository (https://[^\s]+)'
                cloning_matches = re.findall(cloning_pattern, content)
                repos.extend(cloning_matches)
                
                # Remove duplicates and clean up
                repos = list(set(repos))
                repos = [repo.strip() for repo in repos if repo.strip()]
                
                print(f"🔗 Extracted repositories from {log_path}: {repos}")
                
        except Exception as e:
            print(f"Error extracting repos from {log_path}: {e}")
        
        return repos

    def _extract_build_info(self, log_path: str, log_content: str) -> Dict[str, Any]:
        """Extract build-specific information from log"""
        import re
        from datetime import datetime
        
        build_info = {}
        
        # Extract build number from filename
        filename = os.path.basename(log_path)
        build_match = re.search(r'build_(\d+)', filename)
        if build_match:
            build_info['build_number'] = build_match.group(1)
        
        # Extract timestamp from filename
        time_match = re.search(r'(\d{8}_\d{6})', filename)
        if time_match:
            try:
                timestamp = time_match.group(1)
                dt = datetime.strptime(timestamp, '%Y%m%d_%H%M%S')
                build_info['build_time'] = dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                build_info['build_time'] = 'Unknown'
        
        # Extract started by user
        user_match = re.search(r'Started by user (.+)', log_content)
        if user_match:
            build_info['started_by'] = user_match.group(1)
        
        # Extract build status
        status_match = re.search(r'Finished: (\w+)', log_content)
        if status_match:
            build_info['status'] = status_match.group(1)
        
        return build_info

    def get_vectorstore_analysis(self, vectorstore_path: str, query: str) -> str:
        """Get analysis using vector store"""
        qa_chain = self.get_rag_chain(vectorstore_path)
        if qa_chain:
            try:
                result = qa_chain.run(query)
                return result
            except Exception as e:
                return f"Analysis failed: {str(e)}"
        return "Unable to create RAG chain"

def get_llm_analysis(vectorstore_path: str = None, query: str = None) -> str:
    """Legacy function for backward compatibility"""
    analyzer = JenkinsAnalyzer()
    if vectorstore_path and query:
        return analyzer.get_vectorstore_analysis(vectorstore_path, query)
    else:
        return "No vectorstore path or query provided"
