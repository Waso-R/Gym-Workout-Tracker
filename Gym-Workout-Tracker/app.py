from flask import Flask, render_template, session, redirect, url_for, request, g, flash
from flask_session import Session
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db, close_db
from forms import LoginForm, SignupForm, WorkoutForm, SplitForm
from functools import wraps
import calendar
from datetime import datetime
import os

app = Flask(__name__)
app.teardown_appcontext(close_db)
app.config["SECRET_KEY"] = "this-is-my-secret-key"
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"

# Had to ask ChatGpt on how to get file uploads to work
UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
# Until here

Session(app)


@app.before_request
def load_logged_in_user():
    user_id = session.get("user_id")
    if user_id:
        db = get_db()
        g.user = db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    else:
        g.user = None


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login", next=request.url))
        return view(*args, **kwargs)
    return wrapped_view


@app.route("/signup", methods=["GET", "POST"])
def signup():
    form = SignupForm()
    
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        confirm_password = form.confirm_password.data
        db = get_db()

        if password != confirm_password:
            form.confirm_password.errors.append("Passwords do not match!")
            return render_template("signup.html", form=form)

        conflict_user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

        if conflict_user:
            form.username.errors.append("Username already taken!")
        else:
            db.execute("INSERT INTO users (username, password) VALUES (?, ?)", 
                       (username, generate_password_hash(password)))
            db.commit()
            return redirect(url_for("login"))

    return render_template("signup.html", form=form)


@app.route("/login", methods=['GET', 'POST'])
def login():
    form = LoginForm()
    
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

        if user is None:
            form.username.errors.append("No such username!")
        elif not check_password_hash(user["password"], password):
            form.password.errors.append("Incorrect password!")
        else:
            session.clear()
            session["user_id"] = user["user_id"]
            next_page = request.args.get("next") or url_for("index")
            return redirect(next_page)

    return render_template("login.html", form=form)


