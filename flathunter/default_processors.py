"""Built-in expose processor implementations. Used by the processor pipelines
   in flathunter and in the webservice"""
import re
import time # Import time for sleep
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

from flathunter.logging_fh import logger
from flathunter.abstract_processor import Processor

class GetPageHTMLProcessor(Processor):
    """Fetches and stores raw HTML from listing detail pages"""

    def __init__(self, config):
        self.config = config

    def process_expose(self, expose):
        url = expose['url']
        for searcher in self.config.searchers():
            if re.search(searcher.URL_PATTERN, url):
                expose['html'] = searcher.get_entry_html(url)
                logger.debug("Loaded address %s for url %s", expose['address'], url)
                break
        return expose

class Filter(Processor):
    """Filter processor implementation. Applies a filter to the list of exposes"""

    def __init__(self, config, filter_set):
        self.config = config
        self.filter = filter_set

    def process_exposes(self, exposes):
        return self.filter.filter(exposes)

class AddressResolver(Processor):
    """Processor to extract apartment addresses from expose links"""

    def __init__(self, config):
        self.config = config

    def process_expose(self, expose):
        """Fetches the expose from the expose URL and extracts the address"""
        if expose['address'].startswith('http'):
            url = expose['address']
            for searcher in self.config.searchers():
                if re.search(searcher.URL_PATTERN, url):
                    expose['address'] = searcher.load_address(url)
                    logger.debug("Loaded address %s for url %s", expose['address'], url)
                    break
        return expose
    
class AddressGeocode(Processor):
    """Processor to geocode addresses, attempting variations for potentially ambiguous strings."""

    def __init__(self, config):
        self.config = config
        # Initialize the geocoder once per processor instance
        # Provide a descriptive user_agent as required by Nominatim's policy
        self.geolocator = Nominatim(user_agent="flathunter-offenbach")

    def _generate_potential_addresses(self, address_str: str) -> list[str]:
        """Generates potential address variations from a possibly ambiguous string."""
        parts = [part.strip() for part in address_str.split(',') if part.strip()]
        
        if len(parts) <= 1:
            # Cannot split meaningfully or only one part, return original
            return [address_str] 
        
        # Assuming the last part is the most stable (e.g., city/region)
        last_part = parts[-1]
        main_parts = parts[:-1]
        
        potential_addresses = []

        # 1. Preferred: First part + Last Part (e.g., "Street, City")
        if main_parts:
            potential_addresses.append(f"{main_parts[0]}, {last_part}")

        # 2. Original address (if different from preferred)
        if address_str not in potential_addresses:
             potential_addresses.append(address_str)

        # 3. Other parts + Last Part (e.g., "POI, City")
        if len(main_parts) > 1:
            for i in range(1, len(main_parts)):
                 candidate = f"{main_parts[i]}, {last_part}"
                 if candidate not in potential_addresses:
                     potential_addresses.append(candidate)

        # Use dict.fromkeys to remove duplicates while preserving order
        return list(dict.fromkeys(potential_addresses))

    def process_expose(self, expose):
        """Fetches the lat long from the address, trying multiple variations."""
        address = expose.get('address') # Use .get for safety
        expose_id = expose.get('id', 'N/A') # Get ID for logging

        expose['latitude'] = None
        expose['longitude'] = None

        if not address or not isinstance(address, str) or address.startswith('http'):
            logger.debug(f"Skipping geocoding for expose {expose_id}: No valid address string found ('{address}').")
            return expose

        logger.debug(f"Attempting geocoding for expose {expose_id}: Original address '{address}'")
        
        potential_addresses = self._generate_potential_addresses(address)
        location = None

        for potential_addr in potential_addresses:
            if not potential_addr: continue # Skip empty candidates

            logger.debug(f"Trying potential address for expose {expose_id}: '{potential_addr}'")
            try:
                # Add a delay to comply with Nominatim's usage policy (1 req/sec)
                time.sleep(1.1) # Sleep for slightly over 1 second

                location = self.geolocator.geocode(potential_addr, timeout=10) # Added timeout

                if location:
                    expose['latitude'] = location.latitude
                    expose['longitude'] = location.longitude
                    logger.info(f"Successfully geocoded expose {expose_id} using '{potential_addr}' to: ({location.latitude}, {location.longitude})")
                    break # Found a valid location, stop trying other variations
                else:
                    logger.debug(f"Could not geocode potential address '{potential_addr}' for expose {expose_id}.")

            except GeocoderTimedOut:
                logger.warning(f"Geocoding service timed out for potential address '{potential_addr}' (expose {expose_id})")
                # Continue to the next potential address
            except GeocoderServiceError as e:
                logger.warning(f"Geocoding service error for potential address '{potential_addr}' (expose {expose_id}'): {e}")
                # Continue to the next potential address
            except Exception as e:
                # Catch any other unexpected errors during geocoding
                logger.error(f"Unexpected error during geocoding for potential address '{potential_addr}' (expose {expose_id}'): {e}")
                # Continue cautiously, maybe log more details?
        
        if not location:
            logger.warning(f"Could not geocode any variation of address for expose {expose_id}: '{address}'")
            
        return expose

class CrawlExposeDetails(Processor):
    """Processor to extract additional apartment details by parsing page at expose URL"""

    def __init__(self, config):
        self.config = config

    def process_expose(self, expose):
        """Fetches the page at exposes['url'] and extracts additional details from it"""
        for searcher in self.config.searchers():
            if re.search(searcher.URL_PATTERN, expose['url']):
                expose = searcher.get_expose_details(expose)
        return expose

class LambdaProcessor(Processor):
    """Processor to apply arbitrary logic to each expose"""

    def __init__(self, config, func):
        self.config = config
        self.func = func

    def process_expose(self, expose):
        """Apply the lambda function to each expose"""
        res = self.func(expose)
        return res
