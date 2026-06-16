from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URL") or os.getenv("MONGO_URI") or os.getenv("DATABASE_URL")
print("Connecting to:", MONGO_URI)

client = MongoClient(MONGO_URI)

# Sabhi databases list karo
print("\nAll databases:", client.list_database_names())

# Har DB mein users collection check karo
for db_name in client.list_database_names():
    db = client[db_name]
    if "users" in db.list_collection_names():
        user = db.users.find_one({"email": "aryan@ecoconnectservices.com"})
        if user:
            print(f"\n✅ FOUND in DB: '{db_name}' → role: {user.get('role')}")