@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    db = get_db()
    user_id = g.user["user_id"]

    if request.method == "POST":
        current_password = request.form["current_password"]
        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]

        user = db.execute(
            "SELECT password FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()

        if not check_password_hash(user["password"], current_password):
            flash("Current password is incorrect.", "danger")
        elif new_password != confirm_password:
            flash("New passwords do not match.", "danger")
        else:
            db.execute(
                "UPDATE users SET password = ? WHERE user_id = ?",
                (generate_password_hash(new_password), user_id),
            )
            db.commit()
            return redirect(url_for("change_password"))

    return render_template("change_password.html")


########## Home Page ############
@app.route('/')
def index():
    return render_template('index.html')


########## Log_workout ############
@app.route('/log_workout', methods=['GET', 'POST'])
@login_required
def log_workout():
    db = get_db()
    form = WorkoutForm() 

    selected_date = request.args.get('date', datetime.today().strftime('%Y-%m-%d'))

    if form.validate_on_submit():
        db.execute(
            "INSERT INTO workouts (user_id, workout_type, reps, sets, weight, date_logged) VALUES (?, ?, ?, ?, ?, ?)",
            (g.user["user_id"], form.workout_type.data, form.reps.data, form.sets.data, form.weight.data, selected_date)
        )
        db.commit()

        return redirect(url_for('log_workout', date=selected_date))

    if request.method == 'POST' and 'delete' in request.form:
        db.execute(
            "DELETE FROM workouts WHERE user_id = ? AND date_logged = ?",
            (g.user["user_id"], selected_date)
        )
        db.commit()
        return redirect(url_for('log_workout', date=selected_date))

    workouts = db.execute(
        "SELECT workout_type, reps, sets, weight FROM workouts WHERE user_id = ? AND date_logged = ?",
        (g.user["user_id"], selected_date)
    ).fetchall()

    # Part taken from a prompt from chatGPT where I asked it how to use find out the current date for logged workouts
    current_year, current_month = datetime.today().year, datetime.today().month

    workouts_in_month = db.execute(
        "SELECT DISTINCT date_logged FROM workouts WHERE user_id = ? AND strftime('%Y-%m', date_logged) = ?",
        (g.user["user_id"], f"{current_year}-{current_month:02d}")
    ).fetchall()
    workout_dates = {w["date_logged"] for w in workouts_in_month}

    cal = calendar.monthcalendar(current_year, current_month)
    # Until here

    return render_template(
        'log_workout.html',
        form=form,
        workouts=workouts,
        current_year=current_year,
        selected_date=selected_date,
        calendar_data=cal,
        workout_dates=workout_dates,
        year=current_year,
        month=current_month
    )


@app.route('/delete_recent_workout', methods=['POST'])
@login_required
def delete_recent_workout():
    db = get_db()
    
    selected_date = request.form.get('selected_date', datetime.today().strftime('%Y-%m-%d'))
    
    recent_workout = db.execute(
        "SELECT workout_id FROM workouts WHERE user_id = ? ORDER BY workout_id DESC LIMIT 1",
        (g.user["user_id"],)
    ).fetchone()
    
    if recent_workout:
        db.execute("DELETE FROM workouts WHERE workout_id = ?", (recent_workout["workout_id"],))
        db.commit()

    return redirect(url_for('log_workout', date=selected_date))


########## Generate Split ############
@app.route("/generate_split", methods=["GET", "POST"])
@login_required
def generate_split():
    form = SplitForm()
    db = get_db()

    latest_split = db.execute(
        "SELECT id, days_per_week, split FROM workout_splits WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
        (g.user["user_id"],)
    ).fetchone()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "generate":
            days_per_week = form.days_per_week.data
            splits = {
                1: {"Day 1": "Full-Body Workout"},
                2: {"Day 1": "Upper Body", "Day 2": "Lower Body"},
                3: {"Day 1": "Push", "Day 2": "Pull", "Day 3": "Legs"},
                4: {"Day 1": "Upper Body", "Day 2": "Lower Body", "Day 3": "Upper Body", "Day 4": "Lower Body"},
                5: {"Day 1": "Push", "Day 2": "Pull", "Day 3": "Legs", "Day 4": "Push", "Day 5": "Pull"},
                6: {"Day 1": "Chest", "Day 2": "Back", "Day 3": "Legs", "Day 4": "Shoulders", "Day 5": "Arms", "Day 6": "Abs"},
                7: {"Day 1": "Chest", "Day 2": "Back", "Day 3": "Legs", "Day 4": "Shoulders", "Day 5": "Arms", "Day 6": "Abs", "Day 7": "Rest"}
            }
            split = splits.get(days_per_week, {"Day 1": "Custom Workout Split"})
            split_str = "\n".join([f"{day}: {workout}" for day, workout in split.items()])
            return render_template("generate_split.html", form=form, latest_split={"split": split_str})

        elif action == "save":
            days_per_week = request.form.get("days_per_week", type=int)
            updated_split = request.form.get("split")

            if latest_split:
                db.execute(
                    "UPDATE workout_splits SET days_per_week = ?, split = ? WHERE id = ?",
                    (days_per_week, updated_split, latest_split["id"])
                )
            else:
                db.execute(
                    "INSERT INTO workout_splits (user_id, days_per_week, split) VALUES (?, ?, ?)",
                    (g.user["user_id"], days_per_week, updated_split)
                )

            db.commit()
            return redirect(url_for("generate_split"))

    return render_template("generate_split.html", form=form, latest_split=latest_split)



@app.route("/health", methods=["GET", "POST"])
def health():
    if request.method == "POST":
        if "progress_picture" in request.files:
            return redirect(url_for("upload_picture"))

        weight = float(request.form["weight"])
        height = float(request.form["height"])
        height_unit = request.form["height_unit"]
        weight_unit = request.form["weight_unit"]
        age = int(request.form["age"])
        target_weight = float(request.form["target_weight"])

        if weight_unit == "lbs":
            weight *= 0.453592
        if height_unit == "ft":
            height *= 0.3048

        bmi = weight / (height ** 2)
        bmr = 10 * weight + 6.25 * height * 100 - 5 * age + 5
        daily_calories = bmr * 1.55 
        target_calories = daily_calories + (daily_calories * ((target_weight - weight) / weight))

        user_images = session.get("user_images", [])
        user_images = [url_for("static", filename=image.lstrip("/static/")) for image in user_images]

        return render_template(
            "health.html",
            bmi=bmi,
            daily_calories=daily_calories,
            target_calories=target_calories,
            weight=weight,
            height=height,
            age=age,
            target_weight=target_weight,
            user_images=user_images,
        )

    user_images = session.get("user_images", [])
    user_images = [url_for("static", filename=image.lstrip("/static/")) for image in user_images]

    return render_template("health.html", user_images=user_images)



@app.route("/upload_picture", methods=["POST"])
def upload_picture():
    if "progress_picture" not in request.files:
        return redirect(url_for("health"))

    file = request.files["progress_picture"]
    if file.filename == "":
        return redirect(url_for("health"))

    if file:
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
        file.save(filepath)
        rel_path = f"/static/uploads/{file.filename}"

        if "user_images" not in session:
            session["user_images"] = []
        session["user_images"].append(rel_path)
        session.modified = True

    return redirect(url_for("health"))


@app.route("/delete_picture", methods=["POST"])
def delete_picture():
    image_url = request.form.get("image_path")
    
    filename = os.path.basename(image_url)
    
    session_path = f"/static/uploads/{filename}"
    
    if session_path in session.get("user_images", []):
        session["user_images"].remove(session_path)
        session.modified = True
        
        abs_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        if os.path.exists(abs_path):
            os.remove(abs_path)
    
    return redirect(url_for("health"))


########## Personal Records (SBD) ############
@app.route("/personal_records", methods=["GET", "POST"])
@login_required
def personal_records():
    db = get_db()
    user_id = g.user["user_id"]

    if request.method == "POST":
        exercise = request.form["exercise"].strip()
        weight = request.form["weight"]
        date = datetime.now().strftime("%Y-%m-%d")

        existing_pr = db.execute(
            "SELECT * FROM personal_records WHERE user_id = ? AND exercise = ?",
            (user_id, exercise),
        ).fetchone()

        if existing_pr:
            db.execute(
                "UPDATE personal_records SET weight = ?, date = ? WHERE user_id = ? AND exercise = ?",
                (weight, date, user_id, exercise),
            )
        else:
            db.execute(
                "INSERT INTO personal_records (user_id, exercise, weight, date) VALUES (?, ?, ?, ?)",
                (user_id, exercise, weight, date),
            )

        db.commit()
        return redirect(url_for("personal_records"))

    records = db.execute(
        "SELECT exercise, weight, date FROM personal_records WHERE user_id = ?",
        (user_id,),
    ).fetchall()

    sbd = {"Squat": 0, "Bench Press": 0, "Deadlift": 0}
    for record in records:
        sbd[record["exercise"]] = record["weight"]

    total_sbd = sum(sbd.values())
    strongest_lift = max(sbd, key=sbd.get)

    return render_template(
        "pr.html",
        records=sbd,
        total_sbd=total_sbd,
        strongest_lift=strongest_lift
    )


@app.route("/leaderboard")
def leaderboard():
    """See the top lifters for each exercise"""
    
    exercises = ["Bench Press", "Squat", "Deadlift"]

    leaderboard_data = {}
    db = get_db()

    for exercise in exercises:
        query = """
        SELECT users.username, personal_records.weight 
        FROM personal_records
        JOIN users ON personal_records.user_id = users.user_id
        WHERE personal_records.exercise = ?
        ORDER BY personal_records.weight DESC
        LIMIT 5;
        """
        top_lifters = db.execute(query, (exercise,)).fetchall()
        leaderboard_data[exercise] = top_lifters

    return render_template("leaderboard.html", leaderboard_data=leaderboard_data)

if __name__ == '__main__':
    app.run(debug=True)
