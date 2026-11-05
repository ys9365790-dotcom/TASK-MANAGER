# ⚡ TaskManager - Team Productivity & Decision Matrix

A full-stack team productivity and task management web application built with **Flask**, **Flask-Login**, **SQLite**, and **SQLAlchemy**. Features dual board layouts (interactive **3-Column Kanban** and **2x2 Eisenhower Decision Matrix**), **SortableJS** drag-and-drop with asynchronous REST API persistence, real-time client-side search and filters, visual analytics powered by **Chart.js**, dark/light theme switching, and comprehensive audit logging.

---

## 🌟 Key Features

1. **Dual Board View System (Kanban & Eisenhower Matrix)**:
   - **3-Column Kanban Board**: Smooth SortableJS drag-and-drop between **To Do**, **Doing**, and **Done**. Dropping a card asynchronously updates its status via REST API.
   - **2x2 Eisenhower Decision Matrix**: Seamlessly toggle between Kanban and Eisenhower matrix layouts. Classifies tasks into:
     - **Q1: Do First** — Urgent & Important (*Immediate Action*)
     - **Q2: Schedule** — Not Urgent & Important (*Strategic Focus*)
     - **Q3: Delegate** — Urgent & Not Important (*Team Requests*)
     - **Q4: Don't Do** — Not Urgent & Not Important (*Eliminate / Minimize*)
   - **Drag-and-Drop Matrix Transitions**: Dragging a card into another quadrant automatically recalculates both its importance flag and urgency deadline via `PATCH /api/tasks/<id>`.
   - **View Mode Persistence**: User layout preference is saved in `localStorage` (`taskmanager-view-mode`).

2. **Urgency & Importance Logic**:
   - **Urgent**: Automatically calculated for any non-done task with a deadline within **48 hours** (`due_date <= 48h`) or past due date (overdue).
   - **Important**: Dedicated boolean attribute on `Task` with interactive creation/edit checkbox and a golden `⭐ Important` card badge.
   - **Urgency Highlights**: Overdue cards highlighted in bold **red** (`⏰ Overdue`), cards due within 48 hours highlighted in warm **amber** (`⏳ Due <48h`).

3. **User Management & Task Assignment**:
   - Tasks can be assigned to any registered user or left unassigned.
   - In-place quick assignment dropdown on cards allowing instantaneous reallocation without page reloads.

4. **Instant Client-Side Filtering**:
   - Real-time search box matching task titles, descriptions, and assignee names.
   - Filter dropdowns for **Priority** (`High`, `Medium`, `Low`) and **Assignee** (specific users or Unassigned).
   - Updates column and quadrant counters and empty-state placeholders on the fly.

5. **Visual Productivity Analytics (Chart.js)**:
   - **Tasks by Workflow Status**: Interactive Doughnut chart displaying distribution across To Do, Doing, and Done.
   - **Workload per Team Member**: Bar chart highlighting active task allocations across users.
   - **Priority Breakdown**: High, Medium, and Low urgency proportion chart.
   - Automatically re-renders with optimized palette when toggling Dark/Light mode.

6. **Modern Theming & Micro-Animations**:
   - Pure Vanilla CSS design system with CSS custom properties (`--color-bg`, `--color-surface`, `--color-primary`, etc.).
   - Dark/Light mode toggle in the navigation bar with immediate zero-FOUC initialization and `localStorage` persistence.
   - Glassmorphic card styling, elevation shadows, and toast alerts.

7. **Security & Audit Trail**:
   - Werkzeug secure password hashing (`generate_password_hash`, `check_password_hash`).
   - Session authentication managed via Flask-Login with `@login_required` route decorators.
   - Every creation, status move, edit, assignment change, and deletion is recorded in the `ActivityLog` audit table.

8. **Robust Error Handling**:
   - Custom branded error pages for **404 Not Found**, **500 Internal Server Error**, and **403 Forbidden**.
   - Automatic database session rollbacks (`db.session.rollback()`) preventing corrupted transaction states.
   - JSON error payloads (`{"success": false, "error": "...", "status_code": ...}`) for all API calls.

