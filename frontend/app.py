"""FastAPI backend for flathunter frontend"""
import os
import re
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pymongo import MongoClient, DESCENDING
from pymongo.errors import ConnectionFailure
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Flathunter Frontend API")

# MongoDB configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017/")
DB_NAME = "flathunter"
MIN_SIZE_SQM = float(os.getenv("MIN_SIZE_SQM", "12"))

def get_mongo_db():
    """Get MongoDB database connection"""
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ismaster')
        db = client[DB_NAME]
        logger.info(f"Successfully connected to MongoDB at {MONGO_URI}")
        return db
    except ConnectionFailure as e:
        logger.error(f"Could not connect to MongoDB: {e}")
        raise HTTPException(status_code=503, detail="Database connection failed")

def parse_number(value: any) -> Optional[float]:
    """
    Parse a number from various formats (string or numeric).
    Handles both German (1.234,56) and English (1,234.56) number formats.
    """
    if value is None:
        return None
    
    # If already a number, return it
    if isinstance(value, (int, float)):
        return float(value)
    
    # Convert to string for parsing
    value_str = str(value).strip()
    if not value_str:
        return None
    
    # Remove common currency symbols and text
    value_str = value_str.replace('€', '').replace('EUR', '').replace('$', '')
    value_str = value_str.replace('VB', '').replace('Verhandlungsbasis', '')
    value_str = value_str.replace('auf Anfrage', '').replace('m²', '')
    value_str = value_str.replace('qm', '').replace('m2', '').strip()
    
    # Extract number part
    match = re.search(r'[\d.,]+', value_str)
    if not match:
        return None
    
    number_str = match.group()
    
    # Detect format by checking which separator appears last
    # German: 1.234,56 (comma is decimal, period is thousands)
    # English: 1,234.56 (period is decimal, comma is thousands)
    last_comma = number_str.rfind(',')
    last_period = number_str.rfind('.')
    
    try:
        if last_comma > last_period:
            # German format: comma is decimal separator
            # Remove thousand separators (periods) and replace comma with period
            number_str = number_str.replace('.', '').replace(',', '.')
        else:
            # English format or simple number: period is decimal separator
            # Remove thousand separators (commas)
            number_str = number_str.replace(',', '')
        
        return float(number_str)
    except ValueError:
        return None

def parse_price(price_str: str) -> Optional[float]:
    """Parse price string to float, handling various formats"""
    return parse_number(price_str)

def parse_size(size_str: str) -> Optional[float]:
    """Parse size string to float, extracting m² value"""
    return parse_number(size_str)

@app.get("/")
async def read_root():
    """Serve the main HTML page"""
    return FileResponse("static/index.html")

@app.get("/api/debug/collections")
async def debug_collections():
    """Debug endpoint to check MongoDB collections"""
    db = get_mongo_db()
    
    try:
        # Count documents in both collections
        exposes_count = db.exposes.count_documents({})
        processed_count = db.processed_exposes.count_documents({})
        
        # Get sample documents
        sample_expose = db.exposes.find_one()
        sample_processed = db.processed_exposes.find_one()
        
        # List all collections
        all_collections = db.list_collection_names()
        
        return {
            "status": "connected",
            "database": DB_NAME,
            "collections": all_collections,
            "counts": {
                "exposes": exposes_count,
                "processed_exposes": processed_count
            },
            "samples": {
                "expose": {
                    "exists": sample_expose is not None,
                    "fields": list(sample_expose.keys()) if sample_expose else None,
                    "sample_id": str(sample_expose.get('_id')) if sample_expose else None
                },
                "processed_expose": {
                    "exists": sample_processed is not None,
                    "fields": list(sample_processed.keys()) if sample_processed else None,
                    "sample_id": str(sample_processed.get('_id')) if sample_processed else None
                }
            }
        }
    except Exception as e:
        logger.error(f"Debug endpoint error: {e}")
        return {
            "status": "error",
            "error": str(e)
        }

