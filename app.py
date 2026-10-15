import os
import json
import uuid
import urllib.parse
import hmac
from flask import Flask, render_template, request, redirect, session, jsonify, url_for
from flask_sqlalchemy import SQLAlchemy
from config import Config
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime

from services.ai_sorter import (
    analyze_complaint_ai,
    sort_complaints_with_ai,
    chat_with_gemini,
    verify_image_issue_match,
    find_duplicate_complaints
)

app = Flask(__name__)
app.config.from_object(Config)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # Limit uploads/request bodies to 5 MB

db = SQLAlchemy(app)


# ==================================================
# DATABASE MODELS
# ==================================================

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(15))
    pincode = db.Column(db.String(10), nullable=True)
    role = db.Column(db.String(20), default="citizen")  # citizen, admin, department
    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.department_id"),
        nullable=True
    )
    department_name = db.Column(db.String(100), nullable=True)
    official_id = db.Column(db.String(50), nullable=True)
    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now()
    )


class Department(db.Model):
    __tablename__ = "departments"

    department_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True
    )
    department_name = db.Column(
        db.String(100),
        nullable=False,
        unique=True
    )
    description = db.Column(db.String(255))


class Complaint(db.Model):
    __tablename__ = "complaints"

    complaint_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )
    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.department_id"),
        nullable=True
    )
    title = db.Column(
        db.String(150),
        nullable=False
    )
    description = db.Column(
        db.Text,
        nullable=False
    )
    category = db.Column(
        db.String(100),
        default="Other"
    )
    image_path = db.Column(
        db.String(255)
    )
    location = db.Column(
        db.String(255)
    )
    latitude = db.Column(db.Numeric(10, 8), nullable=True)
    longitude = db.Column(db.Numeric(11, 8), nullable=True)

    status = db.Column(
        db.Enum(
            "Reported",
            "Under Review",
            "In Progress",
            "Resolved"
        ),
        nullable=False,
        default="Reported"
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp()
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp()
    )
    upvotes_count = db.Column(db.Integer, default=0, nullable=False)


class ComplaintVote(db.Model):
    __tablename__ = "complaint_votes"

    vote_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True
    )
    complaint_id = db.Column(
        db.Integer,
        db.ForeignKey("complaints.complaint_id", ondelete="CASCADE"),
        nullable=False
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp()
    )

    __table_args__ = (
        db.UniqueConstraint("complaint_id", "user_id", name="uq_complaint_user_vote"),
    )


class ComplaintStatus(db.Model):
    __tablename__ = "complaint_status"

    status_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True
    )
    complaint_id = db.Column(
        db.Integer,
        db.ForeignKey("complaints.complaint_id"),
        nullable=False
    )
    status = db.Column(db.String(30), nullable=False)
    remarks = db.Column(db.String(500), nullable=True)
    changed_by = db.Column(db.Integer, nullable=True)
    changed_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp()
    )



# Seed initial departments if table is empty
def seed_departments():
    with app.app_context():
        try:
            if Department.query.count() == 0:
                default_depts = [
                    ("Roads", "Roads, Potholes & Footpath Maintenance"),
                    ("Sanitation", "Solid Waste Management & Public Cleanliness"),
                    ("Water Supply", "Water Distribution & Pipeline Maintenance"),
                    ("Electricity", "Streetlighting & Electrical Infrastructure"),
                    ("Drainage", "Stormwater & Sewage Drainage Systems"),
                    ("Other", "General Civic Issues & Public Works")
                ]
                for name, desc in default_depts:
                    dept = Department(department_name=name, description=desc)
                    db.session.add(dept)
                db.session.commit()
        except Exception:
            db.session.rollback()


# ==================================================
# HOME ROUTE
# ==================================================

@app.route("/")
def home():
    if "user_id" in session:
        role = session.get("role", "citizen")
        if role == "admin":
            return redirect("/admin/dashboard")
        elif role == "department":
            return redirect("/department/dashboard")
        return redirect("/dashboard")
    return redirect("/login")


