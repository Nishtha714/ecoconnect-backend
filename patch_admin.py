from pymongo import MongoClient
from passlib.context import CryptContext

db = MongoClient("mongodb://localhost:27017/")["ecoconnect"]
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

result = db["users"].update_one(
    {"email": "admin@ecoconnect.com"},
    {"$set": {"password": pwd.hash("admin123"), "role": "admin"}}
)
print("Updated:", result.modified_count)