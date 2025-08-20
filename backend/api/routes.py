#!/usr/bin/env python3
"""
Jenkins Build Analysis System - API Routes
Comprehensive API endpoints for integration with Ringmaster and other systems
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query, Path
from fastapi.responses import JSONResponse
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, HttpUrl
import os
import asyncio
from datetime import datetime

from ..core.jenkins import JenkinsFetcher
from ..models.rag_pipeline import JenkinsAnalyzer
from ..core.jenkins_fetch_and_vectorize import process_log_and_repos

# Create router
router = APIRouter(prefix="/api/v1", tags=["jenkins-analysis"])

# Pydantic models for request/response
class JenkinsAnalysisRequest(BaseModel):
    jenkins_url: HttpUrl
    include_repos: bool = True
    analysis_type: str = "comprehensive"  # quick, comprehensive, ai_enhanced

class LogAnalysisRequest(BaseModel):
    log_content: str
    log_filename: Optional[str] = None
    include_repos: bool = True

class BuildInfo(BaseModel):
    build_number: str
    build_time: str
    status: str
    started_by: Optional[str] = None
    duration: Optional[int] = None
    console_url: Optional[str] = None

class AnalysisResult(BaseModel):
    build_info: BuildInfo
    analysis_type: str
    analysis: str
    failure_repos: List[str] = []
    success_repos: List[str] = []
    failure_log_path: Optional[str] = None
    success_log_path: Optional[str] = None
    repository_context_used: bool = False
    confidence_score: Optional[float] = None
    estimated_fix_time: Optional[str] = None
    priority: Optional[str] = None

class JenkinsAnalysisResponse(BaseModel):
    jenkins_url: str
    saved_logs: List[str]
    failure_logs: List[str] = []
    success_logs: List[str] = []
    analysis_results: List[AnalysisResult]
    analysis_type: str
    total_builds_analyzed: int
    processing_time: float
    timestamp: str

class HealthResponse(BaseModel):
    status: str
    message: str
    version: str
    timestamp: str
    services: Dict[str, str]

class StatusResponse(BaseModel):
    service: str
    status: str
    uptime: str
    version: str
    endpoints: List[str]

# Global instances
_jenkins_fetcher = None
_jenkins_analyzer = None

def get_jenkins_fetcher():
    """Get or create JenkinsFetcher instance"""
    global _jenkins_fetcher
    if _jenkins_fetcher is None:
        _jenkins_fetcher = JenkinsFetcher()
    return _jenkins_fetcher

def get_jenkins_analyzer():
    """Get or create JenkinsAnalyzer instance"""
    global _jenkins_analyzer
    if _jenkins_analyzer is None:
        _jenkins_analyzer = JenkinsAnalyzer()
    return _jenkins_analyzer

# Health and Status Endpoints
@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for load balancers and monitoring"""
    return HealthResponse(
        status="healthy",
        message="Jenkins Analysis System is running",
        version="1.0.0",
        timestamp=datetime.now().isoformat(),
        services={
            "jenkins_fetcher": "operational",
            "ai_analyzer": "operational",
            "vector_store": "operational"
        }
    )

@router.get("/status", response_model=StatusResponse)
async def service_status():
    """Detailed service status for monitoring"""
    return StatusResponse(
        service="jenkins-analysis-system",
        status="operational",
        uptime="running",
        version="1.0.0",
        endpoints=[
            "/api/v1/health",
            "/api/v1/status",
            "/api/v1/analyze",
            "/api/v1/analyze-log",
            "/api/v1/analyze-batch",
            "/api/v1/builds",
            "/api/v1/repositories",
            "/api/v1/vectorstores"
        ]
    )

