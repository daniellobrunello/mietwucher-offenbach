"""MongoDB implementation of IDMaintainer interface"""
import datetime
import json
from pymongo import MongoClient, DESCENDING
from pymongo.errors import ConnectionFailure, OperationFailure, ServerSelectionTimeoutError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from flathunter.logging_fh import logger
from flathunter.abstract_processor import Processor

__author__ = "Nody"
__version__ = "0.2"
__maintainer__ = "Nody"
__email__ = "harrymcfly@protonmail.com"
__status__ = "Production"

class SaveAllExposesProcessor(Processor):
    """Processor that saves all exposes to the database"""

    def __init__(self, config, id_watch):
        self.config = config
        self.id_watch = id_watch

    def process_expose(self, expose):
        """Save a single expose"""
        self.id_watch.save_expose(expose)
        return expose

class IdMaintainer:
    """MongoDB back-end for the database"""

    def __init__(self, mongo_uri, db_name):
        """Initializes the MongoDB connection."""
        self.mongo_uri = mongo_uri
        self.db_name = db_name
        self.client = None
        self.db = None
        self._connect()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionFailure, ServerSelectionTimeoutError)),
        before_sleep=lambda retry_state: logger.warning(
            f"MongoDB connection failed (attempt {retry_state.attempt_number}), retrying..."
        )
    )
    def _connect(self):
        """Establishes the MongoDB connection and selects the database."""
        if self.client is None:
            try:
                self.client = MongoClient(
                    self.mongo_uri, 
                    serverSelectionTimeoutMS=5000,
                    maxPoolSize=50,  # Connection pooling
                    minPoolSize=10,
                    maxIdleTimeMS=45000,
                    retryWrites=True  # Automatic retry for write operations
                )
                # The ismaster command is cheap and does not require auth.
                self.client.admin.command('ismaster')
                self.db = self.client[self.db_name]
                self._ensure_indexes()
                logger.info(f"Successfully connected to MongoDB database '{self.db_name}'.")
            except (ConnectionFailure, ServerSelectionTimeoutError) as e:
                logger.error(f"Could not connect to MongoDB: {e}")
                self.client = None
                self.db = None
                raise # Re-raise the exception to signal connection failure

    def _ensure_indexes(self):
        """Ensures necessary indexes exist in the collections."""
        if self.db is None:
            logger.error("Cannot ensure indexes without a database connection.")
            return
        try:
            # Index for faster lookups of latest revisions
            # Use explicit integer values: -1 for descending, 1 for ascending
            self.db.exposes.create_index([("id", -1), ("crawler", -1), ("revision", -1)])
            # Index for get_exposes_since
            self.db.exposes.create_index([("created", -1)])
            # Index for processed checks
            self.db.processed.create_index("expose_id", unique=True)
            # Index for user lookups
            self.db.users.create_index("user_id", unique=True)
            # Index for last run time
            self.db.executions.create_index([("timestamp", -1)])
            logger.info("MongoDB indexes ensured.")
        except Exception as e: # Catch potential errors during index creation
             logger.error(f"Error creating MongoDB indexes: {e}")
             # Decide if this should halt execution or just log

    def get_connection(self):
        """Returns the database object. Ensures connection is active."""
        if self.client is None or self.db is None:
            logger.warning("MongoDB connection lost or not established. Attempting to reconnect...")
            self._connect() # Try to reconnect
        elif not self._is_connected():
             logger.warning("MongoDB connection check failed. Attempting to reconnect...")
             self._connect()

        if self.db is None:
             raise ConnectionFailure("Failed to establish MongoDB connection.")
        return self.db

    def _is_connected(self):
        """Checks if the MongoDB client is still connected."""
        if not self.client:
            return False
        try:
            # The ismaster command is cheap and does not require auth.
            self.client.admin.command('ismaster')
            return True
        except ConnectionFailure:
            return False

    def is_processed(self, expose_id):
        """Returns true if an expose has already been processed"""
        logger.debug('is_processed(%d)', expose_id)
        db = self.get_connection()
        return db.processed.find_one({"expose_id": expose_id}) is not None

    def mark_processed(self, expose_id):
        """Mark an expose as processed in the database"""
        logger.debug('mark_processed(%d)', expose_id)
        db = self.get_connection()
        try:
            # Use update_one with upsert=True to avoid duplicates if called multiple times
            db.processed.update_one(
                {"expose_id": expose_id},
                {"$setOnInsert": {"expose_id": expose_id, "processed_at": datetime.datetime.now()}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error marking expose {expose_id} as processed: {e}")
            # Decide on error handling: raise e?

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type((ConnectionFailure, OperationFailure, ServerSelectionTimeoutError)),
        before_sleep=lambda retry_state: logger.warning(
            f"MongoDB save_expose operation failed (attempt {retry_state.attempt_number}), retrying..."
        )
    )
    def save_expose(self, expose):
        """Saves an expose revision to the database if HTML content has changed."""
        try:
            db = self.get_connection()
            expose_id = int(expose['id'])
            crawler = expose['crawler']
            new_html = expose.get('html')
            # Store the whole expose dict directly as 'details'
            # We add creation time and revision separately for indexing/querying
            new_details = expose.copy() # Avoid modifying original dict

            # Find the latest revision and its HTML
            latest_rev_doc = db.exposes.find_one(
                {"id": expose_id, "crawler": crawler},
                sort=[("revision", DESCENDING)]
            )

            latest_revision = -1
            needs_insert = True
            if latest_rev_doc:
                latest_revision = latest_rev_doc.get('revision', -1)
                latest_html = latest_rev_doc.get('html') # Check if html exists in the doc
                if new_html == latest_html:
                    needs_insert = False # HTML is the same, don't insert new revision

            if needs_insert:
                new_revision = latest_revision + 1
                doc_to_insert = {
                    "id": expose_id,
                    "crawler": crawler,
                    "created": datetime.datetime.now(),
                    "details": new_details, # Store the full original expose data
                    "html": new_html,
                    "revision": new_revision
                }
                db.exposes.insert_one(doc_to_insert)
                logger.debug(f"Inserted revision {new_revision} for expose {expose_id} ({crawler})")
            else:
                logger.debug(f"HTML unchanged for expose {expose_id} ({crawler}), revision {latest_revision} is current.")
        except (ConnectionFailure, OperationFailure, ServerSelectionTimeoutError):
            # Let the retry decorator handle these
            raise
        except Exception as e:
            # Log other errors but don't retry
            logger.error(f"Unexpected error saving expose {expose.get('id')}: {e}", exc_info=True)
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type((ConnectionFailure, OperationFailure, ServerSelectionTimeoutError)),
        before_sleep=lambda retry_state: logger.warning(
            f"MongoDB get_exposes_since operation failed (attempt {retry_state.attempt_number}), retrying..."
        )
    )
    def get_exposes_since(self, min_datetime):
        """Loads the latest revision of all exposes created since the specified date."""
        try:
            db = self.get_connection()

            # Use aggregation pipeline to get the latest revision for each (id, crawler)
            # and then filter by creation date.
            pipeline = [
                # Sort by revision descending to easily pick the latest
                {"$sort": {"id": 1, "crawler": 1, "revision": DESCENDING}},
                # Group by id and crawler, taking the first document (which is the latest revision)
                {"$group": {
                    "_id": {"id": "$id", "crawler": "$crawler"},
                    "latest_doc": {"$first": "$$ROOT"}
                }},
                # Replace the root with the latest document
                {"$replaceRoot": {"newRoot": "$latest_doc"}},
                # Filter documents created since min_datetime
                {"$match": {"created": {"$gte": min_datetime}}},
                # Sort the final results by creation date descending
                {"$sort": {"created": DESCENDING}}
            ]

            results = list(db.exposes.aggregate(pipeline))

            # Convert BSON documents back to expose-like dicts
            # The 'details' field already holds most of the original expose structure
            exposes = []
            for doc in results:
                expose_obj = doc['details'] # Start with the stored details
                expose_obj['created_at'] = doc['created'] # Add the timestamp of this revision entry
                expose_obj['revision'] = doc['revision'] # Add the revision number
                # expose_obj['html'] = doc['html'] # Optionally include HTML if needed downstream
                exposes.append(expose_obj)
            
            logger.debug(f"Retrieved {len(exposes)} exposes since {min_datetime}")
            return exposes
        except (ConnectionFailure, OperationFailure, ServerSelectionTimeoutError):
            # Let the retry decorator handle these
            raise
        except Exception as e:
            # Log other errors but don't retry
            logger.error(f"Unexpected error retrieving exposes since {min_datetime}: {e}", exc_info=True)
            # Return empty list on error for graceful degradation
            return []

    def get_recent_exposes(self, count, filter_set=None):
        """Returns up to 'count' recent exposes (latest revision only), filtered by the provided filter"""
        db = self.get_connection()

        # Aggregation pipeline to get the latest revision of each expose, ordered by creation time
        pipeline = [
            {"$sort": {"id": 1, "crawler": 1, "revision": DESCENDING}},
            {"$group": {
                "_id": {"id": "$id", "crawler": "$crawler"},
                "latest_doc": {"$first": "$$ROOT"}
            }},
            {"$replaceRoot": {"newRoot": "$latest_doc"}},
            {"$sort": {"created": DESCENDING}}
            # Limit cannot be applied here efficiently if filtering happens after
        ]

        cursor = db.exposes.aggregate(pipeline)
        res = []

        for doc in cursor:
            if len(res) >= count:
                break

            # Extract the main expose data from 'details' field
            expose = doc.get('details', {})
            # Add revision/created time if filter needs it explicitly
            # expose['revision'] = doc.get('revision')
            # expose['created_at'] = doc.get('created')
            # expose['id'] = doc.get('id') # id is already in details if saved correctly
            # expose['crawler'] = doc.get('crawler') # crawler is already in details if saved correctly

            if filter_set is None or filter_set.is_interesting_expose(expose):
                res.append(expose)

        return res

    def save_settings_for_user(self, user_id, settings):
        """Saves the user settings to the database"""
        db = self.get_connection()
        try:
            db.users.update_one(
                {"user_id": user_id},
                {"$set": {"settings": settings, "updated_at": datetime.datetime.now()}},
                upsert=True
            )
        except Exception as e:
             logger.error(f"Error saving settings for user {user_id}: {e}")
             # Decide on error handling

    def get_settings_for_user(self, user_id):
        """Loads the settings for a user from the database"""
        db = self.get_connection()
        user_doc = db.users.find_one({"user_id": user_id})
        if user_doc:
            return user_doc.get('settings')
        return None

    def get_user_settings(self):
        """Loads all users' settings from the database"""
        db = self.get_connection()
        res = []
        try:
            for user_doc in db.users.find({}, {"user_id": 1, "settings": 1, "_id": 0}):
                 # Ensure both fields exist before appending
                 if 'user_id' in user_doc and 'settings' in user_doc:
                    res.append((user_doc['user_id'], user_doc['settings']))
                 else:
                     logger.warning(f"Skipping user document due to missing fields: {user_doc}")
        except Exception as e:
            logger.error(f"Error retrieving user settings: {e}")
        return res

    def get_last_run_time(self):
        """Returns the time of the last hunt"""
        db = self.get_connection()
        last_run = db.executions.find_one(sort=[("timestamp", DESCENDING)])
        if last_run:
            # Timestamps are stored as Python datetime objects by default with PyMongo
            return last_run.get('timestamp')
        return None

    def update_last_run_time(self):
        """Saves the time of the most recent hunt to the database"""
        db = self.get_connection()
        result = datetime.datetime.now()
        try:
            db.executions.insert_one({"timestamp": result})
        except Exception as e:
            logger.error(f"Error updating last run time: {e}")
            # Decide if we should return None or the intended time 'result'
            return None # Or raise e?
        return result

    def close_connection(self):
        """Closes the MongoDB connection."""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed.")
            self.client = None
            self.db = None