# ==================================================
# REGISTER ROUTE
# ==================================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()

        # Accept common alternate field names so phone/pincode are never silently dropped
        phone = (
            request.form.get("phone")
            or request.form.get("mobile")
            or request.form.get("phone_number")
            or ""
        ).strip() or None

        pincode = (
            request.form.get("pincode")
            or request.form.get("pin_code")
            or request.form.get("zip")
            or request.form.get("postal_code")
            or ""
        ).strip() or None

        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        role = request.form.get("role", "citizen").strip().lower()
        department_name = request.form.get("department_name", "").strip() or None
        department_code = request.form.get("department_code", "").strip().upper()
        admin_code = request.form.get("admin_code", "").strip().upper()
        official_id = None

        # Validate allowed roles
        if role not in ["citizen", "department", "admin"]:
            role = "citizen"

        # Validate required fields
        if not name or not email or not password:
            return redirect("/register?error=Please+fill+in+all+required+fields.")

        # Validate password confirmation
        if password != confirm_password:
            return redirect("/register?error=Passwords+do+not+match.")

        # Elevated roles require server-side invitation secrets; prefixes are not authentication.
        if role == "admin":
            expected_code = app.config.get("ADMIN_REGISTRATION_CODE", "")
            if not expected_code or not admin_code or not hmac.compare_digest(admin_code, expected_code.strip().upper()):
                return redirect("/register?error=Administrator+registration+is+restricted.+Contact+the+system+owner.")
            official_id = "admin-invitation"

        department_id = None
        if role == "department":
            expected_code = app.config.get("DEPARTMENT_REGISTRATION_CODE", "")
            if not expected_code or not department_code or not hmac.compare_digest(department_code, expected_code.strip().upper()):
                return redirect("/register?error=Department+registration+is+restricted.+Contact+the+system+owner.")
            if not department_name:
                return redirect("/register?error=Please+select+your+assigned+department.")
            dept_obj = Department.query.filter_by(department_name=department_name).first()
            if not dept_obj:
                return redirect("/register?error=Please+select+a+valid+department.")
            department_id = dept_obj.department_id
            official_id = f"department-{department_id}"

        if len(password) < 8:
            return redirect("/register?error=Password+must+contain+at+least+8+characters.")

        # Check whether email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return redirect("/register?error=Email+address+is+already+registered.+Please+login.")

        # Hash password and create user
        hashed_password = generate_password_hash(password)
        user = User(
            name=name,
            email=email,
            password=hashed_password,
            phone=phone,
            pincode=pincode,
            role=role,
            department_id=department_id,
            department_name=department_name,
            official_id=official_id
        )

        try:
            db.session.add(user)
            db.session.commit()
            return redirect("/login?success=Account+created+successfully!+Please+login.")
        except Exception:
            db.session.rollback()
            app.logger.exception("Registration failed")
            return redirect("/register?error=Registration+failed.+Please+try+again.")

    return render_template("register.html")


# ==================================================
# LOGIN ROUTE
# ==================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            session.clear()
            session["user_id"] = user.id
            session["user_name"] = user.name
            session["email"] = user.email
            session["phone"] = user.phone or ""
            session["official_id"] = user.official_id or ""
            session["role"] = user.role
            session["pincode"] = getattr(user, "pincode", "") or ""
            session["department_id"] = user.department_id
            session["department_name"] = user.department_name

            # Role-based redirection
            if user.role == "admin":
                return redirect("/admin/dashboard")
            elif user.role == "department":
                return redirect("/department/dashboard")
            return redirect("/dashboard")

        return redirect("/login?error=Invalid+email+or+password.+Please+try+again.")

    return render_template("login.html")


# ==================================================
# CITIZEN DASHBOARD ROUTE
# ==================================================

