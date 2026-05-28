"""
patch_db.py — EcoConnect DB Migration
======================================
Run once from your backend folder:
    python patch_db.py

What it does:
  1. Backfills missing fields on all freelancer documents
  2. Backfills missing fields on all project documents
  3. Adds MongoDB indexes on the most-queried fields
  4. Prints a full report of what was changed

Safe to re-run — uses $set only on fields that are None/missing.
"""

from pymongo import MongoClient, ASCENDING, DESCENDING
from datetime import datetime, timezone
import os

# ─── Connection ───────────────────────────────────────────────────────────────
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME   = os.getenv("DB_NAME",   "ecoconnect")

client = MongoClient(MONGO_URI)
db     = client[DB_NAME]

users_collection       = db["users"]
projects_collection    = db["projects"]
allocations_collection = db["allocations"]
revenue_collection     = db["revenue"]


def log(msg):     print(f"  {msg}")
def section(t):   print(f"\n{'─'*60}\n  {t}\n{'─'*60}")


# ═══════════════════════════════════════════════════════════════
# STEP 1 — Backfill freelancer documents
# ═══════════════════════════════════════════════════════════════
section("STEP 1 — Backfilling freelancer documents")

freelancers    = list(users_collection.find({"role": "freelancer"}))
champ_updated  = 0
champ_skipped  = 0
log(f"Found {len(freelancers)} freelancer documents")

for user in freelancers:
    patch = {}
    if user.get("occupation")  is None: patch["occupation"]  = None
    if user.get("country")     is None: patch["country"]     = None
    if user.get("rating")      is None: patch["rating"]      = None
    if user.get("reviews")     is None: patch["reviews"]     = 0
    if user.get("projects")    is None: patch["projects"]    = 0
    if user.get("earnings")    is None: patch["earnings"]    = 0
    if user.get("kyc_status")  is None: patch["kyc_status"]  = "pending"
    if not isinstance(user.get("skills"), list): patch["skills"] = []

    if patch:
        users_collection.update_one({"_id": user["_id"]}, {"$set": patch})
        champ_updated += 1
        log(f"✓ {user.get('name', str(user['_id']))} — patched: {list(patch.keys())}")
    else:
        champ_skipped += 1

log(f"\nChampions updated : {champ_updated}")
log(f"Champions skipped : {champ_skipped} (already complete)")


# ═══════════════════════════════════════════════════════════════
# STEP 2 — Backfill client & admin documents
# ═══════════════════════════════════════════════════════════════
section("STEP 2 — Backfilling client & admin documents")

others        = list(users_collection.find({"role": {"$in": ["client", "admin"]}}))
other_updated = 0
log(f"Found {len(others)} non-freelancer documents")

for user in others:
    patch = {}
    if user.get("earnings") is None: patch["earnings"] = 0
    if patch:
        users_collection.update_one({"_id": user["_id"]}, {"$set": patch})
        other_updated += 1

log(f"Non-freelancers updated: {other_updated}")


# ═══════════════════════════════════════════════════════════════
# STEP 3 — Backfill project documents
# ═══════════════════════════════════════════════════════════════
section("STEP 3 — Backfilling project documents")

projects     = list(projects_collection.find({}))
proj_updated = 0
proj_skipped = 0
log(f"Found {len(projects)} project documents")

for proj in projects:
    patch = {}

    if not proj.get("skills") and proj.get("required_skills"):
        patch["skills"] = proj["required_skills"]

    if not proj.get("duration") and proj.get("timeline"):
        patch["duration"] = proj["timeline"]

    if proj.get("budget_min") is None and proj.get("budget") is not None:
        patch["budget_min"] = proj["budget"]

    if proj.get("budget_max") is None:
        patch["budget_max"] = None

    if not proj.get("company_name"):
        email = proj.get("client_email", "")
        if "@" in email:
            domain = email.split("@")[-1]
            patch["company_name"] = domain.split(".")[0].capitalize()
        else:
            patch["company_name"] = None

    if proj.get("applicants") is None:
        patch["applicants"] = 0

    if not isinstance(proj.get("assigned_users"), list):
        patch["assigned_users"] = []

    if proj.get("status") == "open":
        patch["status"] = "active"

    if not proj.get("created_at"):
        patch["created_at"] = datetime.now(timezone.utc).isoformat()

    if patch:
        projects_collection.update_one({"_id": proj["_id"]}, {"$set": patch})
        proj_updated += 1
        log(f"✓ '{proj.get('title', str(proj['_id']))[:50]}' — patched: {list(patch.keys())}")
    else:
        proj_skipped += 1

log(f"\nProjects updated : {proj_updated}")
log(f"Projects skipped : {proj_skipped} (already complete)")


