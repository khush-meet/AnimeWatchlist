import json
import os
import re
import threading
import time
from functools import wraps
from pathlib import Path

import requests
from flask import (Flask, Response, jsonify, redirect, render_template,
                   request, session, url_for)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

from data import CURATED, _key
from scrape import get_page

BASE = Path(__file__).parent
REFRESH_EVERY = 6 * 3600  # auto-update the list every 6 hours (when someone visits)
ADMIN_USER = os.environ.get("OWNER_USERNAME", "khush-meet").strip().lower()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-change-me")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 90
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024  # biggest upload allowed: 4 MB

db_url = os.environ.get("DATABASE_URL", "sqlite:///" + str(BASE / "anitrack.db"))
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
db = SQLAlchemy(app)


# ---------------------------------------------------------------- database
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False)
    pw = db.Column(db.String(255), nullable=False)


class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(300), unique=True, index=True, nullable=False)
    title = db.Column(db.String(500), nullable=False)
    hindi = db.Column(db.Boolean, default=False)
    movie = db.Column(db.Boolean, default=False)
    image = db.Column(db.String(500), default="")
    year = db.Column(db.Integer)
    eps = db.Column(db.Integer)
    mins = db.Column(db.Integer)
    genres = db.Column(db.String(200), default="")
    curated = db.Column(db.Boolean, default=False)    # written by you (data.py or added on the site)
    listed = db.Column(db.Boolean, default=True)      # currently on the website
    looked_up = db.Column(db.Boolean, default=False)  # poster/details already fetched
    added = db.Column(db.Integer, default=lambda: int(time.time()))


class Extra(db.Model):
    """Priority, note and uploaded poster for an anime."""
    uid = db.Column(db.String(300), primary_key=True)
    tier = db.Column(db.String(20), default="optional")
    note = db.Column(db.String(300), default="")
    mime = db.Column(db.String(50), default="")
    data = db.Column(db.LargeBinary)


class Watched(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    uid = db.Column(db.String(300), nullable=False)
    __table_args__ = (db.UniqueConstraint("user_id", "uid"),)


class Meta(db.Model):
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(100))


def get_meta(key, default=""):
    m = db.session.get(Meta, key)
    return m.value if m else default


def set_meta(key, value):
    m = db.session.get(Meta, key)
    if m:
        m.value = str(value)
    else:
        db.session.add(Meta(key=key, value=str(value)))
    db.session.commit()


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def seed():
    """First run only: fill the database from data.py + the JSON files you already have."""
    db.create_all()
    if Item.query.first():
        return
    seen = set()
    for c in CURATED:
        uid = _key(c["title"])
        seen.add(uid)
        db.session.add(Item(uid=uid, title=c["title"], hindi=c["hindi"],
                            movie=(c["kind"] == "Movie"), curated=True))
    for s in read_json(BASE / "scraped_titles.json", []):
        uid = _key(s.get("title", ""))
        if not uid or uid in seen:
            continue
        seen.add(uid)
        db.session.add(Item(uid=uid, title=s["title"], hindi=bool(s.get("hindi")),
                            movie=bool(s.get("movie"))))
    db.session.commit()


def migrate_curated():
    """One time: copy the details written in data.py into the database,
    so that every anime (even those) can be edited from the website."""
    if get_meta("curated_migrated") == "1":
        return
    items = {i.uid: i for i in Item.query.all()}
    for c in CURATED:
        uid = _key(c["title"])
        it = items.get(uid)
        if not it:
            it = Item(uid=uid, title=c["title"])
            db.session.add(it)
            items[uid] = it
        it.title = c["title"]
        it.curated = True
        it.hindi = c["hindi"]
        it.movie = c["kind"] == "Movie"
        it.year, it.eps, it.mins = c["year"], c["eps"], c["mins"]
        it.genres = ",".join(c["genres"])
        if not db.session.get(Extra, uid):
            db.session.add(Extra(uid=uid, tier=c["tier"], note=c.get("note", "")))
    db.session.commit()
    set_meta("curated_migrated", "1")


def load_local_images():
    """Every start: use posters from images.json for anime that have none yet."""
    images = read_json(BASE / "images.json", {})
    changed = False
    for it in Item.query.filter((Item.image == "") | (Item.image.is_(None))).all():
        url = images.get(it.uid)
        if url:
            it.image = url
            changed = True
    if changed:
        db.session.commit()