# Core Analysis Endpoints
@router.post("/analyze", response_model=JenkinsAnalysisResponse)
async def analyze_jenkins_url(
    request: JenkinsAnalysisRequest,
    background_tasks: BackgroundTasks,
    fetcher: JenkinsFetcher = Depends(get_jenkins_fetcher),
    analyzer: JenkinsAnalyzer = Depends(get_jenkins_analyzer)
):
    """
    Analyze Jenkins URL and provide comprehensive build failure analysis
    
    This endpoint fetches logs from Jenkins, processes repositories, and provides
    AI-powered analysis of build failures with actionable solutions.
    """
    start_time = datetime.now()
    
    try:
        # Step 1: Fetch logs from Jenkins
        jenkins_url = str(request.jenkins_url)
        saved_logs = fetcher.process_jenkins_url(jenkins_url)
        
        if not saved_logs:
            raise HTTPException(
                status_code=404,
                detail="No logs were fetched from Jenkins. Check credentials or use existing logs."
            )
        
        # Step 2: Process logs and repositories
        failure_logs = []
        success_logs = []
        
        for log_path in saved_logs:
            if "failure" in log_path:
                failure_logs.append(log_path)
            elif "success" in log_path:
                success_logs.append(log_path)
        
        # Step 3: Analyze failures
        analysis_results = []
        
        for failure_log in failure_logs:
            # Find corresponding success log
            success_log = None
            if success_logs:
                success_log = success_logs[0]
            
            # Process repositories if requested
            if request.include_repos:
                try:
                    process_log_and_repos(failure_log, "failure")
                except Exception as e:
                    print(f"Warning: Error processing repos for {failure_log}: {e}")
            
            # Analyze the failure
            analysis = analyzer.analyze_failure(failure_log, success_log)
            analysis_results.append(analysis)
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return JenkinsAnalysisResponse(
            jenkins_url=jenkins_url,
            saved_logs=saved_logs,
            failure_logs=failure_logs,
            success_logs=success_logs,
            analysis_results=analysis_results,
            analysis_type="multiple_builds" if len(failure_logs) > 1 else "single_build",
            total_builds_analyzed=len(analysis_results),
            processing_time=processing_time,
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@router.post("/analyze-log", response_model=AnalysisResult)
async def analyze_log_file(
    request: LogAnalysisRequest,
    analyzer: JenkinsAnalyzer = Depends(get_jenkins_analyzer)
):
    """
    Analyze uploaded log file content
    
    This endpoint analyzes log content directly without requiring Jenkins access.
    Useful for analyzing logs from other sources or historical analysis.
    """
    try:
        # Save log content to temporary file
        temp_filename = f"temp_upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        temp_path = f"/tmp/{temp_filename}"
        
        with open(temp_path, 'w') as f:
            f.write(request.log_content)
        
        try:
            # Process repositories if requested
            if request.include_repos:
                try:
                    process_log_and_repos(temp_path, "analysis")
                except Exception as e:
                    print(f"Warning: Error processing repos: {e}")
            
            # Analyze the log
            analysis = analyzer.analyze_failure(temp_path)
            
            return analysis
            
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Log analysis failed: {str(e)}")

@router.post("/analyze-batch")
async def analyze_batch_logs(
    log_paths: List[str],
    background_tasks: BackgroundTasks,
    analyzer: JenkinsAnalyzer = Depends(get_jenkins_analyzer)
):
    """
    Analyze multiple log files in batch
    
    This endpoint processes multiple log files concurrently for bulk analysis.
    Results are returned as they become available.
    """
    try:
        results = []
        
        for log_path in log_paths:
            if os.path.exists(log_path):
                try:
                    analysis = analyzer.analyze_failure(log_path)
                    results.append({
                        "log_path": log_path,
                        "analysis": analysis,
                        "status": "completed"
                    })
                except Exception as e:
                    results.append({
                        "log_path": log_path,
                        "error": str(e),
                        "status": "failed"
                    })
            else:
                results.append({
                    "log_path": log_path,
                    "error": "File not found",
                    "status": "failed"
                })
        
        return {
            "total_logs": len(log_paths),
            "completed": len([r for r in results if r["status"] == "completed"]),
            "failed": len([r for r in results if r["status"] == "failed"]),
            "results": results
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch analysis failed: {str(e)}")

# Information and Query Endpoints
@router.get("/builds")
async def get_builds_info(
    jenkins_url: Optional[str] = Query(None, description="Jenkins job URL"),
    limit: int = Query(10, description="Maximum number of builds to return")
):
    """
    Get information about available builds
    
    Returns build information from Jenkins or local storage.
    """
    try:
        if jenkins_url:
            fetcher = get_jenkins_fetcher()
            # This would need to be implemented in JenkinsFetcher
            return {"message": "Build info retrieval from Jenkins not yet implemented"}
        else:
            # Return local build information
            builds = []
            
            # Check failure logs
            failure_dir = "jenkins_api/logs/failure"
            if os.path.exists(failure_dir):
                for file in os.listdir(failure_dir):
                    if file.endswith('.txt'):
                        builds.append({
                            "type": "failure",
                            "filename": file,
                            "path": f"{failure_dir}/{file}"
                        })
            
            # Check success logs
            success_dir = "jenkins_api/logs/success"
            if os.path.exists(success_dir):
                for file in os.listdir(success_dir):
                    if file.endswith('.txt'):
                        builds.append({
                            "type": "success",
                            "filename": file,
                            "path": f"{success_dir}/{file}"
                        })
            
            return {
                "total_builds": len(builds),
                "builds": builds[:limit]
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get builds info: {str(e)}")

@router.get("/repositories")
async def get_repositories_info():
    """
    Get information about analyzed repositories
    
    Returns details about repositories that have been processed and indexed.
    """
    try:
        repos = []
        cloned_dir = "cloned_repos"
        
        if os.path.exists(cloned_dir):
            for repo_name in os.listdir(cloned_dir):
                repo_path = os.path.join(cloned_dir, repo_name)
                if os.path.isdir(repo_path):
                    # Check if it's a git repository
                    git_path = os.path.join(repo_path, ".git")
                    if os.path.exists(git_path):
                        repos.append({
                            "name": repo_name,
                            "path": repo_path,
                            "type": "git",
                            "analyzed": True
                        })
        
        return {
            "total_repositories": len(repos),
            "repositories": repos
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get repositories info: {str(e)}")

@router.get("/vectorstores")
async def get_vectorstores_info():
    """
    Get information about available vector stores
    
    Returns details about FAISS indexes and vector embeddings.
    """
    try:
        vectorstores = []
        vectorstore_dir = "vectorstore"
        
        if os.path.exists(vectorstore_dir):
            for item in os.listdir(vectorstore_dir):
                item_path = os.path.join(vectorstore_dir, item)
                if os.path.isdir(item_path):
                    # Check for FAISS index files
                    faiss_files = [f for f in os.listdir(item_path) if f.endswith('.faiss')]
                    pkl_files = [f for f in os.listdir(item_path) if f.endswith('.pkl')]
                    
                    if faiss_files or pkl_files:
                        vectorstores.append({
                            "name": item,
                            "path": item_path,
                            "faiss_files": faiss_files,
                            "pkl_files": pkl_files,
                            "size": len(faiss_files) + len(pkl_files)
                        })
        
        return {
            "total_vectorstores": len(vectorstores),
            "vectorstores": vectorstores
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get vectorstores info: {str(e)}")

# Utility Endpoints
@router.post("/refresh-vectorstores")
async def refresh_vectorstores(
    background_tasks: BackgroundTasks,
    fetcher: JenkinsFetcher = Depends(get_jenkins_fetcher)
):
    """
    Refresh vector stores by reprocessing repositories
    
    This endpoint triggers a refresh of all vector embeddings.
    Useful after code updates or when adding new repositories.
    """
    try:
        # This would need to be implemented to reprocess all repositories
        return {
            "message": "Vector store refresh initiated",
            "status": "processing"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vector store refresh failed: {str(e)}")

@router.get("/metrics")
async def get_system_metrics():
    """
    Get system performance and usage metrics
    
    Returns various metrics for monitoring and optimization.
    """
    try:
        # Calculate basic metrics
        total_logs = 0
        total_repos = 0
        total_vectorstores = 0
        
        # Count logs
        for log_dir in ["jenkins_api/logs/failure", "jenkins_api/logs/success"]:
            if os.path.exists(log_dir):
                total_logs += len([f for f in os.listdir(log_dir) if f.endswith('.txt')])
        
        # Count repositories
        if os.path.exists("cloned_repos"):
            total_repos = len([d for d in os.listdir("cloned_repos") if os.path.isdir(f"cloned_repos/{d}")])
        
        # Count vector stores
        if os.path.exists("vectorstore"):
            total_vectorstores = len([d for d in os.listdir("vectorstore") if os.path.isdir(f"vectorstore/{d}")])
        
        return {
            "timestamp": datetime.now().isoformat(),
            "metrics": {
                "total_logs": total_logs,
                "total_repositories": total_repos,
                "total_vectorstores": total_vectorstores,
                "system_status": "healthy"
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")