@app.route("/dashboard")
def dashboard():
    # Check whether the user is logged in
    if "user_id" not in session:
        return redirect("/login")

    # Redirect users according to their role
    role = session.get("role", "citizen")

    if role == "admin":
        return redirect("/admin/dashboard")
    elif role == "department":
        return redirect("/department/dashboard")

    # Fetch the latest user information from the database
    user_id = session["user_id"]
    user = db.session.get(User, user_id)

    if not user:
        session.clear()
        return redirect("/login")

    # Update session with the latest profile information
    session["user_name"] = user.name or ""
    session["email"] = user.email or ""
    session["phone"] = user.phone or ""
    session["pincode"] = user.pincode or ""
    session["department_name"] = user.department_name or ""
    session["official_id"] = user.official_id or ""
    session["department_id"] = user.department_id

    # --------------------------------------------------
    # Complaint statistics
    # --------------------------------------------------

    total_complaints = Complaint.query.filter_by(
        user_id=user_id
    ).count()

    pending_complaints = Complaint.query.filter(
        Complaint.user_id == user_id,
        Complaint.status != "Resolved"
    ).count()

    resolved_complaints = Complaint.query.filter_by(
        user_id=user_id,
        status="Resolved"
    ).count()

    # --------------------------------------------------
    # Recent complaints
    # --------------------------------------------------

    recent_complaints = (
        Complaint.query
        .filter_by(user_id=user_id)
        .order_by(Complaint.created_at.desc())
        .limit(6)
        .all()
    )

    # --------------------------------------------------
    # Fetch complaints voted on by this user
    # --------------------------------------------------

    user_votes = ComplaintVote.query.filter_by(
        user_id=user_id
    ).all()

    user_voted_ids = {
        vote.complaint_id for vote in user_votes
    }

    # --------------------------------------------------
    # Community complaints
    # --------------------------------------------------

    all_community_raw = (
        Complaint.query
        .order_by(
            Complaint.upvotes_count.desc(),
            Complaint.created_at.desc()
        )
        .limit(12)
        .all()
    )

    community_complaints = sort_complaints_with_ai(
        all_community_raw,
        sort_by="community_votes"
    )

    for item in community_complaints:
        item["has_voted"] = (
            item["complaint_id"] in user_voted_ids
        )

    # --------------------------------------------------
    # Prepare map data
    # --------------------------------------------------

    complaints_map_data = []
    seen_ids = set()

    # Add the user's recent complaints
    for complaint in recent_complaints:
        if (
            complaint.latitude is not None
            and complaint.longitude is not None
        ):
            seen_ids.add(complaint.complaint_id)

            complaints_map_data.append({
                "complaint_id": complaint.complaint_id,
                "title": complaint.title,
                "category": complaint.category,
                "status": complaint.status,
                "location": complaint.location,
                "latitude": float(complaint.latitude),
                "longitude": float(complaint.longitude),
                "upvotes_count": complaint.upvotes_count or 0,
                "is_mine": True,
                "has_voted": (
                    complaint.complaint_id in user_voted_ids
                ),
                "created_at": (
                    complaint.created_at.strftime("%b %d, %Y")
                    if complaint.created_at else ""
                )
            })

    # Add other community complaints with coordinates
    for complaint in all_community_raw:
        if (
            complaint.complaint_id not in seen_ids
            and complaint.latitude is not None
            and complaint.longitude is not None
        ):
            seen_ids.add(complaint.complaint_id)

            complaints_map_data.append({
                "complaint_id": complaint.complaint_id,
                "title": complaint.title,
                "category": complaint.category,
                "status": complaint.status,
                "location": complaint.location,
                "latitude": float(complaint.latitude),
                "longitude": float(complaint.longitude),
                "upvotes_count": complaint.upvotes_count or 0,
                "is_mine": False,
                "has_voted": (
                    complaint.complaint_id in user_voted_ids
                ),
                "created_at": (
                    complaint.created_at.strftime("%b %d, %Y")
                    if complaint.created_at else ""
                )
            })

    # --------------------------------------------------
    # Render dashboard with profile and complaint data
    # --------------------------------------------------

    return render_template(
        "dashboard.html",

        # Profile details
        user_name=user.name or "Citizen",
        user_email=user.email or "",
        user_phone=user.phone or "",
        user_pincode=user.pincode or "",
        user_department_name=user.department_name or "",
        user_official_id=user.official_id or "",

        # Complaint statistics
        total_complaints=total_complaints,
        pending_complaints=pending_complaints,
        resolved_complaints=resolved_complaints,

        # Complaint lists and map
        recent_complaints=recent_complaints,
        community_complaints=community_complaints,
        recent_complaints_json=json.dumps(
            complaints_map_data
        )
    )


# ==================================================
# ADMIN DASHBOARD ROUTE
# ==================================================

@app.route("/admin/dashboard")
def admin_dashboard():
    if "user_id" not in session:
        return redirect("/login")

    if session.get("role") != "admin":
        # Allow access or redirect
        if session.get("role") == "department":
            return redirect("/department/dashboard")
        return redirect("/dashboard")

    total_complaints = Complaint.query.count()
    resolved_complaints = Complaint.query.filter_by(status="Resolved").count()
    pending_complaints = Complaint.query.filter(Complaint.status != "Resolved").count()

    resolution_rate = 0
    if total_complaints > 0:
        resolution_rate = round((resolved_complaints / total_complaints) * 100, 1)

    # All complaints enriched with AI
    all_complaints_raw = (
        Complaint.query
        .order_by(Complaint.created_at.desc())
        .all()
    )

    complaints_enriched = sort_complaints_with_ai(all_complaints_raw, sort_by="date_desc")

    # Critical AI complaints count
    critical_count = sum(
        1 for c in complaints_enriched if c.get("ai", {}).get("priority_level") == "Critical"
    )

    # Department statistics for Chart.js
    departments = Department.query.all()
    dept_labels = []
    dept_data = []
    dept_summary = []

    for d in departments:
        dept_labels.append(d.department_name)
        count = Complaint.query.filter_by(category=d.department_name).count()
        dept_data.append(count)

        d_resolved = Complaint.query.filter_by(category=d.department_name, status="Resolved").count()
        d_pending = count - d_resolved
        d_pct = round((d_resolved / count * 100), 1) if count > 0 else 0

        dept_summary.append({
            "name": d.department_name,
            "total": count,
            "resolved": d_resolved,
            "pending": d_pending,
            "pct": d_pct
        })

    # Status distribution for Chart.js
    status_labels = ["Reported", "Under Review", "In Progress", "Resolved"]
    status_data = [
        Complaint.query.filter_by(status="Reported").count(),
        Complaint.query.filter_by(status="Under Review").count(),
        Complaint.query.filter_by(status="In Progress").count(),
        resolved_complaints
    ]

    return render_template(
        "admin_dashboard.html",
        user_name=session.get("user_name", "Administrator"),
        total_complaints=total_complaints,
        resolved_complaints=resolved_complaints,
        pending_complaints=pending_complaints,
        critical_count=critical_count,
        resolution_rate=resolution_rate,
        complaints=complaints_enriched,
        dept_labels=dept_labels,
        dept_data=dept_data,
        dept_summary=dept_summary,
        status_labels=status_labels,
        status_data=status_data
    )