@app.get("/api/statistics")
async def get_statistics():
    """Get statistics about apartments categorized by price per square meter over time"""
    db = get_mongo_db()
    
    # First, try to get processed exposes
    try:
        processed_results = list(db.processed_exposes.find().sort("processed_at", DESCENDING).limit(500))
    except Exception as e:
        logger.warning(f"⚠️  Error querying processed_exposes: {e}")
        processed_results = []
    
    # Fallback to raw exposes if no processed data
    if not processed_results:
        pipeline = [
            {"$sort": {"id": 1, "crawler": 1, "revision": DESCENDING}},
            {"$group": {
                "_id": {"id": "$id", "crawler": "$crawler"},
                "latest_doc": {"$first": "$$ROOT"}
            }},
            {"$replaceRoot": {"newRoot": "$latest_doc"}},
            {"$sort": {"created": DESCENDING}},
            {"$limit": 500}
        ]
        
        try:
            results = list(db.exposes.aggregate(pipeline))
        except Exception as e:
            logger.error(f"Error querying database: {e}")
            raise HTTPException(status_code=500, detail="Database query failed")
        
        apartments_data = []
        for doc in results:
            details = doc.get('details', {})
            price_str = details.get('price', '')
            size_str = details.get('size', '')
            price = parse_price(price_str)
            size = parse_size(size_str)
            
            created_date = doc.get('created')
            if created_date and (size is None or size >= MIN_SIZE_SQM):
                apartments_data.append({
                    'date': created_date,
                    'price': price,
                    'size': size
                })
    else:
        apartments_data = []
        for doc in processed_results:
            def get_field(field_name, fallback=None):
                value = doc.get(field_name)
                if value is None and 'details' in doc:
                    value = doc['details'].get(field_name)
                return value if value is not None else fallback
            
            kaltmiete_raw = get_field('kaltmiete', None)
            warmmiete_raw = get_field('warmmiete', None)
            old_price = get_field('price', None)
            
            price = None
            if kaltmiete_raw:
                price = parse_number(kaltmiete_raw)
            elif warmmiete_raw:
                price = parse_number(warmmiete_raw)
            elif old_price:
                price = parse_number(old_price)
            
            size_sqm = get_field('size_sqm', None)
            old_size = get_field('size', None)
            
            size = None
            if size_sqm:
                size = parse_number(size_sqm)
            elif old_size:
                size = parse_number(old_size)
            
            # Get date - prefer processed_at, fallback to created
            date = doc.get('processed_at') or doc.get('created')
            
            if date and (size is None or size >= MIN_SIZE_SQM):
                apartments_data.append({
                    'date': date,
                    'price': price,
                    'size': size
                })
    
    # Group apartments by date and category
    from collections import defaultdict
    from datetime import datetime
    
    date_stats = defaultdict(lambda: {'niedrig': 0, 'normal': 0, 'hoch': 0})
    total_stats = {'niedrig': 0, 'normal': 0, 'hoch': 0}
    price_per_sqm_values = []
    
    for apt in apartments_data:
        if apt['price'] and apt['size'] and apt['size'] > 0:
            price_per_sqm = apt['price'] / apt['size']
            price_per_sqm_values.append(price_per_sqm)
            
            # Determine category
            if price_per_sqm <= 11:
                category = 'niedrig'
            elif price_per_sqm <= 13:
                category = 'normal'
            else:
                category = 'hoch'
            
            # Increment total stats
            total_stats[category] += 1
            
            # Group by date (day level)
            date = apt['date']
            if isinstance(date, datetime):
                date_key = date.strftime('%Y-%m-%d')
                date_stats[date_key][category] += 1
    
    # Convert to sorted list
    timeline = []
    for date_key in sorted(date_stats.keys()):
        stats = date_stats[date_key]
        timeline.append({
            'date': date_key,
            'niedrig': stats['niedrig'],
            'normal': stats['normal'],
            'hoch': stats['hoch']
        })
    
    mean_price_per_sqm = None
    if price_per_sqm_values:
        mean_price_per_sqm = round(sum(price_per_sqm_values) / len(price_per_sqm_values), 2)
    
    return {
        'total': total_stats,
        'timeline': timeline,
        'mean_eur_per_sqm': mean_price_per_sqm
    }

