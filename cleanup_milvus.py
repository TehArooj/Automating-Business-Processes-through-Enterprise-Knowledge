#!/usr/bin/env python3

import sys
import time
from pymilvus import connections, utility, Collection
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MilvusCleanup:
    def __init__(self, host="localhost", port="19530"):
        self.host = host
        self.port = port
        self.connected = False
    
    def connect(self):
        """Connect to Milvus"""
        try:
            connections.connect("default", host=self.host, port=self.port)
            self.connected = True
            logger.info(f"✅ Connected to Milvus at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to connect to Milvus: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from Milvus"""
        if self.connected:
            try:
                connections.disconnect("default")
                self.connected = False
                logger.info("✅ Disconnected from Milvus")
            except Exception as e:
                logger.error(f"⚠️  Error disconnecting: {e}")
    
    def list_collections(self):
        """List all collections in Milvus"""
        try:
            collections = utility.list_collections()
            return collections
        except Exception as e:
            logger.error(f"❌ Failed to list collections: {e}")
            return []
    
    def delete_collection(self, collection_name):
        """Delete a specific collection"""
        try:
            if utility.has_collection(collection_name):
                # Drop the collection
                utility.drop_collection(collection_name)
                logger.info(f"✅ Deleted collection: {collection_name}")
                return True
            else:
                logger.info(f"ℹ️  Collection '{collection_name}' does not exist")
                return True
        except Exception as e:
            logger.error(f"❌ Failed to delete collection '{collection_name}': {e}")
            return False
    
    def clear_collection_data(self, collection_name):
        """Clear all data from a collection without deleting the collection structure"""
        try:
            if not utility.has_collection(collection_name):
                logger.info(f"ℹ️  Collection '{collection_name}' does not exist")
                return True
            
            collection = Collection(collection_name)
            
            # Get collection info
            num_entities = collection.num_entities
            logger.info(f"📊 Collection '{collection_name}' has {num_entities} entities")
            
            if num_entities == 0:
                logger.info(f"ℹ️  Collection '{collection_name}' is already empty")
                return True
            
            # Delete all entities (this is a more complex operation in Milvus)
            # We'll drop and recreate the collection instead
            logger.info(f"🗑️  Clearing all data from collection '{collection_name}'...")
            
            # Get collection schema before dropping
            schema = collection.schema
            
            # Drop the collection
            utility.drop_collection(collection_name)
            
            # Recreate empty collection with same schema
            Collection(collection_name, schema)
            
            logger.info(f"✅ Cleared all data from collection: {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to clear collection '{collection_name}': {e}")
            return False
    
    def delete_all_collections(self):
        """Delete all collections in Milvus"""
        collections = self.list_collections()
        
        if not collections:
            logger.info("ℹ️  No collections found in Milvus")
            return True
        
        logger.info(f"🗑️  Found {len(collections)} collections to delete")
        
        success_count = 0
        for collection_name in collections:
            if self.delete_collection(collection_name):
                success_count += 1
        
        logger.info(f"📊 Successfully deleted {success_count}/{len(collections)} collections")
        return success_count == len(collections)
    
    def get_milvus_info(self):
        """Get information about Milvus instance"""
        try:
            collections = self.list_collections()
            total_entities = 0
            
            collection_info = []
            for collection_name in collections:
                try:
                    collection = Collection(collection_name)
                    num_entities = collection.num_entities
                    total_entities += num_entities
                    collection_info.append({
                        'name': collection_name,
                        'entities': num_entities
                    })
                except Exception as e:
                    logger.warning(f"⚠️  Could not get info for collection '{collection_name}': {e}")
            
            return {
                'total_collections': len(collections),
                'total_entities': total_entities,
                'collections': collection_info
            }
        except Exception as e:
            logger.error(f"❌ Failed to get Milvus info: {e}")
            return None

def print_milvus_status(cleanup):
    """Print current Milvus status"""
    info = cleanup.get_milvus_info()
    if info:
        print(f"\n📊 Milvus Status:")
        print(f"   Collections: {info['total_collections']}")
        print(f"   Total Entities: {info['total_entities']}")
        
        if info['collections']:
            print(f"\n📋 Collection Details:")
            for col in info['collections']:
                print(f"   • {col['name']}: {col['entities']} entities")
    else:
        print("❌ Could not retrieve Milvus status")

def main():
    print("🧹 Milvus Cleanup Tool")
    print("=" * 50)
    
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description="Clean up Milvus collections and data")
    parser.add_argument("--host", default="localhost", help="Milvus host (default: localhost)")
    parser.add_argument("--port", default="19530", help="Milvus port (default: 19530)")
    parser.add_argument("--collection", help="Specific collection to delete (if not specified, all collections will be deleted)")
    parser.add_argument("--clear-only", action="store_true", help="Clear data but keep collection structure")
    parser.add_argument("--info-only", action="store_true", help="Only show information, don't delete anything")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompts")
    
    args = parser.parse_args()
    
    # Initialize cleanup
    cleanup = MilvusCleanup(host=args.host, port=args.port)
    
    # Connect to Milvus
    if not cleanup.connect():
        print("❌ Cannot connect to Milvus. Make sure it's running:")
        print("   docker compose up -d")
        sys.exit(1)
    
    try:
        # Show current status
        print_milvus_status(cleanup)
        
        # If info-only, just exit
        if args.info_only:
            print("\nℹ️  Info-only mode. No changes made.")
            return
        
        # Get collections
        collections = cleanup.list_collections()
        if not collections:
            print("\n✅ No collections found. Milvus is already clean!")
            return
        
        # Determine what to clean
        if args.collection:
            if args.collection not in collections:
                print(f"❌ Collection '{args.collection}' not found!")
                print(f"Available collections: {', '.join(collections)}")
                sys.exit(1)
            collections_to_process = [args.collection]
        else:
            collections_to_process = collections
        
        # Confirm action
        if not args.yes:
            action = "clear data from" if args.clear_only else "delete"
            if len(collections_to_process) == 1:
                message = f"Are you sure you want to {action} collection '{collections_to_process[0]}'?"
            else:
                message = f"Are you sure you want to {action} ALL {len(collections_to_process)} collections?"
            
            response = input(f"\n⚠️  {message} (y/N): ").strip().lower()
            if response not in ['y', 'yes']:
                print("❌ Operation cancelled")
                return
        
        # Perform cleanup
        print(f"\n🧹 Starting cleanup...")
        success_count = 0
        
        for collection_name in collections_to_process:
            if args.clear_only:
                if cleanup.clear_collection_data(collection_name):
                    success_count += 1
            else:
                if cleanup.delete_collection(collection_name):
                    success_count += 1
        
        # Show results
        action = "cleared" if args.clear_only else "deleted"
        print(f"\n📊 Results: {action} {success_count}/{len(collections_to_process)} collections")
        
        if success_count == len(collections_to_process):
            print("🎉 Cleanup completed successfully!")
        else:
            print("⚠️  Some operations failed. Check the logs above.")
        
        # Show final status
        print_milvus_status(cleanup)
        
    finally:
        cleanup.disconnect()

if __name__ == "__main__":
    main() 