# ==================================================
# DEPARTMENT DASHBOARD ROUTE
# ==================================================

@app.route("/department/dashboard")
def department_dashboard():
    if "user_id" not in session:
        return redirect("/login")

    role = session.get("role")
    if role not in ["department", "admin"]:
        return redirect("/dashboard")

    # Determine department name
    if role == "admin":
        department_name = request.args.get("dept") or "Roads"
    else:
        # Department users must not be able to switch to another department via query string.
        department_name = session.get("department_name")
        if not department_name:
            return "Department assignment is missing. Contact the administrator.", 403

    # Query complaints for this department
    dept_complaints_query = Complaint.query.filter(
        (Complaint.category == department_name) |
        (Complaint.category.ilike(f"%{department_name}%"))
    )

    all_dept_complaints = dept_complaints_query.order_by(Complaint.created_at.desc()).all()

    # Prioritize with AI by default
    complaints_enriched = sort_complaints_with_ai(all_dept_complaints, sort_by="ai_urgency")

    total_count = len(complaints_enriched)
    resolved_count = sum(1 for c in complaints_enriched if c["status"] == "Resolved")
    in_progress_count = sum(1 for c in complaints_enriched if c["status"] == "In Progress")
    critical_count = sum(1 for c in complaints_enriched if c["ai"]["priority_level"] == "Critical")

    resolution_rate = 0
    if total_count > 0:
        resolution_rate = round((resolved_count / total_count) * 100, 1)

    return render_template(
        "department_dashboard.html",
        user_name=session.get("user_name", "Department Official"),
        department_name=department_name,
        total_complaints=total_count,
        resolved_count=resolved_count,
        in_progress_count=in_progress_count,
        critical_count=critical_count,
        resolution_rate=resolution_rate,
        complaints=complaints_enriched
    )


# ==================================================
# AI SORTING & MANAGEMENT API ENDPOINTS
# ==================================================

@app.route("/api/department/issues/ai-sorted", methods=["GET"])
def api_department_ai_sorted():
    """
    Returns department complaints sorted by AI Urgency Score or other criteria.
    """
    if "user_id" not in session:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    role = session.get("role")
    if role not in ["admin", "department"]:
        return jsonify({"success": False, "error": "Insufficient permissions"}), 403
    department_name = (request.args.get("dept") or "Roads") if role == "admin" else session.get("department_name")
    if not department_name:
        return jsonify({"success": False, "error": "Department assignment is missing"}), 403
    sort_by = request.args.get("sort_by", "ai_urgency")

    # Fetch complaints for department or all if requested
    if department_name == "all" and role == "admin":
        complaints_raw = Complaint.query.all()
    else:
        complaints_raw = Complaint.query.filter(
            (Complaint.category == department_name) |
            (Complaint.category.ilike(f"%{department_name}%"))
        ).all()

    # AI sort and enrich
    sorted_issues = sort_complaints_with_ai(complaints_raw, sort_by=sort_by)

    return jsonify({
        "success": True,
        "department": department_name,
        "sort_by": sort_by,
        "count": len(sorted_issues),
        "complaints": sorted_issues
    })


