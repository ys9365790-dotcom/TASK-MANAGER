# ⚡ TaskManager - Team Productivity & Decision Matrix

A full-stack team productivity and task management platform built with **Flask**, **Flask-Login**, **SQLite**, and **SQLAlchemy**. Features dual board layouts (**3-Column Kanban** and **2x2 Eisenhower Decision Matrix**), natural language task quick-add with live parsing, a built-in 25-minute Pomodoro focus timer with persistent time logs, real-time 3-second multi-user synchronization, a smart priority scoring engine, team workload overload detection with reassignment suggestions, and a **GitHub-style 12-week contribution heatmap** with streak counters.

🔗 **GitHub Repository**: [https://github.com/ys9365790-dotcom/TASK-MANAGER](https://github.com/ys9365790-dotcom/TASK-MANAGER)  
☁️ **Live Deployment**: Hosted on [Render](https://render.com) with automatic zero-downtime GitHub CI/CD redeployments.

---

## 🌟 Key Features

### 1. ⚡ Natural Language Quick-Add Bar
- **Smart Sentence Parsing**: Type natural sentences like *"Finish report tomorrow high priority @ravi important"* to instantly create tasks.
- **Python Regex & `dateparser`**: Parses natural dates (*today, tomorrow, next Friday, Nov 5*), priority levels (*high, medium, low*), user mentions (*@name*), and importance (*important*).
- **Live Preview Badges**: Displays dynamic chip previews of the parsed title, due date, priority, assignee, and importance before submission.
- **Endpoints**: `POST /api/tasks/parse` and `POST /api/tasks/quick-add`.

### 2. ⏱️ 25-Minute Pomodoro Focus Mode & Time Tracking
- **"Start focus" Button on Cards**: Every task card features an inline `⏱️ Start focus` button that launches a dedicated modal with circular SVG countdown ring.
- **Full Timer Controls**: Start, Pause, Resume, and Stop with elapsed minute saving.
- **Web Audio Chime**: Synthesizes a melodic 4-tone celebration chime on completion without external audio assets.
- **TimeLog Table**: Logs completed minutes linked to both the task and user (`time_logs` table).
- **Time Spent Badge**: Displays total accumulated time directly on task cards (e.g. `⏱️ 50m`).
- **Daily Focus Time Chart**: Visual bar chart on the Analytics page showing daily focus minutes over the past 7 days.

### 3. 🔄 Real-Time Live Multi-User Synchronization
- **Lightweight 3-Second Polling**: Uses `GET /api/changes?since=<timestamp>` polled every 3 seconds from `main.js` (no heavy WebSocket infrastructure).
- **Zero-Refresh Updates**: Seamlessly updates card positions, edits, additions, and deletions made by teammates.
- **Live Visual Cues**: 
  - Glowing pulse card animation (`card-live-pulse`).
  - Small author avatar pills on updated cards (e.g. *"Ravi moved this to Doing"*).

### 4. 🎯 Smart Priority Scoring Engine & "Next Up" Panel
- **Calibrated Formula**:
  $$\text{Priority Weight} + \text{Importance Weight} + \text{Days until Due} + \text{Overdue Bonus}$$
  - **Priority**: High = 40 pts, Medium = 20 pts, Low = 5 pts.
  - **Importance**: Important = 30 pts, Normal = 0 pts.
  - **Due Urgency**: Scales up to 30 pts as deadline approaches.
  - **Overdue Bonus**: Past-due tasks surge by 35 to 60 pts.
  - Completed (`done`) tasks score 0 pts.
- **"Next up" Priority Panel**: Displays the top 5 highest-priority tasks for the logged-in user at the top of the board, ranked `#1` to `#5` with quick focus shortcuts.
- **Endpoint**: `GET /api/tasks/next-up`.

### 5. 👥 Team Workload View & Overload Detection
- **Visual Member Bars**: Each team member's load is visualized with an inline progress bar showing active tasks.
- **Overload Threshold Detection**: Automatically flags members carrying $>1.5\times$ the team average (`⚠️ Overloaded (>1.5x avg)`).
- **Actionable Reassignment Suggestions**: Identifies overloaded members and automatically recommends reassigning tasks to specific teammates with open capacity.
- **One-Click Reassign Link**: Direct button to filter the board for the overloaded user.

### 6. 🟩 GitHub-Style 12-Week Contribution Heatmap
- **Plain CSS Grid Calendar**: 12 week columns $\times$ 7 day rows (84 day cells) built without external charting dependencies.
- **ActivityLog Date Grouping**: Groups task completion audit logs by calendar date via Flask and SQLite (`db.func.date(ActivityLog.timestamp)`).
- **GitHub 5-Level Intensity Palette**: Theme-aware color scale (Level 0 through Level 4) for both Dark and Light modes.
- **Streak Counters**:
  - 🔥 **Current Streak**: Consecutive days with completed tasks ending today or yesterday.
  - 🏆 **Longest Streak**: All-time maximum consecutive active days across the 12-week window.
  - 🎯 **Total Completed Tasks** & 📅 **Active Days Count**.
- **Interactive Tooltips**: Hovering any square reveals exact completion counts and formatted dates.
- **Endpoints**: `GET /api/analytics/contributions` and `GET /api/contributions`.

### 7. 📋 Dual Board Views (Kanban & Eisenhower Decision Matrix)
- **3-Column Kanban Board**: SortableJS drag-and-drop between **To Do**, **Doing**, and **Done** with asynchronous REST persistence.
- **2x2 Eisenhower Matrix**: Classifies tasks into Q1 (*Do First*), Q2 (*Schedule*), Q3 (*Delegate*), and Q4 (*Don't Do*). Moving between quadrants automatically adjusts urgency and importance.
- **Client-Side Filters & Search**: Search by title/description, filter by priority or assignee, with zero page reloads.

---

## 📁 Project Directory Structure

```text
TASK MANAGER/
├── app/
│   ├── __init__.py        # Flask application factory, database extension, schema auto-migration
│   ├── config.py          # App configuration (SQLite database URI, secret keys)
│   ├── models.py          # SQLAlchemy models: User, Task, ActivityLog, TimeLog, TaskChange
│   ├── routes.py          # Web routes, authentication, quick-add, focus timer, demo seeder
│   ├── api.py             # REST API (/api/tasks, /api/changes, /api/analytics, /api/contributions)
│   └── task_parser.py     # Natural language task parser (Regex + dateparser)
├── templates/
│   ├── base.html          # Base layout template with theme toggle, flash alerts, and user state
│   ├── index.html         # Main dashboard: Quick-Add, Next Up panel, Kanban board, Eisenhower matrix
│   ├── dashboard.html     # Analytics: Contribution Heatmap, Workload View, Charts, Focus Timer graph
│   ├── task_form.html     # Task creation and editing form with importance toggle
│   ├── activity.html      # Chronological audit trail viewer
│   ├── login.html         # User sign-in page
│   ├── signup.html        # User registration page
│   ├── error.html         # Branded error template (404, 500, 403)
│   └── includes/
│       └── task_card.html # Reusable card component: drag handle, badges, score pill, focus button
├── static/
│   ├── css/
│   │   └── style.css      # Vanilla CSS: tokens, Kanban/Matrix, CSS Grid heatmap, dark/light themes
│   └── js/
│       ├── main.js        # SortableJS, quick-add, 3s polling, focus timer, next-up refresh
│       ├── chart.min.js   # Chart.js library for analytics dashboard
│       └── sortable.min.js# SortableJS library for drag-and-drop
├── requirements.txt       # Python dependencies (Flask, SQLAlchemy, dateparser, gunicorn)
├── run.py                 # Application launcher with CLI database initialization
├── taskmanager.db         # SQLite database file
└── README.md              # Documentation and guide
```

---

## 🚀 Setup & Installation Steps

### Prerequisites
- **Python 3.10+**
- Git & Web Browser

### 1. Clone & Navigate
```bash
git clone https://github.com/ys9365790-dotcom/TASK-MANAGER.git
cd "TASK MANAGER"
```

### 2. Set Up Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate    # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Run Application
```bash
python run.py
```
Open **http://127.0.0.1:5000** in your browser.

---

## ☁️ Deployment on Render

This project is configured for continuous deployment on [Render](https://render.com):

1. **Repository**: Linked to GitHub repository [`ys9365790-dotcom/TASK-MANAGER`](https://github.com/ys9365790-dotcom/TASK-MANAGER).
2. **Environment**: `Python 3`
3. **Build Command**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Start Command**:
   ```bash
   gunicorn run:app
   ```
5. Every push to `main` automatically triggers an updated zero-downtime deployment on Render.

---

## 🔌 API Reference Highlights

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/tasks/quick-add` | Creates a task from natural language text |
| `POST` | `/api/tasks/parse` | Returns live parsed preview of natural language text |
| `GET` | `/api/tasks/next-up` | Returns top 5 priority tasks for logged-in user |
| `POST` | `/api/tasks/<id>/timelog` | Records Pomodoro focus session minutes |
| `GET` | `/api/changes?since=<ts>` | 3-second live multi-user polling endpoint |
| `GET` | `/api/analytics/contributions` | 12-week GitHub-style contribution heatmap & streaks |
| `GET` | `/api/analytics` | Aggregated analytics (status, workload, focus, heatmap) |
| `GET` | `/api/tasks` | Lists all tasks with status, priority, and search filters |
| `PATCH` | `/api/tasks/<id>` | Partial task update (status, quadrant, priority, assignee) |
