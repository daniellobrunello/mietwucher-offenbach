"""Expose crawler for Kleinanzeigen"""
import re
import datetime

from bs4 import Tag

from flathunter.webdriver_crawler import WebdriverCrawler
from flathunter.logging_fh import logger

class Kleinanzeigen(WebdriverCrawler):
    """Implementation of Crawler interface for Kleinanzeigen"""

    URL_PATTERN = re.compile(r'https://www\.kleinanzeigen\.de')
    MONTHS = {
        "Januar": "01",
        "Februar": "02",
        "März": "03",
        "April": "04",
        "Mai": "05",
        "Juni": "06",
        "Juli": "07",
        "August": "08",
        "September": "09",
        "Oktober": "10",
        "November": "11",
        "Dezember": "12"
    }

    def get_expose_details(self, expose):
        # Fetch detail page with proper page_type for debug saving
        soup = self.get_soup_from_url(expose['url'], driver=self.get_driver(), page_type="detail")
        
        # Initialize flexible storage structures
        if 'features' not in expose:
            expose['features'] = {}
        if 'amenities' not in expose:
            expose['amenities'] = []
        
        # CRITICAL: Extract price from detail page
        # Price is in the viewad-price element or price meta tag
        price_elem = soup.find('h2', {"id": "viewad-price"})
        if not price_elem:
            price_elem = soup.find('span', {"class": "price"})
        if not price_elem:
            # Try meta tag
            price_meta = soup.find('meta', {"property": "price:amount"})
            if price_meta:
                price_elem = price_meta
        
        if price_elem:
            if price_elem.name == 'meta':
                price_text = price_elem.get('content', '')
            else:
                price_text = price_elem.get_text(strip=True)
            # Clean up price text
            price_text = price_text.replace('VB', '').replace('€', '').strip()
            if price_text:
                expose['price'] = price_text
                logger.debug(f"Extracted price from detail page: {price_text}")
        
        # Extract availability date
        for detail in soup.find_all('li', {"class": "addetailslist--detail"}):
            if re.match(r'Verfügbar ab', detail.text):
                date_string = re.match(r'(\w+) (\d{4})', detail.text)
                if date_string is not None:
                    expose['from'] = "01." + self.MONTHS[date_string[1]] + "." + date_string[2]
        if 'from' not in expose:
            expose['from'] = datetime.datetime.now().strftime('%02d.%02m.%Y')
        
        # Extract description
        description_elem = soup.find('p', {"id": "viewad-description-text"})
        if description_elem:
            expose['description'] = description_elem.get_text(strip=True)
        
        # Extract all details from the detail list
        detail_list = soup.find_all('li', {"class": "addetailslist--detail"})
        for detail_item in detail_list:
            text = detail_item.get_text(strip=True)
            
            # Try to split into label and value
            if ':' in text:
                parts = text.split(':', 1)
                label = parts[0].strip()
                value = parts[1].strip() if len(parts) > 1 else ''
            else:
                label = text
                value = text
            
            # Map common fields
            if 'Zimmer' in label:
                # Update rooms from detail page
                rooms_value = re.search(r'\d+[.,]?\d*', value)
                if rooms_value:
                    expose['rooms'] = rooms_value.group()
                    logger.debug(f"Extracted rooms from detail page: {expose['rooms']}")
                expose['features']['rooms_detail'] = value
            elif 'Wohnfläche' in label or 'Fläche' in label:
                # CRITICAL: Extract size from detail page and update main size field
                size_match = re.search(r'(\d+[.,]?\d*)\s*m', value)
                if size_match:
                    size_value = size_match.group(1).replace(',', '.')
                    expose['size'] = f"{size_value} m²"
                    logger.debug(f"Extracted size from detail page: {expose['size']}")
                expose['features']['size_detail'] = value
            elif 'Etage' in label or 'Stockwerk' in label:
                expose['features']['floor'] = value
            elif 'Verfügbar ab' in label:
                expose['features']['availability'] = value
            elif 'Kaution' in label or 'Deposit' in label:
                expose['features']['deposit'] = value
            elif 'Nebenkosten' in label:
                expose['features']['additional_costs'] = value
            elif 'Heizkosten' in label:
                expose['features']['heating_costs'] = value
            elif 'Baujahr' in label:
                expose['features']['building_year'] = value
            elif 'Heizung' in label:
                expose['features']['heating_type'] = value
            elif 'Haustier' in label:
                expose['features']['pets'] = value
            elif 'Rauch' in label:
                expose['features']['smoking'] = value
            elif 'WG' in label:
                expose['features']['shared_flat'] = value
            else:
                # Store any other fields with sanitized key
                key = label.lower().replace(' ', '_').replace(':', '').replace('-', '_')
                if key and value:
                    expose['features'][key] = value
        
        # Extract amenities from feature tags
        feature_tags = soup.find_all('span', {"class": "tag"})
        for tag in feature_tags:
            feature_text = tag.get_text(strip=True)
            if feature_text and feature_text not in expose['amenities']:
                expose['amenities'].append(feature_text)
        
        # Look for specific amenity keywords in the description and page
        amenity_keywords = {
            'Balkon': 'balcony',
            'Terrasse': 'terrace',
            'Garten': 'garden',
            'Einbauküche': 'fitted_kitchen',
            'EBK': 'fitted_kitchen',
            'Küche': 'kitchen',
            'Keller': 'basement',
            'Aufzug': 'elevator',
            'Fahrstuhl': 'elevator',
            'Garage': 'garage',
            'Stellplatz': 'parking',
            'Parkplatz': 'parking',
            'Barrierefrei': 'barrier_free',
            'Möbliert': 'furnished',
            'teilmöbliert': 'partially_furnished',
            'WG-geeignet': 'shared_flat_suitable',
            'Haustiere erlaubt': 'pets_allowed',
            'Haustiere': 'pets_negotiable',
            'Waschmaschine': 'washing_machine',
            'Geschirrspüler': 'dishwasher',
            'Kabel-TV': 'cable_tv',
            'Internet': 'internet',
            'WLAN': 'wifi'
        }
        
        page_text = soup.get_text()
        for keyword, amenity_name in amenity_keywords.items():
            if keyword in page_text and amenity_name not in expose['amenities']:
                expose['amenities'].append(amenity_name)
        
        # Extract location details if available
        location_elem = soup.find('span', {"id": "street-address"})
        if location_elem:
            expose['features']['street'] = location_elem.get_text(strip=True)
        
        postal_elem = soup.find('span', {"id": "postal-code"})
        if postal_elem:
            expose['features']['postal_code'] = postal_elem.get_text(strip=True)
        
        locality_elem = soup.find('span', {"id": "locality"})
        if locality_elem:
            expose['features']['locality'] = locality_elem.get_text(strip=True)
        
        return expose

    def get_entry_html(self, entry_url):
        """Applies a page number to a formatted search URL and fetches the exposes at that page"""
        return str(self.get_soup_from_url(
            entry_url,
            driver=self.get_driver()
        ))

    # pylint: disable=too-many-locals
    def extract_data(self, soup):
        """Extracts all exposes from a provided Soup object"""
        entries = []
        soup = soup.find(id="srchrslt-adtable")

        if soup is None:
            return entries

        exposes = soup.find_all("article", class_="aditem")
        for  expose in exposes:

            title_elem = expose.find(class_="ellipsis")
            if title_elem.get("href"):
                url = title_elem.get("href")
            else:
                # If there is no title element, just continue since we can't provide an URL
                continue

            try:
                price = expose.find(
                    class_="aditem-main--middle--price-shipping--price").text.strip()
                tags = expose.find_all(class_="simpletag")
                address = expose.find("div", {"class": "aditem-main--top--left"})
                image_element = expose.find("div", {"class": "galleryimage-element"})
            except AttributeError as error:
                logger.warning("Unable to process eBay expose: %s", str(error))
                continue

            if image_element is not None:
                image = image_element["data-imgsrc"]
            else:
                image = None

            address = address.text.strip()
            address = address.replace('\n', ' ').replace('\r', '')
            address = " ".join(address.split())

            rooms = ""
            if len(tags) > 1:
                rooms_match = re.search(r'\d+[.|,]*\d*', tags[1].text, flags=re.MULTILINE)
                if rooms_match is not None:
                    rooms = rooms_match.group()

            try:
                size = tags[0].text.strip()
            except (IndexError, TypeError):
                size = ""

            details = {
                'id': int(expose.get("data-adid")),
                'image': image,
                'url': ("https://www.kleinanzeigen.de" + url),
                'title': title_elem.text.strip(),
                'price': price,
                'size': size,
                'rooms': rooms,
                'address': address,
                'crawler': self.get_name()
            }
            entries.append(details)

        logger.debug('Number of entries found: %d', len(entries))

        return entries

    def load_address(self, url):
        """Extract address from expose itself"""
        expose_soup = self.get_page(url)
        street_raw = ""
        street_el = expose_soup.find(id="street-address")
        if isinstance(street_el, Tag):
            street_raw = street_el.text
        address_raw = ""
        address_el = expose_soup.find(id="viewad-locality")
        if isinstance(address_el, Tag):
            address_raw = address_el.text

        return address_raw.strip().replace("\n", "") + " " + street_raw.strip()
