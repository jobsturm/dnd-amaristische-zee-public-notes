#!/usr/bin/env python3
import os
import sys
import re
import json
import argparse
import shutil
import requests
from rapidfuzz import process, fuzz
from weasyprint import HTML
import mistune
from urllib.parse import unquote
from pathlib import Path
from PIL import Image
import io

# === API CONFIGURATION ===
API_URL = "http://127.0.0.1:12315/api"
API_TOKEN = "printing-authing"  # Your API token
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_TOKEN}"
}

# === CONFIGURATION ===
OUTPUT_DIR = "html-output"  # Directory for HTML output
ASSETS_DIR = os.path.join(OUTPUT_DIR, "assets")  # Directory for assets
CSS_FILE = "styles.css"  # CSS file name

# Logseq assets configuration - set your primary assets location here
LOGSEQ_ASSETS_PATH = "/Users/job/Library/CloudStorage/SynologyDrive-on-demand/database/assets"

# === API HELPER FUNCTIONS ===
def api_call(method, args):
    """Make an API call to Logseq."""
    payload = {"method": method, "args": args}
    try:
        print(f"Making API call: {method} with args: {args}")
        response = requests.post(API_URL, headers=HEADERS, json=payload)
        if response.ok:
            result = response.json()
            print(f"API call successful: {method}")
            return result
        else:
            print(f"API call error for {method}: {response.text}")
            return None
    except Exception as e:
        print(f"Exception during API call: {e}")
        return None

def get_page_property(page, property_name):
    """Get a specific property from a page."""
    if not page or "properties" not in page:
        return None
    props = page.get("properties", {})
    value = props.get(property_name)
    return value

def is_page_public(page):
    """Check if a page is marked as public."""
    public_prop = get_page_property(page, "public")
    is_public = public_prop in [True, "true", "children"]
    return is_public

def is_public_children(page):
    """Check if a page has public children."""
    public_prop = get_page_property(page, "public")
    return public_prop == "children"

def get_nested_pages(page_name):
    """Get all pages that are nested under the given page name."""
    nested_pages = []
    pages = api_call("logseq.Editor.getAllPages", [])
    if not pages:
        return []
    
    base_path = page_name.strip() + "/"
    for page in pages:
        name = (page.get("name") or page.get("title", "")).strip()
        if name.startswith(base_path):
            nested_pages.append(page)
    return nested_pages

def get_public_pages():
    """Get all pages that are marked as public or have public children."""
    pages = api_call("logseq.Editor.getAllPages", [])
    if not pages:
        return []
    
    public_pages = {}
    processed_pages = set()  # To avoid processing the same page multiple times

    def add_page(page):
        if not page:
            return
        uuid = page.get("uuid")
        title = (page.get("name") or page.get("title", "")).strip()
        if uuid and title and title not in processed_pages:
            processed_pages.add(title)
            public_pages[title] = {
                "uuid": uuid,
                "title": title,
                "has_public_children": is_public_children(page)
            }

    # First pass: collect directly public pages and pages with public children
    for page in pages:
        title = (page.get("name") or page.get("title", "")).strip()
        if is_page_public(page):
            add_page(page)
            
            # If this page has public children, add all nested pages
            if is_public_children(page):
                nested_pages = get_nested_pages(title)
                for nested_page in nested_pages:
                    add_page(nested_page)

    return public_pages

def sanitize_filename(title):
    """Convert a page title to a safe filename."""
    # Replace slashes with dashes
    safe_name = title.replace('/', '-')
    # Replace any other unsafe characters
    safe_name = re.sub(r'[^a-zA-Z0-9\-_]', '_', safe_name)
    return safe_name.lower()

def setup_output_directory():
    """Setup the output directory and copy necessary assets."""
    # Clean up and create output directory
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)
    os.makedirs(ASSETS_DIR)
    
    # Copy CSS file to output directory
    shutil.copy2(CSS_FILE, os.path.join(OUTPUT_DIR, CSS_FILE))

