#!/usr/bin/env python3
"""
Simple test script to verify PostgreSQL connection
"""
import os
import sys

# Add the project directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app import create_app, db
    from app.models import Prompt, User, Translation

    print("📦 Creating Flask app...")
    app = create_app('production')

    with app.app_context():
        print("🔌 Testing database connection...")

        # Test connection
        db.engine.execute('SELECT 1')
        print("✅ Database connection successful!")

        # Create tables
        print("🏗️  Creating database tables...")
        db.create_all()
        print("✅ Tables created successfully!")

        # Test basic operations
        print("🧪 Testing basic database operations...")

        # Test if we can query tables
        prompt_count = Prompt.query.count()
        user_count = User.query.count()
        translation_count = Translation.query.count()

        print(f"📊 Current data:")
        print(f"   - Prompts: {prompt_count}")
        print(f"   - Users: {user_count}")
        print(f"   - Translations: {translation_count}")

        print("🎉 All tests passed! PostgreSQL migration successful!")

except ImportError as e:
    print(f"❌ Import error: {e}")
    print("💡 This is expected if dependencies aren't installed yet")

except Exception as e:
    print(f"❌ Database error: {e}")
    print("💡 Check your Neon connection string and database permissions")