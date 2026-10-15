from flask import Blueprint, render_template, request, redirect, url_for
from werkzeug.security import generate_password_hash
import hmac
from flask import current_app

from app import db
from models.user import User

auth = Blueprint("auth", __name__)


@auth.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip() or None
        password = request.form.get("password", "")
        role = request.form.get("role", "citizen").strip().lower()
        department_name = request.form.get("department_name", "").strip() or None
        department_code = request.form.get("department_code", "").strip().upper()
        admin_code = request.form.get("admin_code", "").strip().upper()
        official_id = None

        if role not in {"citizen", "department", "admin"}:
            return redirect("/register?error=Invalid+account+role.")
        if not name or not email or len(password) < 8:
            return redirect("/register?error=Enter+required+fields+and+a+password+of+at+least+8+characters.")
        if role == "admin":
            expected = current_app.config.get("ADMIN_REGISTRATION_CODE", "")
            if not expected or not admin_code or not hmac.compare_digest(admin_code, expected.strip().upper()):
                return redirect("/register?error=Administrator+registration+is+restricted.")
            official_id = "admin-invitation"
        elif role == "department":
            expected = current_app.config.get("DEPARTMENT_REGISTRATION_CODE", "")
            if not expected or not department_code or not hmac.compare_digest(department_code, expected.strip().upper()):
                return redirect("/register?error=Department+registration+is+restricted.")
            official_id = "department-invitation"

        # Check if email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return redirect("/register?error=Email+already+registered!")

        # Hash password
        hashed_password = generate_password_hash(password)

        # Create user
        user = User(
            name=name,
            email=email,
            password=hashed_password,
            phone=phone,
            role=role,
            department_name=department_name,
            official_id=official_id
        )

        db.session.add(user)
        db.session.commit()

        return redirect("/login?success=Registration+successful!+Please+login.")

    return render_template("register.html")