import os
import secrets
from datetime import datetime

from flask import Flask, request, redirect, url_for, session, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///reels_marketplace.db"

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"


# ---------- Models ----------

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # "client" or "editor"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class EditorProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    bio = db.Column(db.Text, default="")
    price_per_reel = db.Column(db.Float, default=0.0)
    earnings = db.Column(db.Float, default=0.0)

    user = db.relationship("User", backref=db.backref("editor_profile", uselist=False))


class PortfolioItem(db.Model):
    """A reference reel an editor has created, shown to prospective clients."""
    id = db.Column(db.Integer, primary_key=True)
    editor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    video_url = db.Column(db.String(400), nullable=False)  # link to the reel (YouTube/Drive/Instagram/etc)
    notes = db.Column(db.String(300), default="")  # e.g. "fast-paced fashion reel, trending audio"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    editor = db.relationship("User")


class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    editor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    editing_instructions = db.Column(db.Text, nullable=False)  # client's creative idea for the reel
    budget = db.Column(db.Float, nullable=False)

    status = db.Column(db.String(20), default="open")
    # open -> assigned -> paid -> delivered -> completed
    delivery_url = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    client = db.relationship("User", foreign_keys=[client_id])
    editor = db.relationship("User", foreign_keys=[editor_id])


class Application(db.Model):
    """Used only for open jobs anyone can apply to (not the direct-hire flow)."""
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("job.id"), nullable=False)
    editor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    message = db.Column(db.Text, default="")
    bid_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    job = db.relationship("Job", backref="applications")
    editor = db.relationship("User")


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ---------- CSRF (minimal, session-token based) ----------

def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def check_csrf():
    token = request.form.get("_csrf")
    if not token or token != session.get("_csrf"):
        abort(400, "Invalid CSRF token")


# ---------- Layout helper ----------

