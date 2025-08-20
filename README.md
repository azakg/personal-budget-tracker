Budget Tracker — MVP (Flask + SQLite)

A simple web application for tracking income and expenses. This is a minimal viable product (MVP) built with Flask and SQLite.

✨ Features

✔️ Add income and expenses✔️ View monthly totals (Income, Expenses, Balance)✔️ Transaction table for the current month✔️ Delete transactions✔️ Switch between months

🚀 Installation & Run

1. Clone the repository

git clone https://github.com/USERNAME/personal-budget-tracker.git
cd personal-budget-tracker

2. Create virtual environment & install dependencies

python3 -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\\Scripts\\Activate.ps1 # Windows PowerShell

pip install -r requirements.txt

3. Run the app

python app.py

➡️ Then open http://127.0.0.1:5000 in your browser.

📂 Project structure

personal-budget-tracker/
├── app.py              # main Flask code
├── requirements.txt    # dependencies
├── templates/          # HTML templates (base.html, index.html)
├── instance/           # SQLite database (auto-created)
└── .gitignore

🛠 Tech stack

Python 3.11+

Flask 3.0

SQLite (embedded DB)

Bootstrap 5 (UI)

🔮 Roadmap

📊 Categories & category reports

🎯 Budgets and monthly goals

📈 Charts with Chart.js

🔐 User authentication

📤 CSV export/import

📜 License

MIT — free to use and modify.
