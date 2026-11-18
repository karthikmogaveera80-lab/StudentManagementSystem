STUDENT MANAGEMENT SYSTEM - CLASS & SUBJECT VERSION

Features:
- Create different classes (CSE-A, CSE-B, etc.)
- Create subjects and assign each subject to one or more classes
- Add students and assign them to a class
- Open Class Attendance, choose class + subject + date, and mark Present/Absent for every student in that class in one save
- Enter subject-wise marks for a whole class and exam
- Student report shows subject-wise marks and attendance

Run on Windows:
1. Extract this ZIP.
2. Open the extracted StudentManagementSystem_Class_Subject folder in VS Code.
3. In the terminal run:
   py -m venv .venv
   .venv\Scripts\Activate.ps1
   py -m pip install -r requirements.txt
   py app.py
4. Open http://127.0.0.1:5000

Login:
Username: admin
Password: admin123

Important:
This version creates student_management_v2.db so your old database.db is not overwritten.
The new version starts with a clean database. Keep your old project/database.db as a backup.
Change SECRET_KEY before deploying publicly. This is a development app; do not expose it directly to the internet.
