# Kikuyu Translation Platform - Deployment Guide

## 🚀 Local Testing with Docker

### 1. Build the Docker Image
```bash
docker build -t kikuyu-app .
```

### 2. Run Locally
```bash
docker run -d -p 5000:5000 \
  --name kikuyu-local \
  -e OPENROUTER_API_KEY="your-api-key-here" \
  -e ADMIN_PASSWORD="your-admin-password" \
  kikuyu-app
```

### 3. Test the Application
- Main app: http://localhost:5000
- Translation page: http://localhost:5000/translate
- Admin panel: http://localhost:5000/admin/

### 4. Stop and Clean Up
```bash
docker stop kikuyu-local
docker rm kikuyu-local
```

## 🌐 Render Deployment

### Method 1: Using Docker (Recommended)

1. **Connect Repository to Render**
   - Go to [Render Dashboard](https://dashboard.render.com)
   - Click "New +" → "Web Service"
   - Connect your GitHub repository

2. **Configure Service**
   - **Environment**: Docker
   - **Region**: Choose closest to your users
   - **Branch**: main (or your preferred branch)
   - **Dockerfile Path**: ./Dockerfile

3. **Set Environment Variables** (Important!)
   ```
   FLASK_ENV=production
   DEBUG=false
   OPENROUTER_API_KEY=your-openrouter-api-key
   ADMIN_PASSWORD=your-secure-admin-password
   SECRET_KEY=your-secret-key-for-sessions
   SESSION_COOKIE_SECURE=true
   PORT=5000
   ```

4. **Deploy**
   - Click "Create Web Service"
   - Wait for deployment to complete (5-10 minutes)

### Method 2: Using Buildpack (Alternative)

If Docker doesn't work, you can use Python buildpack:

1. **Configure Service**
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn --bind 0.0.0.0:$PORT --timeout 120 --workers 1 --threads 2 run:app`

2. **Set the same environment variables as above**

## 🔧 Environment Variables Reference

### Required Variables
- `OPENROUTER_API_KEY`: Your OpenRouter API key for generating prompts
- `ADMIN_PASSWORD`: Password for admin panel access
- `SECRET_KEY`: Flask secret key for sessions (auto-generated on Render)

### Optional Variables
- `MIN_CACHE_SIZE`: Minimum number of cached prompts (default: 10)
- `PROMPT_BATCH_SIZE`: Number of prompts to generate per batch (default: 20)
- `DAILY_SUBMISSION_LIMIT`: Max translations per user per day (default: unlimited)

## 📊 Post-Deployment Checklist

1. **Test Core Functionality**
   - [ ] Homepage loads correctly
   - [ ] Translation page works
   - [ ] Admin login works
   - [ ] Database initializes properly

2. **Verify Environment**
   - [ ] All environment variables are set
   - [ ] API key is working (check logs)
   - [ ] Admin password is secure

3. **Monitor Health**
   - [ ] Check Render logs for errors
   - [ ] Test prompt generation
   - [ ] Verify database persistence

## 🐛 Troubleshooting

### Common Issues

**Build Fails with GCC Errors**
- This is normal - the Dockerfile installs GCC for Python package compilation
- Build time: ~5-10 minutes (first time)

**App Doesn't Start**
- Check environment variables are set correctly
- Verify OPENROUTER_API_KEY is valid
- Check Render logs for specific error messages

**Database Issues**
- SQLite database is created automatically
- Data persists in Render's disk storage
- For production, consider PostgreSQL addon

**Prompt Generation Fails**
- Verify OPENROUTER_API_KEY is valid
- Check API quota/limits
- Monitor API usage in OpenRouter dashboard

### Render-Specific Tips

1. **Free Tier Limitations**
   - Service sleeps after 15 minutes of inactivity
   - First request after sleep takes ~30 seconds
   - 750 hours/month limit

2. **Upgrading to Paid Plan**
   - No sleep/wake delays
   - More CPU/memory resources
   - Custom domains available

3. **Monitoring**
   - Use Render dashboard to monitor resource usage
   - Check logs for errors and performance
   - Set up health checks if needed

## 🔄 Updating Your Deployment

1. **Automatic Deployment**
   - Push changes to your main branch
   - Render auto-deploys (if enabled)

2. **Manual Deployment**
   - Go to Render dashboard
   - Click "Manual Deploy" → "Deploy latest commit"

3. **Environment Variable Updates**
   - Update in Render dashboard
   - Triggers automatic redeployment

## 📝 Notes

- The application uses SQLite for simplicity
- All user data and translations are stored locally
- Consider database backups for production use
- Monitor OpenRouter API usage to avoid quota issues

## 🆘 Getting Help

If you encounter issues:
1. Check Render service logs
2. Verify all environment variables
3. Test locally with Docker first
4. Check OpenRouter API status
5. Review application logs for specific errors

---

**Happy Deploying! 🎉**

Your Kikuyu Translation Platform will help preserve an important language and culture.