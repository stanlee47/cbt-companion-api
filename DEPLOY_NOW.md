# 🚀 Quick Deployment Guide

## What Was Fixed

Your backend was **crashing every 1-2.5 hours** with:
- `WORKER TIMEOUT (pid:7)`
- `Worker was sent SIGKILL! Perhaps out of memory?`

**Root causes**:
1. Gunicorn timeout too short (30s)
2. Groq API calls had no timeout
3. PyTorch ML model consuming 2GB+ at startup
4. Single worker = one slow request blocks everything

## Files Changed

1. ✅ `gunicorn.conf.py` - **NEW** - Worker configuration
2. ✅ `Dockerfile` - Uses new config file
3. ✅ `groq_client.py:22` - Added 60s API timeout
4. ✅ `app.py` - Lazy ML loading + health endpoint
5. ✅ `requirements.txt` - Added psutil for monitoring

## Deploy Now

```bash
# 1. Review changes
git status

# 2. Commit
git add gunicorn.conf.py Dockerfile groq_client.py app.py requirements.txt
git commit -m "Fix HF worker timeouts and memory issues

- Configure gunicorn: 2 workers, 180s timeout
- Add 60s timeout to Groq API calls
- Lazy load ML model (saves 2GB RAM)
- Add /health endpoint for monitoring
- Improve error handling"

# 3. Push to HF
git push origin main
```

## Verify After Deploy

### 1. Check Startup Logs
Look for:
```
===== Gunicorn Configuration =====
Workers: 2
Timeout: 180s
==================================
Groq client initialized with model: llama-3.3-70b-versatile (timeout: 60s)
```

### 2. Test Health Endpoint
```bash
curl https://YOUR-HF-SPACE.hf.space/health
```

Expected response:
```json
{
  "status": "healthy",
  "memory_mb": 1200.5,
  "ml_model_loaded": false
}
```

### 3. Monitor for 1 Hour
Watch logs - you should **NOT** see:
- ❌ `WORKER TIMEOUT`
- ❌ `SIGKILL`
- ❌ `out of memory`

## What to Expect

| Issue | Before | After |
|-------|--------|-------|
| Worker crashes | Every 1-2.5 hrs | Should not happen |
| Memory at start | ~3-4GB | ~1-2GB |
| Request timeout | 30s | 180s |
| API hangs | Possible | Prevented (60s max) |

## If Still Having Issues

### Option 1: Reduce to 1 Worker
Edit `gunicorn.conf.py`:
```python
workers = 1  # Instead of 2
```

### Option 2: Increase Timeout
Edit `gunicorn.conf.py`:
```python
timeout = 300  # 5 minutes instead of 3
```

### Option 3: Check Groq API Status
- Visit Groq status page
- API might be slow during peak hours
- Consider rate limiting on frontend

## Success Criteria

✅ App runs for **24+ hours** without crashes
✅ Health endpoint shows stable memory usage
✅ Full Beck protocol sessions complete successfully
✅ No WORKER TIMEOUT in logs

---

**Ready to deploy!** 🚀

Read `HF_OPTIMIZATION_FIXES.md` for full technical details.
