#!/bin/bash

# Exit on error
set -e

# Print steps as they're executed
set -x

# Check if venv exists, if not create it
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Generate the HTML files
python3 dnd-logseq-to-html.py

# Deactivate venv
deactivate

# Check if there are changes in html-output
if [[ -n $(git status -s html-output/) ]]
then
    # Add all changes in html-output
    git add html-output/

    # Commit with timestamp
    git commit -m "Update site content: $(date '+%Y-%m-%d %H:%M:%S')"

    # Push to GitHub (which triggers the GitHub Action)
    git push
    
    echo "✅ Changes published successfully!"
else
    echo "ℹ️ No changes to publish"
fi 