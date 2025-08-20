#!/usr/bin/env python3
"""
Jenkins Build Analysis System - Main Application
A comprehensive system for analyzing Jenkins build failures with AI-powered insights.
"""

import os
import sys
import uvicorn
from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

# Import API routes
from backend.api.routes import router as api_router

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv('sample.env')
except ImportError:
    pass

# Initialize FastAPI app
app = FastAPI(
    title="Jenkins Build Analysis System",
    description="AI-powered Jenkins build failure analysis with repository context",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware for integration with Ringmaster
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Templates
templates = Jinja2Templates(directory="frontend/templates")

# Include API routes
app.include_router(api_router)

# Legacy endpoints for backward compatibility
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page with analysis form"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/health")
async def legacy_health_check():
    """Legacy health check endpoint for backward compatibility"""
    return {"status": "healthy", "message": "Jenkins Analysis System is running"}

@app.post("/analyze")
async def legacy_analyze_jenkins_url(jenkins_url: str = Form(...)):
    """Legacy analyze endpoint for backward compatibility"""
    try:
        # Redirect to new API endpoint
        from backend.api.routes import get_jenkins_fetcher, get_jenkins_analyzer
        from backend.core.jenkins_fetch_and_vectorize import process_log_and_repos
        
        fetcher = get_jenkins_fetcher()
        analyzer = get_jenkins_analyzer()
        
        # Process the request
        saved_logs = fetcher.process_jenkins_url(jenkins_url)
        
        if not saved_logs:
            return {"error": "No logs were fetched from Jenkins"}
        
        # Process logs and repositories
        failure_logs = []
        success_logs = []
        
        for log_path in saved_logs:
            if "failure" in log_path:
                failure_logs.append(log_path)
            elif "success" in log_path:
                success_logs.append(log_path)
        
        # Analyze failures
        analysis_results = []
        
        for failure_log in failure_logs:
            success_log = None
            if success_logs:
                success_log = success_logs[0]
            
            try:
                process_log_and_repos(failure_log, "failure")
            except Exception as e:
                print(f"Warning: Error processing {failure_log}: {e}")
            
            analysis = analyzer.analyze_failure(failure_log, success_log)
            analysis_results.append(analysis)
        
        return {
            "jenkins_url": jenkins_url,
            "saved_logs": saved_logs,
            "failure_logs": failure_logs,
            "success_logs": success_logs,
            "analysis_results": analysis_results,
            "analysis_type": "multiple_builds" if len(failure_logs) > 1 else "single_build"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze-log")
async def legacy_analyze_log_file(log_file: UploadFile = File(...)):
    """Legacy log analysis endpoint for backward compatibility"""
    try:
        # Save uploaded file temporarily
        temp_path = f"temp_upload_{log_file.filename}"
        with open(temp_path, "wb") as f:
            content = await log_file.read()
            f.write(content)
        
        try:
            from backend.api.routes import get_jenkins_analyzer
            from backend.core.jenkins_fetch_and_vectorize import process_log_and_repos
            
            analyzer = get_jenkins_analyzer()
            
            # Process the log
            tag = "failure" if "failure" in temp_path else "success"
            try:
                process_log_and_repos(temp_path, tag)
            except Exception as e:
                print(f"Warning: Error processing log: {e}")
            
            # Analyze the failure
            analysis = analyzer.analyze_failure(temp_path)
            
            return {
                "log_path": temp_path,
                "analysis": analysis
            }
            
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    print("🚀 Starting Jenkins Analysis System...")
    print("📱 Open your browser and go to: http://localhost:8005")
    print("📚 API Documentation: http://localhost:8005/docs")
    print("🔗 New API Endpoints: http://localhost:8005/api/v1/")
    uvicorn.run(app, host="0.0.0.0", port=8005) 