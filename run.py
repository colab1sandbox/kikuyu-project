#!/usr/bin/env python3
"""
Entry point for the Kikuyu-English Translation Platform
"""
import os
from app import create_app

# Create app with production config in deployment
config_name = os.environ.get('FLASK_ENV', 'production')
app = create_app(config_name)

if __name__ == '__main__':
    # For local development only
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    app.run(debug=debug, host='0.0.0.0', port=port)