#!/usr/bin/env python3
"""
Continuous processor for exposes - runs LLM enhancement periodically
This script continuously processes new exposes from MongoDB and enhances them with LLM extraction
"""
import os
import sys
import time
import logging
from datetime import datetime
from dotenv import load_dotenv

# Add flathunter to path
sys.path.insert(0, os.path.dirname(__file__))

from flathunter.process_exposes import ExposeProcessor

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Main loop for continuous expose processing"""
    # Get configuration from environment variables
    mongo_uri = os.getenv('MONGODB_URI', os.getenv('MONGO_URI', 'mongodb://mongodb:27017/'))
    db_name = os.getenv('MONGODB_DB', 'flathunter')
    openai_api_key = os.getenv('OPENAI_API_KEY')
    
    # Processing interval in seconds (default: 5 minutes)
    interval = int(os.getenv('PROCESSING_INTERVAL', '300'))
    
    # Days to look back for exposes (default: 7 days)
    days_back = int(os.getenv('PROCESSING_DAYS_BACK', '7'))
    
    # Validate required environment variables
    if not mongo_uri:
        logger.error("Required environment variable MONGODB_URI or MONGO_URI is not set")
        sys.exit(1)
    
    if not openai_api_key:
        logger.warning("OPENAI_API_KEY is not set - LLM enhancement will be disabled")
    
    logger.info("="*80)
    logger.info("🤖 EXPOSE LLM PROCESSOR STARTED")
    logger.info("="*80)
    logger.info(f"MongoDB URI: {mongo_uri}")
    logger.info(f"Database: {db_name}")
    logger.info(f"OpenAI API Key: {'✅ Configured' if openai_api_key else '❌ Not configured'}")
    logger.info(f"Processing interval: {interval} seconds ({interval/60:.1f} minutes)")
    logger.info(f"Looking back: {days_back} days")
    logger.info("="*80 + "\n")
    
    # Initialize processor
    try:
        processor = ExposeProcessor(mongo_uri, db_name, openai_api_key)
        logger.info("✅ Processor initialized successfully\n")
    except Exception as e:
        logger.error(f"❌ Failed to initialize processor: {e}")
        sys.exit(1)
    
    # Main processing loop
    cycle = 0
    while True:
        cycle += 1
        try:
            logger.info(f"\n{'='*80}")
            logger.info(f"🔄 PROCESSING CYCLE #{cycle} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"{'='*80}\n")
            
            # Process exposes
            processed_exposes = processor.process_exposes(days_back=days_back)
            
            if processed_exposes:
                # Save to MongoDB
                saved_count = processor.save_processed_exposes(processed_exposes, "processed_exposes")
                
                logger.info(f"\n✅ CYCLE #{cycle} COMPLETE")
                logger.info(f"   Processed: {len(processed_exposes)} exposes")
                logger.info(f"   Saved: {saved_count} exposes")
                
                # Show summary of first few
                if len(processed_exposes) > 0:
                    logger.info(f"\n📊 Sample of processed exposes:")
                    for expose in processed_exposes[:3]:
                        logger.info(f"   • {expose.get('title', 'N/A')}")
                        logger.info(f"     Kaltmiete: {expose.get('kaltmiete', 'N/A')} | "
                                  f"Warmmiete: {expose.get('warmmiete', 'N/A')} | "
                                  f"Size: {expose.get('size_sqm', 'N/A')} m² | "
                                  f"Furnished: {expose.get('furnished', 'N/A')}")
            else:
                logger.info(f"\n✅ CYCLE #{cycle} COMPLETE")
                logger.info(f"   No new exposes to process")
            
        except KeyboardInterrupt:
            logger.info("\n\n⚠️  Received interrupt signal - shutting down gracefully...")
            break
        except Exception as e:
            logger.error(f"\n❌ Error in processing cycle #{cycle}: {e}", exc_info=True)
            logger.info("   Will retry in next cycle...")
        
        # Wait for next cycle
        logger.info(f"\n💤 Sleeping for {interval} seconds ({interval/60:.1f} minutes)...")
        logger.info(f"   Next cycle at: {datetime.fromtimestamp(time.time() + interval).strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*80}\n")
        
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("\n\n⚠️  Received interrupt signal - shutting down gracefully...")
            break
    
    logger.info("\n👋 Processor stopped cleanly\n")

if __name__ == '__main__':
    main()