@app.route("/api/complaints/<int:complaint_id>/status", methods=["POST"])
def api_update_complaint_status(complaint_id):
    """
    Updates the status of a complaint and logs it in complaint_status history.
    """
    if "user_id" not in session:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "error": "A JSON object is required"}), 400
    new_status = data.get("status")
    raw_remarks = data.get("remarks", "")
    remarks = raw_remarks.strip() or None if isinstance(raw_remarks, str) else None

    allowed_statuses = ["Reported", "Under Review", "In Progress", "Resolved"]
    if new_status not in allowed_statuses:
        return jsonify({"success": False, "error": "Invalid status value"}), 400

    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        return jsonify({"success": False, "error": "Complaint not found"}), 404

    role = session.get("role")
    if role == "department":
        assigned = (session.get("department_name") or "").strip().lower()
        category = (complaint.category or "").strip().lower()
        if not assigned or category != assigned:
            return jsonify({"success": False, "error": "You cannot update complaints outside your assigned department"}), 403
    elif role != "admin":
        return jsonify({"success": False, "error": "Insufficient permissions"}), 403

    try:
        complaint.status = new_status
        complaint.updated_at = datetime.now()

        # Log to complaint_status audit table
        status_entry = ComplaintStatus(
            complaint_id=complaint.complaint_id,
            status=new_status,
            remarks=remarks,
            changed_by=session.get("user_id")
        )
        db.session.add(status_entry)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Complaint status updated successfully",
            "complaint_id": complaint_id,
            "new_status": new_status
        })

    except Exception:
        db.session.rollback()
        app.logger.exception("Failed to update complaint status")
        return jsonify({"success": False, "error": "Internal database error"}), 500


@app.route("/api/ai/analyze-complaint", methods=["POST"])
def api_analyze_complaint():
    """Analyze complaint urgency, severity tags, and estimated resolution time."""
    if "user_id" not in session:
        return jsonify({"success": False, "error": "Authentication required"}), 401
    data = request.get_json() or {}
    title = data.get("title", "")
    description = data.get("description", "")
    category = data.get("category", "")

    analysis = analyze_complaint_ai(
        title=title,
        description=description,
        category=category
    )

    return jsonify({
        "success": True,
        "analysis": analysis
    })


@app.route("/api/ai/chat", methods=["POST"])
def api_ai_chat():
    """Provide AI-assisted civic guidance and complaint drafting."""
    if "user_id" not in session:
        return jsonify({"success": False, "error": "Authentication required"}), 401
    data = request.get_json() or {}
    message = data.get("message", "").strip()
    history = data.get("history", [])
    context = data.get("context", {})

    if not message:
        return jsonify({"success": False, "error": "Message cannot be empty."}), 400

    chat_result = chat_with_gemini(message=message, history=history, form_context=context)
    return jsonify(chat_result)


@app.route("/api/ai/validate-image", methods=["POST"])
def api_validate_image():
    """Check whether an uploaded photo matches the reported issue."""
    if "user_id" not in session:
        return jsonify({"success": False, "error": "Authentication required"}), 401
    image_file = request.files.get("image")
    category = request.form.get("category", "")
    title = request.form.get("title", "")
    description = request.form.get("description", "")

    if not image_file or not image_file.filename:
        return jsonify({"success": False, "is_match": False, "error": "No image file provided."}), 400

    image_bytes = image_file.read()
    mime_type = image_file.content_type or "image/jpeg"

    val_result = verify_image_issue_match(
        image_bytes=image_bytes,
        mime_type=mime_type,
        category=category,
        title=title,
        description=description
    )

    return jsonify(val_result)


@app.route("/api/complaints/nearby", methods=["GET"])
def api_nearby_complaints():
    """
    Returns nearby active complaints so citizens can see if others have also
    reported this issue in their area, and encourages duplicate reports for priority escalation.
    """
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    category = request.args.get("category", "")
    loc = request.args.get("location", "")
    user_id = session.get("user_id")

    if lat is None or lng is None:
        return jsonify({"success": True, "count": 0, "duplicates": []})

    all_open = Complaint.query.filter(Complaint.status != "Resolved").all()
    duplicates = find_duplicate_complaints(
        complaints_list=all_open,
        category=category,
        latitude=lat,
        longitude=lng,
        location_text=loc,
        exclude_user_id=user_id
    )

    return jsonify({
        "success": True,
        "count": len(duplicates),
        "duplicates": duplicates[:5]
    })


