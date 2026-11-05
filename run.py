"""
run.py
------
Main application entry point for the TaskManager Flask project.

This script:
1. Instantiates the Flask app using the application factory (`create_app`).
2. Ensures the SQLite database tables are created automatically before serving traffic.
3. Automatically seeds initial demo data on the first launch if the database is empty,
   providing immediate interactivity out of the box.
4. Starts the local Flask development server with interactive debugging enabled.

How to run:
    python run.py
"""

import os
from app import create_app, db
from app.models import User, Task

# Create the application instance using the factory function in app/__init__.py
app = create_app()


import sys

def initialize_database(force_reset=False):
    """
    Initializes the database schema and populates 10 sample demo tasks
    if the database is brand new or force_reset is requested.
    """
    with app.app_context():
        # Create all tables declared in app/models.py
        db.create_all()

        # Check if the database has tasks; seed if empty or reset requested
        if force_reset or Task.query.count() == 0:
            print(">> Initializing and seeding 10 sample demo tasks across Eisenhower quadrants...")
            from app.routes import seed_demo_data
            with app.test_request_context('/seed-demo-data' + ('?reset=1' if force_reset else '')):
                seed_demo_data()
            print(">> Database successfully initialized and seeded with 10 sample tasks!")


if __name__ == '__main__':
    # Check if reset or seed flag passed via CLI (e.g. python run.py --seed or --reset)
    force_reset = any(arg in sys.argv for arg in ['--seed', '--reset', '-s'])
    initialize_database(force_reset=force_reset)

    # Determine port and host (defaults to 127.0.0.1:5000)
    host = os.environ.get('FLASK_RUN_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_RUN_PORT', 5000))

    print(f"\n========================================================")
    print(f"🚀 TaskManager server running at http://{host}:{port}/")
    print(f"📁 SQLite database file: taskmanager.db")
    print(f"💡 Press CTRL+C to stop the development server.")
    print(f"========================================================\n")

    # Run the Flask development server
    # debug=True enables live code reloading and detailed in-browser tracebacks
    app.run(host=host, port=port, debug=True)
