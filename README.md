# School Results Management System

A web app for computing and managing student results: enter test/exam scores per class
and subject, automatic totals/averages/positions/grading, class spreadsheet export, and
individual student PDF report cards (matching the Dominion Noble Global Academy style:
header info, subject table, affective/psychomotor skill ratings, attendance, fees, and
teacher/principal remarks).

Built with **Python (Flask) + SQLite**, so it's lightweight and easy to run on almost any
host without needing a database server.

---

## 1. What it can do

- Up to 20 classes, each with its **own subject list** (subjects don't have to match across classes)
- Multiple teacher accounts — each teacher only sees and enters scores for the class/subject
  they're assigned to
- Test (40%) + Exam (60%) = Total (100%) — fully editable grading scale (grade bands & remarks)
- Auto-computed: subject totals, class subject averages, subject position/rank, overall grand
  total, percentage, and overall class position
- Form-teacher view for entering affective/psychomotor skill ratings, attendance, fees, and
  teacher/principal remarks
- **Export a class spreadsheet (.xlsx)** — one sheet per class, matching the multi-subject
  layout (Test/Exam/Total/Average/Position/Grade per subject)
- **Export student report cards as PDF** — either one student at a time, or the whole class
  as a single multi-page PDF

---

## 2. Running it on your own computer (first, before hosting it online)

You'll need **Python 3.10+** installed. Check with:
```bash
python3 --version
```

Then, inside the project folder:

```bash
# 1. Create a virtual environment (keeps this project's packages separate)
python3 -m venv venv
source venv/bin/activate          # On Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy the example environment file and edit SECRET_KEY
cp .env.example .env
# open .env in any text editor and replace SECRET_KEY with a long random string

# 4. Run the app
python3 app.py
```

Open **http://127.0.0.1:5000** in your browser. The first time you visit, you'll be asked
to create your **admin account** — this is you, the school admin. From there:

1. Go to **Settings** -> set your school name, address, current term & session
2. Go to **Classes** -> add your classes (e.g. "Basic 4", "JSS 2", up to 20)
3. Click **Manage** on a class -> add the subjects that class offers
4. Go to **Teachers** -> create a login for each teacher
5. Back in **Classes -> Manage subjects** -> assign which teacher handles which subject for
   that class
6. Go to a class's **Students** page -> add students (one at a time, or paste a list for bulk add)
7. Set a **Form Teacher** for each class (on the Classes page) — that teacher can then enter
   skill ratings, attendance, fees and remarks for that class
8. Teachers log in, go to **My Classes**, and enter scores
9. From a class's **Results** page, export the spreadsheet or PDFs at any time — they always
   reflect the latest scores entered

The database is a single file: `instance/results.db`. Back it up regularly (just copy that file).

---

## 3. Hosting it online (so teachers can access it from anywhere)

Below are three beginner-friendly options. All of them work with this project as-is because
it already includes a `Procfile` and `requirements.txt`.

### Option A — Render.com (recommended, free tier available)
1. Push this project to a GitHub repository (see step 4 below if you're not familiar with Git)
2. On render.com, click **New -> Web Service**, connect your GitHub repo
3. Settings:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn "app:create_app()" --bind 0.0.0.0:$PORT`
4. Add an environment variable `SECRET_KEY` with a long random value
5. **Important:** Render's free disk is temporary by default. Add a **Render Disk** (small,
   ~1GB is plenty) mounted at `/opt/render/project/src/instance` so your SQLite database
   survives restarts/deploys. Otherwise your data will be wiped on every redeploy.
6. Click **Create Web Service** — Render gives you a live URL like `yourschool.onrender.com`

### Option B — Railway.app
1. Push to GitHub, then on railway.app choose **Deploy from GitHub repo**
2. Railway auto-detects Python and reads the `Procfile`
3. Add a **Volume** mounted at `/app/instance` so the database persists between deploys
4. Set the `SECRET_KEY` environment variable in the Railway dashboard

### Option C — PythonAnywhere (simplest for absolute beginners, no Git required)
1. Create a free account at pythonanywhere.com
2. Upload your project folder using their **Files** tab (or `git clone` from their Bash console)
3. Open a **Bash console** and run: `pip install --user -r requirements.txt`
4. Go to the **Web** tab -> **Add a new web app** -> choose **Flask** -> point it at `app.py`
   using the `create_app()` factory (PythonAnywhere's wizard will guide you through this)
5. Set the `SECRET_KEY` in the WSGI config file it generates
6. Reload the web app — your site is live at `yourusername.pythonanywhere.com`

PythonAnywhere's disk is persistent by default, so no extra volume/disk setup is needed there.

### A note on the database as you grow
SQLite (the included `instance/results.db` file) comfortably handles a single school with
20 classes and a handful of concurrent teachers. If you eventually need many people typing
scores in at the exact same time, or want automatic offsite backups, you can switch to a
hosted Postgres database (Render and Railway both offer one) just by changing the
`DATABASE_URL` environment variable — no code changes needed, since the app already reads
this from the environment.

---

## 4. If you're not familiar with Git/GitHub (needed for Option A & B)

```bash
cd school_results
git init
git add .
git commit -m "Initial commit"
```
Then create a new (empty) repository on github.com, and follow the push instructions GitHub
shows you (`git remote add origin ...`, `git push -u origin main`).

---

## 5. Project structure

```
school_results/
├── app.py                  # Flask app factory + startup
├── config.py                # Configuration (reads .env)
├── extensions.py             # Shared Flask extensions (db, login manager)
├── models.py                # Database tables (SQLAlchemy)
├── requirements.txt
├── Procfile                 # For Render/Railway deployment
├── routes/
│   ├── auth.py              # Login, logout, first-run admin setup
│   ├── admin.py              # Classes, subjects, teachers, students, grading, settings
│   ├── teacher.py             # Score entry, skills/remarks entry
│   └── results.py             # Computed results view + exports
├── utils/
│   ├── grading.py             # All scoring/ranking/grading computation logic
│   ├── xlsx_export.py          # Class spreadsheet export
│   └── pdf_export.py           # Student report card PDF export
├── templates/                # HTML pages (Bootstrap 5 styling)
└── instance/results.db         # SQLite database (auto-created on first run)
```

## 6. Customizing the grading scale or skills list

Both are editable from the Admin panel — no code changes needed:
- **Admin -> Grading Scale**: add/remove score bands and their grade/remark
- **Admin -> Skills**: add/remove the affective/psychomotor skills shown on report cards

## 7. Common issues

- **"Internal Server Error" right after deploying**: usually means `SECRET_KEY` isn't set, or
  the `instance/` folder isn't writable. Check your host's logs.
- **Scores disappear after a redeploy**: your host's filesystem is ephemeral — add a
  persistent disk/volume as described above, or switch to a hosted Postgres database.
- **A teacher can't see a class**: confirm they're assigned to that class+subject under
  Admin -> Classes -> Manage (subjects page), or set as Form Teacher for skills/remarks access.
