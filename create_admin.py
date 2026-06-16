from database import users_collection
from passlib.context import CryptContext
import uuid
import os
os.environ["MONGODB_URI"] = "mongodb+srv://nishthadhariwal2005_db_user:Ecoconnect123@cluster0.nftafjf.mongodb.net/"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_admin():
    admin = {
        "user_id":  str(uuid.uuid4()),
        "name":     "Aryan Gupta",
        "email":    "aryan@ecoconnectservices.com",
        "password": pwd_context.hash("Admin@123"),
        "role":     "admin",
        "skills":   [],
        "earnings": 0,
    }

    if users_collection.find_one({"email": admin["email"]}):
        print("Admin already exists — email: aryan@ecoconnectservices.com")
    else:
        users_collection.insert_one(admin)
        print("✅ Admin created")

if __name__ == "__main__":
    create_admin()