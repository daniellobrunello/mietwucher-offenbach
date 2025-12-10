"""Expose crawler for ImmoWelt"""
import re
import datetime
import hashlib

from bs4 import BeautifulSoup, Tag

from flathunter.logging_fh import logger
from flathunter.abstract_crawler import Crawler

class Immowelt(Crawler):
    """Implementation of Crawler interface for ImmoWelt"""

    URL_PATTERN = re.compile(r'https://www\.immowelt\.de')

    def __init__(self, config):
        super().__init__(config)
        self.config = config

    def get_entry_html(self, entry_url):
        """Applies a page number to a formatted search URL and fetches the exposes at that page"""
        return str(self.get_soup_from_url(
            entry_url
        ))

    def get_expose_details(self, expose):
        """Loads additional details for an expose by processing the expose detail URL"""
        # Fetch detail page with proper page_type for debug saving
        soup = self.get_soup_from_url(expose['url'], page_type="detail")
        
        # Initialize flexible storage structures
        if 'features' not in expose:
            expose['features'] = {}
        if 'amenities' not in expose:
            expose['amenities'] = []
        
        # CRITICAL: Extract price from detail page
        # Price can be in multiple locations on Immowelt detail pages
        price_elem = soup.find("div", {"data-test": "price"})
        if not price_elem:
            price_elem = soup.find("strong", {"data-test": "price-value"})
        if not price_elem:
            # Try to find it in meta tags
            price_meta = soup.find("meta", {"property": "price:amount"})
            if price_meta:
                price_elem = price_meta
        
        if price_elem:
            if price_elem.name == 'meta':
                price_text = price_elem.get('content', '')
            else:
                price_text = price_elem.get_text(strip=True)
            # Clean up price text - remove currency symbols and extra text
            price_text = re.sub(r'[^\d,.]', '', price_text).replace(',', '.')
            if price_text:
                expose['price'] = price_text + ' €'
                logger.debug(f"Extracted price from detail page: {expose['price']}")
        
        # Set default availability date
        date = datetime.datetime.now().strftime("%2d.%2m.%Y")
        expose['from'] = date

        # Extract availability date from equipment section
        immo_div = soup.find("app-estate-object-informations")
        if isinstance(immo_div, Tag):
            immo_div = soup.find("div", {"class": "equipment ng-star-inserted"})
            if isinstance(immo_div, Tag):
                details = immo_div.find_all("p")
                for detail in details:
                    if detail.text.strip() == "Bezug":
                        date = detail.findNext("p").text.strip()
                        no_exact_date_given = re.match(
                            r'.*sofort.*|.*Nach Vereinbarung.*',
                            date,
                            re.MULTILINE|re.DOTALL|re.IGNORECASE
                        )
                        if no_exact_date_given:
                            date = datetime.datetime.now().strftime("%2d.%2m.%Y")
                        break
                expose['from'] = date
        
        # Extract description
        description_elem = soup.find("div", {"data-test": "estate-description"})
        if not description_elem:
            description_elem = soup.find("div", {"class": "description"})
        if description_elem:
            expose['description'] = description_elem.get_text(strip=True)
        
        # Extract all key facts and details
        keyfacts = soup.find_all("div", {"data-test": "estate-key-fact"})
        for keyfact in keyfacts:
            try:
                label_elem = keyfact.find("div", {"class": "key-fact-label"})
                value_elem = keyfact.find("div", {"class": "key-fact-value"})
                
                if label_elem and value_elem:
                    label = label_elem.get_text(strip=True)
                    value = value_elem.get_text(strip=True)
                    
                    # Map common fields
                    if 'Etage' in label or 'Stockwerk' in label:
                        expose['features']['floor'] = value
                    elif 'Baujahr' in label:
                        expose['features']['building_year'] = value
                    elif 'Kaution' in label or 'Deposit' in label:
                        expose['features']['deposit'] = value
                    elif 'Nebenkosten' in label:
                        expose['features']['additional_costs'] = value
                    elif 'Heizkosten' in label:
                        expose['features']['heating_costs'] = value
                    elif 'Wohnfläche' in label or 'Fläche' in label:
                        # CRITICAL: Extract size from detail page and update main size field
                        size_match = re.search(r'(\d+[.,]?\d*)\s*m', value)
                        if size_match:
                            size_value = size_match.group(1).replace(',', '.')
                            expose['size'] = f"{size_value} m²"
                            logger.debug(f"Extracted size from detail page: {expose['size']}")
                        expose['features']['living_space'] = value
                    elif 'Zimmer' in label:
                        # CRITICAL: Extract rooms from detail page
                        rooms_match = re.search(r'(\d+[.,]?\d*)', value)
                        if rooms_match:
                            expose['rooms'] = rooms_match.group(1).replace(',', '.')
                            logger.debug(f"Extracted rooms from detail page: {expose['rooms']}")
                        expose['features']['rooms_detail'] = value
                    elif 'Heizung' in label:
                        expose['features']['heating_type'] = value
                    elif 'Energieeffizienz' in label:
                        expose['features']['energy_class'] = value
                    elif 'Energieverbrauch' in label or 'Endenergie' in label:
                        expose['features']['energy_consumption'] = value
                    elif 'Energieausweis' in label:
                        expose['features']['energy_certificate'] = value
                    else:
                        # Store any other fields with sanitized key
                        key = label.lower().replace(' ', '_').replace(':', '').replace('-', '_')
                        if key and value:
                            expose['features'][key] = value
            except AttributeError:
                continue
        
        # Extract equipment/amenities
        equipment_section = soup.find("app-estate-object-informations")
        if isinstance(equipment_section, Tag):
            # Look for equipment items
            equipment_items = equipment_section.find_all("span")
            for item in equipment_items:
                text = item.get_text(strip=True)
                if text and len(text) > 2 and text not in expose['amenities']:
                    expose['amenities'].append(text)
        
        # Extract detailed property information from structured sections
        info_sections = soup.find_all("div", {"class": "equipment ng-star-inserted"})
        for section in info_sections:
            p_tags = section.find_all("p")
            for i in range(0, len(p_tags) - 1, 2):
                try:
                    label = p_tags[i].get_text(strip=True)
                    value = p_tags[i + 1].get_text(strip=True)
                    
                    if label and value:
                        # Map or store fields
                        if 'Bezug' in label:
                            continue  # Already handled
                        elif 'Etage' in label:
                            expose['features']['floor'] = value
                        elif 'Bad' in label or 'Badezimmer' in label:
                            expose['features']['bathroom'] = value
                        elif 'Schlafzimmer' in label:
                            expose['features']['bedrooms'] = value
                        elif 'Haustiere' in label:
                            expose['features']['pets'] = value
                        else:
                            key = label.lower().replace(' ', '_').replace(':', '').replace('-', '_')
                            if key and value:
                                expose['features'][key] = value
                except (AttributeError, IndexError):
                    continue
        
        # Look for specific amenity keywords in the page text
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
            'Waschmaschine': 'washing_machine',
            'Geschirrspüler': 'dishwasher',
            'Kabel-TV': 'cable_tv',
            'Internet': 'internet',
            'WLAN': 'wifi',
            'Fußbodenheizung': 'floor_heating',
            'Zentralheizung': 'central_heating'
        }
        
        page_text = soup.get_text()
        for keyword, amenity_name in amenity_keywords.items():
            if keyword in page_text and amenity_name not in expose['amenities']:
                expose['amenities'].append(amenity_name)
        
        # Extract additional price information if available
        price_section = soup.find("div", {"data-test": "price-information"})
        if price_section:
            price_items = price_section.find_all("div")
            for item in price_items:
                text = item.get_text(strip=True)
                if 'Kaltmiete' in text:
                    expose['features']['base_rent'] = text
                elif 'Warmmiete' in text or 'Gesamtmiete' in text:
                    expose['features']['total_rent'] = text
        
        return expose

    # pylint: disable=too-many-locals
    def extract_data(self, soup: BeautifulSoup):
        """Extracts all exposes from a provided Soup object"""
        entries = []
        soup_res = soup
        if not isinstance(soup_res, Tag):
            return []

        advertisements = soup_res.find_all("div", attrs={"class": "css-79elbk"})
        for adv in advertisements:
            try:
                title = adv.find("div", {"class": "css-1cbj9xw"}).text
            except AttributeError:
                title = ""

            try:
                price = adv.find(
                    "div", attrs={"data-testid": "cardmfe-price-testid"}).text
            except AttributeError:
                price = ""

            try:
                descriptions = adv.find("div",
                    attrs={"data-testid": "cardmfe-keyfacts-testid"}).children
                descriptions = [result.text for result in descriptions]
            except AttributeError:
                descriptions = []

            size = list(filter(lambda x: "m²" in x, descriptions))
            try:
                size = size[0]
            except IndexError:
                size = ""

            rooms = list(filter(lambda x: "Zimmer" in x, descriptions))
            try:
                rooms = rooms[0]
            except IndexError:
                rooms = ""

            id_element = adv.find("a")
            try:
                url = id_element.get("href")
                if "https" not in url:
                    url = "https://immowelt.de/" + url
            except IndexError:
                continue

            picture = adv.find("img")
            image = None
            if picture:
                image = picture.get('src')

            try:
                address = adv.find(
                    "div", attrs={"data-testid": "cardmfe-description-box-address"}
                  ).text
            except (IndexError, AttributeError):
                address = ""
            ad_id = url.split('/')[-1]
            processed_id = int(
              hashlib.sha256(ad_id.encode('utf-8')).hexdigest(), 16
            ) % 10**16

            details = {
                'id': processed_id,
                'image': image,
                'url': url,
                'title': title.strip(),
                'rooms': rooms,
                'price': price,
                'size': size,
                'address': address,
                'crawler': self.get_name()
            }
            entries.append(details)

        logger.debug('Number of entries found: %d', len(entries))
        return entries
