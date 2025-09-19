# Deployment Instructions for Render

## Prerequisites
1. Create a GitHub account and push this project to a repository
2. Create a Render account at https://render.com
3. Get an OpenRouter API key from https://openrouter.ai

## Step 1: Remove Development Files
Before deploying, remove these files to save space:
```bash
rm -rf venv/
rm -rf __pycache__/
rm test_*.py debug_csv.py migrate_to_hybrid.py admin_working.py
rm claude.md task.md project.md README.md
rm kikuyu_backup_*.db
rm -rf .claude/
```

## Step 2: Set Up Render Service

1. **Connect GitHub**: Link your GitHub repository to Render
2. **Create Web Service**:
   - Choose "Web Service"
   - Connect your GitHub repo
   - Use these settings:
     - **Name**: kikuyu-translation
     - **Environment**: Python 3
     - **Build Command**: `pip install -r requirements.txt`
     - **Start Command**: `gunicorn --bind 0.0.0.0:$PORT run:app`

## Step 3: Configure Environment Variables
In Render dashboard, add these environment variables:

### Required Variables:
- `SECRET_KEY`: Generate a random 32-character string
- `FLASK_ENV`: `production`
- `DEBUG`: `false`
- `OPENROUTER_API_KEY`: Your OpenRouter API key
- `ADMIN_PASSWORD`: Secure admin password

### Optional Variables (with defaults):
- `OPENROUTER_MODEL`: `meta-llama/llama-3.3-70b-instruct:free`
- `OPENROUTER_DAILY_LIMIT`: `50`
- `API_RATE_LIMIT`: `100 per hour`
- `LOG_LEVEL`: `INFO`

## Step 4: Deploy
1. Push changes to GitHub
2. Render will automatically deploy
3. Check logs for any issues
4. Visit your app URL provided by Render

## Project Structure (Deployment-Ready)
```
kikuyu/
├── app/                    # Flask application
├── templates/              # HTML templates
├── static/                 # CSS/JS/images
├── data/                   # Dataset files (19MB)
├── kikuyu.db              # SQLite database
├── requirements.txt        # Dependencies + gunicorn
├── run.py                 # Production-ready entry point
├── config.py              # Environment-based config
├── render.yaml            # Render configuration
└── .env.production        # Environment variables template
```

## Troubleshooting
- Check Render logs for deployment errors
- Ensure all environment variables are set
- SQLite database will be recreated automatically
- Free tier sleeps after 15 minutes of inactivity

## Post-Deployment
- Test all features
- Monitor logs for errors
- Set up custom domain (optional)
- Consider upgrading to paid tier for production use