@app.route("/api/complaints/<int:complaint_id>/vote", methods=["POST"])
def api_vote_complaint(complaint_id):
    """
    Toggles a citizen's vote on an issue (upvote / remove vote).
    Escalates complaint priority as more community members endorse the issue.
    """
    if "user_id" not in session:
        return jsonify({"success": False, "error": "Please login to upvote this issue."}), 401

    user_id = session["user_id"]
    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        return jsonify({"success": False, "error": "Complaint not found."}), 404

    existing_vote = ComplaintVote.query.filter_by(
        complaint_id=complaint_id,
        user_id=user_id
    ).first()

    try:
        if existing_vote:
            db.session.delete(existing_vote)
            complaint.upvotes_count = max(0, (complaint.upvotes_count or 1) - 1)
            voted = False
            msg = "Vote removed."
        else:
            new_vote = ComplaintVote(complaint_id=complaint_id, user_id=user_id)
            db.session.add(new_vote)
            complaint.upvotes_count = (complaint.upvotes_count or 0) + 1
            voted = True
            msg = "Issue upvoted! Priority escalated."

        db.session.commit()

        # Recalculate AI urgency with community votes
        ai_meta = analyze_complaint_ai(
            title=complaint.title,
            description=complaint.description,
            category=complaint.category,
            created_at=complaint.created_at,
            upvotes_count=complaint.upvotes_count
        )

        return jsonify({
            "success": True,
            "voted": voted,
            "upvotes_count": complaint.upvotes_count,
            "ai_urgency": ai_meta["urgency_score"],
            "priority_level": ai_meta["priority_level"],
            "message": msg
        })

    except Exception:
        db.session.rollback()
        app.logger.exception("Vote operation failed")
        return jsonify({"success": False, "error": "Unable to process vote."}), 500


@app.route("/api/complaints/community", methods=["GET"])
def api_community_complaints():
    """
    Returns public complaints in the city/area with upvote stats and user vote status.
    Allows citizens to discover issues in their locality and upvote for faster remediation.
    """
    category = request.args.get("category", "all")
    sort_by = request.args.get("sort_by", "community_votes")
    limit = request.args.get("limit", 50, type=int)

    query = Complaint.query
    if category and category.lower() != "all":
        query = query.filter(
            (Complaint.category == category) |
            (Complaint.category.ilike(f"%{category}%"))
        )

    complaints_raw = query.all()

    user_voted_ids = set()
    if "user_id" in session:
        votes = ComplaintVote.query.filter_by(user_id=session["user_id"]).all()
        user_voted_ids = {v.complaint_id for v in votes}

    enriched = sort_complaints_with_ai(complaints_raw, sort_by=sort_by)

    for item in enriched:
        item["has_voted"] = item["complaint_id"] in user_voted_ids

    return jsonify({
        "success": True,
        "count": len(enriched[:limit]),
        "complaints": enriched[:limit]
    })


@app.route("/api/profile", methods=["POST"])
def api_update_profile():
    """Lets a logged-in user add or update their phone number and pincode."""
    if "user_id" not in session:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "error": "A JSON object is required"}), 400

    phone = str(data.get("phone") or "").strip()
    pincode = str(data.get("pincode") or "").strip()

    # Validation (phone: 10-15 digits, optional leading +; pincode: 6 digits)
    if phone and not (phone.lstrip("+").isdigit() and 10 <= len(phone.lstrip("+")) <= 15):
        return jsonify({"success": False, "error": "Enter a valid phone number (10-15 digits)."}), 400
    if pincode and not (pincode.isdigit() and len(pincode) == 6):
        return jsonify({"success": False, "error": "Pincode must be exactly 6 digits."}), 400

    user = db.session.get(User, session["user_id"])
    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404

    user.phone = phone or None
    user.pincode = pincode or None

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Profile update failed")
        return jsonify({"success": False, "error": "Could not update profile."}), 500

    session["phone"] = user.phone or ""
    session["pincode"] = user.pincode or ""

    return jsonify({
        "success": True,
        "phone": user.phone or "",
        "pincode": user.pincode or ""
    })


# ==================================================
# REPORT ISSUE ROUTE
# ==================================================