def layout(title, body):
    if current_user.is_authenticated:
        nav_links = f'<span>Hi, {current_user.name} ({current_user.role})</span>'
        nav_links += ' <a href="/dashboard">Dashboard</a>'
        if current_user.role == "client":
            nav_links += ' <a href="/editors">Browse Editors</a> <a href="/jobs/new">Post an Open Job</a>'
        else:
            nav_links += ' <a href="/jobs/browse">Browse Open Jobs</a> <a href="/editor/portfolio">My Portfolio</a>'
        nav_links += ' <a href="/logout">Logout</a>'
    else:
        nav_links = '<a href="/login">Login</a> <a href="/register">Register</a>'

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{title} - Reels Marketplace</title>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 900px; margin: 30px auto; padding: 0 15px; color: #222; }}
            nav {{ margin-bottom: 25px; border-bottom: 1px solid #ddd; padding-bottom: 10px; }}
            nav a {{ margin-right: 12px; text-decoration: none; color: #0a58ca; }}
            input, textarea, select {{ width: 100%; padding: 8px; margin: 6px 0 14px; box-sizing: border-box; }}
            button {{ padding: 8px 16px; background: #0a58ca; color: white; border: none; border-radius: 4px; cursor: pointer; }}
            .card {{ border: 1px solid #ddd; border-radius: 6px; padding: 15px; margin-bottom: 15px; }}
            .status {{ display: inline-block; padding: 2px 8px; border-radius: 10px; background: #eee; font-size: 12px; }}
            .reel {{ display: inline-block; width: 200px; vertical-align: top; margin: 0 12px 12px 0; border: 1px solid #eee; border-radius: 6px; padding: 10px; }}
        </style>
    </head>
    <body>
        <nav><a href="/"><strong>ReelsMarketplace</strong></a> &nbsp; {nav_links}</nav>
        {body}
    </body>
    </html>
    """


# ---------- Auth ----------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        check_csrf()
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        role = request.form["role"]

        if role not in ("client", "editor"):
            return layout("Register", "<p>Invalid role.</p>")
        if User.query.filter_by(email=email).first():
            return layout("Register", "<p>Email already registered. <a href='/login'>Login instead</a>.</p>")

        user = User(name=name, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        if role == "editor":
            db.session.add(EditorProfile(user_id=user.id))
            db.session.commit()

        login_user(user)
        return redirect(url_for("dashboard"))

    token = csrf_token()
    body = f"""
    <h2>Register</h2>
    <form method="post">
        <input type="hidden" name="_csrf" value="{token}">
        <label>Name</label><input name="name" required>
        <label>Email</label><input type="email" name="email" required>
        <label>Password</label><input type="password" name="password" required minlength="6">
        <label>I am a...</label>
        <select name="role">
            <option value="client">Client (hiring an editor)</option>
            <option value="editor">Editor (offering services)</option>
        </select>
        <button type="submit">Create account</button>
    </form>
    """
    return layout("Register", body)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        check_csrf()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("dashboard"))
        return layout("Login", "<p>Invalid credentials.</p>")

    token = csrf_token()
    body = f"""
    <h2>Login</h2>
    <form method="post">
        <input type="hidden" name="_csrf" value="{token}">
        <label>Email</label><input type="email" name="email" required>
        <label>Password</label><input type="password" name="password" required>
        <button type="submit">Login</button>
    </form>
    """
    return layout("Login", body)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


# ---------- Home / Dashboard ----------

@app.route("/")
def index():
    profiles = EditorProfile.query.limit(6).all()
    cards = "".join(f"""
        <div class="card">
            <h3><a href="/editors/{p.id}">{p.user.name}</a></h3>
            <p>{(p.bio or "No bio yet.")[:120]}</p>
            <p>Rate: ${p.price_per_reel:.2f} / reel &nbsp; . &nbsp; {len(p.portfolio_items)} reference reels</p>
        </div>
    """ for p in profiles) or "<p>No editors have joined yet.</p>"

    body = f"""
    <h1>Hire a Reels Editor</h1>
    <p>Browse editors' reference reels, hire the one whose style you like, tell them exactly how you want your reel edited, and pay securely.</p>
    <h2>Featured editors</h2>
    {cards}
    """
    return layout("Home", body)


@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.role == "client":
        jobs = Job.query.filter_by(client_id=current_user.id).order_by(Job.created_at.desc()).all()
        rows = "".join(f"""
            <div class="card">
                <h3><a href="/jobs/{j.id}">{j.title}</a></h3>
                <p>Status: <span class="status">{j.status}</span> &nbsp; Budget: ${j.budget:.2f}</p>
            </div>
        """ for j in jobs) or "<p>You haven't hired anyone yet. <a href='/editors'>Browse editors</a>.</p>"
        body = f"<h1>My Jobs</h1>{rows}"
    else:
        assigned = Job.query.filter_by(editor_id=current_user.id).order_by(Job.created_at.desc()).all()
        rows = "".join(f"""
            <div class="card">
                <h3><a href="/jobs/{j.id}">{j.title}</a></h3>
                <p>Status: <span class="status">{j.status}</span> &nbsp; Budget: ${j.budget:.2f}</p>
            </div>
        """ for j in assigned) or "<p>No jobs yet.</p>"
        body = f"<h1>My Jobs</h1>{rows}"

    return layout("Dashboard", body)


# ---------- Editors & portfolio (reference reels) ----------

@app.route("/editors")
@login_required
def browse_editors():
    profiles = EditorProfile.query.all()
    cards = "".join(f"""
        <div class="card">
            <h3><a href="/editors/{p.id}">{p.user.name}</a></h3>
            <p>{p.bio or "No bio yet."}</p>
            <p>Rate: ${p.price_per_reel:.2f} / reel &nbsp; . &nbsp; {len(p.portfolio_items)} reference reels</p>
        </div>
    """ for p in profiles) or "<p>No editors have joined yet.</p>"
    return layout("Editors", f"<h1>Browse Editors</h1>{cards}")


@app.route("/editors/<int:profile_id>")
@login_required
def editor_public_profile(profile_id):
    profile = EditorProfile.query.get_or_404(profile_id)
    reels = "".join(f"""
        <div class="reel">
            <strong>{r.title}</strong>
            <p><a href="{r.video_url}" target="_blank">Watch reel</a></p>
            <p style="font-size:13px;color:#666">{r.notes}</p>
        </div>
    """ for r in profile.portfolio_items) or "<p>No reference reels uploaded yet.</p>"

    hire_button = ""
    if current_user.role == "client":
        hire_button = f'<a href="/jobs/hire/{profile.user_id}"><button>Hire {profile.user.name} directly</button></a>'

    body = f"""
    <h1>{profile.user.name}</h1>
    <p>{profile.bio or "No bio yet."}</p>
    <p>Rate: ${profile.price_per_reel:.2f} / reel</p>
    {hire_button}
    <h3>Reference reels</h3>
    {reels}
    """
    return layout(profile.user.name, body)


@app.route("/editor/portfolio", methods=["GET", "POST"])
@login_required
def editor_portfolio():
    if current_user.role != "editor":
        abort(403)
    profile = current_user.editor_profile

    if request.method == "POST":
        check_csrf()
        action = request.form.get("action")
        if action == "update_profile":
            profile.bio = request.form.get("bio", "").strip()
            try:
                profile.price_per_reel = float(request.form.get("price_per_reel", 0))
            except ValueError:
                profile.price_per_reel = 0.0
        elif action == "add_reel":
            db.session.add(PortfolioItem(
                editor_id=current_user.id,
                title=request.form["title"].strip(),
                video_url=request.form["video_url"].strip(),
                notes=request.form.get("notes", "").strip(),
            ))
        elif action == "delete_reel":
            item = PortfolioItem.query.get(int(request.form["reel_id"]))
            if item and item.editor_id == current_user.id:
                db.session.delete(item)
        db.session.commit()
        return redirect(url_for("editor_portfolio"))

    token = csrf_token()
    reels = "".join(f"""
        <div class="reel">
            <strong>{r.title}</strong>
            <p><a href="{r.video_url}" target="_blank">Watch</a></p>
            <p style="font-size:13px;color:#666">{r.notes}</p>
            <form method="post">
                <input type="hidden" name="_csrf" value="{token}">
                <input type="hidden" name="action" value="delete_reel">
                <input type="hidden" name="reel_id" value="{r.id}">
                <button type="submit">Delete</button>
            </form>
        </div>
    """ for r in profile.portfolio_items) or "<p>You haven't added any reference reels yet.</p>"

    body = f"""
    <h1>My Profile & Reference Reels</h1>

    <h3>Profile</h3>
    <form method="post">
        <input type="hidden" name="_csrf" value="{token}">
        <input type="hidden" name="action" value="update_profile">
        <label>Bio</label><textarea name="bio" rows="4">{profile.bio}</textarea>
        <label>Price per reel ($)</label><input type="number" step="0.01" name="price_per_reel" value="{profile.price_per_reel}">
        <button type="submit">Save profile</button>
    </form>
    <p>Total earnings so far: ${profile.earnings:.2f}</p>

    <h3>Add a reference reel</h3>
    <form method="post">
        <input type="hidden" name="_csrf" value="{token}">
        <input type="hidden" name="action" value="add_reel">
        <label>Title</label><input name="title" required placeholder="e.g. Fashion brand launch reel">
        <label>Video link</label><input name="video_url" required placeholder="YouTube / Instagram / Drive link">
        <label>Notes</label><input name="notes" placeholder="e.g. fast cuts, trending audio, bold captions">
        <button type="submit">Add reel</button>
    </form>

    <h3>My reference reels</h3>
    {reels}
    """
    return layout("My Portfolio", body)


# ---------- Direct hire flow (based on reference reel) ----------

@app.route("/jobs/hire/<int:editor_id>", methods=["GET", "POST"])
@login_required
def hire_editor(editor_id):
    if current_user.role != "client":
        abort(403)
    editor = User.query.get_or_404(editor_id)
    if editor.role != "editor":
        abort(404)
    profile = editor.editor_profile

    if request.method == "POST":
        check_csrf()
        try:
            budget = float(request.form["budget"])
        except ValueError:
            budget = profile.price_per_reel

        job = Job(
            client_id=current_user.id,
            editor_id=editor.id,
            title=request.form["title"].strip(),
            description=request.form["description"].strip(),
            editing_instructions=request.form["editing_instructions"].strip(),
            budget=budget,
            status="assigned",  # skip the open/apply step -- client picked this editor directly
        )
        db.session.add(job)
        db.session.commit()
        return redirect(url_for("job_detail", job_id=job.id))

    token = csrf_token()
    body = f"""
    <h1>Hire {editor.name}</h1>
    <p>Rate: ${profile.price_per_reel:.2f} / reel</p>
    <form method="post">
        <input type="hidden" name="_csrf" value="{token}">
        <label>Title</label><input name="title" required placeholder="e.g. 30s Reel for product drop">
        <label>Description</label>
        <textarea name="description" rows="3" required placeholder="What's the reel about, raw footage links, deadline..."></textarea>
        <label>Your idea / editing instructions</label>
        <textarea name="editing_instructions" rows="6" required
            placeholder="Describe how you want it edited: pacing, music style, captions, transitions, hook in first 2s, color grade, CTA, aspect ratio, reference to one of their reels you liked..."></textarea>
        <label>Budget ($)</label><input type="number" step="0.01" name="budget" value="{profile.price_per_reel}" required>
        <button type="submit">Send hire request</button>
    </form>
    """
    return layout(f"Hire {editor.name}", body)


# ---------- Open jobs (anyone can apply) ----------

@app.route("/jobs/new", methods=["GET", "POST"])
@login_required
def new_job():
    if current_user.role != "client":
        abort(403)

    if request.method == "POST":
        check_csrf()
        try:
            budget = float(request.form["budget"])
        except ValueError:
            return layout("Post a Job", "<p>Invalid budget.</p>")

        job = Job(
            client_id=current_user.id,
            title=request.form["title"].strip(),
            description=request.form["description"].strip(),
            editing_instructions=request.form["editing_instructions"].strip(),
            budget=budget,
        )
        db.session.add(job)
        db.session.commit()
        return redirect(url_for("job_detail", job_id=job.id))

    token = csrf_token()
    body = f"""
    <h1>Post an Open Job</h1>
    <p>Not sure who to hire? Post the job and let editors apply with a bid.</p>
    <form method="post">
        <input type="hidden" name="_csrf" value="{token}">
        <label>Title</label><input name="title" required>
        <label>Description</label><textarea name="description" rows="3" required></textarea>
        <label>Editing instructions</label>
        <textarea name="editing_instructions" rows="6" required
            placeholder="Pacing, music, captions, transitions, hook, CTA, aspect ratio, reference reels..."></textarea>
        <label>Budget ($)</label><input type="number" step="0.01" name="budget" required>
        <button type="submit">Post Job</button>
    </form>
    """
    return layout("Post a Job", body)


@app.route("/jobs/browse")
@login_required
def browse_jobs():
    if current_user.role != "editor":
        abort(403)
    jobs = Job.query.filter_by(status="open").order_by(Job.created_at.desc()).all()
    cards = "".join(f"""
        <div class="card">
            <h3><a href="/jobs/{j.id}">{j.title}</a></h3>
            <p>{j.description[:150]}</p>
            <p>Budget: ${j.budget:.2f}</p>
        </div>
    """ for j in jobs) or "<p>No open jobs right now.</p>"
    return layout("Browse Jobs", f"<h1>Open Jobs</h1>{cards}")


# ---------- Job detail & lifecycle ----------

@app.route("/jobs/<int:job_id>")
@login_required
def job_detail(job_id):
    job = Job.query.get_or_404(job_id)
    is_owner = current_user.role == "client" and job.client_id == current_user.id
    is_assigned_editor = current_user.role == "editor" and job.editor_id == current_user.id

    if not is_owner and not is_assigned_editor and current_user.role != "editor":
        abort(403)

    token = csrf_token()
    extra = ""

    if is_owner:
        if job.status == "open" and job.applications:
            apps_html = "".join(f"""
                <div class="card">
                    <p><strong>{a.editor.name}</strong> bid ${a.bid_amount:.2f}</p>
                    <p>{a.message}</p>
                    <form method="post" action="/jobs/{job.id}/accept/{a.id}">
                        <input type="hidden" name="_csrf" value="{token}">
                        <button type="submit">Hire this editor</button>
                    </form>
                </div>
            """ for a in job.applications if a.status == "pending")
            extra += f"<h3>Applications</h3>{apps_html}"
        elif job.status == "assigned":
            extra += f"""
                <p>Editor: <strong>{job.editor.name}</strong></p>
                <form method="post" action="/jobs/{job.id}/pay">
                    <input type="hidden" name="_csrf" value="{token}">
                    <button type="submit">Pay ${job.budget:.2f} now</button>
                </form>
            """
        elif job.status == "delivered":
            extra += f"""
                <p>Delivery: <a href="{job.delivery_url}" target="_blank">{job.delivery_url}</a></p>
                <form method="post" action="/jobs/{job.id}/complete">
                    <input type="hidden" name="_csrf" value="{token}">
                    <button type="submit">Approve & Mark Complete</button>
                </form>
            """
        elif job.status == "completed":
            extra += "<p>Job completed and paid out.</p>"

    if current_user.role == "editor" and not is_owner:
        if job.status == "open":
            extra += f"""
                <h3>Apply</h3>
                <form method="post" action="/jobs/{job.id}/apply">
                    <input type="hidden" name="_csrf" value="{token}">
                    <label>Your bid ($)</label><input type="number" step="0.01" name="bid_amount" required>
                    <label>Message</label><textarea name="message" rows="3" required></textarea>
                    <button type="submit">Send application</button>
                </form>
            """
        elif is_assigned_editor and job.status == "paid":
            extra += f"""
                <h3>Deliver your work</h3>
                <form method="post" action="/jobs/{job.id}/deliver">
                    <input type="hidden" name="_csrf" value="{token}">
                    <label>Link to edited reel</label>
                    <input name="delivery_url" required>
                    <button type="submit">Submit delivery</button>
                </form>
            """
        elif is_assigned_editor and job.status == "assigned":
            extra += "<p>Waiting for client to pay before you deliver.</p>"

    body = f"""
    <h1>{job.title}</h1>
    <p><span class="status">{job.status}</span> &nbsp; Budget: ${job.budget:.2f}</p>
    <h3>Description</h3><p>{job.description}</p>
    <h3>Editing instructions</h3><p style="white-space: pre-line">{job.editing_instructions}</p>
    {extra}
    """
    return layout(job.title, body)


@app.route("/jobs/<int:job_id>/apply", methods=["POST"])
@login_required
def apply_to_job(job_id):
    check_csrf()
    if current_user.role != "editor":
        abort(403)
    job = Job.query.get_or_404(job_id)
    if job.status != "open":
        abort(400)

    db.session.add(Application(
        job_id=job.id,
        editor_id=current_user.id,
        message=request.form["message"].strip(),
        bid_amount=float(request.form["bid_amount"]),
    ))
    db.session.commit()
    return redirect(url_for("job_detail", job_id=job.id))


@app.route("/jobs/<int:job_id>/accept/<int:app_id>", methods=["POST"])
@login_required
def accept_application(job_id, app_id):
    check_csrf()
    job = Job.query.get_or_404(job_id)
    if current_user.role != "client" or job.client_id != current_user.id or job.status != "open":
        abort(403)

    application = Application.query.get_or_404(app_id)
    if application.job_id != job.id:
        abort(400)

    application.status = "accepted"
    job.editor_id = application.editor_id
    job.status = "assigned"

    for other in job.applications:
        if other.id != application.id:
            other.status = "rejected"

    db.session.commit()
    return redirect(url_for("job_detail", job_id=job.id))


@app.route("/jobs/<int:job_id>/pay", methods=["POST"])
@login_required
def pay_job(job_id):
    check_csrf()
    job = Job.query.get_or_404(job_id)
    if current_user.role != "client" or job.client_id != current_user.id or job.status != "assigned":
        abort(403)

    # --- Payment happens here ---
    # Mock/escrow flow so the app runs standalone with zero setup.
    # To take real card payments, replace this with a Stripe Checkout Session:
    #   session = stripe.checkout.Session.create(
    #       payment_method_types=["card"],
    #       line_items=[{"price_data": {
    #           "currency": "usd",
    #           "product_data": {"name": job.title},
    #           "unit_amount": int(job.budget * 100),
    #       }, "quantity": 1}],
    #       mode="payment",
    #       success_url=url_for("job_detail", job_id=job.id, _external=True),
    #       cancel_url=url_for("job_detail", job_id=job.id, _external=True),
    #   )
    #   return redirect(session.url, code=303)
    # then confirm the charge in a webhook before flipping status to "paid".
    job.status = "paid"
    db.session.commit()
    return redirect(url_for("job_detail", job_id=job.id))


@app.route("/jobs/<int:job_id>/deliver", methods=["POST"])
@login_required
def deliver_job(job_id):
    check_csrf()
    job = Job.query.get_or_404(job_id)
    if current_user.role != "editor" or job.editor_id != current_user.id or job.status != "paid":
        abort(403)

    job.delivery_url = request.form["delivery_url"].strip()
    job.status = "delivered"
    db.session.commit()
    return redirect(url_for("job_detail", job_id=job.id))


@app.route("/jobs/<int:job_id>/complete", methods=["POST"])
@login_required
def complete_job(job_id):
    check_csrf()
    job = Job.query.get_or_404(job_id)
    if current_user.role != "client" or job.client_id != current_user.id or job.status != "delivered":
        abort(403)

    job.status = "completed"
    job.editor.editor_profile.earnings += job.budget
    db.session.commit()
    return redirect(url_for("job_detail", job_id=job.id))


# link portfolio items on the relationship (declared after PortfolioItem for clarity)
EditorProfile.portfolio_items = db.relationship(
    "PortfolioItem", primaryjoin=EditorProfile.user_id == PortfolioItem.editor_id,
    foreign_keys=[PortfolioItem.editor_id], viewonly=False
)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