def get_first_sentence(page_name):
    """Get the first meaningful sentence from a page's content."""
    pages = api_call("logseq.Editor.getAllPages", [])
    page = next((p for p in pages if (p.get("name") or p.get("title", "")).strip() == page_name), None)
    
    if not page:
        return ""
    
    # Get the page's blocks
    blocks = api_call("logseq.Editor.getPageBlocksTree", [page["uuid"]])
    if not blocks:
        return ""

    # Get content from the first block with actual content
    def find_first_content(block):
        if isinstance(block, list):
            for b in block:
                content = find_first_content(b)
                if content:
                    return content
            return ""
        
        content = block.get("content", "").strip()
        # Skip if it's just a property or empty
        if not content or "::" in content or content.startswith("public::"):
            if block.get("children"):
                return find_first_content(block["children"])
            return ""
        return content

    content = find_first_content(blocks)
    
    # Clean the content
    content = clean_logseq_metadata(content)
    content = re.sub(r'^[-*] ', '', content)  # Remove list markers
    content = re.sub(r'\[\[([^\]]+)\]\]', r'\1', content)  # Remove link markers
    
    # Get first sentence
    sentences = re.split(r'(?<=[.!?])\s+', content)
    if sentences:
        first_sentence = sentences[0].strip()
        # If sentence is too long, truncate it
        if len(first_sentence) > 150:
            first_sentence = first_sentence[:147] + "..."
        return first_sentence
    return ""

def generate_index_page(public_pages):
    """Generate an index page with links to all public pages."""
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>De Amaristische Zee</title>
    <link rel="stylesheet" href="{CSS_FILE}">
</head>
<body>
    <main>
        <article>
            <h1>De Amaristische Zee</h1>
            <div class="page-list">"""
    
    # Sort pages by title
    sorted_pages = sorted(public_pages.items(), key=lambda x: x[0])
    
    for title, page_info in sorted_pages:
        safe_name = sanitize_filename(title)
        # Get the last part of the path for display
        display_title = title.split('/')[-1].replace('_', ' ').title()
        
        # Get first sentence
        first_sentence = get_first_sentence(title)
        
        html += f"""
                <a href="{safe_name}.html" class="page-list-item">
                    <div class="page-list-content">
                        <h3>{display_title}</h3>"""
        
        # If it's a nested page, show the parent path
        if '/' in title:
            parent_path = '/'.join(title.split('/')[:-1])
            html += f"""
                        <p class="page-path">{parent_path}</p>"""
        
        if first_sentence:
            html += f"""
                        <p class="page-excerpt">{first_sentence}</p>"""
            
        html += """
                    </div>
                </a>"""
    
    html += """
            </div>
        </article>
    </main>
</body>
</html>"""
    
    # Write to file
    filepath = os.path.join(OUTPUT_DIR, "index.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

def get_page_children(title, public_pages):
    """Get all child pages for a given page title."""
    children = []
    base = title + "/"
    for page_title in public_pages.keys():
        if page_title.startswith(base):
            children.append(page_title)
    return sorted(children)

def generate_hierarchy_section(title, public_pages):
    """Generate hierarchy section if the page has children."""
    children = get_page_children(title, public_pages)
    if not children:
        return ""
    
    html = '<section class="hierarchy-section">\n'
    html += '<h2>Related Pages</h2>\n'
    html += '<ul class="hierarchy-list">\n'
    
    for child in children:
        safe_name = sanitize_filename(child)
        display_name = child.split('/')[-1].replace('_', ' ').title()
        html += f'<li><a href="{safe_name}.html">{display_name}</a></li>\n'
    
    html += '</ul>\n</section>\n'
    return html

def export_page_to_html(page_name, public_pages):
    """Export a page to HTML using Logseq's API."""
    # First, get the page object
    pages = api_call("logseq.Editor.getAllPages", [])
    page = next((p for p in pages if (p.get("name") or p.get("title", "")).strip() == page_name), None)
    
    if not page:
        print(f"Page not found: {page_name}")
        return None
    
    # Get the page content
    content = api_call("logseq.Editor.getPage", [page["name"]])
    if not content:
        print(f"Failed to get content for page: {page_name}")
        return None
    
    # Get the page's blocks
    blocks = api_call("logseq.Editor.getPageBlocksTree", [page["uuid"]])
    if not blocks:
        print(f"Failed to get blocks for page: {page_name}")
        return None

    # Convert blocks to HTML
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{page_name}</title>
    <link rel="stylesheet" href="{CSS_FILE}">
</head>
<body>
    <main>
        <article>
            <a href="index.html" class="back-to-index">Back to Index</a>
            <h1>{page_name}</h1>