# ═══════════════════════════════════════════════════════════════
# STEP 4 — Create indexes
# ═══════════════════════════════════════════════════════════════
section("STEP 4 — Creating indexes")

# Drop old indexes first to avoid conflicts on re-run
for idx_name in [
    "idx_users_email", "idx_users_user_id", "idx_users_role", "idx_users_rating",
    "idx_projects_project_id", "idx_projects_status",
    "idx_projects_client_email", "idx_projects_created_at",
    "idx_alloc_project_id", "idx_alloc_user_id", "idx_alloc_decided_at",
    "idx_revenue_id", "idx_revenue_project_id",
]:
    try:
        collection_name = (
            "users"       if "users"    in idx_name else
            "projects"    if "projects" in idx_name else
            "allocations" if "alloc"    in idx_name else
            "revenue"
        )
        db[collection_name].drop_index(idx_name)
        log(f"Dropped old index: {idx_name}")
    except Exception:
        pass  # Index didn't exist — fine

# Users
# FIX: sparse=True on email index so documents with email:null don't conflict
users_collection.create_index(
    [("email",   ASCENDING)], unique=True, sparse=True, name="idx_users_email"
)
users_collection.create_index(
    [("user_id", ASCENDING)], unique=True, sparse=True, name="idx_users_user_id"
)
users_collection.create_index([("role",   ASCENDING)],  name="idx_users_role")
users_collection.create_index([("rating", DESCENDING)], name="idx_users_rating")
log("✓ users — email (unique sparse), user_id (unique sparse), role, rating")

# Projects
projects_collection.create_index(
    [("project_id", ASCENDING)], unique=True, sparse=True, name="idx_projects_project_id"
)
projects_collection.create_index([("status",       ASCENDING)],  name="idx_projects_status")
projects_collection.create_index([("client_email", ASCENDING)],  name="idx_projects_client_email")
projects_collection.create_index([("created_at",   DESCENDING)], name="idx_projects_created_at")
log("✓ projects — project_id (unique sparse), status, client_email, created_at")

# Allocations
allocations_collection.create_index([("project_id", ASCENDING)],  name="idx_alloc_project_id")
allocations_collection.create_index([("user_id",    ASCENDING)],  name="idx_alloc_user_id")
allocations_collection.create_index([("decided_at", DESCENDING)], name="idx_alloc_decided_at")
log("✓ allocations — project_id, user_id, decided_at")

# Revenue
revenue_collection.create_index(
    [("revenue_id", ASCENDING)], unique=True, sparse=True, name="idx_revenue_id"
)
revenue_collection.create_index([("project_id", ASCENDING)], name="idx_revenue_project_id")
log("✓ revenue — revenue_id (unique sparse), project_id")


# ═══════════════════════════════════════════════════════════════
# STEP 5 — Champion card readiness check
# ═══════════════════════════════════════════════════════════════
section("STEP 5 — Champion card readiness check")

champions = list(users_collection.find(
    {"role": "freelancer"},
    {"name": 1, "occupation": 1, "country": 1, "rating": 1, "skills": 1, "projects": 1}
))

ready      = 0
needs_data = 0

print(f"\n  {'NAME':<28} {'OCC':<6} {'CTRY':<6} {'RTG':<6} {'SKLS':<6} STATUS")
print(f"  {'─'*28} {'─'*6} {'─'*6} {'─'*6} {'─'*6} {'─'*12}")

for c in champions:
    ho = bool(c.get("occupation"))
    hc = bool(c.get("country"))
    hr = c.get("rating") is not None
    hs = bool(c.get("skills"))
    ok = all([ho, hc, hr, hs])
    if ok: ready += 1
    else:  needs_data += 1
    print(
        f"  {c.get('name','?'):<28} "
        f"{'✓' if ho else '✗':<6} {'✓' if hc else '✗':<6} "
        f"{'✓' if hr else '✗':<6} {'✓' if hs else '✗':<6} "
        f"{'✅ Ready' if ok else '⚠️  Needs data'}"
    )

print(f"\n  ✅ Card-ready      : {ready}")
print(f"  ⚠️  Needs manual data : {needs_data}")

if needs_data > 0:
    print("""
  To fill in missing champion data, call:
    PATCH /update-user/{user_id}
    Body: { "occupation": "...", "country": "...", "rating": 4.5 }
  Or let champions complete their own profiles after logging in.
    """)

section("MIGRATION COMPLETE")
print(f"""
  Champions backfilled : {champ_updated}
  Projects backfilled  : {proj_updated}
  Indexes created      : 13 across 4 collections
  Card-ready champions : {ready} / {len(champions)}
""")

client.close()
