#!/usr/bin/env python3
"""
Cleanup script to remove existing rejected translations from database
since we no longer store rejections (they go back to CSV pool)
"""

import os
import sys

# Add the app directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import Translation
from app.services.csv_prompt_manager import CSVPromptManager
import hashlib

def cleanup_rejected_translations():
    """Remove all existing rejected translations and return their prompts to CSV pool"""
    app = create_app()

    with app.app_context():
        # Get all rejected translations
        rejected_translations = Translation.query.filter_by(status='rejected').all()

        print(f"Found {len(rejected_translations)} rejected translations to clean up")

        csv_manager = CSVPromptManager()
        returned_count = 0
        deleted_count = 0

        for translation in rejected_translations:
            try:
                # Return prompt back to CSV pool if it exists
                if translation.prompt:
                    prompt_id = hashlib.md5(translation.prompt.text.encode('utf-8')).hexdigest()[:12]
                    if csv_manager.return_prompt_to_pool(prompt_id):
                        returned_count += 1
                        print(f"✅ Returned prompt '{translation.prompt.text[:50]}...' to CSV pool")
                    else:
                        print(f"⚠️  Could not return prompt '{translation.prompt.text[:50]}...' to CSV pool")

                # Delete the rejected translation
                db.session.delete(translation)
                deleted_count += 1

            except Exception as e:
                print(f"❌ Error processing translation {translation.id}: {str(e)}")

        # Commit all changes
        try:
            db.session.commit()
            print(f"\n✅ Cleanup completed:")
            print(f"   - {deleted_count} rejected translations deleted")
            print(f"   - {returned_count} prompts returned to CSV pool")
            print(f"   - Database space freed up")
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error committing changes: {str(e)}")

if __name__ == "__main__":
    cleanup_rejected_translations()