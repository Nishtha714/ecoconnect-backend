import os
from pymongo import MongoClient, DESCENDING

MONGO_URI = os.getenv("MONGODB_URI", "mongodb+srv://nishthadhariwal2005_db_user:Ecoconnect123@cluster0.nftafjf.mongodb.net/")
client = MongoClient(MONGO_URI)
db = client["ecoconnect_db"]

users_collection       = db["users"]
projects_collection    = db["projects"]
revenue_collection     = db["revenue"]
allocations_collection = db["allocations"]

# ── Indexes (safe to run multiple times) ──────────────────────
try:
    users_collection.create_index("email",   unique=True, sparse=True, name="email_unique")
    users_collection.create_index("user_id",               name="user_id_idx", sparse=True)
    users_collection.create_index("role",                  name="role_idx")

    projects_collection.create_index("project_id",         name="project_id_idx", sparse=True)
    projects_collection.create_index("status",             name="status_idx")
    projects_collection.create_index("client_email",       name="client_email_idx")

    allocations_collection.create_index("project_id",      name="alloc_project_idx")
    allocations_collection.create_index("user_id",         name="alloc_user_idx")
    allocations_collection.create_index(
        [("decided_at", DESCENDING)],                      name="alloc_date_idx"
    )

    revenue_collection.create_index("revenue_id",          name="revenue_id_idx", sparse=True)
    revenue_collection.create_index("project_id",          name="rev_project_idx")

except Exception as e:
    print(f"Index setup skipped (already exists): {e}")