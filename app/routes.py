"""
app/routes.py
-------------
Defines web routes and API endpoints for the TaskManager application.

This module provides:
1. Authentication Routes:
   - Signup (`/signup`): Registers a new user with Werkzeug-hashed passwords.
   - Login (`/login`): Authenticates credentials and starts a Flask-Login session.
   - Logout (`/logout`): Terminates the current session.
2. Dashboard Route (`/`): Protected by `@login_required`, displays tasks organized by
   status (todo, doing, done), summary statistics, and quick-filter controls.
3. Task Creation (`/tasks/new`): Creates tasks authored by `current_user`.
4. Task Editing (`/tasks/<id>/edit`): Modifies task attributes and logs updates.
5. Quick Status Update (`/tasks/<id>/status`): Moves tasks between todo, doing, and done.
6. Task Deletion (`/tasks/<id>/delete`): Removes tasks and logs the deletion event.
7. Activity Log View (`/activity`): Shows the chronological audit trail.
8. Demo Data Seeder (`/seed-demo-data`): Injects sample users, tasks, and logs for instant testing.
9. REST API endpoints (`/api/tasks`, `/api/activity`): Returns JSON data for external integration.
"""

from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User, Task, ActivityLog, TaskChange, record_task_change, calculate_workload_summary

# Define the main Blueprint
main_bp = Blueprint('main', __name__)


def log_activity(action: str, task_id: int = None, user_id: int = None) -> ActivityLog:
    """
    Helper function to record an event in the ActivityLog audit table.
    Safely commits or rolls back without corrupting the session.

    Args:
        action (str): Description of what occurred.
        task_id (int, optional): The ID of the task associated with this action.
        user_id (int, optional): The ID of the user performing the action.

    Returns:
        ActivityLog or None: The newly created activity log entry, or None if failed.
    """
    try:
        entry = ActivityLog(action=action, task_id=task_id, user_id=user_id)
        db.session.add(entry)
        db.session.commit()
        return entry
    except Exception:
        db.session.rollback()
        return None


# -------------------------------------------------------------------
# Authentication Routes (Signup, Login, Logout)
# -------------------------------------------------------------------

@main_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    """
    User Registration:
    GET: Displays the signup form.
    POST: Validates inputs, hashes the password using Werkzeug security,
          saves the new User, logs them into Flask-Login, and records activity.
    """
    # Redirect already authenticated users to the dashboard
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Basic input validation
        if not name or not email or not password:
            flash('Please fill in all required fields.', 'danger')
            return render_template('signup.html', name=name, email=email)

        if len(name) < 2:
            flash('Full name must be at least 2 characters long.', 'danger')
            return render_template('signup.html', name=name, email=email)

        if '@' not in email or '.' not in email:
            flash('Please enter a valid email address (e.g. alex@example.com).', 'danger')
            return render_template('signup.html', name=name, email=email)

        if password != confirm_password:
            flash('Passwords do not match. Please re-enter your password.', 'danger')
            return render_template('signup.html', name=name, email=email)

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return render_template('signup.html', name=name, email=email)

        try:
            # Check if email is already registered
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                flash('An account with this email address already exists. Please log in.', 'warning')
                return redirect(url_for('main.login'))

            # Create new user and hash password securely with Werkzeug
            new_user = User(name=name, email=email)
            new_user.set_password(password)

            db.session.add(new_user)
            db.session.commit()

            # Record registration in the audit log
            log_activity(f"User '{new_user.name}' registered an account", user_id=new_user.id)

            # Automatically log the user in via Flask-Login
            login_user(new_user)
            flash(f'Welcome to TaskManager, {new_user.name}! Your account was created successfully.', 'success')
            return redirect(url_for('main.index'))

        except Exception as e:
            db.session.rollback()
            flash('An unexpected error occurred while creating your account. Please try again.', 'danger')
            return render_template('signup.html', name=name, email=email)

    return render_template('signup.html')


