#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python3 pipeline.py
read -p "Press Enter to close..."