@app.route("/report-issue", methods=["GET", "POST"])
def report_issue():
    if "user_id" not in session:
        return redirect("/login")

    if request.method == "GET":
        return render_template("report_issue.html")

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    category = request.form.get("category", "").strip()
    location = request.form.get("location", "").strip()

    latitude = request.form.get("latitude", type=float)
    longitude = request.form.get("longitude", type=float)

    if not title or not description or not category or not location:
        return "Please fill in all required fields.", 400

    if latitude is None or longitude is None:
        return "Please select the issue location on the map.", 400

    if not -90 <= latitude <= 90:
        return "Invalid latitude value.", 400

    if not -180 <= longitude <= 180:
        return "Invalid longitude value.", 400

    # Handle image upload if provided
    image_file = request.files.get("image")
    image_path = None
    if image_file and image_file.filename:
        allowed_extensions = {"png", "jpg", "jpeg", "webp"}
        ext = image_file.filename.rsplit(".", 1)[-1].lower() if "." in image_file.filename else ""
        if ext in allowed_extensions:
            upload_dir = os.path.join(app.root_path, "static", "uploads")
            os.makedirs(upload_dir, exist_ok=True)
            unique_filename = f"{uuid.uuid4().hex[:10]}_{secure_filename(image_file.filename)}"
            file_dest = os.path.join(upload_dir, unique_filename)
            image_file.save(file_dest)

            # AI Vision Verification: ensure image matches reported issue
            try:
                with open(file_dest, "rb") as f:
                    img_bytes = f.read()

                val_res = verify_image_issue_match(
                    image_bytes=img_bytes,
                    mime_type=image_file.content_type or f"image/{ext}",
                    category=category,
                    title=title,
                    description=description
                )

                if not val_res.get("is_match", True) and val_res.get("confidence", 0) >= 0.65:
                    try:
                        os.remove(file_dest)
                    except OSError:
                        pass
                    reason = val_res.get("reason", "Uploaded photo does not match the reported civic issue.")
                    detected = ", ".join(val_res.get("detected_elements", []))
                    err_msg = f"Image Mismatch: {reason} (Detected: {detected}). Please upload an authentic photo of the issue."
                    return redirect(f"/report-issue?error={urllib.parse.quote(err_msg)}")
            except Exception as e:
                app.logger.warning(f"Image vision verification skipped: {e}")

            image_path = f"uploads/{unique_filename}"

    department = Department.query.filter_by(
        department_name=category
    ).first()

    complaint = Complaint(
        user_id=session["user_id"],
        department_id=(
            department.department_id if department else None
        ),
        title=title,
        description=description,
        category=category,
        location=location,
        latitude=latitude,
        longitude=longitude,
        image_path=image_path,
        status="Reported"
    )

    try:
        db.session.add(complaint)
        db.session.commit()

        # Check for duplicate / cluster complaints from other citizens
        all_open = Complaint.query.filter(Complaint.status != "Resolved").all()
        duplicates = find_duplicate_complaints(
            complaints_list=all_open,
            category=category,
            latitude=latitude,
            longitude=longitude,
            location_text=location,
            title_text=title,
            exclude_user_id=session["user_id"],
            exclude_complaint_id=complaint.complaint_id
        )

        cluster_remarks = "Issue reported by citizen"
        if duplicates:
            primary_id = duplicates[0]["complaint_id"]
            primary = Complaint.query.get(primary_id)
            if primary:
                # Duplicate report from another citizen automatically endorses / upvotes the issue
                existing_vote = ComplaintVote.query.filter_by(
                    complaint_id=primary.complaint_id,
                    user_id=session["user_id"]
                ).first()
                if not existing_vote:
                    db.session.add(ComplaintVote(complaint_id=primary.complaint_id, user_id=session["user_id"]))
                    primary.upvotes_count = (primary.upvotes_count or 0) + 1

                # Sync community vote count
                complaint.upvotes_count = primary.upvotes_count

                # Audit log on existing primary issue
                db.session.add(ComplaintStatus(
                    complaint_id=primary.complaint_id,
                    status=primary.status,
                    remarks=f"Multi-Citizen Report: Citizen #{session['user_id']} also reported this problem (Ticket #{complaint.complaint_id}). Priority escalated.",
                    changed_by=session["user_id"]
                ))
                cluster_remarks = f"Issue recorded. Linked to existing neighborhood report #{primary.complaint_id} (Multi-citizen cluster). Priority escalated."

        # Log initial Reported status
        status_entry = ComplaintStatus(
            complaint_id=complaint.complaint_id,
            status="Reported",
            remarks=cluster_remarks,
            changed_by=session["user_id"]
        )
        db.session.add(status_entry)
        db.session.commit()

        redirect_url = "/my-complaints"
        if duplicates:
            redirect_url += f"?duplicate_cluster=1&linked_id={duplicates[0]['complaint_id']}&count={len(duplicates)+1}"
        return redirect(redirect_url)

    except Exception:
        db.session.rollback()
        app.logger.exception("Complaint submission failed")
        return "Unable to submit the complaint. Please try again.", 500


# ==================================================
# MY COMPLAINTS ROUTE
# ==================================================

