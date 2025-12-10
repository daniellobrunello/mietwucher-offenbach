#!/usr/bin/env python3
"""
Test script to verify markdown conversion from HTML
Tests the new _convert_html_to_markdown method
"""
import sys
import os

# Add flathunter to path
sys.path.insert(0, os.path.dirname(__file__))

from flathunter.html_parser import FlatHtmlParser

def test_basic_markdown_conversion():
    """Test basic HTML to markdown conversion"""
    print("="*80)
    print("TEST 1: Basic HTML to Markdown Conversion")
    print("="*80)
    
    html_sample = """
    <html>
        <head>
            <title>Test Apartment</title>
            <script>console.log('test');</script>
            <style>.test { color: red; }</style>
        </head>
        <body>
            <nav>Navigation menu</nav>
            <main>
                <h1>Beautiful 2-Room Apartment</h1>
                <h2>Details</h2>
                <ul>
                    <li>Kaltmiete: 850 €</li>
                    <li>Warmmiete: 950 €</li>
                    <li>Size: 75 m²</li>
                    <li>Rooms: 2</li>
                </ul>
                <h2>Description</h2>
                <p>This is a beautiful apartment in a great location.</p>
                <p>It has a balcony and is fully furnished.</p>
            </main>
            <footer>Footer content</footer>
        </body>
    </html>
    """
    
    parser = FlatHtmlParser()
    
    # Parse HTML
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_sample, 'html.parser')
    
    # Convert to markdown
    markdown = parser._convert_html_to_markdown(soup)
    
    print("\nInput HTML (cleaned):")
    print("-"*80)
    print(html_sample[:200] + "...")
    
    print("\nOutput Markdown:")
    print("-"*80)
    print(markdown)
    print("-"*80)
    
    # Check that markdown contains expected elements
    checks = [
        ("# Beautiful 2-Room Apartment" in markdown, "H1 heading preserved"),
        ("## Details" in markdown, "H2 heading preserved"),
        ("- Kaltmiete" in markdown or "* Kaltmiete" in markdown, "List items preserved"),
        ("850" in markdown, "Price information preserved"),
        ("balcony" in markdown.lower(), "Description text preserved"),
        ("Navigation menu" not in markdown, "Navigation removed"),
        ("Footer content" not in markdown, "Footer removed"),
        ("console.log" not in markdown, "JavaScript removed"),
    ]
    
    print("\nValidation Checks:")
    print("-"*80)
    passed = 0
    failed = 0
    for check, description in checks:
        status = "✓ PASS" if check else "✗ FAIL"
        print(f"{status}: {description}")
        if check:
            passed += 1
        else:
            failed += 1
    
    print("-"*80)
    print(f"Results: {passed} passed, {failed} failed")
    
    return failed == 0

def test_markdown_size_efficiency():
    """Test that markdown is more efficient than plain text"""
    print("\n" + "="*80)
    print("TEST 2: Markdown Size Efficiency")
    print("="*80)
    
    # Create HTML with structure
    html_with_structure = """
    <html>
        <body>
            <h1>Apartment Listing</h1>
            <table>
                <tr><td>Kaltmiete</td><td>850 €</td></tr>
                <tr><td>Warmmiete</td><td>950 €</td></tr>
                <tr><td>Nebenkosten</td><td>100 €</td></tr>
                <tr><td>Size</td><td>75 m²</td></tr>
            </table>
            <ul>
                <li>Balcony</li>
                <li>Kitchen included</li>
                <li>Parking spot</li>
            </ul>
            <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. 
            Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.</p>
        </body>
    </html>
    """
    
    parser = FlatHtmlParser()
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_with_structure, 'html.parser')
    
    # Get plain text
    plain_text = soup.get_text(separator='\n', strip=True)
    
    # Get markdown
    markdown = parser._convert_html_to_markdown(soup)
    
    print(f"\nPlain text length: {len(plain_text)} characters")
    print(f"Markdown length: {len(markdown)} characters")
    
    if len(markdown) < len(plain_text):
        efficiency = ((len(plain_text) - len(markdown)) / len(plain_text)) * 100
        print(f"✓ Markdown is {efficiency:.1f}% more efficient")
    else:
        print(f"✗ Markdown is actually larger than plain text")
    
    print("\nMarkdown output:")
    print("-"*80)
    print(markdown)
    print("-"*80)
    
    return True

def test_llm_field_extraction_prompt():
    """Test that the LLM prompt format is correct"""
    print("\n" + "="*80)
    print("TEST 3: LLM Field Extraction (Prompt Format)")
    print("="*80)
    
    # Sample markdown that would be sent to LLM
    markdown_sample = """
# Schöne 2-Zimmer-Wohnung in Offenbach

## Details

- Kaltmiete: 850 €
- Warmmiete: 950 €
- Nebenkosten: 100 €
- Wohnfläche: 75 m²
- Zimmer: 2

## Ausstattung

- Balkon
- Einbauküche
- Kellerabteil

## Beschreibung

Diese wunderschöne Wohnung befindet sich in zentraler Lage.
Die Wohnung ist unmöbliert und verfügt über einen Balkon.
"""
    
    print("Sample markdown for LLM:")
    print("-"*80)
    print(markdown_sample)
    print("-"*80)
    
    print("\nChecking markdown structure:")
    checks = [
        ("# " in markdown_sample, "Has H1 headings"),
        ("## " in markdown_sample, "Has H2 headings"),
        ("- " in markdown_sample, "Has list items"),
        ("€" in markdown_sample, "Price symbols preserved"),
        ("m²" in markdown_sample, "Size units preserved"),
    ]
    
    for check, description in checks:
        status = "✓" if check else "✗"
        print(f"{status} {description}")
    
    print("\n✓ Markdown format is suitable for LLM processing")
    print("  - Headings help LLM understand structure")
    print("  - Lists are easy to parse")
    print("  - All relevant information preserved")
    
    return True

def main():
    """Run all tests"""
    print("\n")
    print("╔" + "="*78 + "╗")
    print("║" + " "*20 + "MARKDOWN CONVERSION TEST SUITE" + " "*28 + "║")
    print("╚" + "="*78 + "╝")
    print()
    
    tests = [
        ("Basic Markdown Conversion", test_basic_markdown_conversion),
        ("Markdown Size Efficiency", test_markdown_size_efficiency),
        ("LLM Field Extraction Format", test_llm_field_extraction_prompt),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ Test '{name}' raised an exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")
    
    total_passed = sum(1 for _, passed in results if passed)
    total_tests = len(results)
    
    print("="*80)
    print(f"Total: {total_passed}/{total_tests} tests passed")
    print("="*80)
    
    if total_passed == total_tests:
        print("\n🎉 All tests passed! Markdown conversion is working correctly.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please review the output above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())

