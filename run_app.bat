@echo off
cd /d "%~dp0"
set STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
streamlit run app.py --server.maxUploadSize=2048 --server.headless=true --server.showEmailPrompt=false --browser.gatherUsageStats=false
