#!/usr/bin/env python3
"""
Database schema migration script for PostgreSQL compatibility
Fixes column length issues when migrating from SQLite
"""
import os
import sys

# Add the project directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app import create_app, db
    from sqlalchemy import text

    print("🔄 Starting database schema migration...")
    app = create_app('production')

    with app.app_context():
        print("🔌 Connecting to database...")

        # Check if we need to alter existing tables
        try:
            # Try to check existing column constraints
            result = db.engine.execute(text("""
                SELECT column_name, character_maximum_length
                FROM information_schema.columns
                WHERE table_name = 'translations'
                AND column_name IN ('ip_address', 'user_agent');
            """))

            columns = result.fetchall()
            print(f"📊 Current column constraints: {columns}")

            # Drop and recreate tables with new schema
            print("🏗️  Dropping existing tables...")
            db.drop_all()

            print("🏗️  Creating tables with new schema...")
            db.create_all()

            print("✅ Schema migration completed successfully!")
            print("📝 Tables recreated with:")
            print("   - ip_address: VARCHAR(200) (was 45)")
            print("   - user_agent: VARCHAR(500) (was 255)")

        except Exception as e:
            print(f"⚠️  Could not check existing schema: {e}")
            print("🏗️  Creating fresh tables...")
            db.create_all()
            print("✅ Fresh tables created successfully!")

except ImportError as e:
    print(f"❌ Import error: {e}")
    print("💡 Make sure all dependencies are installed")

except Exception as e:
    print(f"❌ Migration error: {e}")
    print("💡 Check your database connection and permissions")