@app.route("/my-complaints")
def my_complaints():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    complaints = (
        Complaint.query
        .filter_by(user_id=user_id)
        .order_by(Complaint.created_at.desc())
        .all()
    )

    user_votes = ComplaintVote.query.filter_by(user_id=user_id).all()
    user_voted_ids = {v.complaint_id for v in user_votes}

    # Community issues (most voted)
    community_complaints_raw = (
        Complaint.query
        .order_by(Complaint.upvotes_count.desc(), Complaint.created_at.desc())
        .limit(20)
        .all()
    )
    community_complaints = sort_complaints_with_ai(community_complaints_raw, sort_by="community_votes")
    for item in community_complaints:
        item["has_voted"] = item["complaint_id"] in user_voted_ids

    return render_template(
        "my_complaints.html",
        complaints=complaints,
        community_complaints=community_complaints,
        user_voted_ids=user_voted_ids,
        user_name=session.get("user_name", "Citizen")
    )


# ==================================================
# COMMUNITY VOTING & ISSUE ESCALATION ROUTE
# ==================================================

@app.route("/community-voting")
@app.route("/vote-issues")
@app.route("/vote")
def community_voting():
    if "user_id" not in session:
        return redirect("/login?error=Please+login+to+vote+and+escalate+community+issues.")

    user_id = session["user_id"]

    # User's already voted complaints
    user_votes = ComplaintVote.query.filter_by(user_id=user_id).all()
    user_voted_ids = {v.complaint_id for v in user_votes}

    # Fetch all complaints in the city
    complaints_raw = (
        Complaint.query
        .order_by(Complaint.upvotes_count.desc(), Complaint.created_at.desc())
        .all()
    )

    # Enrich with AI triage and user vote status
    community_complaints = sort_complaints_with_ai(complaints_raw, sort_by="community_votes")
    for item in community_complaints:
        item["has_voted"] = item["complaint_id"] in user_voted_ids

    # Aggregate Statistics
    total_issues = len(community_complaints)
    total_votes = sum(item.get("upvotes_count", 0) for item in community_complaints)
    escalated_issues = sum(
        1 for item in community_complaints
        if (item.get("upvotes_count", 0) >= 3 or item.get("ai", {}).get("priority_level") in ("Critical", "High"))
    )
    user_voted_count = len(user_voted_ids)

    return render_template(
        "community_voting.html",
        complaints=community_complaints,
        user_voted_ids=user_voted_ids,
        total_issues=total_issues,
        total_votes=total_votes,
        escalated_issues=escalated_issues,
        user_voted_count=user_voted_count,
        user_name=session.get("user_name", "Citizen")
    )


# ==================================================
# TRACK COMPLAINT ROUTE
# ==================================================

@app.route("/track-complaint", methods=["GET"])
@app.route("/track-complaint/<int:complaint_id>", methods=["GET"])
def track_complaint(complaint_id=None):
    if complaint_id is None:
        query_id = request.args.get("id", type=int)
        if query_id:
            complaint_id = query_id

    # If user is logged in, fetch their recent complaints for quick access pills
    user_complaints = []
    if "user_id" in session:
        user_complaints = (
            Complaint.query
            .filter_by(user_id=session["user_id"])
            .order_by(Complaint.created_at.desc())
            .limit(6)
            .all()
        )
        if complaint_id is None and user_complaints:
            complaint_id = user_complaints[0].complaint_id

    complaint = None
    history_logs = []
    searched_id = complaint_id
    has_voted = False

    if complaint_id:
        complaint = Complaint.query.get(complaint_id)
        if complaint:
            history_logs = (
                ComplaintStatus.query
                .filter_by(complaint_id=complaint_id)
                .order_by(ComplaintStatus.changed_at.asc())
                .all()
            )
            if "user_id" in session:
                has_voted = ComplaintVote.query.filter_by(
                    complaint_id=complaint.complaint_id,
                    user_id=session["user_id"]
                ).first() is not None

    return render_template(
        "track_complaint.html",
        complaint=complaint,
        history_logs=history_logs,
        user_complaints=user_complaints,
        searched_id=searched_id,
        has_voted=has_voted,
        user_name=session.get("user_name", "Citizen")
    )



# ==================================================
# LOGOUT ROUTE
# ==================================================

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login?success=You+have+been+logged+out+successfully.")


# ==================================================
# RUN APPLICATION
# ==================================================

 
# ==================================================
# DATABASE INITIALIZATION
# ==================================================

def initialize_database():
    with app.app_context():
        db.create_all()
        seed_departments()


# Initialize tables when the app starts, including on Render/Gunicorn
initialize_database()


# ==================================================
# RUN APPLICATION
# ==================================================


# ==================================================
# DATABASE INITIALIZATION
# ==================================================

def initialize_database():
    with app.app_context():
        db.create_all()
        seed_departments()


# Initialize tables when the app starts, including on Render/Gunicorn
initialize_database()


# ==================================================
# RUN APPLICATION
# ==================================================

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
