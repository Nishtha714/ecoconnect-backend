from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import shutil
import os
import jwt
import uuid
from email_utils import send_admin_notification
from email_utils import send_admin_notification, generate_otp, send_otp_email, send_welcome_email
import time

from database import (
    db, users_collection, projects_collection,
    revenue_collection, allocations_collection
)

app = FastAPI()

# ================================================================
# AUTH
# ================================================================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY  = os.getenv("SECRET_KEY", "ecoconnect-secret-2024")
security    = HTTPBearer()


def create_token(user_id: str, role: str) -> str:
    return jwt.encode(
        {"sub": user_id, "role": role,
         "exp": datetime.now(timezone.utc) + timedelta(days=7)},
        SECRET_KEY, algorithm="HS256",
    )


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    return decode_token(credentials.credentials)


def require_admin(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    payload = decode_token(credentials.credentials)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return payload


# ================================================================
# CORS
# ================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

otp_store = {}  # { email: { otp, expiry, user_data } }


# ================================================================
# MODELS
# ================================================================
class User(BaseModel):
    name:     str
    email:    str
    skills:   List[str] = []
    password: str
    role:     str = "freelancer"
    company:  Optional[str] = None


class ClientUser(BaseModel):
    name:         str
    email:        str
    password:     str
    company:      str
    budget_range: Optional[str] = None
    preferences:  Optional[str] = None
    role:         str = "client"


class LoginRequest(BaseModel):
    email:    str
    password: str


class UpdateUserRequest(BaseModel):
    name:                 Optional[str] = None
    skills:               Optional[List[str]] = None
    company:              Optional[str] = None
    budget_range:         Optional[str] = None
    preferences:          Optional[str] = None
    occupation:           Optional[str] = None
    country:              Optional[str] = None
    rating:               Optional[float] = None
    reviews:              Optional[int] = None
    projects:             Optional[int] = None
    # ── Onboarding fields (new) ──────────────────────────────────────────────
    bio:                  Optional[str] = None
    experience_years:     Optional[str] = None   # e.g. "3–5 years"
    employer:             Optional[str] = None
    internships:          Optional[str] = None
    portfolio:            Optional[str] = None
    certifications:       Optional[str] = None
    id_proof:             Optional[str] = None
    domains:              Optional[List[str]] = None
    kyc_status:           Optional[str] = None   # "pending" | "verified" | "rejected"
    onboarding_complete:  Optional[bool] = None



class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password:     str


class Project(BaseModel):
    title:           str
    required_skills: List[str]
    budget:          float
    timeline:        str
    scope:           Optional[str] = None
    client_email:    Optional[str] = None
    company_name:    Optional[str] = None
    budget_min:      Optional[float] = None
    budget_max:      Optional[float] = None
    duration:        Optional[str] = None
    applicants:      Optional[int] = None


class AllocationDecision(BaseModel):
    project_id: str
    user_id:    str
    decision:   str        # "approve" or "reshortlist"
    notes:      Optional[str] = None


# ── Public response models ────────────────────────────────────────────────────

class PublicChampion(BaseModel):
    user_id:   str
    name:      str
    role:      Optional[str] = None
    skills:    List[str] = []
    country:   Optional[str] = None
    rating:    Optional[float] = None
    reviews:   Optional[int] = None
    projects:  Optional[int] = None


class PublicProject(BaseModel):
    project_id:   str
    title:        str
    company_name: Optional[str] = None
    status:       str
    budget_min:   Optional[float] = None
    budget_max:   Optional[float] = None
    duration:     Optional[str] = None
    skills:       List[str] = []
    applicants:   int = 0


# ================================================================
# HOME
# ================================================================
@app.get("/")
def home():
    return {"message": "Backend is running 🚀"}


# ================================================================
# PUBLIC STATS  (no auth)
# ================================================================
@app.get("/get-stats")
def get_public_stats():
    projects = list(projects_collection.find({}, {"assigned_users": 1, "status": 1}))
    return {
        "total_champions":  users_collection.count_documents({"role": "freelancer"}),
        "active_projects":  sum(1 for p in projects if p.get("status") == "active"),
        "total_placements": sum(len(p.get("assigned_users", [])) for p in projects),
    }


# ================================================================
# PUBLIC CHAMPIONS & PROJECTS  (no auth)
# ================================================================

@app.get("/public/champions", response_model=List[PublicChampion])
def get_champions_public(limit: int = 28):
    cursor = users_collection.find(
        {"role": "freelancer"},
        {"_id": 0, "password": 0, "email": 0}
    ).sort([("rating", -1), ("projects", -1)]).limit(limit)

    result = []
    for doc in cursor:
        result.append(PublicChampion(
            user_id=  doc.get("user_id", ""),
            name=     doc.get("name", ""),
            role=     doc.get("occupation") or (
                      None if doc.get("role") in ("freelancer", "admin", "client")
                      else doc.get("role")
                      ),
            skills=   doc.get("skills", []),
            country=  doc.get("country"),
            rating=   doc.get("rating"),
            reviews=  doc.get("reviews"),
            projects= doc.get("projects"),
        ))
    return result


@app.get("/public/projects", response_model=List[PublicProject])
def get_projects_public(limit: int = 20, status: Optional[str] = None):
    query: dict = {}
    if status:
        query["status"] = status

    cursor = projects_collection.find(
        query,
        {"_id": 0, "assigned_users": 0}
    ).sort("created_at", -1).limit(limit)

    result: list[PublicProject] = []
    for doc in cursor:
        company = doc.get("company_name")
        if not company and doc.get("client_email"):
            domain  = doc["client_email"].split("@")[-1]
            company = domain.split(".")[0].capitalize()

        b_min = doc.get("budget_min")
        b_max = doc.get("budget_max")
        if b_min is None and b_max is None and doc.get("budget"):
            b_min = doc["budget"]

        result.append(PublicProject(
            project_id=   doc.get("project_id", ""),
            title=        doc.get("title", ""),
            company_name= company,
            status=       doc.get("status", "active"),
            budget_min=   b_min,
            budget_max=   b_max,
            duration=     doc.get("duration") or doc.get("timeline"),
            skills=       doc.get("skills") or doc.get("required_skills", []),
            applicants=   doc.get("applicants", 0),
        ))

    result.sort(key=lambda p: (p.status not in ("active", "open"), ""))
    return result


# Legacy aliases
@app.get("/get-public-champions")
def get_public_champions_legacy():
    return list(users_collection.find(
        {"role": "freelancer"},
        {"_id": 0, "password": 0, "email": 0}
    ))


@app.get("/get-public-projects")
def get_public_projects_legacy():
    return list(projects_collection.find(
        {},
        {"_id": 0, "assigned_users": 1, "title": 1,
         "required_skills": 1, "budget": 1, "timeline": 1,
         "status": 1, "project_id": 1, "scope": 1, "created_at": 1}
    ))


# ================================================================
# USERS
# ================================================================
# ================================================================
# USERS
# ================================================================
otp_store = {}  # OTP temporary storage

@app.post("/add-user/send-otp")
def send_user_otp(data: User):
    if users_collection.find_one({"email": data.email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    otp = generate_otp()
    otp_store[data.email] = {
        "otp":       otp,
        "expiry":    time.time() + 600,
        "user_data": data.model_dump()
    }
    send_otp_email(data.email, data.name, otp)
    return {"message": "OTP sent to your email"}

@app.post("/add-user/verify-otp")
def verify_user_otp(email: str, otp: str):
    record = otp_store.get(email)
    if not record:
        raise HTTPException(status_code=400, detail="OTP not found. Request again.")
    if time.time() > record["expiry"]:
        raise HTTPException(status_code=400, detail="OTP expired.")
    if record["otp"] != otp:
        raise HTTPException(status_code=400, detail="Invalid OTP.")
    user_data             = record["user_data"]
    user_data["password"] = pwd_context.hash(user_data["password"])
    user_data["earnings"] = 0
    user_data["user_id"]  = str(uuid.uuid4())
    users_collection.insert_one(user_data)
    send_admin_notification(user_data["name"], email, "champion")
    send_welcome_email(email, user_data["name"])  # ← ye add karo
    del otp_store[email]
    return {"message": "Account verified!", "user_id": user_data["user_id"]}


@app.post("/add-client")
def add_client(data: ClientUser):
    if users_collection.find_one({"email": data.email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    doc             = data.model_dump()
    doc["password"] = pwd_context.hash(doc["password"])
    doc["user_id"]  = str(uuid.uuid4())
    doc["earnings"] = 0
    users_collection.insert_one(doc)
    send_admin_notification(data.name, data.email, "client")
    return {"message": "Client registered successfully", "user_id": doc["user_id"]}


@app.get("/get-users")
def get_users(_: dict = Depends(get_current_user)):
    return list(users_collection.find({}, {"_id": 0, "password": 0}))


@app.get("/get-freelancers")
def get_freelancers(_: dict = Depends(get_current_user)):
    return list(users_collection.find({"role": "freelancer"}, {"_id": 0, "password": 0}))


@app.get("/get-clients")
def get_clients(_: dict = Depends(require_admin)):
    return list(users_collection.find({"role": "client"}, {"_id": 0, "password": 0}))


@app.get("/get-user/{user_id}")
def get_user(user_id: str, _: dict = Depends(get_current_user)):
    user = users_collection.find_one({"user_id": user_id}, {"_id": 0, "password": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.patch("/update-user/{user_id}")
def update_user(user_id: str, data: UpdateUserRequest, current: dict = Depends(get_current_user)):
    if current.get("sub") != user_id and current.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not authorised to update this profile")
    update = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = users_collection.update_one({"user_id": user_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "Profile updated successfully"}


@app.patch("/change-password/{user_id}")
def change_password(user_id: str, data: ChangePasswordRequest, current: dict = Depends(get_current_user)):
    if current.get("sub") != user_id:
        raise HTTPException(status_code=403, detail="Not authorised")
    user = users_collection.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not pwd_context.verify(data.current_password, user["password"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"password": pwd_context.hash(data.new_password)}}
    )
    return {"message": "Password changed successfully"}


# ================================================================
# LOGIN
# ================================================================
@app.post("/login")
def login(req: LoginRequest):
    user = users_collection.find_one({"email": req.email})
    if not user or not pwd_context.verify(req.password, user.get("password", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user_id = user.get("user_id")
    if not user_id:
        user_id = str(uuid.uuid4())
        users_collection.update_one(
            {"_id": user["_id"]},
            {"$set": {"user_id": user_id, "role": user.get("role", "freelancer")}}
        )

    token = create_token(user_id, user.get("role", "freelancer"))
    return {
        "access_token": token,
        "user": {
            "user_id": user_id,
            "name":    user["name"],
            "email":   user["email"],
            "role":    user.get("role", "freelancer"),
        },
    }


# ================================================================
# RESUME
# ================================================================
UPLOAD_DIR = "resumes"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.post("/upload-resume/{user_id}")
def upload_resume(
    user_id: str,
    file: UploadFile = File(...),
    _: dict = Depends(get_current_user),
):
    file_path = f"{UPLOAD_DIR}/{user_id}_{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    users_collection.update_one({"user_id": user_id}, {"$set": {"resume": file_path}})
    return {"message": "Resume uploaded", "path": file_path}


# ================================================================
# PROJECTS
# ================================================================
@app.post("/add-project")
def add_project(data: Project, _: dict = Depends(get_current_user)):
    project                    = data.model_dump()
    project["project_id"]      = str(uuid.uuid4())
    project["assigned_users"]  = []
    project["assigned_user_ids"] = []   # FIX: initialise id list
    project["status"]          = "active"
    project["applicants"]      = 0
    project["created_at"]      = datetime.now(timezone.utc).isoformat()

    if project.get("budget") and not project.get("budget_min"):
        project["budget_min"] = project["budget"]
    if project.get("timeline") and not project.get("duration"):
        project["duration"] = project["timeline"]
    if project.get("required_skills") and not project.get("skills"):
        project["skills"] = project["required_skills"]

    projects_collection.insert_one(project)
    return {"message": "Project added successfully", "project_id": project["project_id"]}


@app.get("/get-projects")
def get_projects(_: dict = Depends(get_current_user)):
    return list(projects_collection.find({}, {"_id": 0}))


@app.get("/get-project/{project_id}")
def get_project(project_id: str, _: dict = Depends(get_current_user)):
    project = projects_collection.find_one({"project_id": project_id}, {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.get("/get-client-projects/{client_email}")
def get_client_projects(client_email: str, _: dict = Depends(get_current_user)):
    return list(projects_collection.find(
        {"client_email": client_email}, {"_id": 0}
    ))


@app.put("/update-project/{project_id}")
def update_project(project_id: str, data: Project, _: dict = Depends(get_current_user)):
    update_doc = {
        **data.model_dump(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    if update_doc.get("required_skills") and not update_doc.get("skills"):
        update_doc["skills"] = update_doc["required_skills"]
    if update_doc.get("timeline") and not update_doc.get("duration"):
        update_doc["duration"] = update_doc["timeline"]
    if update_doc.get("budget") and not update_doc.get("budget_min"):
        update_doc["budget_min"] = update_doc["budget"]

    result = projects_collection.update_one(
        {"project_id": project_id},
        {"$set": update_doc}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"message": "Project updated successfully"}


@app.patch("/update-project-status/{project_id}")
def update_project_status(project_id: str, data: dict, _: dict = Depends(require_admin)):
    valid_statuses = ["active", "completed", "closed"]
    status = data.get("status")
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Status must be one of {valid_statuses}")
    result = projects_collection.update_one(
        {"project_id": project_id}, {"$set": {"status": status}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"message": f"Project status updated to {status}"}


@app.delete("/delete-project/{project_id}")
def delete_project(project_id: str, _: dict = Depends(require_admin)):
    result = projects_collection.delete_one({"project_id": project_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Project not found")
    allocations_collection.delete_many({"project_id": project_id})
    return {"message": "Project deleted successfully"}


# ================================================================
# APPLICANT COUNT
# ================================================================
@app.post("/apply-project/{project_id}")
def apply_to_project(project_id: str, _: dict = Depends(get_current_user)):
    result = projects_collection.update_one(
        {"project_id": project_id},
        {"$inc": {"applicants": 1}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"message": "Application recorded"}


# ================================================================
# AI SUGGEST
# ================================================================
@app.post("/suggest-users")
def suggest_users(data: dict):
    required_skills = [s.lower() for s in data.get("skills", [])]
    users = list(users_collection.find({"role": "freelancer"}, {"_id": 0, "password": 0}))
    scored_users = []

    for user in users:
        user_skills = [s.lower() for s in user.get("skills", [])]
        # FIX: count unique matching skills — no duplicate entries
        score = sum(
            1 for req in required_skills
            if any(req in us for us in user_skills)
        )
        if score > 0:
            user["score"] = score
            scored_users.append(user)

    return sorted(scored_users, key=lambda x: x["score"], reverse=True)[:5]


# ================================================================
# ASSIGN USER + EARNINGS
# ================================================================

def recalculate_earnings(project_id: str):
    """
    FIX: uses assigned_user_ids (UUID list) instead of name-based regex.
    Guarantees correct earnings even if two champions share the same name.
    """
    project      = projects_collection.find_one({"project_id": project_id})
    assigned_ids = project.get("assigned_user_ids", [])
    budget       = project.get("budget", 0)
    share        = round(budget / len(assigned_ids), 2) if assigned_ids else 0
    if assigned_ids:
        users_collection.update_many(
            {"user_id": {"$in": assigned_ids}},
            {"$set": {"earnings": share}},
        )
    return share


@app.post("/assign-user")
def assign_user(data: dict, _: dict = Depends(require_admin)):
    project_id = data.get("project_id")
    user_id    = data.get("user_id")    # FIX: user_id not name
    if not project_id or not user_id:
        raise HTTPException(status_code=400, detail="project_id and user_id are required")

    user = users_collection.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not projects_collection.find_one({"project_id": project_id}):
        raise HTTPException(status_code=404, detail="Project not found")

    projects_collection.update_one(
        {"project_id": project_id},
        {
            "$addToSet": {
                "assigned_user_ids": user_id,       # for earnings — unique by ID
                "assigned_users":    user["name"],  # for display only
            }
        },
    )
    share = recalculate_earnings(project_id)
    return {"message": "User assigned & earnings recalculated", "share_per_user": share}


# ================================================================
# ADMIN DECISION GATE
# ================================================================
@app.post("/admin/decision")
def admin_decision(data: AllocationDecision, admin: dict = Depends(require_admin)):
    if data.decision not in ("approve", "reshortlist"):
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reshortlist'")

    project = projects_collection.find_one({"project_id": data.project_id})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    user = users_collection.find_one({"user_id": data.user_id}, {"_id": 0, "password": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    log = {
        "allocation_id": str(uuid.uuid4()),
        "project_id":    data.project_id,
        "project_title": project.get("title"),
        "user_id":       data.user_id,
        "user_name":     user.get("name"),
        "decision":      data.decision,
        "notes":         data.notes,
        "decided_by":    admin.get("sub"),
        "decided_at":    datetime.now(timezone.utc).isoformat(),
    }
    allocations_collection.insert_one(log)

    if data.decision == "approve":
        # FIX: store both user_id (for earnings) and name (for display)
        projects_collection.update_one(
            {"project_id": data.project_id},
            {
                "$addToSet": {
                    "assigned_user_ids": data.user_id,      # unique by ID
                    "assigned_users":    user["name"],      # display name
                }
            },
        )
        share = recalculate_earnings(data.project_id)
        return {"message": f"{user['name']} approved and allocated", "share_per_user": share}

    return {
        "message":   f"{user['name']} rejected — returned to shortlist",
        "next_step": "Call POST /suggest-users to get next candidates",
    }


@app.get("/get-allocations/{project_id}")
def get_allocations(project_id: str, _: dict = Depends(get_current_user)):
    return list(allocations_collection.find(
        {"project_id": project_id}, {"_id": 0}
    ).sort("decided_at", -1))


@app.get("/get-user-allocations/{user_id}")
def get_user_allocations(user_id: str, _: dict = Depends(get_current_user)):
    return list(allocations_collection.find(
        {"user_id": user_id}, {"_id": 0}
    ).sort("decided_at", -1))


@app.get("/get-all-allocations")
def get_all_allocations(_: dict = Depends(require_admin)):
    return list(allocations_collection.find({}, {"_id": 0}).sort("decided_at", -1))


@app.delete("/remove-allocation/{project_id}/{user_id}")
def remove_allocation(project_id: str, user_id: str, _: dict = Depends(require_admin)):
    user = users_collection.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # FIX: pull by both user_id and name, recalculate using IDs
    projects_collection.update_one(
        {"project_id": project_id},
        {
            "$pull": {
                "assigned_user_ids": user_id,
                "assigned_users":    user["name"],
            }
        }
    )
    # Zero out earnings for removed user
    users_collection.update_one({"user_id": user_id}, {"$set": {"earnings": 0}})
    # Recalculate for remaining users using ID-based method
    share = recalculate_earnings(project_id)
    return {"message": f"{user['name']} removed. Remaining share: ₹{share} per person"}


# ================================================================
# REVENUE
# ================================================================
@app.post("/add-revenue")
def add_revenue(data: dict, _: dict = Depends(require_admin)):
    data["revenue_id"] = str(uuid.uuid4())
    data["date"]       = datetime.now().strftime("%Y-%m-%d")
    revenue_collection.insert_one(data)
    return {"message": "Revenue added", "revenue_id": data["revenue_id"]}


@app.get("/get-revenue")
def get_revenue(_: dict = Depends(get_current_user)):
    return list(revenue_collection.find({}, {"_id": 0}))


@app.get("/get-revenue/{project_id}")
def get_project_revenue(project_id: str, _: dict = Depends(get_current_user)):
    return list(revenue_collection.find({"project_id": project_id}, {"_id": 0}))


@app.delete("/delete-revenue/{revenue_id}")
def delete_revenue(revenue_id: str, _: dict = Depends(require_admin)):
    result = revenue_collection.delete_one({"revenue_id": revenue_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Revenue record not found")
    return {"message": "Revenue record deleted"}


# ================================================================
# USER EARNINGS
# ================================================================
@app.get("/get-earnings/{user_id}")
def get_earnings(user_id: str, _: dict = Depends(get_current_user)):
    user = users_collection.find_one({"user_id": user_id}, {"_id": 0, "password": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ================================================================
# DASHBOARD  (admin only)
# ================================================================
@app.get("/dashboard")
def dashboard(_: dict = Depends(require_admin)):
    projects        = list(projects_collection.find({}, {"assigned_users": 1, "status": 1}))
    revenue_records = list(revenue_collection.find({}, {"total_revenue": 1}))
    total_revenue   = sum(r.get("total_revenue", 0) for r in revenue_records)

    return {
        "total_users":       users_collection.count_documents({}),
        "total_champions":   users_collection.count_documents({"role": "freelancer"}),
        "total_projects":    len(projects),
        "active_projects":   sum(1 for p in projects if p.get("status") == "active"),
        "total_assignments": sum(len(p.get("assigned_users", [])) for p in projects),
        "total_revenue":     total_revenue,
    }

@app.get("/debug/champions")
def debug_champions():
    return list(users_collection.find({"role": "freelancer"}, {"_id": 0, "password": 0}))