@app.get("/api/apartments")
async def get_apartments():
    """Get all apartments - prioritize processed_exposes, fallback to raw exposes"""
    db = get_mongo_db()
    
    # Debug: Log collection status
    try:
        exposes_count = db.exposes.count_documents({})
        processed_count = db.processed_exposes.count_documents({})
        logger.info(f"📊 MongoDB Status: exposes={exposes_count}, processed_exposes={processed_count}")
    except Exception as e:
        logger.error(f"❌ Error counting documents: {e}")
    
    # First, try to get processed exposes (with LLM enhancements)
    try:
        processed_results = list(db.processed_exposes.find().sort("processed_at", DESCENDING).limit(500))
        logger.info(f"✅ Retrieved {len(processed_results)} apartments from processed_exposes collection")
        
        # Log sample if available
        if processed_results:
            sample = processed_results[0]
            logger.info(f"📝 Sample processed expose fields: {list(sample.keys())}")
    except Exception as e:
        logger.warning(f"⚠️  Error querying processed_exposes: {e}")
        processed_results = []
    
    # If no processed exposes, fall back to raw exposes
    if not processed_results:
        logger.info("No processed exposes found, falling back to raw exposes collection")
        # Aggregation pipeline to get latest revision of each expose
        pipeline = [
            {"$sort": {"id": 1, "crawler": 1, "revision": DESCENDING}},
            {"$group": {
                "_id": {"id": "$id", "crawler": "$crawler"},
                "latest_doc": {"$first": "$$ROOT"}
            }},
            {"$replaceRoot": {"newRoot": "$latest_doc"}},
            {"$sort": {"created": DESCENDING}},
            {"$limit": 500}  # Limit to most recent 500 apartments
        ]
        
        try:
            results = list(db.exposes.aggregate(pipeline))
            logger.info(f"Retrieved {len(results)} apartments from raw exposes")
        except Exception as e:
            logger.error(f"Error querying database: {e}")
            raise HTTPException(status_code=500, detail="Database query failed")
        
        apartments = []
        for doc in results:
            # Extract expose details
            details = doc.get('details', {})
            
            # Get basic fields
            apt = {
                'id': details.get('id') or doc.get('id'),
                'title': details.get('title', 'N/A'),
                'url': details.get('url', ''),
                'address': details.get('address', 'N/A'),
                'crawler': details.get('crawler') or doc.get('crawler'),
                'created_at': doc.get('created').isoformat() if doc.get('created') else None
            }
            
            # Get image
            apt['image'] = details.get('image')
            
            # Parse price
            price_str = details.get('price', '')
            price = parse_price(price_str)
            apt['price'] = price
            apt['price_str'] = price_str
            
            # Parse size
            size_str = details.get('size', '')
            size = parse_size(size_str)
            apt['size'] = size
            apt['size_str'] = size_str
            
            # Get rooms
            rooms = details.get('rooms', '')
            apt['rooms'] = rooms
            
            # Get coordinates
            apt['latitude'] = details.get('latitude')
            apt['longitude'] = details.get('longitude')
            
            # Calculate price per square meter
            if price and size and size > 0:
                apt['price_per_sqm'] = round(price / size, 2)
                apt['high_rent'] = apt['price_per_sqm'] > 13
            else:
                apt['price_per_sqm'] = None
                apt['high_rent'] = False
            
            if size is None or size >= MIN_SIZE_SQM:
                apartments.append(apt)
    else:
        # Process the LLM-enhanced exposes
        apartments = []
        for doc in processed_results:
            # These docs are already processed by FlatHtmlParser with LLM
            # Data can be at top level or in 'details' subdocument
            
            # Try to get from top level first, then from details
            def get_field(field_name, fallback='N/A'):
                value = doc.get(field_name)
                if value is None and 'details' in doc:
                    value = doc['details'].get(field_name)
                return value if value is not None else fallback
            
            # Extract price fields - kaltmiete, warmmiete, nebenkosten
            kaltmiete_raw = get_field('kaltmiete', None)
            warmmiete_raw = get_field('warmmiete', None)
            nebenkosten_raw = get_field('nebenkosten', None)
            old_price = get_field('price', None)
            
            # Parse numeric values
            kaltmiete = parse_number(kaltmiete_raw) if kaltmiete_raw else None
            warmmiete = parse_number(warmmiete_raw) if warmmiete_raw else None
            nebenkosten = parse_number(nebenkosten_raw) if nebenkosten_raw else None
            
            # Calculate missing fields based on available data
            # kaltmiete = warmmiete - nebenkosten
            # warmmiete = kaltmiete + nebenkosten
            # nebenkosten = warmmiete - kaltmiete
            
            if kaltmiete is None and warmmiete is not None and nebenkosten is not None:
                kaltmiete = warmmiete - nebenkosten
                logger.debug(f"Calculated kaltmiete: {kaltmiete} = {warmmiete} - {nebenkosten}")
            
            if warmmiete is None and kaltmiete is not None and nebenkosten is not None:
                warmmiete = kaltmiete + nebenkosten
                logger.debug(f"Calculated warmmiete: {warmmiete} = {kaltmiete} + {nebenkosten}")
            
            if nebenkosten is None and warmmiete is not None and kaltmiete is not None:
                nebenkosten = warmmiete - kaltmiete
                logger.debug(f"Calculated nebenkosten: {nebenkosten} = {warmmiete} - {kaltmiete}")
            
            # Determine display price and price_str
            price = None
            price_str = 'N/A'
            
            if kaltmiete:
                price = kaltmiete
                price_str = f"{price:.0f} € (Kalt)"
            elif warmmiete:
                price = warmmiete
                price_str = f"{price:.0f} € (Warm)"
            elif old_price:
                price = parse_price(str(old_price))
                if price:
                    price_str = str(old_price)
            
            # Extract size - prefer size_sqm, fallback to old 'size' field
            size_sqm = get_field('size_sqm', None)
            old_size = get_field('size', None)
            
            size = None
            size_str = 'N/A'
            
            if size_sqm:
                size = parse_number(size_sqm)
                if size:
                    size_str = f"{size:.1f} m²"
            
            # Fallback to old size field
            if size is None and old_size:
                size = parse_number(old_size)
                if size:
                    size_str = str(old_size)
            
            apt = {
                'id': get_field('id', 'unknown'),
                'title': get_field('title', 'N/A'),
                'url': get_field('url', ''),
                'address': get_field('address', 'N/A'),
                'crawler': get_field('crawler', 'N/A'),
                'created_at': doc.get('processed_at').isoformat() if doc.get('processed_at') else 
                              (doc.get('created').isoformat() if doc.get('created') else None),
                'image': get_field('image', None),
                'price': price,
                'price_str': price_str,
                'kaltmiete': kaltmiete,
                'warmmiete': warmmiete,
                'nebenkosten': nebenkosten,
                'size': size,
                'size_str': size_str,
                'rooms': str(get_field('rooms', 'N/A')),
                'latitude': get_field('latitude', None),
                'longitude': get_field('longitude', None),
                'furnished': get_field('furnished', 'N/A')
            }
            
            # Calculate price per square meter
            if price and size and size > 0:
                apt['price_per_sqm'] = round(price / size, 2)
                apt['high_rent'] = apt['price_per_sqm'] > 13
            else:
                apt['price_per_sqm'] = None
                apt['high_rent'] = False
            
            if size is None or size >= MIN_SIZE_SQM:
                apartments.append(apt)
    
    logger.info(f"Returning {len(apartments)} processed apartments")
    return apartments

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

