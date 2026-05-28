import json
from database import collection

with open("ecoconnect_users.json") as f:
    users = json.load(f)

collection.insert_many(users)

print("Users inserted 🚀")