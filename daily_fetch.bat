@echo off
set PATH=C:\Users\pablo\.pixi\bin;%PATH%
cd /d "C:\Users\pablo\claude_projects\portfolio tracker"
pixi run python tracker.py fetch
pixi run python tracker.py dash
