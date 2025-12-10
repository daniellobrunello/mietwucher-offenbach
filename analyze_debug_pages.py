#!/usr/bin/env python3
"""
Analyze debug HTML pages to verify price and size extraction.

This script helps identify extraction issues by:
1. Listing all saved HTML pages
2. Searching for price and size patterns
3. Comparing with what crawlers extract
"""

import os
import re
import sys
from pathlib import Path
from bs4 import BeautifulSoup


def analyze_kleinanzeigen_page(html_file):
    """Analyze a Kleinanzeigen HTML page for price and size."""
    with open(html_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    soup = BeautifulSoup(content, 'lxml')
    results = {}
    
    # Price extraction
    price_elem = soup.find(class_="aditem-main--middle--price-shipping--price")
    if price_elem:
        results['price'] = price_elem.text.strip()
    else:
        results['price'] = "NOT FOUND"
    
    # Size extraction
    tags = soup.find_all(class_="simpletag")
    if tags:
        size_tags = [tag for tag in tags if "m²" in tag.text]
        results['size'] = size_tags[0].text.strip() if size_tags else "NOT FOUND"
    else:
        results['size'] = "NOT FOUND"
    
    return results


def analyze_immobilienscout_page(html_file):
    """Analyze an Immobilienscout page for price and size."""
    with open(html_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    soup = BeautifulSoup(content, 'lxml')
    results = {}
    
    # Check for JavaScript data
    if "window.IS24.resultList" in content:
        results['type'] = "JavaScript data available"
        # Extract some sample data
        match = re.search(r'"price":\s*{[^}]*"value":\s*(\d+)', content)
        if match:
            results['price'] = f"{match.group(1)} EUR (from JS)"
        else:
            results['price'] = "NOT FOUND IN JS"
        
        match = re.search(r'"livingSpace":\s*([0-9.]+)', content)
        if match:
            results['size'] = f"{match.group(1)} m² (from JS)"
        else:
            results['size'] = "NOT FOUND IN JS"
    else:
        results['type'] = "HTML parsing"
        # Try HTML extraction
        attrs = soup.find_all('dd')
        if len(attrs) >= 2:
            results['price'] = attrs[0].text.strip()
            results['size'] = attrs[1].text.strip()
        else:
            results['price'] = "NOT FOUND"
            results['size'] = "NOT FOUND"
    
    return results


def analyze_immowelt_page(html_file):
    """Analyze an Immowelt page for price and size."""
    with open(html_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    soup = BeautifulSoup(content, 'lxml')
    results = {}
    
    # Price extraction
    price_elem = soup.find("div", attrs={"data-testid": "cardmfe-price-testid"})
    if price_elem:
        results['price'] = price_elem.text.strip()
    else:
        results['price'] = "NOT FOUND"
    
    # Size extraction
    descriptions = soup.find("div", attrs={"data-testid": "cardmfe-keyfacts-testid"})
    if descriptions:
        size_elems = [elem for elem in descriptions.children if "m²" in elem.text]
        results['size'] = size_elems[0].text.strip() if size_elems else "NOT FOUND"
    else:
        results['size'] = "NOT FOUND"
    
    return results


def main():
    """Main function to analyze debug pages."""
    debug_dir = Path("debug_pages")
    
    if not debug_dir.exists():
        print("Error: debug_pages directory not found.")
        print("Make sure you've enabled debug mode and run the crawler first.")
        sys.exit(1)
    
    analyzers = {
        "Kleinanzeigen": analyze_kleinanzeigen_page,
        "Immobilienscout": analyze_immobilienscout_page,
        "Immowelt": analyze_immowelt_page,
    }
    
    print("=" * 80)
    print("FLATHUNTER DEBUG PAGE ANALYZER")
    print("=" * 80)
    print()
    
    for crawler_name, analyzer_func in analyzers.items():
        crawler_dir = debug_dir / crawler_name
        if not crawler_dir.exists():
            print(f"[{crawler_name}] No debug pages found")
            print()
            continue
        
        html_files = list(crawler_dir.glob("*.html"))
        if not html_files:
            print(f"[{crawler_name}] Directory exists but no HTML files found")
            print()
            continue
        
        print(f"[{crawler_name}] Found {len(html_files)} HTML page(s)")
        print("-" * 80)
        
        for html_file in html_files[:5]:  # Analyze first 5 files
            print(f"\nFile: {html_file.name}")
            try:
                results = analyzer_func(html_file)
                for key, value in results.items():
                    print(f"  {key}: {value}")
            except Exception as e:
                print(f"  Error analyzing: {str(e)}")
        
        if len(html_files) > 5:
            print(f"\n  ... and {len(html_files) - 5} more file(s)")
        
        print()
    
    print("=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()