"""

    def process_block(block):
        if not block:
            return ""
        
        content = block.get("content", "").strip()
        if not content:
            return ""
        
        # Clean metadata first
        content = clean_logseq_metadata(content)
        
        # Process task markers
        content = re.sub(r'^DONE ', '☑️ ', content)
        content = re.sub(r'^DOING ', '⏳ ', content)
        content = re.sub(r'^TODO ', '☐ ', content)
        content = re.sub(r'^NOW ', '▶️ ', content)
        content = re.sub(r'^LATER ', '⏰ ', content)
        
        # Split content into lines and process each line
        lines = content.split('\n')
        processed_lines = []
        
        for line in lines:
            line = line.strip()
            if line:
                # Process Logseq's markdown-style formatting
                line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
                line = re.sub(r'\*(.+?)\*', r'<em>\1</em>', line)
                line = re.sub(r'~~(.+?)~~', r'<del>\1</del>', line)
                line = re.sub(r'==(.+?)==', r'<mark>\1</mark>', line)
                
                # Process links using resolve_links_for_html
                line = resolve_links_for_html(line, public_pages)
                
                # Convert URLs to links
                line = re.sub(r'(https?://\S+)', r'<a href="\1">\1</a>', line)
                
                # Process code blocks
                line = re.sub(r'`([^`]+)`', r'<code>\1</code>', line)
                
                # Process images
                line = process_image_links(line)
                
                # Wrap line in paragraph
                processed_lines.append(f"<p>{line}</p>")
        
        html = f"<div class='block'>{chr(10).join(processed_lines)}"
        
        # Process children
        children = block.get("children", [])
        if children:
            html += "<ul>"
            for child in children:
                html += f"<li>{process_block(child)}</li>"
            html += "</ul>"
        
        html += "</div>"
        return html

    # Process all blocks
    if isinstance(blocks, list):
        for block in blocks:
            html_content += process_block(block)
    else:
        html_content += process_block(blocks)

    # Add hierarchy section if this page has children
    hierarchy_html = generate_hierarchy_section(page_name, public_pages)
    if hierarchy_html:
        html_content += hierarchy_html

    html_content += """
        </article>
    </main>
