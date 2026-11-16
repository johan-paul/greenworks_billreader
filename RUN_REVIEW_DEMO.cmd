@echo off
cd /d "%~dp0"
python -m scripts.prepare_review
if errorlevel 1 (
 echo Demo preparation failed. See the error above and docs/REVIEW_GUIDE.md.
 pause
 exit /b 1
)
start "" "output\review\review-demo.html"
