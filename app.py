import os, sqlite3
from functools import wraps
from datetime import date
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "student_management_v2.db")
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key-before-deployment")
app.config["DATABASE"] = DB_PATH

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db: db.close()

def init_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS admins(
      id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS classes(
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
    CREATE TABLE IF NOT EXISTS subjects(
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, code TEXT UNIQUE NOT NULL);
    CREATE TABLE IF NOT EXISTS class_subjects(
      class_id INTEGER NOT NULL, subject_id INTEGER NOT NULL,
      PRIMARY KEY(class_id,subject_id),
      FOREIGN KEY(class_id) REFERENCES classes(id) ON DELETE CASCADE,
      FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS students(
      id INTEGER PRIMARY KEY AUTOINCREMENT, roll_no TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
      email TEXT, phone TEXT, department TEXT NOT NULL, year INTEGER NOT NULL,
      class_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(class_id) REFERENCES classes(id) ON DELETE SET NULL);
    CREATE TABLE IF NOT EXISTS attendance(
      id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL, class_id INTEGER NOT NULL,
      subject_id INTEGER NOT NULL, attendance_date TEXT NOT NULL,
      status TEXT NOT NULL CHECK(status IN ('Present','Absent')),
      UNIQUE(student_id,class_id,subject_id,attendance_date),
      FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
      FOREIGN KEY(class_id) REFERENCES classes(id) ON DELETE CASCADE,
      FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS marks(
      id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL, class_id INTEGER NOT NULL,
      subject_id INTEGER NOT NULL, exam_name TEXT NOT NULL, marks_obtained REAL NOT NULL,
      max_marks REAL NOT NULL, UNIQUE(student_id,class_id,subject_id,exam_name),
      FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
      FOREIGN KEY(class_id) REFERENCES classes(id) ON DELETE CASCADE,
      FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE);
    """)
    row = db.execute("SELECT id FROM admins WHERE username='admin'").fetchone()
    if not row:
        db.execute("INSERT INTO admins(username,password_hash) VALUES(?,?)",
                   ("admin", generate_password_hash("admin123")))
    db.commit()
    db.close()

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if "admin_id" not in session: return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped

@app.route("/")
def index():
    return redirect(url_for("dashboard") if session.get("admin_id") else url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        db=get_db()
        row=db.execute("SELECT * FROM admins WHERE username=?", (request.form.get("username","").strip(),)).fetchone()
        if row and check_password_hash(row["password_hash"], request.form.get("password","")):
            session.clear(); session["admin_id"]=row["id"]; session["username"]=row["username"]
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.","error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    db=get_db()
    stats={
      "students":db.execute("SELECT COUNT(*) FROM students").fetchone()[0],
      "classes":db.execute("SELECT COUNT(*) FROM classes").fetchone()[0],
      "subjects":db.execute("SELECT COUNT(*) FROM subjects").fetchone()[0],
      "today":date.today().isoformat(),
      "present":db.execute("SELECT COUNT(*) FROM attendance WHERE attendance_date=? AND status='Present'",(date.today().isoformat(),)).fetchone()[0]
    }
    recent=db.execute("""SELECT s.*,c.name class_name FROM students s LEFT JOIN classes c ON c.id=s.class_id ORDER BY s.id DESC LIMIT 6""").fetchall()
    return render_template("dashboard.html",stats=stats,recent=recent)

@app.route("/classes", methods=["GET","POST"])
@login_required
def classes():
    db=get_db()
    if request.method=="POST":
        name=request.form.get("name","").strip()
        if not name: flash("Enter a class name.","error")
        else:
            try:
                db.execute("INSERT INTO classes(name) VALUES(?)",(name,)); db.commit()
                flash("Class created.","success")
            except sqlite3.IntegrityError: flash("That class already exists.","error")
        return redirect(url_for("classes"))
    rows=db.execute("""SELECT c.*,COUNT(DISTINCT s.id) student_count FROM classes c
      LEFT JOIN students s ON s.class_id=c.id GROUP BY c.id ORDER BY c.name""").fetchall()
    return render_template("classes.html",classes=rows)

@app.route("/subjects", methods=["GET","POST"])
@login_required
def subjects():
    db=get_db()
    if request.method=="POST":
        name=request.form.get("name","").strip(); code=request.form.get("code","").strip().upper()
        class_ids=request.form.getlist("class_ids")
        if not name or not code: flash("Enter subject name and code.","error")
        else:
            try:
                cur=db.execute("INSERT INTO subjects(name,code) VALUES(?,?)",(name,code))
                for cid in class_ids:
                    db.execute("INSERT OR IGNORE INTO class_subjects(class_id,subject_id) VALUES(?,?)",(int(cid),cur.lastrowid))
                db.commit(); flash("Subject created and assigned to selected classes.","success")
            except (sqlite3.IntegrityError,ValueError): db.rollback(); flash("Subject name/code already exists or class selection is invalid.","error")
        return redirect(url_for("subjects"))
    rows=db.execute("""SELECT sub.*,GROUP_CONCAT(c.name, ', ') class_names FROM subjects sub
      LEFT JOIN class_subjects cs ON cs.subject_id=sub.id LEFT JOIN classes c ON c.id=cs.class_id
      GROUP BY sub.id ORDER BY sub.name""").fetchall()
    class_rows=db.execute("SELECT * FROM classes ORDER BY name").fetchall()
    return render_template("subjects.html",subjects=rows,classes=class_rows)

@app.route("/subjects/<int:subject_id>/assign", methods=["POST"])
@login_required
def assign_subject(subject_id):
    db=get_db()
    if not db.execute("SELECT id FROM subjects WHERE id=?",(subject_id,)).fetchone(): return redirect(url_for("subjects"))
    db.execute("DELETE FROM class_subjects WHERE subject_id=?",(subject_id,))
    for cid in request.form.getlist("class_ids"):
        db.execute("INSERT OR IGNORE INTO class_subjects(class_id,subject_id) VALUES(?,?)",(int(cid),subject_id))
    db.commit(); flash("Subject class assignments updated.","success")
    return redirect(url_for("subjects"))

@app.route("/students")
@login_required
def students():
    db=get_db(); q=request.args.get("q","").strip()
    sql="""SELECT s.*,c.name class_name FROM students s LEFT JOIN classes c ON c.id=s.class_id"""
    args=()
    if q:
        sql+=" WHERE s.roll_no LIKE ? OR s.name LIKE ? OR s.department LIKE ? OR c.name LIKE ?"
        args=(f"%{q}%",)*4
    rows=db.execute(sql+" ORDER BY s.id DESC",args).fetchall()
    return render_template("students.html",students=rows,q=q)

@app.route("/students/add", methods=["GET","POST"])
@login_required
def add_student():
    db=get_db(); class_rows=db.execute("SELECT * FROM classes ORDER BY name").fetchall()
    if request.method=="POST":
        f=request.form; roll=f.get("roll_no","").strip(); name=f.get("name","").strip()
        dept=f.get("department","").strip(); email=f.get("email","").strip(); phone=f.get("phone","").strip()
        try:
            year=int(f.get("year",""))
            cid=int(f.get("class_id","")) if f.get("class_id") else None
            if not roll or not name or not dept or year not in (1,2,3,4): raise ValueError
            db.execute("""INSERT INTO students(roll_no,name,email,phone,department,year,class_id)
              VALUES(?,?,?,?,?,?,?)""",(roll,name,email,phone,dept,year,cid))
            db.commit(); flash("Student added and assigned to class.","success"); return redirect(url_for("students"))
        except ValueError: flash("Enter required details and select a valid year/class.","error")
        except sqlite3.IntegrityError: flash("Roll number already exists or selected class is invalid.","error")
    return render_template("add_student.html",student=None,classes=class_rows)

@app.route("/students/<int:student_id>/edit",methods=["GET","POST"])
@login_required
def edit_student(student_id):
    db=get_db(); student=db.execute("SELECT * FROM students WHERE id=?",(student_id,)).fetchone()
    if not student: return redirect(url_for("students"))
    class_rows=db.execute("SELECT * FROM classes ORDER BY name").fetchall()
    if request.method=="POST":
        f=request.form
        try:
            year=int(f.get("year","")); cid=int(f.get("class_id","")) if f.get("class_id") else None
            vals=(f.get("roll_no","").strip(),f.get("name","").strip(),f.get("email","").strip(),
              f.get("phone","").strip(),f.get("department","").strip(),year,cid,student_id)
            if not vals[0] or not vals[1] or not vals[4] or year not in (1,2,3,4): raise ValueError
            db.execute("""UPDATE students SET roll_no=?,name=?,email=?,phone=?,department=?,year=?,class_id=? WHERE id=?""",vals)
            db.commit(); flash("Student updated.","success"); return redirect(url_for("students"))
        except ValueError: flash("Check required details and year.","error")
        except sqlite3.IntegrityError: flash("Roll number already exists.","error")
    return render_template("add_student.html",student=student,classes=class_rows)

@app.route("/students/<int:student_id>/delete",methods=["POST"])
@login_required
def delete_student(student_id):
    db=get_db(); db.execute("DELETE FROM students WHERE id=?",(student_id,)); db.commit()
    flash("Student deleted.","success"); return redirect(url_for("students"))

def class_subject_options(db, class_id):
    return db.execute("""SELECT sub.* FROM subjects sub JOIN class_subjects cs ON cs.subject_id=sub.id
      WHERE cs.class_id=? ORDER BY sub.name""",(class_id,)).fetchall()

@app.route("/class-attendance",methods=["GET","POST"])
@login_required
def class_attendance():
    db=get_db(); class_rows=db.execute("SELECT * FROM classes ORDER BY name").fetchall()
    cid=request.values.get("class_id",""); sid=request.values.get("subject_id","")
    day=request.values.get("attendance_date",date.today().isoformat())
    subjects=[]; students=[]; saved={}
    if cid:
        try:
            cid=int(cid); subjects=class_subject_options(db,cid)
            if sid and any(int(x["id"])==int(sid) for x in subjects):
                sid=int(sid)
                students=db.execute("SELECT * FROM students WHERE class_id=? ORDER BY roll_no",(cid,)).fetchall()
                saved_rows=db.execute("""SELECT student_id,status FROM attendance
                    WHERE class_id=? AND subject_id=? AND attendance_date=?""",(cid,sid,day)).fetchall()
                saved={r["student_id"]:r["status"] for r in saved_rows}
        except ValueError: cid=""; sid=""
    if request.method=="POST":
        if not cid or not sid or not students:
            flash("Choose a class, subject and ensure students are assigned to the class.","error")
        else:
            try:
                date.fromisoformat(day)
                for st in students:
                    status=request.form.get(f"status_{st['id']}")
                    if status not in ("Present","Absent"): raise ValueError
                    db.execute("""INSERT INTO attendance(student_id,class_id,subject_id,attendance_date,status)
                      VALUES(?,?,?,?,?) ON CONFLICT(student_id,class_id,subject_id,attendance_date)
                      DO UPDATE SET status=excluded.status""",(st["id"],cid,sid,day,status))
                db.commit(); flash("Attendance saved for the whole class.","success")
                return redirect(url_for("class_attendance",class_id=cid,subject_id=sid,attendance_date=day))
            except ValueError: db.rollback(); flash("Select Present or Absent for every student and use a valid date.","error")
    return render_template("class_attendance.html",classes=class_rows,subjects=subjects,
      students=students,class_id=cid,subject_id=sid,attendance_date=day,saved=saved)

@app.route("/class-marks",methods=["GET","POST"])
@login_required
def class_marks():
    db=get_db(); class_rows=db.execute("SELECT * FROM classes ORDER BY name").fetchall()
    cid=request.values.get("class_id",""); sid=request.values.get("subject_id","")
    exam=request.values.get("exam_name","").strip(); max_marks=request.values.get("max_marks","100")
    subjects=[]; students=[]; saved={}
    if cid:
        try:
            cid=int(cid); subjects=class_subject_options(db,cid)
            if sid and any(int(x["id"])==int(sid) for x in subjects):
                sid=int(sid); students=db.execute("SELECT * FROM students WHERE class_id=? ORDER BY roll_no",(cid,)).fetchall()
                if exam:
                    rows=db.execute("""SELECT student_id,marks_obtained FROM marks
                      WHERE class_id=? AND subject_id=? AND exam_name=?""",(cid,sid,exam)).fetchall()
                    saved={r["student_id"]:r["marks_obtained"] for r in rows}
        except ValueError: cid=""; sid=""
    if request.method=="POST":
        try:
            max_value=float(max_marks)
            if not cid or not sid or not exam or max_value<=0 or not students: raise ValueError
            for st in students:
                score=float(request.form.get(f"mark_{st['id']}",""))
                if score<0 or score>max_value: raise ValueError
                db.execute("""INSERT INTO marks(student_id,class_id,subject_id,exam_name,marks_obtained,max_marks)
                  VALUES(?,?,?,?,?,?) ON CONFLICT(student_id,class_id,subject_id,exam_name)
                  DO UPDATE SET marks_obtained=excluded.marks_obtained,max_marks=excluded.max_marks""",
                  (st["id"],cid,sid,exam,score,max_value))
            db.commit(); flash("Marks saved for the whole class.","success")
            return redirect(url_for("class_marks",class_id=cid,subject_id=sid,exam_name=exam,max_marks=max_value))
        except (ValueError,TypeError): db.rollback(); flash("Enter an exam name, valid maximum marks, and scores within the range for every student.","error")
    return render_template("class_marks.html",classes=class_rows,subjects=subjects,students=students,
      class_id=cid,subject_id=sid,exam_name=exam,max_marks=max_marks,saved=saved)

@app.route("/students/<int:student_id>/report")
@login_required
def report(student_id):
    db=get_db(); student=db.execute("""SELECT s.*,c.name class_name FROM students s
      LEFT JOIN classes c ON c.id=s.class_id WHERE s.id=?""",(student_id,)).fetchone()
    if not student: return redirect(url_for("students"))
    marks=db.execute("""SELECT sub.name subject,m.exam_name,m.marks_obtained,m.max_marks
      FROM marks m JOIN subjects sub ON sub.id=m.subject_id WHERE m.student_id=? ORDER BY sub.name,m.exam_name""",(student_id,)).fetchall()
    attendance=db.execute("""SELECT sub.name subject,COUNT(*) total,
      SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END) present
      FROM attendance a JOIN subjects sub ON sub.id=a.subject_id WHERE a.student_id=?
      GROUP BY a.subject_id ORDER BY sub.name""",(student_id,)).fetchall()
    return render_template("report.html",student=student,marks=marks,attendance=attendance)

if __name__=="__main__":
    init_db()
    app.run(debug=True)