</body>
</html>"""

    return html_content

def optimize_image(src_path, max_width=2000):
    """
    Optimize an image for web use:
    - Remove metadata
    - Resize if too large
    - Optimize quality
    - Convert to appropriate format
    """
    try:
        with Image.open(src_path) as img:
            # Convert to RGB if RGBA (this removes transparency but is better for web)
            if img.mode == 'RGBA':
                bg = Image.new('RGB', img.size, 'WHITE')
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Resize if width is larger than max_width while maintaining aspect ratio
            if img.width > max_width:
                ratio = max_width / img.width
                new_height = int(img.height * ratio)
                img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

            # Create a BytesIO object to hold the optimized image
            output = io.BytesIO()
            
            # Save with optimization
            img.save(output, 
                    format='JPEG', 
                    quality=85,  # Good balance between quality and file size
                    optimize=True,
                    progressive=True)  # Progressive loading
            
            return output.getvalue()
    except Exception as e:
        print(f"Error optimizing image {src_path}: {e}")
        return None

def copy_asset(src_path):
    """
    Copy an asset file to the assets directory, optimizing images if possible.
    Returns the new relative path.
    """
    if not os.path.exists(src_path):
        return None
    
    # Create a safe filename
    filename = os.path.basename(src_path)
    safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    
    # Get file extension
    ext = os.path.splitext(filename)[1].lower()
    
    # Handle images
    if ext in ['.jpg', '.jpeg', '.png', '.webp']:
        try:
            # Optimize the image
            optimized_data = optimize_image(src_path)
            if optimized_data:
                # Always save as .jpg for consistency
                safe_filename = os.path.splitext(safe_filename)[0] + '.jpg'
                dest_path = os.path.join(ASSETS_DIR, safe_filename)
                
                # Write the optimized image
                with open(dest_path, 'wb') as f:
                    f.write(optimized_data)
                
                print(f"Optimized image: {filename}")
                return f"assets/{safe_filename}"
        except Exception as e:
            print(f"Failed to optimize image {filename}: {e}")
            # Fall back to regular copy if optimization fails
    
    # For non-image files or if optimization failed, just copy
    dest_path = os.path.join(ASSETS_DIR, safe_filename)
    shutil.copy2(src_path, dest_path)
    
    # Return the relative path from the HTML file to the asset
    return f"assets/{safe_filename}"

def find_asset(filename):
    """
    Try to find an asset in various possible locations.
    """
    # Common Logseq asset locations, starting with the configured path
    possible_locations = [
        LOGSEQ_ASSETS_PATH,  # Primary configured location
        "assets",  # Current directory assets
        "~/Documents/logseq/assets",  # Default Logseq location
        os.path.expanduser("~/logseq/assets"),  # Alternative Logseq location
        os.path.expanduser("~/Library/CloudStorage/SynologyDrive-on-demand/database/assets"),  # Synology location
    ]
    
    # Clean up filename - try different variations
    variations = [
        filename,  # Original filename
        filename.replace('_-_', '-'),  # Replace _-_ with -
        filename.replace('-', '_'),  # Replace - with _
        filename.replace('_', '-'),  # Replace _ with -
    ]
    
    # Remove duplicates while preserving order
    variations = list(dict.fromkeys(variations))
    
    print(f"Looking for asset: {filename}")
    print(f"Trying variations: {variations}")
    
    # Try each location with each variation
    for location in possible_locations:
        location = os.path.expanduser(location)
        if os.path.exists(location):
            print(f"Checking location: {location}")
            
            # Try exact matches first
            for variant in variations:
                full_path = os.path.join(location, variant)
                if os.path.exists(full_path):
                    print(f"Found exact match: {full_path}")
                    return full_path
            
            # If no exact match, try partial matching
            basename_no_ext = os.path.splitext(os.path.basename(filename))[0]
            base_variations = [
                basename_no_ext,
                basename_no_ext.replace('_-_', '-'),
                basename_no_ext.replace('-', '_'),
                basename_no_ext.replace('_', '-')
            ]
            base_variations = list(dict.fromkeys(base_variations))
            
            for file in os.listdir(location):
                file_lower = file.lower()
                for base_variant in base_variations:
                    if base_variant.lower() in file_lower:
                        full_path = os.path.join(location, file)
                        print(f"Found partial match: {full_path}")
                        return full_path
    
    print(f"Asset not found: {filename}")
    return None

def process_image_links(content):
    """
    Process image links in the content and copy images to assets directory.
    """
    def repl(match):
        img_path = unquote(match.group(1))
        
        # Remove any ../ from the path and strip any leading assets/ or img/
        img_path = re.sub(r'\.\./+', '', img_path)
        img_path = re.sub(r'^(assets/|img/)', '', img_path)
        
        # Try to find the asset
        asset_path = find_asset(img_path)
        if asset_path:
            new_path = copy_asset(asset_path)
            if new_path:
                return f'<img src="{new_path}" alt=""/>'
        
        return f'[Image not found: {img_path}]'
    
    # Match both Markdown and HTML image patterns
    md_pattern = r'!\[(?:[^\]]*)\]\(([^)]+)\)'
    html_pattern = r'<img[^>]+src="([^"]+)"[^>]*>'
    
    content = re.sub(md_pattern, repl, content)
    content = re.sub(html_pattern, repl, content)
    return content

def get_page_hierarchy(pages):
    """
    Organize pages into a hierarchy based on their paths.
    Returns a tuple of (base_pages, child_pages) where:
    - base_pages are top-level pages or first parts of paths
    - child_pages is a dict mapping parent titles to their children
    """
    base_pages = {}
    child_pages = {}
    
    # First pass: collect all base categories and their direct pages
    for title, page_info in pages.items():
        parts = title.split('/')
        base_category = parts[0]
        
        # If this is a base page or we haven't found a page for this category yet
        if len(parts) == 1:
            base_pages[base_category] = {
                'title': title,
                'info': page_info,
                'is_base': True
            }
        elif base_category not in base_pages:
            base_pages[base_category] = {
                'title': title,
                'info': page_info,
                'is_base': False
            }
    
    # Then collect children under their respective parents
    for title, page_info in pages.items():
        parts = title.split('/')
        if len(parts) > 1:
            parent = parts[0]
            if parent not in child_pages:
                child_pages[parent] = []
            # Don't include the base page in its own children list
            if title != base_pages[parent]['title']:
                child_pages[parent].append({
                    'title': title,
                    'info': page_info,
                    'depth': len(parts) - 1
                })
    
    return base_pages, child_pages

def preprocess_markdown(content):
    """
    Preprocess Logseq markdown content before passing it to the markdown parser.
    """
    if not content:
        return ""
    
    # Handle Logseq-specific syntax
    content = re.sub(r'#\[\[([^\]]+)\]\]', r'[\1](\1)', content)  # Convert #[[tag]] to [tag](tag)
    content = re.sub(r'\(\(([a-f0-9-]+)\)\)', '', content)  # Remove block references
    
    # Fix Logseq's task markers
    content = re.sub(r'^DONE ', '- [x] ', content, flags=re.MULTILINE)
    content = re.sub(r'^DOING ', '- [ ] ', content, flags=re.MULTILINE)
    content = re.sub(r'^TODO ', '- [ ] ', content, flags=re.MULTILINE)
    content = re.sub(r'^NOW ', '- [ ] ', content, flags=re.MULTILINE)
    content = re.sub(r'^LATER ', '- [ ] ', content, flags=re.MULTILINE)
    
    # Fix Logseq's property syntax
    content = format_properties(content)
    
    # Clean up any remaining Logseq metadata
    content = clean_logseq_metadata(content)
    
    return content

def block_tree_to_html(block, title, public_pages, indent=0):
    """Convert a block tree to HTML."""
    if not block:
        return ""

    content = block.get("content", "").strip()
    children = block.get("children", [])
    
    # Skip empty blocks
    if not content and not children:
        return ""
    
    # Process the block's content
    content = preprocess_markdown(content)
    content = resolve_links_for_html(content, public_pages)
    content = process_image_links(content)
    
    # Create markdown renderer with custom options
    markdown = mistune.create_markdown(
        escape=False,  # Don't escape HTML
        plugins=['strikethrough', 'footnotes', 'table'],
        hard_wrap=True  # Convert newlines to <br>
    )
    
    # Convert markdown to HTML
    html_content = markdown(content) if content else ""
    
    # Process children
    if children:
        child_html = "\n".join(block_tree_to_html(child, title, public_pages, indent + 1) 
                              for child in children if child)
        if child_html:
            html_content += f"\n<ul>\n{child_html}\n</ul>"
    
    # Wrap in list item if it's not the root block
    if indent > 0:
        return f"<li>{html_content}</li>"
    return html_content

def generate_html_file(title, content, public_pages):
    """Generate an HTML file for a page."""
    # Create markdown renderer with custom options
    markdown = mistune.create_markdown(
        escape=False,  # Don't escape HTML
        plugins=['strikethrough', 'footnotes', 'table'],
        hard_wrap=True  # Convert newlines to <br>
    )
    
    # Process content
    content = preprocess_markdown(content)
    content = resolve_links_for_html(content, public_pages)
    content = process_image_links(content)
    
    # Convert to HTML
    html_content = markdown(content)
    
    # Generate hierarchy section
    hierarchy_html = generate_hierarchy_section(title, public_pages)
    
    # Create the complete HTML document
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="stylesheet" href="{CSS_FILE}">
</head>
<body>
    <nav class="sidebar" aria-label="Navigation">
        <div class="sidebar-content">
            <button class="close-sidebar" aria-label="Close navigation">×</button>
            {hierarchy_html}
        </div>
    </nav>
    <main>
        <button class="open-sidebar" aria-label="Open navigation">☰</button>
        <article>
            <h1>{title}</h1>
            {html_content}
        </article>
    </main>
</body>
</html>"""
    
    # Write to file
    filename = f"{sanitize_filename(title)}.html"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    
    return filename

