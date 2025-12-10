import re
import os
import copy
from datetime import datetime
from html import unescape as html_unescape
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
import openai
from dotenv import load_dotenv
from markdownify import markdownify as md
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import APIError, APITimeoutError, RateLimitError

import logging

# Load environment variables from .env file
load_dotenv()

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Placeholder for potential LLM integration (e.g., OpenAI, Anthropic)
# from some_llm_library import LLMClient # Comment kept for reference
# OpenAI Client Initialization handled in __init__

class FlatHtmlParser:
    """
    Parses HTML content of a flat listing to extract relevant details.
    Handles potential errors during parsing and logs them.
    """

    # Define standard fields we aim to extract
    # CRITICAL: Separate Kaltmiete (cold rent) and Warmmiete (warm rent)
    EXTRACTED_FIELDS = [
        'url', 'raw_html_hash', 'title', 'kaltmiete', 'warmmiete', 'nebenkosten', 'size_sqm', 'rooms',
        'address', 'description', 'availability', 'furnished', 'features'
    ]

    def __init__(self, openai_api_key: Optional[str] = None, llm_model: Optional[str] = None):
        """
        Initializes the parser.

        Args:
            openai_api_key: Optional OpenAI API key. If not provided, attempts
                            to read from the OPENAI_API_KEY environment variable.
                            LLM features are disabled if no key is found.
            llm_model: The OpenAI model to use for enhancements. If not provided,
                       attempts to read from OPENAI_MODEL environment variable.
                       Default: "gpt-4-turbo"
        """
        self.llm_client = None
        # Resolve model: parameter > env var > default
        self.llm_model = llm_model or os.getenv("OPENAI_MODEL", "gpt-4-turbo")
        resolved_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")

        if resolved_api_key:
            try:
                self.llm_client = openai.OpenAI(api_key=resolved_api_key)
                # Optional: Add a simple test call to verify the key
                # self.llm_client.models.list()
                logging.info(f"OpenAI client initialized successfully using model '{self.llm_model}'.")
            except Exception as e:
                logging.error(f"Failed to initialize OpenAI client: {e}", exc_info=False)
                # Continue without LLM features
        else:
            logging.warning("OpenAI API key not provided or found in environment variable 'OPENAI_API_KEY'. LLM enhancement disabled.")

    def _clean_html(self, html_content: str) -> str:
        """
        Performs basic HTML cleaning before BeautifulSoup parsing.
        Removes large binary data, scripts, and styles to reduce size.
        
        Note: Most cleaning is now handled by markdownify during conversion.
        This method focuses on removing large binary blobs that waste memory.
        
        Args:
            html_content: Raw HTML content to clean
            
        Returns:
            Cleaned HTML content
        """
        try:
            # Remove Base64 encoded data (can be megabytes of binary data)
            html_content = re.sub(r'data:[^;]+;base64,[a-zA-Z0-9+/=]+', '', html_content)
            
            # Remove srcset attributes (often contain multiple large image URLs)
            html_content = re.sub(r'srcset="[^"]*"', '', html_content)
            
            # Remove script and style tags (JavaScript and CSS)
            html_content = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL)
            html_content = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL)
            
            # Remove HTML comments
            html_content = re.sub(r'<!--.*?-->', '', html_content, flags=re.DOTALL)
            
            # Compress whitespace (but keep some structure)
            html_content = re.sub(r'\s+', ' ', html_content)
            
            return html_content.strip()
            
        except Exception as e:
            logging.warning(f"Error cleaning HTML content: {e}")
            return html_content  # Return original content if cleaning fails

    def extract_details(self, html_content: str, url: Optional[str] = None) -> Dict[str, Any]:
        """
        Extracts structured details from the provided HTML content.

        Args:
            html_content: The HTML source code of the listing page.
            url: The URL of the listing (optional, can be useful context).

        Returns:
            A dictionary containing extracted flat details. Returns an empty dict on major errors.
        """
        details = {field: None for field in self.EXTRACTED_FIELDS} # Initialize with None
        details['url'] = url # Set URL if provided

        if not html_content:
            logging.warning("Received empty HTML content.")
            return details # Return initialized dict with URL

        soup = None  # Initialize soup variable outside try block
        try:
            # Clean HTML content before parsing
            cleaned_html = self._clean_html(html_content)

            print(f"HTML size before cleaning: {len(html_content)/1048576:.2f} MB, after cleaning: {len(cleaned_html)/1048576:.2f} MB")
            
            # Save cleaned HTML for debugging if URL is available
            if url:
                self._save_cleaned_html_debug(cleaned_html, url)
            
            soup = BeautifulSoup(cleaned_html, 'html.parser')
            details['raw_html_hash'] = hash(cleaned_html) # Hash cleaned content

            # Call individual extraction methods
            # Note: We DON'T extract title here as crawlers provide better titles
            # The H1 tag often contains status prefixes like "Reserviert •Gelöscht"
            # If we need title extraction, use LLM or crawler data
            # extracted_title = self._extract_title(soup)
            
            details['kaltmiete'] = self._extract_kaltmiete(soup)
            details['warmmiete'] = self._extract_warmmiete(soup)
            details['nebenkosten'] = self._extract_nebenkosten(soup)
            details['size_sqm'] = self._extract_size(soup)
            details['rooms'] = self._extract_rooms(soup)
            details['address'] = self._extract_address(soup)
            details['description'] = self._extract_description(soup)
            details['availability'] = self._extract_availability(soup)
            details['furnished'] = self._extract_furnished(soup)  # Extract furnished status
            details['features'] = self._extract_features(soup) # Example for features

        except Exception as e:
            logging.error(f"Failed to parse HTML for URL {url}: {e}", exc_info=True)
            # Return partially filled details or empty dict depending on desired robustness
            return details # Return whatever was extracted before the error

        # --- LLM Enhancement Step ---
        if self.llm_client and soup is not None:
            try:
                # Example: Use LLM to potentially fill missing fields or add summary
                details = self._enhance_with_llm(details, soup)
            except Exception as e:
                logging.error(f"LLM enhancement failed for URL {url}: {e}", exc_info=True)

        return details

    # --- Individual Extraction Methods ---

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extracts the main title of the listing.
        
        NOTE: This often extracts titles with status prefixes like "Reserviert •Gelöscht"
        from the H1 tag. Consider using crawler-provided titles instead.
        """
        try:
            # Try common tags, prioritize H1
            title_tag = soup.find('h1')
            if title_tag and title_tag.get_text(strip=True):
                raw_title = title_tag.get_text(strip=True)
                logging.info(f"📝 Raw title from H1: '{raw_title}'")
                return raw_title

            # Fallback to <title> tag
            title_tag = soup.find('title')
            if title_tag and title_tag.get_text(strip=True):
                raw_title = title_tag.get_text(strip=True)
                logging.info(f"📝 Raw title from <title>: '{raw_title}'")
                return raw_title

            # Add more specific selectors based on target website structure here
            # e.g., soup.select_one('div.headline span.title-text')

        except Exception as e:
            logging.warning(f"Could not extract title: {e}", exc_info=False) # Log less critical errors
        return None

    def _extract_kaltmiete(self, soup: BeautifulSoup) -> Optional[float]:
        """Extracts Kaltmiete (cold rent / base rent without utilities)."""
        try:
            # --- THIS IS HIGHLY SITE-SPECIFIC ---
            # Look for keywords: "Kaltmiete", "Grundmiete", "Nettokaltmiete"
            # Example: Look for specific elements
            # kalt_element = soup.find(string=re.compile(r'Kaltmiete|Grundmiete', re.IGNORECASE))
            # if kalt_element:
            #     parent = kalt_element.find_parent()
            #     price_text = parent.get_text(strip=True)
            #     return self._parse_currency(price_text)
            pass # Placeholder - Requires specific selectors

        except Exception as e:
            logging.warning(f"Could not extract Kaltmiete: {e}", exc_info=False)
        return None

    def _extract_warmmiete(self, soup: BeautifulSoup) -> Optional[float]:
        """Extracts Warmmiete (warm rent / total rent including utilities)."""
        try:
            # --- THIS IS HIGHLY SITE-SPECIFIC ---
            # Look for keywords: "Warmmiete", "Gesamtmiete", "Bruttowarmmiete"
            # Example: Look for specific elements
            # warm_element = soup.find(string=re.compile(r'Warmmiete|Gesamtmiete|Bruttowarmmiete', re.IGNORECASE))
            # if warm_element:
            #     parent = warm_element.find_parent()
            #     price_text = parent.get_text(strip=True)
            #     return self._parse_currency(price_text)
            pass # Placeholder - Requires specific selectors

        except Exception as e:
            logging.warning(f"Could not extract Warmmiete: {e}", exc_info=False)
        return None

    def _extract_nebenkosten(self, soup: BeautifulSoup) -> Optional[float]:
        """Extracts Nebenkosten (additional costs / utilities)."""
        try:
            # --- THIS IS HIGHLY SITE-SPECIFIC ---
            # Look for keywords: "Nebenkosten", "Betriebskosten", "Umlagen", "NK"
            # Example: Look for specific elements
            # nk_element = soup.find(string=re.compile(r'Nebenkosten|Betriebskosten|Umlagen', re.IGNORECASE))
            # if nk_element:
            #     parent = nk_element.find_parent()
            #     price_text = parent.get_text(strip=True)
            #     return self._parse_currency(price_text)
            pass # Placeholder - Requires specific selectors

        except Exception as e:
            logging.warning(f"Could not extract Nebenkosten: {e}", exc_info=False)
        return None

    def _extract_size(self, soup: BeautifulSoup) -> Optional[float]:
        """Extracts the size in square meters."""
        try:
            # --- THIS IS HIGHLY SITE-SPECIFIC ---
            # Example: Look for a key-value pair or specific element
            # size_element = soup.select_one('.is24qa-wohnflaeche-ca') # Example for ImmoScout24
            # if size_element:
            #    size_text = size_element.get_text(strip=True)
            #    return self._parse_sqm(size_text)
            pass # Placeholder
        except Exception as e:
            logging.warning(f"Could not extract size: {e}", exc_info=False)
        return None

    def _extract_rooms(self, soup: BeautifulSoup) -> Optional[float]:
        """Extracts the number of rooms."""
        try:
            # --- THIS IS HIGHLY SITE-SPECIFIC ---
            # Example:
            # rooms_element = soup.select_one('.is24qa-zimmer') # Example for ImmoScout24
            # if rooms_element:
            #    rooms_text = rooms_element.get_text(strip=True)
            #    return self._parse_rooms(rooms_text)
             pass # Placeholder
        except Exception as e:
            logging.warning(f"Could not extract rooms: {e}", exc_info=False)
        return None

    def _extract_address(self, soup: BeautifulSoup) -> Optional[str]:
        """Extracts the address."""
        try:
            # --- THIS IS HIGHLY SITE-SPECIFIC ---
            # Example: Combine street, zip, city if separate, or find containing element
            # address_element = soup.select_one('.address-block') # Generic example
            # if address_element:
            #     # Clean up potential multiple lines/spaces
            #     address_parts = [part.strip() for part in address_element.get_text(separator=' ', strip=True).split()]
            #     return ' '.join(filter(None, address_parts))
            pass # Placeholder
        except Exception as e:
            logging.warning(f"Could not extract address: {e}", exc_info=False)
        return None

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        """Extracts the main description text."""
        try:
            # --- THIS IS HIGHLY SITE-SPECIFIC ---
            # Example: Look for common IDs or classes
            desc_element = soup.find(id='beschreibung') or \
                           soup.select_one('.listing-description') or \
                           soup.select_one('div[data-qa="description"]') # More examples
            if desc_element:
                # Consider joining paragraphs if description is split into multiple <p> tags
                return desc_element.get_text(separator='\n', strip=True)
        except Exception as e:
            logging.warning(f"Could not extract description: {e}", exc_info=False)
        return None

    def _extract_availability(self, soup: BeautifulSoup) -> Optional[str]:
        """Extracts the availability date or status."""
        try:
            # --- THIS IS HIGHLY SITE-SPECIFIC ---
            # Example: Look for specific labels/terms
            # avail_element = soup.find(lambda tag: tag.name == 'dt' and 'Verfügbar ab' in tag.text) # Find label
            # if avail_element and avail_element.find_next_sibling('dd'):
            #    return avail_element.find_next_sibling('dd').get_text(strip=True)

            # Alternative: Regex search in the whole text (less reliable)
            # text_content = soup.get_text(" ", strip=True)
            # match = re.search(r'(Verfügbar ab|Available from)[:\s]*([\w\d.\s-]+)', text_content, re.IGNORECASE)
            # if match:
            #     return match.group(2).strip()
            pass # Placeholder
        except Exception as e:
            logging.warning(f"Could not extract availability: {e}", exc_info=False)
        return None

    def _extract_furnished(self, soup: BeautifulSoup) -> Optional[bool]:
        """
        Extracts whether the apartment is furnished (möbliert).
        
        IMPORTANT: A kitchen (Küche/Einbauküche/EBK) does NOT make an apartment furnished!
        Furnished means: furniture like bed, sofa, wardrobe, table, etc.
        
        Returns:
            True if furnished, False if not furnished/unmöbliert, None if unknown
        """
        try:
            # Get all text from the page
            text_content = soup.get_text(" ", strip=True).lower()
            
            # Check for German furnished keywords
            # Note: We're looking for actual furniture, not just a kitchen
            furnished_keywords = [
                'möbliert', 'moebliert', 'möbiliert', 'mobiliert',
                'teilmöbliert', 'teilmoebliert', 'komplett möbliert',
                'voll möbliert', 'vollmöbliert', 'eingerichtet'
            ]
            
            unfurnished_keywords = [
                'unmöbliert', 'unmoebliert', 'nicht möbliert',
                'ohne möbel', 'ohne möblierung'
            ]
            
            # Kitchen-only indicators (these should NOT count as furnished)
            kitchen_only_keywords = [
                'nur küche', 'nur einbauküche', 'lediglich küche',
                'ausschließlich küche', 'only kitchen'
            ]
            
            # Check for "only kitchen" indicators first (most specific)
            for keyword in kitchen_only_keywords:
                if keyword in text_content:
                    logging.debug(f"Found 'kitchen only' indicator: {keyword} - NOT furnished")
                    return False
            
            # Check for unfurnished keywords
            for keyword in unfurnished_keywords:
                if keyword in text_content:
                    logging.debug(f"Found unfurnished keyword: {keyword}")
                    return False
            
            # Then check for furnished keywords
            has_furnished_keyword = False
            for keyword in furnished_keywords:
                if keyword in text_content:
                    logging.debug(f"Found furnished keyword: {keyword}")
                    has_furnished_keyword = True
                    break
            
            # If we found "möbliert" but also find phrases indicating only kitchen is available
            # then it's not really furnished
            if has_furnished_keyword:
                # Check if text mentions only having a kitchen (EBK/Einbauküche)
                # but no other furniture
                kitchen_indicators = ['einbauküche', 'ebk', 'küche vorhanden']
                furniture_indicators = ['bett', 'sofa', 'couch', 'schrank', 'tisch', 
                                      'sessel', 'kommode', 'regal', 'möbel']
                
                has_kitchen = any(k in text_content for k in kitchen_indicators)
                has_furniture = any(f in text_content for f in furniture_indicators)
                
                # If only kitchen mentioned but no furniture, it's likely not furnished
                if has_kitchen and not has_furniture:
                    logging.debug(f"Found 'möbliert' keyword, but only kitchen mentioned, no furniture - treating as NOT furnished")
                    return False
                
                return True
            
            # Also check in specific tags/attributes if they exist
            # Example: Look for feature lists or amenity sections
            feature_elements = soup.find_all(['li', 'span', 'div'], class_=re.compile(r'(feature|amenity|ausstattung)', re.IGNORECASE))
            for element in feature_elements:
                element_text = element.get_text(strip=True).lower()
                for keyword in unfurnished_keywords:
                    if keyword in element_text:
                        return False
                for keyword in furnished_keywords:
                    if keyword in element_text:
                        return True
            
        except Exception as e:
            logging.warning(f"Could not extract furnished status: {e}", exc_info=False)
        
        return None  # Unknown/not found

    def _extract_features(self, soup: BeautifulSoup) -> Optional[List[str]]:
        """Extracts a list of features (e.g., Balcony, Lift)."""
        features = []
        try:
            # --- THIS IS HIGHLY SITE-SPECIFIC ---
            # Example 1: Look for a list (<ul>) with feature items (<li>)
            # feature_list = soup.select_one('ul.features')
            # if feature_list:
            #     features = [item.get_text(strip=True) for item in feature_list.find_all('li')]

            # Example 2: Check for keywords in the description or specific sections
            # description_text = self._extract_description(soup) or ""
            # if "Balkon" in description_text or soup.find(string=re.compile("Balkon")):
            #      if "Balkon" not in features: features.append("Balkon")
            # if "Einbauküche" in description_text or "EBK" in description_text or soup.find(string=re.compile("Einbauküche|EBK")):
            #       if "Einbauküche" not in features: features.append("Einbauküche")
            # ... etc for Lift, Keller, Garten...
            pass # Placeholder
        except Exception as e:
            logging.warning(f"Could not extract features: {e}", exc_info=False)
        return features if features else None # Return list or None if empty

    def _convert_html_to_markdown(self, soup: Optional[BeautifulSoup], debug_filename: Optional[str] = None, max_length: int = 8000) -> str:
        """
        Converts HTML content to clean markdown format for efficient LLM processing.
        Removes navigation, ads, scripts, and other non-content elements before conversion.
        
        Args:
            soup: BeautifulSoup object containing parsed HTML
            debug_filename: Optional filename (without extension) to save markdown for debugging.
                          Will save to debug_pages/ directory with .md extension
            max_length: Maximum length of markdown text in characters (default: 8000)
        
        Returns:
            Markdown-formatted text preserving structure (headings, lists, tables)
        """
        if soup is None:
            logging.warning("Cannot convert HTML to markdown from None soup object")
            return ""
            
        try:
            # Create a copy of the soup to avoid modifying the original
            soup_copy = copy.copy(soup)
            
            # AGGRESSIVELY remove all script and style content first
            for script in soup_copy.find_all('script'):
                script.decompose()
            
            for style in soup_copy.find_all('style'):
                style.decompose()
            
            for noscript in soup_copy.find_all('noscript'):
                noscript.decompose()
            
            # Remove other non-content elements
            unwanted_tags = ['iframe', 'embed', 'object', 'svg', 'canvas', 'link', 'meta']
            for tag_name in unwanted_tags:
                for tag in soup_copy.find_all(tag_name):
                    tag.decompose()
            
            # Remove unwanted sections by selector (navigation, ads, etc.)
            unwanted_selectors = [
                'nav', 'header', 'footer', 'aside',
                '.advertisement', '.ads', '.banner', '.sidebar',
                '.navigation', '.menu', '.breadcrumb',
                '.social-share', '.social-media',
                '.cookie-notice', '.privacy-notice',
                '.newsletter', '.subscribe',
                '.related-articles', '.recommendations',
                '.comments', '.comment-section',
                '.pagination', '.pager',
                '.search-box', '.search-form',
                '.filter', '.sort',
                '.back-to-top', '.scroll-to-top'
            ]
            
            for selector in unwanted_selectors:
                for element in soup_copy.select(selector):
                    element.decompose()
            
            # Remove form controls and interactive elements (not useful for property info)
            non_content_tags = [
                'button', 'input', 'select', 'textarea', 'option',
                'form', 'label', 'fieldset', 'legend'
            ]
            
            for tag_name in non_content_tags:
                for tag in soup_copy.find_all(tag_name):
                    tag.decompose()
            
            # Try to focus on main content area if it exists
            main_content = None
            main_selectors = [
                'main', 'article', '[role="main"]',
                '.content', '.main-content', '.property-details',
                '.listing-details', '.expose-details', '.apartment-details'
            ]
            
            for selector in main_selectors:
                main_content = soup_copy.select_one(selector)
                if main_content:
                    logging.debug(f"Found main content using selector: {selector}")
                    break
            
            # Use main content if found, otherwise use entire soup
            content_to_convert = main_content if main_content else soup_copy
            
            # Convert to markdown using markdownify
            # Options:
            # - strip=['img', 'picture', 'video', 'audio']: Remove media tags
            # - heading_style='ATX': Use # style headings (better for LLMs)
            # - bullets='-': Use - for bullet lists (cleaner)
            markdown_text = md(
                str(content_to_convert),
                heading_style='ATX',
                bullets='-',
                strip=['img', 'picture', 'video', 'audio', 'source', 'track', 'figure', 'figcaption']
            )
            
            # Clean up the markdown
            lines = markdown_text.split('\n')
            cleaned_lines = []
            
            for line in lines:
                line = line.strip()
                
                # Skip empty lines (but we'll add them back between sections)
                if not line:
                    # Keep one empty line for readability
                    if cleaned_lines and cleaned_lines[-1] != '':
                        cleaned_lines.append('')
                    continue
                
                # Skip lines that look like JavaScript code remnants
                js_patterns = [
                    'function', 'var ', 'let ', 'const ', 'return ', '=> {',
                    'window.', 'document.', 'addEventListener', 'console.',
                    '$(', 'jQuery', '.click(', '.on('
                ]
                if any(pattern in line for pattern in js_patterns):
                    continue
                
                # Skip lines that are mostly just punctuation or special characters
                if len(line) > 3 and len([c for c in line if c.isalnum()]) < len(line) * 0.3:
                    continue
                
                cleaned_lines.append(line)
            
            # Join lines
            markdown_text = '\n'.join(cleaned_lines)
            
            # Remove excessive newlines (more than 2 in a row)
            markdown_text = re.sub(r'\n{3,}', '\n\n', markdown_text)
            
            # Intelligent truncation: try to keep complete sections
            if len(markdown_text) > max_length:
                # Try to truncate at a section boundary (heading or double newline)
                truncated = markdown_text[:max_length]
                
                # Find the last section boundary
                last_heading = max(
                    truncated.rfind('\n# '),
                    truncated.rfind('\n## '),
                    truncated.rfind('\n### ')
                )
                last_double_newline = truncated.rfind('\n\n')
                
                # Use the closest section boundary, or just cut at max_length
                cut_point = max(last_heading, last_double_newline)
                if cut_point > max_length * 0.7:  # Only use if we're not losing too much
                    markdown_text = truncated[:cut_point]
                else:
                    markdown_text = truncated
                
                markdown_text += f"\n\n[Content truncated at {len(markdown_text)} characters]"
            
            logging.debug(f"Converted HTML to {len(markdown_text)} characters of markdown")
            
            # Save to debug file if requested
            if debug_filename:
                self._save_markdown_debug(markdown_text, debug_filename)
            
            return markdown_text.strip()
            
        except Exception as e:
            logging.error(f"Error converting HTML to markdown: {e}", exc_info=True)
            # Fallback to basic text extraction
            try:
                fallback_text = soup.get_text(separator='\n', strip=True)
                fallback_text = fallback_text[:max_length]
                
                if debug_filename:
                    self._save_markdown_debug(fallback_text, debug_filename)
                
                return fallback_text
            except Exception as fallback_error:
                logging.error(f"Fallback markdown conversion also failed: {fallback_error}")
                return ""

    # --- Helper methods for parsing specific values --- #

    def _save_markdown_debug(self, markdown_text: str, filename: str) -> None:
        """
        Save markdown text to a .md file for debugging purposes.
        
        Args:
            markdown_text: The markdown text to save
            filename: Base filename (without extension) for the debug file
        """
        try:
            # Create debug_pages directory if it doesn't exist
            debug_dir = os.path.join(os.getcwd(), "debug_pages")
            os.makedirs(debug_dir, exist_ok=True)
            
            # Sanitize filename - remove/replace problematic characters
            safe_filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            safe_filename = safe_filename.strip('._')
            
            # Ensure .md extension
            if not safe_filename.endswith('.md'):
                safe_filename += '.md'
            
            filepath = os.path.join(debug_dir, safe_filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"<!-- Markdown Conversion for LLM Processing -->\n")
                f.write(f"<!-- Timestamp: {datetime.now().isoformat()} -->\n")
                f.write(f"<!-- Text length: {len(markdown_text)} characters -->\n")
                f.write(f"<!-- Processing Pipeline: -->\n")
                f.write(f"<!--   1. Raw HTML (saved by crawler as .html) -->\n")
                f.write(f"<!--   2. Cleaned HTML (saved as _cleaned.html) - scripts/styles/base64 removed -->\n")
                f.write(f"<!--   3. Markdown (this file) - nav/ads/footers removed, converted to markdown -->\n")
                f.write(f"\n{'='*80}\n\n")
                f.write(markdown_text)
            
            logging.info(f"Debug: Saved markdown to {filepath}")
        except Exception as e:
            logging.warning(f"Failed to save markdown debug file: {e}")

    def _save_cleaned_html_debug(self, html_content: str, url: str) -> None:
        """
        Save cleaned HTML to file for debugging purposes.
        This is the HTML after _clean_html() but before text extraction.
        
        Args:
            html_content: The cleaned HTML content to save
            url: The URL of the listing (used for filename generation)
        """
        try:
            # Create debug_pages directory if it doesn't exist
            debug_dir = os.path.join(os.getcwd(), "debug_pages")
            os.makedirs(debug_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            # Extract a clean identifier from URL
            url_parts = url.split('/')
            url_id = next((part for part in reversed(url_parts) if part and len(part) > 3), 'unknown')
            
            # Sanitize filename
            safe_filename = re.sub(r'[<>:"/\\|?*]', '_', f"{timestamp}_cleaned_{url_id}")
            safe_filename = safe_filename.strip('._') + '.html'
            
            filepath = os.path.join(debug_dir, safe_filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"<!-- Cleaned HTML (Stage 2: After _clean_html()) -->\n")
                f.write(f"<!-- Timestamp: {datetime.now().isoformat()} -->\n")
                f.write(f"<!-- Original URL: {url} -->\n")
                f.write(f"<!-- Size: {len(html_content)} characters -->\n")
                f.write(f"<!-- \n")
                f.write(f"     Processing Pipeline:\n")
                f.write(f"     1. Raw HTML (saved by crawler) - Contains everything\n")
                f.write(f"     2. Cleaned HTML (this file) - Scripts, styles, base64 data removed\n")
                f.write(f"     3. Readable Text (saved as .txt) - Navigation/ads/footers removed\n")
                f.write(f"-->\n")
                f.write(html_content)
            
            logging.info(f"Debug: Saved cleaned HTML to {filepath}")
        except Exception as e:
            logging.warning(f"Failed to save cleaned HTML debug file: {e}")

    def _parse_currency(self, text: str) -> Optional[float]:
        """Helper to parse price strings."""
        if not text:
            return None
        # Remove currency symbols, thousand separators, convert comma decimal separator
        cleaned_text = re.sub(r'[€$£]|[.\s]', '', text).replace(',', '.')
        try:
            return float(cleaned_text)
        except ValueError:
            return None

    def _parse_sqm(self, text: str) -> Optional[float]:
        """Helper to parse size strings (e.g., '100.5 m²')."""
        if not text:
            return None
        match = re.search(r'([\d.,]+)', text)
        if match:
            try:
                return float(match.group(1).replace('.', '').replace(',', '.'))
            except ValueError:
                return None
        return None

    def _parse_rooms(self, text: str) -> Optional[float]:
        """Helper to parse room count strings (e.g., '3 Zimmer', '2.5 rooms')."""
        if not text:
            return None
        match = re.search(r'([\d.,]+)', text)
        if match:
            try:
                return float(match.group(1).replace(',', '.'))
            except ValueError:
                return None
        return None

    # --- LLM Interaction with Retry Logic --- #

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=16),
        retry=retry_if_exception_type((RateLimitError, APITimeoutError, APIError)),
        before_sleep=lambda retry_state: logging.warning(
            f"OpenAI API call failed (attempt {retry_state.attempt_number}), retrying... Error: {retry_state.outcome.exception()}"
        )
    )
    def _call_openai_with_retry(self, system_prompt: str, user_prompt: str) -> str:
        """
        Calls OpenAI API with retry logic for transient failures.
        
        Args:
            system_prompt: System message defining the role
            user_prompt: User message with the request
            
        Returns:
            Response text from the API
        """
        response = self.llm_client.chat.completions.create(
            model=self.llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,
            max_tokens=200
        )
        return response.choices[0].message.content

    def _enhance_with_llm(self, details: Dict[str, Any], soup: Optional[BeautifulSoup]) -> Dict[str, Any]:
        """Uses the configured OpenAI LLM to potentially fill missing fields."""
        if not self.llm_client:
            return details

        if soup is None:
            logging.warning(f"Cannot enhance details with LLM for URL {details.get('url')} - soup is None")
            return details

        # Convert HTML to markdown for LLM context
        # Generate debug filename from URL if available
        debug_filename = None
        url = details.get('url')
        if url:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            # Extract a clean identifier from URL
            url_parts = url.split('/')
            url_id = next((part for part in reversed(url_parts) if part and len(part) > 3), 'unknown')
            debug_filename = f"{timestamp}_markdown_{url_id}"
        
        markdown_text = self._convert_html_to_markdown(soup, debug_filename=debug_filename)
        if not markdown_text:
            logging.warning(f"No markdown text extracted for LLM enhancement for URL {details.get('url')}. LLM enhancement disabled.")
            return details # Cannot enhance without text

        # Use the extracted markdown for LLM enhancement
        text_content = markdown_text

        # Construct a prompt asking for specific missing info based on 'details' dict
        missing_fields = [k for k, v in details.items() if v is None and k not in ['raw_html_hash', 'url', 'title', 'description']] # Identify missing fields
        if not missing_fields:
             logging.debug(f"No fields missing for LLM enhancement for URL {details.get('url')}")
             return details # Nothing obvious missing for LLM

        # System message defining the role and desired output format
        system_prompt = (
            "Du bist ein Experte für die Extraktion von Informationen aus deutschen Wohnungsanzeigen. "
            "Deine Aufgabe ist es, den bereitgestellten HTML-Text zu analysieren und die angeforderten Felder präzise zu extrahieren.\n"
            "\n**WICHTIG: Antworte NUR mit den extrahierten Informationen im Format 'feld: wert' in separaten Zeilen.**\n"
            "Wenn ein Wert nicht gefunden werden kann, antworte mit 'feld: None'.\n"
            "Es kann sein, das weitere Inserate am Ende folgen, die aber nichts mit dem eigentlichen Inserat zu tun haben. Ignoriere diese."
            "\n**EXTRAKTIONSREGELN:**\n"
            "\n1. **kaltmiete**: Die KALTMIETE (Grundmiete, Nettokaltmiete) - nur die Basismiete OHNE Nebenkosten"
            "\n   - Suche nach: 'Kaltmiete', 'Grundmiete', 'Nettokaltmiete', 'Miete zzgl. NK'"
            "\n   - Format: Nur die Zahl ohne Währung (z.B. '850' oder '850.50')"
            "\n   - Wenn nur Warmmiete vorhanden ist: None"
            "\n"
            "\n2. **warmmiete**: Die WARMMIETE (Gesamtmiete, Bruttowarmmiete) - Miete INKLUSIVE aller Nebenkosten"
            "\n   - Suche nach: 'Warmmiete', 'Gesamtmiete', 'Bruttowarmmiete', 'Miete inkl. NK', 'Gesamtbelastung'"
            "\n   - Format: Nur die Zahl ohne Währung (z.B. '950' oder '950.75')"
            "\n   - Wenn nur Kaltmiete vorhanden ist: None"
            "\n"
            "\n3. **nebenkosten**: Die NEBENKOSTEN (Betriebskosten, Umlagen) - nur die Zusatzkosten"
            "\n   - Suche nach: 'Nebenkosten', 'Betriebskosten', 'Umlagen', 'NK', 'Zusatzkosten'"
            "\n   - Format: Nur die Zahl ohne Währung (z.B. '100' oder '100.50')"
            "\n   - WICHTIG: Warmmiete = Kaltmiete + Nebenkosten"
            "\n   - Wenn nicht explizit angegeben: None"
            "\n"
            "\n4. **size_sqm**: Die Wohnfläche in Quadratmetern"
            "\n   - Suche nach: 'Wohnfläche', 'Fläche', 'm²', 'qm', 'Quadratmeter'"
            "\n   - Format: Nur die Zahl (z.B. '75' oder '75.5')"
            "\n"
            "\n5. **furnished**: Möblierungsstatus der Wohnung"
            "\n   - Antworte mit 'ja' wenn: möbliert, teilmöbliert, komplett möbliert, voll möbliert, eingerichtet"
            "\n   - Antworte mit 'nein' wenn: unmöbliert, nicht möbliert, ohne Möbel"
            "\n   - **WICHTIG**: Eine Küche/Einbauküche/EBK macht die Wohnung NICHT möbliert!"
            "\n   - Möbliert bedeutet: Es gibt Möbel wie Bett, Sofa, Schrank, Tisch etc."
            "\n   - Nur Küche = NICHT möbliert (nein)"
            "\n   - Antworte mit 'None' wenn: keine Information zur Möblierung gefunden"
            "\n"
            "\n**BEISPIEL-ANTWORTEN:**"
            "\n"
            "\nBeispiel 1 (Unmöbliert mit Küche):"
            "\nkaltmiete: 850"
            "\nwarmmiete: 950.50"
            "\nnebenkosten: 100.50"
            "\nsize_sqm: 75"
            "\nfurnished: nein  # Hat nur Küche, keine Möbel"
            "\n"
            "\nBeispiel 2 (Möbliert):"
            "\nkaltmiete: 1200"
            "\nwarmmiete: 1350"
            "\nnebenkosten: 150"
            "\nsize_sqm: 60"
            "\nfurnished: ja  # Hat Möbel wie Bett, Sofa, Schrank"
            "\n"
            "\n**Füge KEINE einleitenden Texte, Erklärungen oder zusätzlichen Kommentare hinzu!**"
        )

        # User message with the context and request
        # Increased from 4000 to 8000 chars since markdown is more concise
        user_prompt = f"""Analysiere den folgenden Wohnungsanzeigen-Text (Markdown-Format):
        --- TEXT ANFANG ---
        {text_content[:8000]}
        --- TEXT ENDE ---

        Extrahiere die folgenden fehlenden Felder:
        """
        for field in missing_fields:
            user_prompt += f"\n- {field}" # List missing fields

        try:
            print("\n" + "="*80)
            print("🤖 LLM EXTRACTION STARTED")
            print("="*80)
            print(f"📍 URL: {details.get('url', 'unknown')}")
            print(f"🔍 Missing fields: {', '.join(missing_fields)}")
            print(f"🧠 Model: {self.llm_model}")
            print(f"📝 Format: Markdown ({len(text_content)} chars)")
            print("="*80 + "\n")
            
            logging.info(f"Sending request to OpenAI model '{self.llm_model}' for URL {details.get('url')} to find fields: {missing_fields}")
            
            # Use the retry-wrapped API call
            response_text = self._call_openai_with_retry(system_prompt, user_prompt)
            
            print("\n" + "="*80)
            print("💬 LLM RESPONSE")
            print("="*80)
            print(response_text)
            print("="*80 + "\n")
            
            logging.debug(f"Raw LLM response for URL {details.get('url')}:\n{response_text}")

            llm_results = self._parse_llm_response(response_text, missing_fields)
            
            print("📊 PARSED RESULTS")
            print("-"*80)
            for field, value in llm_results.items():
                print(f"  {field:15} → {value}")
            print("-"*80 + "\n")
            
            logging.debug(f"Parsed LLM response for URL {details.get('url')}: {llm_results}")

            # Update details with LLM results
            # IMPORTANT: Only ADD or ENHANCE data, never remove existing values
            # LLM should not overwrite existing data with None
            updated_count = 0
            for field, value in llm_results.items():
                 # Only update if:
                 # 1. Field exists in details
                 # 2. Original value is None (no data yet)
                 # 3. LLM provided a non-None value (actual data)
                 if field in details and details[field] is None and value is not None:
                     # Attempt type conversion based on field name
                     try:
                        if field in ['kaltmiete', 'warmmiete', 'nebenkosten', 'size_sqm', 'rooms'] and isinstance(value, str):
                            # Use existing parser helpers if applicable, or basic conversion
                            if field in ['kaltmiete', 'warmmiete', 'nebenkosten']:
                                converted_value = self._parse_currency(value)
                            elif field == 'size_sqm':
                                converted_value = self._parse_sqm(value)
                            elif field == 'rooms':
                                converted_value = self._parse_rooms(value)
                            else: # Fallback just in case
                                converted_value = float(re.sub(r'[^\d.,]', '', value).replace(',', '.'))
                        elif field == 'furnished' and isinstance(value, str):
                            # Parse furnished status - expecting 'ja', 'nein', 'true', 'false' etc
                            value_lower = value.lower().strip()
                            if value_lower in ['ja', 'yes', 'true', 'möbliert', 'moebliert', '1']:
                                converted_value = True
                            elif value_lower in ['nein', 'no', 'false', 'unmöbliert', 'unmoebliert', '0']:
                                converted_value = False
                            else:
                                converted_value = None  # Unknown
                        elif field == 'features' and isinstance(value, str):
                            # Simple list splitting if LLM returns comma-separated string
                            converted_value = [f.strip() for f in value.split(',') if f.strip()]
                        else:
                            converted_value = value # Keep as string or original type

                        if converted_value is not None:
                            details[field] = converted_value
                            logging.info(f"LLM provided and parsed value for field '{field}' ({type(converted_value).__name__}) for URL {details.get('url')}")
                            updated_count += 1
                        else:
                            logging.warning(f"LLM provided value for field '{field}' for URL {details.get('url')}, but parsing failed.")

                     except (ValueError, TypeError) as parse_error:
                         logging.warning(f"LLM provided value for field '{field}' for URL {details.get('url')}, but type conversion failed: {parse_error}. Keeping raw value '{value}'.")
                         details[field] = value # Keep raw value if conversion fails
                         updated_count += 1
                 elif field in details and details[field] is not None and value is None:
                     # LLM tried to remove existing data - prevent this
                     logging.warning(f"LLM tried to set field '{field}' to None, but existing value '{details[field]}' will be kept. LLM should only add data, not remove it.")
                 elif field in details and details[field] is not None and value is not None:
                     # Both have values - keep original, log the difference
                     logging.info(f"Field '{field}' already has value '{details[field]}'. LLM suggested '{value}', but keeping original.")

            if updated_count > 0:
                print("✅ LLM EXTRACTION SUCCESSFUL")
                print(f"   Updated {updated_count} field(s)")
                print("="*80 + "\n")
                logging.info(f"LLM enhancement updated {updated_count} fields for URL {details.get('url')}")
            else:
                print("⚠️  LLM EXTRACTION COMPLETED")
                print(f"   No new values found for missing fields")
                print("="*80 + "\n")
                logging.info(f"LLM enhancement did not find new values for missing fields for URL {details.get('url')}")


        except Exception as e:
            logging.error(f"Error during OpenAI API call or processing for URL {details.get('url')}: {e}", exc_info=True)

        return details

    def _parse_llm_response(self, response_text: str, requested_fields: List[str]) -> Dict[str, Any]:
         """Parses the LLM's text response (expected 'field: value' format) to extract field values."""
         parsed = {}
         if not response_text:
             return parsed

         lines = response_text.strip().split('\n')
         for line in lines:
             if ':' in line:
                 parts = line.split(':', 1)
                 field = parts[0].strip().replace('-', '').strip() # Clean field name
                 value_str = parts[1].strip()

                 if field in requested_fields:
                     if value_str.lower() == 'none' or not value_str:
                         parsed[field] = None
                     else:
                         # Basic type guessing / keep as string for now, conversion happens in _enhance_with_llm
                         parsed[field] = value_str
                 else:
                     logging.warning(f"LLM returned unexpected field '{field}' in response.")
         return parsed