@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    User Login:
    GET: Displays the login form.
    POST: Validates credentials, verifies password hash using Werkzeug security,
          establishes session via Flask-Login, and redirects to requested page.
    """
    # Redirect already authenticated users to the dashboard
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        if not email or not password:
            flash('Please enter both email and password.', 'danger')
            return render_template('login.html', email=email)

        try:
            # Lookup user by unique email
            user = User.query.filter_by(email=email).first()

            # Verify user exists and password hash matches
            if not user or not user.check_password(password):
                flash('Invalid email or password. Please verify your credentials and try again.', 'danger')
                return render_template('login.html', email=email)

            # Log user in with Flask-Login
            login_user(user, remember=remember)

            # Record login in audit log
            log_activity(f"User '{user.name}' logged in", user_id=user.id)
            flash(f"Welcome back, {user.name}!", 'success')

            # Handle 'next' query parameter securely (protecting against open redirects)
            next_page = request.args.get('next')
            if not next_page or not next_page.startswith('/'):
                next_page = url_for('main.index')
            return redirect(next_page)

        except Exception:
            flash('An unexpected error occurred during login. Please try again.', 'danger')
            return render_template('login.html', email=email)

    return render_template('login.html')


@main_bp.route('/logout')
@login_required
def logout():
    """
    User Logout:
    Logs the user out of Flask-Login, clears session, logs activity, and redirects to login.
    """
    user_name = current_user.name
    user_id = current_user.id
    log_activity(f"User '{user_name}' logged out", user_id=user_id)
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('main.login'))


# -------------------------------------------------------------------
# Protected Task Management Routes
# -------------------------------------------------------------------

@main_bp.route('/')
@login_required
def index():
    """
    Dashboard / Kanban View (Protected):
    Accessible ONLY to authenticated users.
    Renders the primary application interface with tasks separated into columns
    by status ('todo', 'doing', 'done'), alongside key metrics and filtering options.
    """
    # Optional query parameters for filtering tasks
    selected_user_id = request.args.get('user_id', type=int)
    selected_priority = request.args.get('priority', type=str)
    search_query = request.args.get('q', type=str, default='').strip()

    # Base query ordered by priority and due date
    query = Task.query

    # Apply user filter if selected
    if selected_user_id:
        query = query.filter((Task.assigned_to == selected_user_id) | (Task.created_by == selected_user_id))

    # Apply priority filter if valid
    if selected_priority in ['low', 'medium', 'high']:
        query = query.filter(Task.priority == selected_priority)

    # Apply keyword search filter (matches title or description)
    if search_query:
        query = query.filter(
            (Task.title.ilike(f"%{search_query}%")) |
            (Task.description.ilike(f"%{search_query}%"))
        )

    all_tasks = query.order_by(Task.created_at.desc()).all()

    # Split tasks by status for the Kanban columns
    todo_tasks = [t for t in all_tasks if t.status == 'todo']
    doing_tasks = [t for t in all_tasks if t.status == 'doing']
    done_tasks = [t for t in all_tasks if t.status == 'done']

    # Split tasks for the 2x2 Eisenhower Matrix quadrants:
    # Q1: Urgent & Important ("Do First")
    # Q2: Not Urgent & Important ("Schedule / Plan")
    # Q3: Urgent & Not Important ("Delegate")
    # Q4: Not Urgent & Not Important ("Don't Do / Eliminate")
    q1_tasks = [t for t in all_tasks if t.is_urgent and t.important]
    q2_tasks = [t for t in all_tasks if not t.is_urgent and t.important]
    q3_tasks = [t for t in all_tasks if t.is_urgent and not t.important]
    q4_tasks = [t for t in all_tasks if not t.is_urgent and not t.important]

    # Retrieve all users for assignment dropdowns
    users = User.query.order_by(User.name.asc()).all()

    # Recent 5 activity entries to show on the dashboard sidebar
    recent_activity = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(5).all()

    # Summary metrics
    metrics = {
        'total': len(all_tasks),
        'todo': len(todo_tasks),
        'doing': len(doing_tasks),
        'done': len(done_tasks),
        'overdue': sum(1 for t in all_tasks if t.is_overdue),
        'due_soon': sum(1 for t in all_tasks if t.is_due_soon),
        'q1': len(q1_tasks),
        'q2': len(q2_tasks),
        'q3': len(q3_tasks),
        'q4': len(q4_tasks)
    }

    # Calculate top 5 "Next up" tasks for current_user based on the priority scoring formula:
    # priority weight + importance weight + days until due + overdue bonus
    user_active_tasks = [t for t in all_tasks if t.assigned_to == current_user.id and t.status != 'done']
    user_active_tasks.sort(key=lambda t: t.score, reverse=True)
    next_up_tasks = user_active_tasks[:5]

    if len(next_up_tasks) < 5:
        other_active_tasks = [t for t in all_tasks if t.status != 'done' and t not in next_up_tasks]
        other_active_tasks.sort(key=lambda t: t.score, reverse=True)
        next_up_tasks.extend(other_active_tasks[:(5 - len(next_up_tasks))])

    # Calculate workload analysis & reassignment suggestions
    workload_summary = calculate_workload_summary(all_tasks, users)

    return render_template(
        'index.html',
        todo_tasks=todo_tasks,
        doing_tasks=doing_tasks,
        done_tasks=done_tasks,
        q1_tasks=q1_tasks,
        q2_tasks=q2_tasks,
        q3_tasks=q3_tasks,
        q4_tasks=q4_tasks,
        users=users,
        recent_activity=recent_activity,
        metrics=metrics,
        next_up_tasks=next_up_tasks,
        workload_summary=workload_summary,
        selected_user_id=selected_user_id,
        selected_priority=selected_priority,
        search_query=search_query
    )


@main_bp.route('/tasks/new', methods=['GET', 'POST'])
@login_required
def create_task():
    """
    Create Task (Protected):
    GET: Displays the task creation form.
    POST: Processes form submission, validates inputs, binds 'created_by' to
          the authenticated 'current_user.id', inserts Task, and logs activity.
    """
    users = User.query.order_by(User.name.asc()).all()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        status = request.form.get('status', 'todo').lower().strip()
        priority = request.form.get('priority', 'medium').lower().strip()
        important = bool(request.form.get('important'))
        due_date_str = request.form.get('due_date', '').strip()
        assigned_to = request.form.get('assigned_to', type=int)

        # Form data dictionary to retain user inputs if validation errors occur
        form_task = {
            'title': title,
            'description': description,
            'status': status,
            'priority': priority,
            'important': important,
            'due_date': None,
            'assigned_to': assigned_to
        }

        # Validate title
        if not title:
            flash('Task title is required.', 'danger')
            return render_template('task_form.html', action='create', task=form_task, users=users)

        if len(title) > 200:
            flash('Task title cannot exceed 200 characters.', 'danger')
            return render_template('task_form.html', action='create', task=form_task, users=users)

        # Validate status & priority bounds
        if status not in ['todo', 'doing', 'done']:
            status = 'todo'

        if priority not in ['low', 'medium', 'high']:
            priority = 'medium'

        # Parse and validate due date
        due_date = None
        if due_date_str:
            try:
                due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
                form_task['due_date'] = due_date
            except ValueError:
                flash("Invalid date format for due date. Expected format: YYYY-MM-DD.", 'warning')

        # Validate assignee exists in database
        if assigned_to:
            assignee_user = User.query.get(assigned_to)
            if not assignee_user:
                flash('Selected assignee does not exist.', 'warning')
                assigned_to = None

        try:
            task = Task(
                title=title,
                description=description if description else None,
                status=status,
                priority=priority,
                important=important,
                due_date=due_date,
                assigned_to=assigned_to,
                created_by=current_user.id
            )
            db.session.add(task)
            db.session.commit()

            # Record creation activity & TaskChange
            log_activity(
                action=f"{current_user.name} created task '{task.title}'",
                task_id=task.id,
                user_id=current_user.id
            )
            record_task_change(
                task=task,
                action='added',
                user_name=current_user.name,
                user_id=current_user.id,
                details='added this'
            )

            flash(f"Task '{task.title}' created successfully!", 'success')
            return redirect(url_for('main.index'))

        except Exception as e:
            db.session.rollback()
            flash(f"Database error while creating task: {str(e)}", 'danger')
            return render_template('task_form.html', action='create', task=form_task, users=users)

    return render_template('task_form.html', action='create', task=None, users=users)


@main_bp.route('/tasks/quick-add', methods=['POST'])
@login_required
def quick_add_task():
    """
    Handles natural language task creation from quick-add bar form submission.
    Parses title, due date, priority, @assignee, and importance.
    """
    from app.task_parser import parse_quick_task

    raw_text = request.form.get('quick_text', '').strip()
    if not raw_text:
        flash('Please enter a task description.', 'warning')
        return redirect(url_for('main.index'))

    all_users = [{'id': u.id, 'name': u.name, 'email': u.email} for u in User.query.all()]
    parsed = parse_quick_task(raw_text, users=all_users)

    if not parsed or not parsed.get('title'):
        flash('Could not parse a valid task title from input.', 'danger')
        return redirect(url_for('main.index'))

    due_date_obj = None
    if parsed.get('due_date'):
        try:
            due_date_obj = datetime.strptime(parsed['due_date'], '%Y-%m-%d').date()
        except ValueError:
            due_date_obj = None

    try:
        new_task = Task(
            title=parsed['title'],
            description=None,
            status='todo',
            priority=parsed['priority'],
            important=parsed['important'],
            due_date=due_date_obj,
            assigned_to=parsed['assignee_id'],
            created_by=current_user.id
        )
        db.session.add(new_task)
        db.session.commit()

        log_activity(
            action=f"Quick-Add: {current_user.name} created task '{new_task.title}'",
            task_id=new_task.id,
            user_id=current_user.id
        )
        record_task_change(
            task=new_task,
            action='added',
            user_name=current_user.name,
            user_id=current_user.id,
            details='added this'
        )
        flash(f"Task '{new_task.title}' created successfully!", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to create task: {str(e)}', 'danger')

    return redirect(url_for('main.index'))



@main_bp.route('/tasks/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_task(task_id: int):
    """
    Edit Task (Protected):
    GET: Displays pre-filled form with current task details.
    POST: Updates task attributes, validates inputs, rolls back on error,
          and logs changes to the activity audit trail.
    """
    task = Task.query.get(task_id)
    if not task:
        flash(f'Task #{task_id} not found or may have been deleted.', 'danger')
        return redirect(url_for('main.index'))

    users = User.query.order_by(User.name.asc()).all()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        status = request.form.get('status', task.status).lower().strip()
        priority = request.form.get('priority', task.priority).lower().strip()
        important = bool(request.form.get('important'))
        due_date_str = request.form.get('due_date', '').strip()
        assigned_to = request.form.get('assigned_to', type=int)

        if not title:
            flash('Task title cannot be empty.', 'danger')
            return render_template('task_form.html', action='edit', task=task, users=users)

        if len(title) > 200:
            flash('Task title cannot exceed 200 characters.', 'danger')
            return render_template('task_form.html', action='edit', task=task, users=users)

        if status not in ['todo', 'doing', 'done']:
            status = task.status

        if priority not in ['low', 'medium', 'high']:
            priority = task.priority

        due_date = None
        if due_date_str:
            try:
                due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash("Invalid date format. Expected 'YYYY-MM-DD'.", 'warning')
                due_date = task.due_date

        if assigned_to:
            assignee_exists = User.query.get(assigned_to)
            if not assignee_exists:
                flash('Selected assignee does not exist.', 'warning')
                assigned_to = None

        try:
            # Track changes for activity logging
            changes = []
            if task.title != title:
                changes.append(f"renamed to '{title}'")
            if task.status != status:
                changes.append(f"status changed from '{task.status}' to '{status}'")
                task.status = status
            if task.priority != priority:
                changes.append(f"priority changed to '{priority}'")
                task.priority = priority
            if task.important != important:
                changes.append(f"marked as {'important' if important else 'not important'}")
                task.important = important
            if task.due_date != due_date:
                changes.append(f"due date changed to {due_date.isoformat() if due_date else 'None'}")
                task.due_date = due_date

            if task.assigned_to != assigned_to:
                new_assignee = User.query.get(assigned_to) if assigned_to else None
                assignee_name = new_assignee.name if new_assignee else 'Unassigned'
                changes.append(f"reassigned to '{assignee_name}'")
                task.assigned_to = assigned_to

            task.title = title
            task.description = description if description else None
            db.session.commit()

            # Record activity log
            change_desc = ", ".join(changes) if changes else "updated task details"
            log_activity(
                action=f"{current_user.name} updated task '{task.title}': {change_desc}",
                task_id=task.id,
                user_id=current_user.id
            )
            record_task_change(
                task=task,
                action='edited',
                user_name=current_user.name,
                user_id=current_user.id,
                details='edited this'
            )

            flash(f"Task '{task.title}' updated successfully!", 'success')
            return redirect(url_for('main.index'))

        except Exception as e:
            db.session.rollback()
            flash(f"Database error updating task: {str(e)}", 'danger')
            return render_template('task_form.html', action='edit', task=task, users=users)

    return render_template('task_form.html', action='edit', task=task, users=users)


@main_bp.route('/tasks/<int:task_id>/status', methods=['POST'])
@login_required
def update_status(task_id: int):
    """
    Quick Status Update (Protected):
    Updates only the 'status' column of a task (todo, doing, done).
    Supports both traditional form POST and JavaScript JSON fetch calls.
    """
    task = Task.query.get(task_id)
    if not task:
        if request.is_json:
            return jsonify({'success': False, 'error': f'Task #{task_id} not found.'}), 404
        flash(f'Task #{task_id} not found.', 'danger')
        return redirect(url_for('main.index'))

    # Extract status from JSON or form payload
    if request.is_json:
        data = request.get_json(silent=True) or {}
        new_status = str(data.get('status', '')).lower().strip()
    else:
        new_status = request.form.get('status', '').lower().strip()

    if new_status not in ['todo', 'doing', 'done']:
        if request.is_json:
            return jsonify({'success': False, 'error': 'Invalid status. Must be todo, doing, or done.'}), 400
        flash('Invalid status provided.', 'danger')
        return redirect(url_for('main.index'))

    old_status = task.status
    if old_status == new_status:
        if request.is_json:
            return jsonify({
                'success': True,
                'task_id': task.id,
                'old_status': old_status,
                'new_status': new_status,
                'task': task.to_dict()
            })
        return redirect(url_for('main.index'))

    try:
        task.status = new_status
        db.session.commit()

        # Log status change event
        log_activity(
            action=f"{current_user.name} moved task '{task.title}' from '{old_status}' to '{new_status}'",
            task_id=task.id,
            user_id=current_user.id
        )
        record_task_change(
            task=task,
            action='moved',
            user_name=current_user.name,
            user_id=current_user.id,
            details=f"moved this to {new_status.capitalize()}"
        )

        if request.is_json:
            return jsonify({
                'success': True,
                'task_id': task.id,
                'old_status': old_status,
                'new_status': new_status,
                'task': task.to_dict()
            })

        flash(f"Moved '{task.title}' to {new_status.title()}.", 'info')
        return redirect(url_for('main.index'))

    except Exception as e:
        db.session.rollback()
        if request.is_json:
            return jsonify({'success': False, 'error': f'Database error updating status: {str(e)}'}), 500
        flash(f'Failed to update status: {str(e)}', 'danger')
        return redirect(url_for('main.index'))


@main_bp.route('/tasks/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id: int):
    """
    Delete Task (Protected):
    Permanently removes the specified task and creates a corresponding ActivityLog entry.
    """
    task = Task.query.get(task_id)
    if not task:
        flash(f'Task #{task_id} not found or already deleted.', 'warning')
        return redirect(url_for('main.index'))

    title = task.title
    try:
        # Nullify task_id in previous activity logs so audit records are permanently retained
        ActivityLog.query.filter_by(task_id=task.id).update({'task_id': None})

        # Delete task
        db.session.delete(task)
        db.session.commit()

        # Log deletion event
        log_activity(
            action=f"{current_user.name} deleted task '{title}'",
            task_id=None,
            user_id=current_user.id
        )
        record_task_change(
            task=task,
            action='deleted',
            user_name=current_user.name,
            user_id=current_user.id,
            details='deleted this'
        )

        flash(f"Task '{title}' was deleted successfully.", 'warning')
        return redirect(url_for('main.index'))

    except Exception as e:
        db.session.rollback()
        flash(f"Database error deleting task: {str(e)}", 'danger')
        return redirect(url_for('main.index'))


@main_bp.route('/activity')
@login_required
def activity_view():
    """
    Activity Audit Log (Protected):
    Displays chronological history of all user and task actions.
    """
    logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).all()
    return render_template('activity.html', logs=logs)


@main_bp.route('/dashboard')
@main_bp.route('/analytics')
@login_required
def dashboard_view():
    """
    Analytics & Visual Charts Dashboard (Protected):
    Displays Chart.js interactive charts (tasks per status doughnut,
    tasks per member bar, priority breakdown) and productivity metrics.
    Data is loaded asynchronously from the /api/analytics endpoint.
    """
    all_tasks = Task.query.all()
    all_users = User.query.order_by(User.name.asc()).all()
    workload_summary = calculate_workload_summary(all_tasks, all_users)
    return render_template('dashboard.html', workload_summary=workload_summary)


@main_bp.route('/seed-demo-data')
def seed_demo_data():
    """
    Demo Seeder:
    Populates 3 sample team users, 10 realistic engineering tasks across all 4
    Eisenhower quadrants (Urgent & Important, Schedule, Delegate, Don't Do),
    Kanban columns (To Do, Doing, Done), priorities (High, Medium, Low),
    and comprehensive ActivityLog audit entries.

    Supports query parameter ?reset=1 or ?force=1 to re-seed anytime.
    """
    from datetime import date, timedelta
    today = date.today()
    reset = request.args.get('reset') in ['1', 'true', 'yes'] or request.args.get('force') in ['1', 'true', 'yes']

    try:
        # 1. Ensure sample users exist
        u1 = User.query.filter_by(email='alex.rivera@example.com').first()
        u2 = User.query.filter_by(email='sarah.chen@example.com').first()
        u3 = User.query.filter_by(email='marcus.brody@example.com').first()

        if not u1:
            u1 = User(name='Alex Rivera', email='alex.rivera@example.com')
            u1.set_password('secure123')
            db.session.add(u1)

        if not u2:
            u2 = User(name='Sarah Chen', email='sarah.chen@example.com')
            u2.set_password('secure123')
            db.session.add(u2)

        if not u3:
            u3 = User(name='Marcus Brody', email='marcus.brody@example.com')
            u3.set_password('secure123')
            db.session.add(u3)

        db.session.commit()

        # If reset is requested, clear existing tasks and activity logs
        if reset:
            ActivityLog.query.delete()
            Task.query.delete()
            db.session.commit()

        # 2. Populate 10 comprehensive sample tasks if table is empty or reset
        if Task.query.count() == 0 or reset:
            sample_tasks = [
                # 1. Q1 (Do First): Urgent (Overdue) & Important | Doing | High | Alex Rivera
                Task(
                    title='Resolve Critical Database Connection Pool Leak in Production',
                    description='Investigate and fix connection pool exhaustion causing transient 504 Gateway Timeouts during peak user load.',
                    status='doing',
                    priority='high',
                    important=True,
                    due_date=today - timedelta(days=1),  # Overdue (Urgent)
                    assigned_to=u1.id,
                    created_by=u1.id
                ),

                # 2. Q1 (Do First): Urgent (<48h) & Important | To Do | High | Sarah Chen
                Task(
                    title='Hotfix Security Vulnerability in Session Cookie Validation',
                    description='Enforce SameSite=Lax and HttpOnly flags on session tokens to safeguard against cross-site scripting and session hijacking.',
                    status='todo',
                    priority='high',
                    important=True,
                    due_date=today + timedelta(days=1),  # Due <48h (Urgent)
                    assigned_to=u2.id,
                    created_by=u1.id
                ),

                # 3. Q1 (Do First): Urgent (<48h) & Important | Done | High | Alex Rivera
                Task(
                    title='Patch SQLite Schema Migration Script for Eisenhower Matrix',
                    description='Added automated PRAGMA schema check and ALTER TABLE hook in create_app() to support important column without wiping existing data.',
                    status='done',
                    priority='high',
                    important=True,
                    due_date=today - timedelta(days=1),
                    assigned_to=u1.id,
                    created_by=u1.id
                ),

                # 4. Q2 (Schedule / Plan): Not Urgent & Important | Doing | High | Alex Rivera
                Task(
                    title='Architect Microservices Roadmap & API Gateway Strategy',
                    description='Draft technical RFC outlining service boundaries, gRPC inter-service communication, and token-based rate limiting.',
                    status='doing',
                    priority='high',
                    important=True,
                    due_date=today + timedelta(days=6),  # Not Urgent (6 days)
                    assigned_to=u1.id,
                    created_by=u1.id
                ),

                # 5. Q2 (Schedule / Plan): Not Urgent & Important | To Do | Medium | Marcus Brody
                Task(
                    title='Build Automated End-to-End Regression Test Suite',
                    description='Set up comprehensive test suites for user authentication, drag-and-drop Kanban updates, and 2x2 matrix transitions.',
                    status='todo',
                    priority='medium',
                    important=True,
                    due_date=today + timedelta(days=10),  # Not Urgent (10 days)
                    assigned_to=u3.id,
                    created_by=u2.id
                ),

                # 6. Q2 (Schedule / Plan): Not Urgent & Important | Done | Medium | Marcus Brody
                Task(
                    title='Refactor Frontend Design System with Glassmorphism & Tokens',
                    description='Standardize CSS custom properties, elevation curves, typography scales, and dark/light color schemes.',
                    status='done',
                    priority='medium',
                    important=True,
                    due_date=today - timedelta(days=3),
                    assigned_to=u3.id,
                    created_by=u2.id
                ),

                # 7. Q3 (Delegate): Urgent (<48h) & Not Important | To Do | High | Sarah Chen
                Task(
                    title='Renew SSL/TLS Certificates for Staging Subdomains',
                    description='Staging Let\'s Encrypt certificates expire in 24 hours. Verify automated certbot cron jobs and DNS ACME challenge hooks.',
                    status='todo',
                    priority='high',
                    important=False,
                    due_date=today,  # Due today (Urgent)
                    assigned_to=u2.id,
                    created_by=u1.id
                ),

                # 8. Q3 (Delegate): Urgent (<48h) & Not Important | Doing | Medium | Marcus Brody
                Task(
                    title='Prepare Weekly Team Standup & Sprint Retrospective Deck',
                    description='Compile completed sprint velocity metrics, team blocker items, and distribute stakeholder survey slides.',
                    status='doing',
                    priority='medium',
                    important=False,
                    due_date=today + timedelta(days=1),  # Due tomorrow (Urgent)
                    assigned_to=u3.id,
                    created_by=u1.id
                ),

                # 9. Q4 (Don\'t Do / Eliminate): Not Urgent & Not Important | To Do | Low | Unassigned
                Task(
                    title='Audit Third-Party NPM Dependencies & License Compliance',
                    description='Run license-checker to ensure all bundled frontend libraries comply with MIT/Apache-2.0 open-source distribution standards.',
                    status='todo',
                    priority='low',
                    important=False,
                    due_date=today + timedelta(days=14),  # Not Urgent (14 days)
                    assigned_to=None,  # Unassigned
                    created_by=u2.id
                ),

                # 10. Q4 (Don\'t Do / Eliminate): Not Urgent & Not Important | To Do | Low | Unassigned
                Task(
                    title='Archive Legacy v1 API Documentation & Deprecated Endpoints',
                    description='Remove obsolete Swagger specs and route stubs for decommissioned 2023 legacy endpoints to reduce documentation clutter.',
                    status='todo',
                    priority='low',
                    important=False,
                    due_date=today + timedelta(days=21),  # Not Urgent (21 days)
                    assigned_to=None,  # Unassigned
                    created_by=u1.id
                )
            ]

            db.session.add_all(sample_tasks)
            db.session.commit()

            # Create rich audit logs for demo history
            log_activity(f"Alex Rivera initialized demo workspace with 10 sample tasks across Eisenhower quadrants", user_id=u1.id)
            log_activity(f"Alex Rivera moved 'Resolve Critical Database Connection Pool Leak in Production' to doing", task_id=sample_tasks[0].id, user_id=u1.id)
            log_activity(f"Sarah Chen moved 'Hotfix Security Vulnerability in Session Cookie Validation' to todo", task_id=sample_tasks[1].id, user_id=u2.id)
            log_activity(f"Alex Rivera completed 'Patch SQLite Schema Migration Script for Eisenhower Matrix'", task_id=sample_tasks[2].id, user_id=u1.id)
            log_activity(f"Marcus Brody completed 'Refactor Frontend Design System with Glassmorphism & Tokens'", task_id=sample_tasks[5].id, user_id=u3.id)
            log_activity(f"Marcus Brody moved 'Prepare Weekly Team Standup & Sprint Retrospective Deck' to doing", task_id=sample_tasks[7].id, user_id=u3.id)

            flash('✅ 10 sample demo tasks successfully seeded! Demo login: alex.rivera@example.com / secure123', 'success')
        else:
            flash(f'Database currently contains {Task.query.count()} tasks. To reload the 10 demo sample tasks, use /seed-demo-data?reset=1', 'info')

    except Exception as e:
        db.session.rollback()
        flash(f'Error seeding demo data: {str(e)}', 'danger')

    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    return redirect(url_for('main.login'))


# -------------------------------------------------------------------
# Error Handlers (404, 500, 403)
# -------------------------------------------------------------------

@main_bp.app_errorhandler(404)
def handle_404(e):
    """Handles 404 Not Found errors with JSON or custom HTML template."""
    if request.path.startswith('/api/') or request.is_json:
        return jsonify({
            'success': False,
            'error': 'The requested resource was not found on this server.',
            'status_code': 404
        }), 404
    return render_template(
        'error.html',
        error_code=404,
        error_title='Page Not Found',
        error_message='The page or task you are looking for might have been removed, had its name changed, or is temporarily unavailable.'
    ), 404


@main_bp.app_errorhandler(500)
def handle_500(e):
    """Handles 500 Internal Server Error with database rollback and JSON/HTML response."""
    db.session.rollback()
    if request.path.startswith('/api/') or request.is_json:
        return jsonify({
            'success': False,
            'error': 'An internal server error occurred. Please try again later.',
            'status_code': 500
        }), 500
    return render_template(
        'error.html',
        error_code=500,
        error_title='Internal Server Error',
        error_message='Our server encountered an unexpected error while processing your request. Please try again shortly.'
    ), 500


@main_bp.app_errorhandler(403)
def handle_403(e):
    """Handles 403 Forbidden errors."""
    if request.path.startswith('/api/') or request.is_json:
        return jsonify({
            'success': False,
            'error': 'You do not have permission to access this resource.',
            'status_code': 403
        }), 403
    return render_template(
        'error.html',
        error_code=403,
        error_title='Access Forbidden',
        error_message='You do not have permission to access the requested resource. Please sign in with an authorized account.'
    ), 403