def resolve_links_for_html(content, public_pages):
    """Process links in content to point to the correct HTML files."""
    def repl(match):
        page_name = match.group(1)
        if page_name in public_pages:
            safe_name = sanitize_filename(page_name)
            return f'<a href="{safe_name}.html">{page_name}</a>'
        # For non-public pages, use a span with a special class
        return f'<span class="non-public-link">{page_name}</span>'
    
    link_pattern = r'\[\[([^\]]+)\]\]'
    return re.sub(link_pattern, repl, content)

def resolve_embeds_in_block(block, processed, public_pages):
    """
    Recursively resolve embed markers in the block's content and its children.
    Only includes content from public pages.
    """
    if processed is None:
        processed = set()
    
    block_uuid = block.get("uuid")
    if block_uuid:
        if block_uuid in processed:
            return block
        processed.add(block_uuid)
    
    content = block.get("content", "")
    block["content"] = resolve_embeds(content, processed, public_pages)
    block["content"] = resolve_links_for_html(block["content"], public_pages)
    block["content"] = process_image_links(block["content"])
    
    if "children" in block:
        for child in block["children"]:
            resolve_embeds_in_block(child, processed, public_pages)
    
    return block

def clean_logseq_metadata(content):
    """Remove Logseq-specific metadata from content."""
    # Remove block IDs
    content = re.sub(r'\s*id::\s*[a-f0-9-]+', '', content)
    # Remove UUIDs
    content = re.sub(r'\s*[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', '', content)
    # Remove public property
    content = re.sub(r'\s*public::\s*(true|children)', '', content)
    return content

