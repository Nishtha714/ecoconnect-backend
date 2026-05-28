from database import users_collection
from passlib.context import CryptContext
import uuid

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_admin():
    admin = {
        "user_id":  str(uuid.uuid4()),
        "name":     "Admin",
        "email":    "admin@ecoconnect.com",
        "password": pwd_context.hash("admin123"),
        "role":     "admin",
        "skills":   [],
        "earnings": 0,
    }

    if users_collection.find_one({"email": admin["email"]}):
        print("Admin already exists — email: admin@ecoconnect.com")
    else:
        users_collection.insert_one(admin)
        print("✅ Admin created")
        print("   email   : admin@ecoconnect.com")
        print("   password: admin123")
        print("   Change the password after first login!")

if __name__ == "__main__":
    create_admin()