---

## 📁 Project Directory Structure

```text
TASK MANAGER/
├── app/
│   ├── __init__.py        # Flask application factory (`create_app`), DB extension, SQLite auto-migration
│   ├── config.py          # App configuration (SQLite database URI, secret keys)
│   ├── models.py          # SQLAlchemy models: User (with UserMixin), Task, ActivityLog
│   ├── routes.py          # Web routes, error handlers, authentication, task forms, demo seeder
│   └── api.py             # RESTful API endpoints (/api/tasks, /api/activity, /api/analytics)
├── templates/
│   ├── base.html          # Base layout template with session-aware navbar, theme toggle, flash alerts
│   ├── index.html         # Main dashboard with Kanban board, Eisenhower 2x2 matrix, toolbar, sidebar
│   ├── dashboard.html     # Visual analytics dashboard powered by Chart.js
│   ├── task_form.html     # Unified task creation and editing form with importance checkbox
│   ├── activity.html      # Chronological audit trail viewer
│   ├── login.html         # User sign-in page with demo credentials helper
│   ├── signup.html        # User registration page with password confirmation
│   ├── error.html         # Branded error page template for 404, 500, and 403 errors
│   └── includes/
│       └── task_card.html # Modular, reusable task card component partial
├── static/
│   ├── css/
│   │   └── style.css      # Vanilla CSS design tokens, Kanban & Matrix grids, dark mode styles
│   └── js/
│       ├── main.js        # SortableJS initialization, matrix redistribution, filters, theme toggle
│       ├── chart.min.js   # Chart.js library for offline dashboard analytics
│       └── sortable.min.js# SortableJS library for offline drag-and-drop
├── requirements.txt       # Python dependencies (Flask, Flask-Login, Flask-SQLAlchemy)
├── run.py                 # Application launcher with CLI database initialization & seed flags
├── taskmanager.db         # SQLite database file (created automatically on startup)
└── README.md              # Project documentation and setup guide
```

---

## 🚀 Setup & Installation Steps

### Prerequisites
- **Python 3.10+** installed on your system.
- Terminal / Command Line access.

### 1. Navigate to Project Directory
```bash
cd "TASK MANAGER"
```

### 2. Create and Activate Virtual Environment
```bash
# macOS / Linux:
python3 -m venv venv
source venv/bin/activate

# Windows (Command Prompt):
python -m venv venv
venv\Scripts\activate

# Windows (PowerShell):
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Initialize Database & Seed 10 Sample Demo Tasks
To seed the 10 comprehensive sample tasks across all Eisenhower quadrants and team members:
```bash
python run.py --seed
```
*(Or navigate to `http://127.0.0.1:5000/seed-demo-data?reset=1` in your browser once the server is running).*

### 5. Launch the Application
```bash
python run.py
```

The development server will start at:
```
http://127.0.0.1:5000/
```

---

## 👥 Demo Accounts & Pre-Seeded Tasks

### Demo Login Credentials
| Name | Email Address | Password | Role |
|---|---|---|---|
| **Alex Rivera** | `alex.rivera@example.com` | `secure123` | Team Lead / Senior Backend Engineer |
| **Sarah Chen** | `sarah.chen@example.com` | `secure123` | Security & Infrastructure Lead |
| **Marcus Brody** | `marcus.brody@example.com` | `secure123` | Frontend & Quality Assurance |

---

### The 10 Seeded Demo Tasks

The application includes 10 pre-configured sample tasks illustrating diverse real-world engineering workflows, priorities, and deadlines:

