import os
import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

from flathunter.idmaintainer_mongo import IdMaintainer
from flathunter.html_parser import FlatHtmlParser

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ExposeProcessor:
    """Processes exposes from MongoDB using FlatHtmlParser"""

    def __init__(self, mongo_uri: str, db_name: str, openai_api_key: str = None):
        """
        Initialize the processor with MongoDB connection and HTML parser
        
        Args:
            mongo_uri: MongoDB connection URI
            db_name: Name of the database
            openai_api_key: Optional OpenAI API key for enhanced parsing
        """
        self.id_maintainer = IdMaintainer(mongo_uri, db_name)
        self.html_parser = FlatHtmlParser(openai_api_key=openai_api_key)
        self.db = self.id_maintainer.get_connection()
        logger.info("ExposeProcessor initialized with MongoDB and HTML parser")

    def process_exposes(self, days_back: int = 7) -> List[Dict[str, Any]]:
        """
        Process exposes from the last N days
        
        Args:
            days_back: Number of days to look back for exposes
            
        Returns:
            List of processed exposes with enhanced data
        """
        # Calculate the date to fetch exposes from
        min_date = datetime.now() - timedelta(days=days_back)
        logger.info(f"Fetching exposes since {min_date}")
        
        # Get exposes from MongoDB
        exposes = self.id_maintainer.get_exposes_since(min_date)
        logger.info(f"Found {len(exposes)} exposes to process")
        
        processed_exposes = []
        for expose in exposes:
            try:
                # Process the HTML content
                html_content = expose.get('html')
                if not html_content:
                    logger.warning(f"Expose {expose.get('id')} has no HTML content")
                    continue
                
                # Extract details using the HTML parser
                # Note: HTML parser does NOT overwrite the title - crawler titles are preserved
                original_title = expose.get('title', 'N/A')
                logger.info(f"Processing expose {expose.get('id')} - Crawler title: '{original_title}'")
                
                enhanced_details = self.html_parser.extract_details(
                    html_content=html_content,
                    url=expose.get('url')
                )

                # Preserve crawler-provided title when parser returns None
                title_fallback = expose.get('title')
                if title_fallback is None and 'details' in expose:
                    title_fallback = expose['details'].get('title')
                if enhanced_details.get('title') is None and title_fallback:
                    enhanced_details['title'] = title_fallback
                
                # Merge the enhanced details with the original expose
                # Crawler-provided fields (like title) are NOT overwritten by HTML parser
                processed_expose = expose.copy()
                for key, value in enhanced_details.items():
                    if value is not None:
                        processed_expose[key] = value

                # Normalize size_sqm from crawler size string to avoid locale issues
                size_text = expose.get('size')
                if size_text is None and 'details' in expose:
                    size_text = expose['details'].get('size')
                size_text = size_text or expose.get('size_sqm')
                if size_text is None and 'details' in expose:
                    size_text = expose['details'].get('size_sqm')

                parsed_size = self._parse_number(size_text)
                if parsed_size is not None:
                    processed_expose['size_sqm'] = parsed_size
                elif 'size_sqm' in processed_expose:
                    processed_expose['size_sqm'] = None

                
                processed_exposes.append(processed_expose)
                
                logger.info(f"Successfully processed expose {expose.get('id')}")
                
            except Exception as e:
                logger.error(f"Error processing expose {expose.get('id')}: {e}")
                continue
        
        return processed_exposes

    def _parse_number(self, value: Optional[str]) -> Optional[float]:
        """Parse German/English formatted numbers like 40,21 or 1.234,56."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)

        value_str = str(value).strip()
        if not value_str:
            return None

        value_str = value_str.replace('m²', '').replace('m2', '').replace('qm', '')
        match = re.search(r'[\d.,]+', value_str)
        if not match:
            return None

        number_str = match.group()
        last_comma = number_str.rfind(',')
        last_period = number_str.rfind('.')

        try:
            if last_comma > last_period:
                number_str = number_str.replace('.', '').replace(',', '.')
            else:
                number_str = number_str.replace(',', '')
            return float(number_str)
        except ValueError:
            return None


    def save_processed_exposes(self, processed_exposes: List[Dict[str, Any]], collection_name: str = "processed_exposes") -> int:
        """
        Save processed exposes to a new MongoDB collection
        
        Args:
            processed_exposes: List of processed exposes to save
            collection_name: Name of the collection to save to
            
        Returns:
            Number of exposes successfully saved
        """
        if not processed_exposes:
            logger.info("No processed exposes to save")
            return 0
        
        saved_count = 0
        for expose in processed_exposes:
            try:
                # Add processing metadata
                expose_to_save = expose.copy()
                expose_to_save['processed_at'] = datetime.now()
                expose_to_save['processing_version'] = '1.0'  # Version tracking for future compatibility
                
                # Use expose ID as unique identifier to avoid duplicates
                expose_id = expose.get('id')
                if not expose_id:
                    logger.warning("Expose missing ID, skipping save")
                    continue
                
                # Upsert to avoid duplicates
                result = self.db[collection_name].update_one(
                    {"id": expose_id},
                    {"$set": expose_to_save},
                    upsert=True
                )
                
                if result.upserted_id or result.modified_count > 0:
                    saved_count += 1
                    logger.debug(f"Saved processed expose {expose_id} to collection '{collection_name}'")
                
            except Exception as e:
                logger.error(f"Error saving processed expose {expose.get('id')}: {e}")
                continue
        
        logger.info(f"Successfully saved {saved_count} processed exposes to collection '{collection_name}'")
        return saved_count

    def get_processed_exposes(self, collection_name: str = "processed_exposes", limit: int = None) -> List[Dict[str, Any]]:
        """
        Retrieve processed exposes from the collection
        
        Args:
            collection_name: Name of the collection to read from
            limit: Maximum number of exposes to retrieve (None for all)
            
        Returns:
            List of processed exposes
        """
        try:
            query = {}
            cursor = self.db[collection_name].find(query).sort("processed_at", -1)
            
            if limit:
                cursor = cursor.limit(limit)
            
            processed_exposes = list(cursor)
            logger.info(f"Retrieved {len(processed_exposes)} processed exposes from collection '{collection_name}'")
            return processed_exposes
            
        except Exception as e:
            logger.error(f"Error retrieving processed exposes: {e}")
            return []

def main():
    """Main function to run the expose processor"""
    # Get configuration from environment variables
    mongo_uri = os.getenv('MONGODB_URI')
    db_name = os.getenv('MONGODB_DB')
    openai_api_key = os.getenv('OPENAI_API_KEY')
    
    # Validate required environment variables
    if not mongo_uri or not db_name:
        logger.error("Required environment variables MONGODB_URI and MONGODB_DB are not set")
        return
    
    # Initialize and run the processor
    processor = ExposeProcessor(mongo_uri, db_name, openai_api_key)
    processed_exposes = processor.process_exposes(days_back=7)
    
    # Log results
    logger.info(f"Processing complete. Successfully processed {len(processed_exposes)} exposes")
    
    # Save processed exposes to new MongoDB collection
    if processed_exposes:
        saved_count = processor.save_processed_exposes(processed_exposes, "processed_exposes")
        logger.info(f"Saved {saved_count} processed exposes to MongoDB collection 'processed_exposes'")
    
    # Example: Print some statistics about the processed exposes
    for expose in processed_exposes[:5]:  # Show first 5 as example
        logger.info(f"Expose {expose.get('id')}:")
        logger.info(f"  Title: {expose.get('title')}")
        logger.info(f"  Price: {expose.get('price')}")
        logger.info(f"  Size: {expose.get('size_sqm')} m²")
        logger.info(f"  Rooms: {expose.get('rooms')}")
        logger.info(f"  Address: {expose.get('address')}")
        logger.info("---")

if __name__ == '__main__':
    main() 