#!/usr/bin/env python3
"""
Health check script to verify system functionality before deployment
Tests Unicode handling, database connections, and critical functions
"""

import os
import sys

# Add the app directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User, Translation, Prompt
from app.utils import normalize_kikuyu_text, validate_kikuyu_text, check_duplicate_translation

def test_unicode_handling():
    """Test Unicode handling with Kikuyu special characters"""
    print("🧪 Testing Unicode handling...")

    # Test text with Kikuyu special characters
    test_texts = [
        "Nĩ gũkena",  # Simple with tilde
        "Mũtũmia ũcio nĩ mũrũme",  # Multiple special chars
        "Gĩkũyũ nĩ rũthiomi rũrũ",  # Complex example
        "Gũtirĩ mũndũ ũngĩ",  # More complex
        "Hello",  # Regular ASCII
        "",  # Empty
        "   ",  # Whitespace only
    ]

    for text in test_texts:
        try:
            normalized = normalize_kikuyu_text(text)
            is_valid, error = validate_kikuyu_text(text)
            print(f"  ✓ '{text}' → normalized: '{normalized}', valid: {is_valid}")
        except Exception as e:
            print(f"  ❌ Error with '{text}': {e}")
            return False

    return True

def test_database_connection():
    """Test database connection and basic operations"""
    print("🧪 Testing database connection...")

    app = create_app()
    with app.app_context():
        try:
            # Test connection
            db.session.execute(db.text("SELECT 1"))
            print("  ✓ Database connection successful")

            # Test user creation
            test_user = User.query.first()
            if test_user:
                print(f"  ✓ Found test user: {test_user.session_id}")
            else:
                print("  ⚠️  No users in database")

            # Test prompt query
            prompt_count = Prompt.query.count()
            print(f"  ✓ Found {prompt_count} prompts in database")

            # Test translation query
            translation_count = Translation.query.count()
            print(f"  ✓ Found {translation_count} translations in database")

            return True
        except Exception as e:
            print(f"  ❌ Database error: {e}")
            return False

def test_duplicate_detection():
    """Test duplicate detection with Unicode text"""
    print("🧪 Testing duplicate detection...")

    app = create_app()
    with app.app_context():
        try:
            # Test with sample texts
            test_cases = [
                ("Nĩ gũkena", 1),
                ("NĨ GŨKENA", 1),  # Case insensitive
                ("  Nĩ gũkena  ", 1),  # Whitespace
                ("Different text", 1),
            ]

            for text, prompt_id in test_cases:
                result = check_duplicate_translation(text, prompt_id)
                print(f"  ✓ Duplicate check '{text}' → {result}")

            return True
        except Exception as e:
            print(f"  ❌ Duplicate detection error: {e}")
            return False

def test_stats_performance():
    """Test stats caching and performance"""
    print("🧪 Testing stats performance...")

    app = create_app()
    with app.app_context():
        try:
            from app.utils import get_translation_stats
            import time

            # Test stats retrieval
            start_time = time.time()
            stats = get_translation_stats()
            end_time = time.time()

            duration = (end_time - start_time) * 1000  # Convert to milliseconds

            print(f"  ✓ Stats retrieved in {duration:.2f}ms")
            print(f"  ✓ Stats: {stats}")

            # Test cache hit
            start_time = time.time()
            stats2 = get_translation_stats()
            end_time = time.time()

            cache_duration = (end_time - start_time) * 1000

            print(f"  ✓ Cached stats retrieved in {cache_duration:.2f}ms")

            if cache_duration < duration:
                print("  ✓ Caching is working!")
            else:
                print("  ⚠️  Caching may not be working")

            return True
        except Exception as e:
            print(f"  ❌ Stats performance error: {e}")
            return False

def main():
    """Run all health checks"""
    print("🏥 Kikuyu Translation Platform Health Check")
    print("=" * 50)

    tests = [
        test_unicode_handling,
        test_database_connection,
        test_duplicate_detection,
        test_stats_performance,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if test():
                passed += 1
                print("✅ PASSED\n")
            else:
                print("❌ FAILED\n")
        except Exception as e:
            print(f"💥 CRASHED: {e}\n")

    print("=" * 50)
    print(f"Health Check Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All systems are go! Ready for deployment.")
        return True
    else:
        print("⚠️  Some issues detected. Please review before deployment.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)