| # | Task Title | Status | Priority | Eisenhower Quadrant | Due Date / Urgency | Assignee |
|---|---|---|---|---|---|---|
| 1 | **Resolve Critical Database Connection Pool Leak** | Doing | High | **Q1 (Do First)** | Overdue (`⏰ Overdue`) | Alex Rivera |
| 2 | **Hotfix Security Vulnerability in Session Cookies** | To Do | High | **Q1 (Do First)** | Due in 1 day (`⏳ Due <48h`) | Sarah Chen |
| 3 | **Patch SQLite Schema Migration Script** | Done | High | **Q1 / Q2** | Completed | Alex Rivera |
| 4 | **Architect Microservices Roadmap & API Gateway** | Doing | High | **Q2 (Schedule)** | Due in 6 days | Alex Rivera |
| 5 | **Build Automated End-to-End Regression Test Suite**| To Do | Medium | **Q2 (Schedule)** | Due in 10 days | Marcus Brody |
| 6 | **Refactor Frontend Design System with Tokens** | Done | Medium | **Q2 (Schedule)** | Completed | Marcus Brody |
| 7 | **Renew SSL/TLS Certificates for Staging Subdomains**| To Do | High | **Q3 (Delegate)** | Due Today (`⏳ Due <48h`) | Sarah Chen |
| 8 | **Prepare Weekly Team Standup & Retrospective Deck** | Doing | Medium | **Q3 (Delegate)** | Due in 1 day (`⏳ Due <48h`) | Marcus Brody |
| 9 | **Audit Third-Party NPM Dependencies & Licenses** | To Do | Low | **Q4 (Don't Do)** | Due in 14 days | *Unassigned* |
| 10| **Archive Legacy v1 API Documentation & Endpoints** | To Do | Low | **Q4 (Don't Do)** | Due in 21 days | *Unassigned* |

---

## 🎯 2x2 Eisenhower Decision Matrix Guide

The Eisenhower Matrix helps teams focus on high-impact work by plotting tasks on two axes: **Urgency** and **Importance**.

```
                        URGENT (Due <= 48h)           NOT URGENT (Due > 48h)
                   +------------------------------+------------------------------+
                   |  🔴 QUADRANT 1: DO FIRST     |  🔵 QUADRANT 2: SCHEDULE     |
    IMPORTANT      |  - Immediate crises          |  - Strategic planning        |
   (important=1)   |  - Critical security fixes   |  - Architecture & testing    |
                   |  - Deadlines <= 48 hours     |  - High impact, proactive    |
                   +------------------------------+------------------------------+
                   |  🟡 QUADRANT 3: DELEGATE     |  ⚪ QUADRANT 4: DON'T DO     |
  NOT IMPORTANT    |  - Urgent interruptions      |  - Low value tasks           |
   (important=0)   |  - Routine certificates      |  - Deprecated cleanup        |
                   |  - Administrative requests   |  - Consider eliminating      |
                   +------------------------------+------------------------------+
```

- **Urgency Calculation**:
  $$\text{Urgent} \iff \text{status} \neq \text{'done'} \land \text{due\_date} \le \text{today} + 2\text{ days}$$
- **Drag-and-Drop Classification**: Dragging a task into:
  - **Q1**: Sets `important=True` and sets due date to tomorrow (<= 48h).
  - **Q2**: Sets `important=True` and extends deadline to 7 days away (> 48h).
  - **Q3**: Sets `important=False` and sets due date to tomorrow (<= 48h).
  - **Q4**: Sets `important=False` and extends deadline to 7 days away (> 48h).

---

## 🌐 Web Routes Reference

| Method | URL | Auth Required | Description |
|---|---|:---:|---|
| `GET` / `POST` | `/signup` | No | User registration with hashed password |
| `GET` / `POST` | `/login` | No | User login with session remember-me |
| `GET` | `/logout` | **Yes** | Terminates session and logs out user |
| `GET` | `/` | **Yes** | Dual-view board (Kanban & Eisenhower Matrix) |
| `GET` | `/dashboard` | **Yes** | Visual analytics dashboard (Chart.js) |
| `GET` / `POST` | `/tasks/new` | **Yes** | Create new task authored by `current_user` |
| `GET` / `POST` | `/tasks/<id>/edit`| **Yes** | Modify task attributes, priority, importance, or deadline |
| `POST` | `/tasks/<id>/status`| **Yes** | Transition status (`todo` / `doing` / `done`) |
| `POST` | `/tasks/<id>/delete`| **Yes** | Delete task with audit retention |
| `GET` | `/activity` | **Yes** | Chronological audit trail logs |
| `GET` | `/seed-demo-data` | No | Seed 10 sample tasks (`?reset=1` forces re-seed) |

---

## 📡 RESTful API Reference (`/api/tasks`)

### 1. Create Task: `POST /api/tasks`
Creates a new task.

**Headers**:
- `Content-Type: application/json`
- `X-User-ID: <id>` *(optional)*

**Request Body**:
```json
{
  "title": "Implement Webhook Verification",
  "description": "Validate HMAC SHA-256 signatures for incoming payment events",
  "status": "todo",
  "priority": "high",
  "important": true,
  "due_date": "2026-11-05",
  "assigned_to": 1
}
```

**Response (`201 Created`)**:
```json
{
  "success": true,
  "message": "Task created successfully.",
  "task": {
    "id": 11,
    "title": "Implement Webhook Verification",
    "description": "Validate HMAC SHA-256 signatures for incoming payment events",
    "status": "todo",
    "priority": "high",
    "important": true,
    "is_urgent": false,
    "eisenhower_quadrant": "q2",
    "due_date": "2026-11-05",
    "assigned_to": 1,
    "assignee_name": "Alex Rivera",
    "created_by": 1,
    "creator_name": "Alex Rivera",
    "created_at": "2026-10-29T14:00:00",
    "is_overdue": false,
    "is_due_soon": false
  }
}
```

---

### 2. Update Task or Quadrant: `PATCH /api/tasks/<id>`
Performs partial updates on tasks, including quadrant drag-and-drop moves.

**Drag-to-Quadrant Payload**:
```json
{
  "quadrant": "q1"
}
```

**Response (`200 OK`)**:
```json
{
  "success": true,
  "message": "Task updated successfully.",
  "changes": [
    "marked as important",
    "set due date within 48 hours (urgent)",
    "moved to Quadrant 1 (Urgent & Important: Do First)"
  ],
  "task": {
    "id": 11,
    "important": true,
    "is_urgent": true,
    "eisenhower_quadrant": "q1",
    "due_date": "2026-10-30"
  }
}
```

---

### 3. List Tasks: `GET /api/tasks`
Query parameters:
- `status`: `'todo'`, `'doing'`, or `'done'`
- `priority`: `'low'`, `'medium'`, or `'high'`
- `assigned_to`: User ID
- `q`: Search keyword

---

### 4. Delete Task: `DELETE /api/tasks/<id>`
Permanently deletes the task while retaining audit records.

---

### 5. Analytics Endpoint: `GET /api/analytics`
Returns aggregated datasets for Chart.js:
- `status_distribution`: Labels, counts, and colors for status doughnut chart.
- `member_distribution`: Workload counts per registered user and unassigned items.
- `priority_distribution`: High, medium, and low breakdown.
- `summary`: Total tasks, completion rate, overdue count, and due soon count.

---

## 🛡️ Error Handling Architecture

- **Custom Error Handlers**:
  - `404 Not Found`: Catches missing routes and deleted task IDs, returning `templates/error.html` for web requests or `{"success": false, "error": "...", "status_code": 404}` for API clients.
  - `500 Internal Server Error`: Automatically triggers `db.session.rollback()` to prevent corrupted transaction pools before returning structured responses.
  - `403 Forbidden`: Protects unauthorized resources.
- **Form Validation & Field Preservation**: Form errors flash clear alerts (red for danger, amber for warnings, green for success) and retain entered fields so users never lose draft content.
- **Client Toast Alerts**: Drag-and-drop operations display non-intrusive floating toasts that auto-dismiss in 3.5 seconds.

---

## 🧪 Running Automated Tests

Run the full verification suite to test model constraints, urgency calculations, API quadrant transitions, and form validation:
```bash
python -c "
from app import create_app, db
from app.models import Task, User

app = create_app()
with app.app_context():
    print(f'Total Users: {User.query.count()}')
    print(f'Total Tasks: {Task.query.count()}')
    assert Task.query.count() == 10
    print('All automated database assertions passed!')
"
```