def ensure_admin():
    """Create the admin account on startup. Password comes from ADMIN_PASSWORD
    (set it on your hosting site); if not set, it is 'Khush-meet'."""
    pw = os.environ.get("ADMIN_PASSWORD") or "Khush-meet"
    if not User.query.filter_by(username=ADMIN_USER).first():
        db.session.add(User(username=ADMIN_USER, pw=generate_password_hash(pw)))
        db.session.commit()


# ------------------------------------------------- auto-update from the site
_lock = threading.Lock()
ANILIST_Q = ("query($s:String){Media(search:$s,type:ANIME)"
             "{coverImage{large} episodes duration seasonYear genres}}")


def anilist(title):
    """Returns details dict, {} if not found, None if the network failed."""
    for q in (title, re.sub(r"\s*\(?season\s*\d+\)?", "", title, flags=re.I).strip()):
        try:
            r = requests.post("https://graphql.anilist.co",
                              json={"query": ANILIST_Q, "variables": {"s": q}}, timeout=20)
        except requests.RequestException:
            return None
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", 30)))
            continue
        if r.status_code == 200:
            media = (r.json().get("data") or {}).get("Media")
            if media:
                return media
        time.sleep(1)
    return {}


def _refresh():
    set_meta("last_refresh", int(time.time()))  # set first so a failure doesn't retry on every visit

    # 1) read the website's list
    found = {}
    for n in range(1, 56):
        try:
            page = get_page(n)
        except Exception as e:
            print(f"refresh: page {n} stopped: {e}")
            break
        if not page:
            break
        for p in page:
            found.setdefault(_key(p["title"]), p)
        time.sleep(1)

    # 2) add new titles, hide removed ones
    if found:
        existing = {i.uid: i for i in Item.query.all()}
        for uid, p in found.items():
            if not uid:
                continue
            it = existing.get(uid)
            if it:
                it.listed = True
            else:
                db.session.add(Item(uid=uid, title=p["title"], hindi=p["hindi"], movie=p["movie"]))
        scraped_listed = [i for i in existing.values() if not i.curated and i.listed]
        if len(found) >= max(30, len(scraped_listed) // 2):  # only if the scrape looks complete
            for i in scraped_listed:
                if i.uid not in found:
                    i.listed = False
        db.session.commit()

    # 3) fetch poster + genres + episodes, but only fill what is missing
    deadline = time.time() + 150
    todo = Item.query.filter_by(looked_up=False, listed=True).order_by(Item.id).all()
    todo.sort(key=lambda i: bool(i.image))  # anime without a poster first
    for it in todo:
        if time.time() > deadline:
            break
        m = anilist(it.title)
        if m is None:
            break  # network trouble, try next time
        if m:
            cover = (m.get("coverImage") or {}).get("large")
            it.image = it.image or cover or ""
            it.year = it.year or m.get("seasonYear")
            it.eps = it.eps or m.get("episodes")
            it.mins = it.mins or m.get("duration")
            it.genres = it.genres or ",".join(m.get("genres") or [])
        it.looked_up = True
        db.session.commit()
        time.sleep(1)


def refresh():
    if not _lock.acquire(blocking=False):
        return
    try:
        with app.app_context():
            _refresh()
    except Exception as e:
        print("refresh failed:", e)
    finally:
        _lock.release()


def maybe_refresh():
    last = float(get_meta("last_refresh", "0") or 0)
    if time.time() - last > REFRESH_EVERY and not _lock.locked():
        threading.Thread(target=refresh, daemon=True).start()


# ------------------------------------------------------------------ titles
def build_titles():
    rows = Item.query.filter(db.or_(Item.curated, Item.listed)).order_by(Item.id).all()
    extras = {e.uid: e for e in db.session.query(Extra.uid, Extra.tier, Extra.note)}
    out = []
    for it in rows:
        ex = extras.get(it.uid)
        out.append(dict(
            uid=it.uid,
            title=it.title,
            kind="Movie" if it.movie else "Series",
            year=it.year, eps=it.eps, mins=it.mins,
            genres=[g for g in (it.genres or "").split(",") if g] or ["Unsorted"],
            hindi=bool(it.hindi),
            tier=(ex.tier if ex and ex.tier else "optional"),
            note=(ex.note if ex and ex.note else ""),
            image=it.image or "",
            added=it.added or 0,
            custom=bool(it.curated),   # can be deleted
        ))
    return out


# -------------------------------------------------------------------- login
_fails = {}  # ip -> (count, first_time): simple brute-force guard


def login_required(f):
    @wraps(f)
    def wrapper(*a, **k):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify(error="login"), 401
            return redirect(url_for("login"))
        return f(*a, **k)
    return wrapper


def is_owner():
    """Only the admin account can add / edit / delete anime."""
    return "user_id" in session and session.get("username") == ADMIN_USER


def owner_required(f):
    @wraps(f)
    @login_required
    def wrapper(*a, **k):
        if not is_owner():
            return jsonify(error="Only the admin can do this."), 403
        return f(*a, **k)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
        count, first = _fails.get(ip, (0, time.time()))
        if time.time() - first > 600:
            count, first = 0, time.time()
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        action = request.form.get("action", "login")

        if count >= 8:
            error = "Too many attempts. Try again in 10 minutes."
        elif action == "register":
            if not re.fullmatch(r"[a-z0-9_-]{3,30}", username):
                error = "Username: 3 to 30 letters, numbers, - or _ ."
            elif len(password) < 6:
                error = "Password must be at least 6 characters."
            elif User.query.filter_by(username=username).first():
                error = "That username is taken."
            else:
                u = User(username=username, pw=generate_password_hash(password))
                db.session.add(u)
                db.session.commit()
                session.permanent = True
                session["user_id"], session["username"] = u.id, u.username
                return redirect(url_for("index"))
        else:
            u = User.query.filter_by(username=username).first()
            if u and check_password_hash(u.pw, password):
                session.permanent = True
                session["user_id"], session["username"] = u.id, u.username
                _fails.pop(ip, None)
                return redirect(url_for("index"))
            _fails[ip] = (count + 1, first)
            error = "Wrong username or password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# --------------------------------------------------------------------- pages
@app.route("/")
@login_required
def index():
    maybe_refresh()
    titles = build_titles()
    genres = sorted({g for x in titles for g in x["genres"]})
    watched = [w.uid for w in Watched.query.filter_by(user_id=session["user_id"])]
    return render_template("index.html", titles=titles, genres=genres,
                           watched=watched, username=session.get("username", ""),
                           is_owner=is_owner())


@app.route("/api/watch", methods=["POST"])
@login_required
def api_watch():
    data = request.get_json(silent=True) or {}
    uid, on = data.get("uid", ""), bool(data.get("on"))
    if not Item.query.filter_by(uid=uid).first():
        return jsonify(error="unknown title"), 400
    row = Watched.query.filter_by(user_id=session["user_id"], uid=uid).first()
    if on and not row:
        db.session.add(Watched(user_id=session["user_id"], uid=uid))
    elif not on and row:
        db.session.delete(row)
    db.session.commit()
    return jsonify(ok=True)


@app.route("/api/export")
@login_required
def api_export():
    data = {w.uid: True for w in Watched.query.filter_by(user_id=session["user_id"])}
    return Response(json.dumps(data, indent=1), mimetype="application/json",
                    headers={"Content-Disposition": "attachment; filename=anitrack-watched.json"})


@app.route("/api/import", methods=["POST"])
@login_required
def api_import():
    data = request.get_json(silent=True)
    if isinstance(data, dict):
        uids = [k for k, v in data.items() if v]
    elif isinstance(data, list):
        uids = [u for u in data if isinstance(u, str)]
    else:
        return jsonify(error="bad file"), 400
    uids = uids[:5000]
    valid = {i.uid for i in Item.query.filter(Item.uid.in_(uids)).all()}
    have = {w.uid for w in Watched.query.filter_by(user_id=session["user_id"])}
    new = valid - have
    for u in new:
        db.session.add(Watched(user_id=session["user_id"], uid=u))
    db.session.commit()
    return jsonify(added=len(new))


# ------------------------------------------- add / edit / delete (admin only)
def sniff_image(data):
    """Work out the real image type from the file itself (never trust the filename)."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return ""


def num(value, lo, hi):
    try:
        n = int(str(value).strip())
    except ValueError:
        return None
    return n if lo <= n <= hi else None


@app.route("/api/title", methods=["POST"])
@owner_required
def api_title():
    f = request.form
    title = f.get("title", "").strip()
    if not title or len(title) > 200:
        return jsonify(error="Please type the anime name (up to 200 letters)."), 400

    kind = "Movie" if f.get("kind") == "Movie" else "Series"
    tier = f.get("tier") if f.get("tier") in ("essential", "recommended", "optional") else "optional"
    genres = [g.strip() for g in f.get("genres", "").split(",") if g.strip()][:8]
    note = f.get("note", "").strip()[:300]
    image_url = f.get("image_url", "").strip()
    file = request.files.get("image")

    orig = f.get("uid", "").strip()
    if orig:  # editing an existing one
        it = Item.query.filter_by(uid=orig).first()
        if not it:
            return jsonify(error="That anime was not found."), 400
        it.title = title
    else:     # adding a new one
        uid = _key(title)
        if not uid:
            return jsonify(error="Please use letters or numbers in the name."), 400
        if Item.query.filter_by(uid=uid).first():
            return jsonify(error="That anime is already in the list. Use its Edit button."), 400
        it = Item(uid=uid, title=title, curated=True, listed=True)
        db.session.add(it)

    it.movie = kind == "Movie"
    it.year = num(f.get("year"), 1900, 2100)
    it.eps = num(f.get("eps"), 1, 5000)
    it.mins = num(f.get("mins"), 1, 600)
    it.genres = ",".join(genres)
    it.hindi = f.get("hindi") == "1"
    it.looked_up = True  # stops the auto-updater from touching your details

    ex = db.session.get(Extra, it.uid)
    if not ex:
        ex = Extra(uid=it.uid)
        db.session.add(ex)
    ex.tier, ex.note = tier, note

    if file and file.filename:
        data = file.read()
        mime = sniff_image(data)
        if not mime:
            db.session.rollback()
            return jsonify(error="That file is not a picture (use JPG, PNG, WEBP or GIF)."), 400
        if len(data) > 2 * 1024 * 1024:
            db.session.rollback()
            return jsonify(error="Picture is too big (max 2 MB)."), 400
        ex.data, ex.mime = data, mime
        it.image = f"/img/{it.uid}?v={int(time.time())}"
    elif image_url:
        if not re.match(r"^https?://", image_url, re.I) or len(image_url) > 500:
            db.session.rollback()
            return jsonify(error="Image link must start with http:// or https://"), 400
        it.image = image_url
        ex.data, ex.mime = None, ""

    db.session.commit()
    return jsonify(ok=True)


@app.route("/api/title/<uid>/delete", methods=["POST"])
@owner_required
def api_title_delete(uid):
    it = Item.query.filter_by(uid=uid).first()
    if not it or not it.curated:
        return jsonify(error="Anime that come from the website cannot be deleted."), 400
    Watched.query.filter_by(uid=uid).delete()
    Extra.query.filter_by(uid=uid).delete()
    db.session.delete(it)
    db.session.commit()
    return jsonify(ok=True)


@app.route("/img/<uid>")
def img(uid):
    ex = db.session.get(Extra, uid)
    if not ex or not ex.data:
        return Response(status=404)
    return Response(ex.data, mimetype=ex.mime or "image/jpeg",
                    headers={"Cache-Control": "public, max-age=31536000",
                             "X-Content-Type-Options": "nosniff"})


@app.errorhandler(413)
def too_big(e):
    return jsonify(error="Picture is too big (max 4 MB)."), 413


@app.route("/admin/refresh")
def admin_refresh():
    """Force an update: /admin/refresh?token=YOUR_ADMIN_TOKEN"""
    token = os.environ.get("ADMIN_TOKEN")
    if not token or request.args.get("token") != token:
        return "Not allowed", 403
    threading.Thread(target=refresh, daemon=True).start()
    return "Refresh started. Check again in a few minutes."


with app.app_context():
    seed()
    migrate_curated()
    load_local_images()
    ensure_admin()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)),
            debug=os.environ.get("FLASK_DEBUG") == "1")