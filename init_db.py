#!/usr/bin/env python3
"""
Initialize the database for the Kikuyu Translation Platform
"""
import os
from app import create_app, db

def init_database():
    """Initialize the database with all tables"""
    app = create_app()

    with app.app_context():
        # Create all tables
        db.create_all()
        print("✅ Database tables created successfully!")

        # Verify tables were created
        from sqlalchemy import text
        result = db.session.execute(text("SELECT name FROM sqlite_master WHERE type='table';"))
        tables = [row[0] for row in result.fetchall()]

        print(f"📊 Created tables: {', '.join(tables)}")

        if len(tables) > 0:
            print("🎉 Database initialization completed successfully!")
            return True
        else:
            print("❌ No tables were created")
            return False

if __name__ == "__main__":
    success = init_database()
    if not success:
        exit(1)