def format_properties(content):
    """
    Format Logseq properties as a semantic HTML description list within a section.
    Properties are identified by the :: pattern, excluding certain system properties.
    """
    # Find all property definitions (key:: value)
    property_pattern = r'^([a-zA-Z][a-zA-Z0-9-_]*)::(.+?)$'
    properties = []
    
    # Process each line to find properties
    lines = []
    in_properties = False
    property_lines = []
    
    for line in content.split('\n'):
        match = re.match(property_pattern, line.strip())
        if match:
            key, value = match.groups()
            # Skip system properties
            if key not in ['id', 'public']:
                property_lines.append((key.strip(), value.strip()))
            continue
        
        # If we have properties and hit a non-property line, format them
        if property_lines and not match:
            if property_lines:
                section_id = f'props-{hash("".join([k+v for k,v in property_lines])) & 0xFFFFFFFF}'
                dl_html = f'<section id="{section_id}" class="page-properties" aria-label="Page properties">\n'
                dl_html += '<h2 class="visually-hidden">Page Properties</h2>\n'  # Hidden but semantic heading
                dl_html += '<dl role="list">\n'
                for prop_key, prop_value in property_lines:
                    # Create unique IDs for key-value pairs for better accessibility
                    key_id = f'prop-{hash(prop_key) & 0xFFFFFFFF}'
                    dl_html += f'    <div class="property-pair" role="listitem">\n'
                    dl_html += f'    <dt id="{key_id}">{prop_key}</dt>\n'
                    dl_html += f'    <dd aria-labelledby="{key_id}">{prop_value}</dd>\n'
                    dl_html += f'    </div>\n'
                dl_html += '</dl>\n'
                dl_html += '</section>\n'
                lines.append(dl_html)
                property_lines = []
        
        if line.strip():
            # Wrap non-empty lines in paragraph tags if they don't start with HTML tags
            if not line.strip().startswith('<'):
                line = f'<p>{line}</p>'
            lines.append(line)
    
    # Handle any remaining properties at the end
    if property_lines:
        section_id = f'props-{hash("".join([k+v for k,v in property_lines])) & 0xFFFFFFFF}'
        dl_html = f'<section id="{section_id}" class="page-properties" aria-label="Page properties">\n'
        dl_html += '<h2 class="visually-hidden">Page Properties</h2>\n'  # Hidden but semantic heading
        dl_html += '<dl role="list">\n'
        for prop_key, prop_value in property_lines:
            key_id = f'prop-{hash(prop_key) & 0xFFFFFFFF}'
            dl_html += f'    <div class="property-pair" role="listitem">\n'
            dl_html += f'    <dt id="{key_id}">{prop_key}</dt>\n'
            dl_html += f'    <dd aria-labelledby="{key_id}">{prop_value}</dd>\n'
            dl_html += f'    </div>\n'
        dl_html += '</dl>\n'
        dl_html += '</section>\n'
        lines.append(dl_html)
    
    return '\n'.join(lines)

# === MAIN FUNCTION ===
def main():
    # Setup output directory
    setup_output_directory()

    # Get all public pages
    print("Fetching public pages...")
    public_pages = get_public_pages()
    if not public_pages:
        print("No public pages found.")
        sys.exit(1)

    print(f"\nFound {len(public_pages)} public pages:")
    for title in public_pages:
        print(f"- {title}")

    # Generate index page
    print("\nGenerating index page...")
    generate_index_page(public_pages)
    print("Generated: index.html")

    # Process each public page
    for title, page_info in public_pages.items():
        print(f"\nProcessing page: {title}")
        
        # Export the page using Logseq's API
        html_content = export_page_to_html(title, public_pages)
        if not html_content:
            print(f"Failed to export page: {title}")
            continue
        
        # Write to file
        filename = f"{sanitize_filename(title)}.html"
        filepath = os.path.join(OUTPUT_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"Generated: {filename}")

    print(f"\nAll HTML files have been generated in the '{OUTPUT_DIR}' directory.")

if __name__ == "__main__":
    main()
