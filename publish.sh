#!/bin/bash

# Print steps as they're executed
set -x

# Generate the HTML files
python3 dnd-logseq-to-html.py

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