@echo off
cd /d "%~dp0"
streamlit run app.py --server.maxUploadSize=2048
