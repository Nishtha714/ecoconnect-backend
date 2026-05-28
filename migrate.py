"""
One-time migration script.
Run once from your backend folder:  python migrate.py
Safe to run multiple times — skips documents that already have the new fields.
"""

from pymongo import MongoClient
import uuid

client = MongoClient("mongodb://localhost:27017/")
db = client["ecoconnect"]

users_collection    = db["users"]
projects_collection = db["projects"]

# ────────────────────────────────────────────
# MIGRATE USERS
# ────────────────────────────────────────────
print("\n── Migrating users ──")

users = list(users_collection.find({}))
users_updated = 0

for user in users:
    updates = {}

    # Add user_id if missing
    if not user.get("user_id"):
        updates["user_id"] = str(uuid.uuid4())

    # Add role if missing
    if not user.get("role"):
        updates["role"] = "freelancer"

    # Add earnings if missing
    if "earnings" not in user:
        updates["earnings"] = 0

    if updates:
        users_collection.update_one({"_id": user["_id"]}, {"$set": updates})
        print(f"  ✓ Updated user: {user.get('name', user['_id'])} → {list(updates.keys())}")
        users_updated += 1
    else:
        print(f"  – Skipped (already migrated): {user.get('name', user['_id'])}")

print(f"\n  Users migrated: {users_updated} / {len(users)}")


# ────────────────────────────────────────────
# MIGRATE PROJECTS
# ────────────────────────────────────────────
print("\n── Migrating projects ──")

projects = list(projects_collection.find({}))
projects_updated = 0

for project in projects:
    updates = {}

    # Add project_id if missing
    if not project.get("project_id"):
        updates["project_id"] = str(uuid.uuid4())

    # Add status if missing
    if not project.get("status"):
        updates["status"] = "active"

    # Add assigned_users if missing
    if "assigned_users" not in project:
        updates["assigned_users"] = []

    # Rename 'skills' → 'required_skills' if old format
    if "skills" in project and "required_skills" not in project:
        updates["required_skills"] = project["skills"]
        projects_collection.update_one(
            {"_id": project["_id"]},
            {"$unset": {"skills": ""}}
        )

    if updates:
        projects_collection.update_one({"_id": project["_id"]}, {"$set": updates})
        print(f"  ✓ Updated project: {project.get('title', project['_id'])} → {list(updates.keys())}")
        projects_updated += 1
    else:
        print(f"  – Skipped (already migrated): {project.get('title', project['_id'])}")

print(f"\n  Projects migrated: {projects_updated} / {len(projects)}")


# ────────────────────────────────────────────
# CREATE INDEXES (safe to run multiple times)
# ────────────────────────────────────────────
print("\n── Creating indexes ──")

users_collection.create_index("user_id",    unique=True, sparse=True)
users_collection.create_index("email",      unique=True, sparse= True)
projects_collection.create_index("project_id", unique=True, sparse=True)
projects_collection.create_index("status")

print("  ✓ Indexes created")
print("\n✅ Migration complete!\n")
