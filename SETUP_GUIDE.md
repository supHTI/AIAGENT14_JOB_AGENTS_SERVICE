# Call Processing API - Setup Guide

## Quick Start

### 1. Install System Dependencies

#### Windows
```powershell
# Install FFmpeg (required for audio processing)
choco install ffmpeg

# Verify installation
ffmpeg -version
```

#### Linux (Ubuntu/Debian)
```bash
sudo apt-get update
sudo apt-get install -y ffmpeg redis-server
```

#### macOS
```bash
brew install ffmpeg redis
```

### 2. Install Python Dependencies

```bash
# Navigate to project directory
cd AIAGENT14_JOB_AGENTS_SERVICE

# Install all dependencies
pip install -e .

# Or use uv (if available)
uv pip install -e .
```

**Required packages (already in pyproject.toml):**
- `pydub>=0.25.1` - Audio processing
- `google-cloud-speech>=2.27.0` - Speech-to-Text
- `tiktoken>=0.8.0` - Token counting
- `celery>=5.6.0` - Async task processing
- `redis>=5.0.0` - Cache and message broker
- `fastapi>=0.116.1` - API framework
- `python-multipart>=0.0.20` - File uploads

### 3. Google Cloud Setup

#### 3.1 Create Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable **Speech-to-Text API**:
   - Go to "APIs & Services" > "Library"
   - Search for "Cloud Speech-to-Text API"
   - Click "Enable"

#### 3.2 Create Service Account
1. Go to "IAM & Admin" > "Service Accounts"
2. Click "Create Service Account"
3. Name: `call-processing-stt`
4. Grant role: **Cloud Speech Client** or **Cloud Speech Administrator**
5. Click "Done"

#### 3.3 Create and Download Credentials
1. Click on the service account you just created
2. Go to "Keys" tab
3. Click "Add Key" > "Create new key"
4. Select "JSON" format
5. Download the JSON file
6. Save it securely (e.g., `credentials/google-credentials.json`)

#### 3.4 Set Environment Variable

**Windows (PowerShell):**
```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\credentials\google-credentials.json"

# Make it permanent
[System.Environment]::SetEnvironmentVariable('GOOGLE_APPLICATION_CREDENTIALS', 'C:\path\to\credentials\google-credentials.json', 'User')
```

**Linux/macOS:**
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/credentials/google-credentials.json"

# Add to ~/.bashrc or ~/.zshrc for permanent
echo 'export GOOGLE_APPLICATION_CREDENTIALS="/path/to/credentials/google-credentials.json"' >> ~/.bashrc
source ~/.bashrc
```

### 4. Start Redis

#### Using Docker (Recommended)
```bash
docker run -d --name redis-server -p 6379:6379 redis:latest
```

#### Local Installation

**Windows:**
```powershell
# Download from https://github.com/microsoftarchive/redis/releases
# Or use WSL and install Redis there

# Using WSL
wsl
sudo apt-get install redis-server
redis-server
```

**Linux:**
```bash
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Check status
redis-cli ping
# Should return: PONG
```

**macOS:**
```bash
brew services start redis

# Check status
redis-cli ping
```

### 5. Start Celery Worker

Open a new terminal:

```bash
cd AIAGENT14_JOB_AGENTS_SERVICE

# Start Celery worker
celery -A app.celery.celery_config.celery_app worker --loglevel=info --pool=threads --concurrency=4
```

**Expected output:**
```
celery@hostname ready.
```

### 6. Start FastAPI Server

Open another terminal:

```bash
cd AIAGENT14_JOB_AGENTS_SERVICE

# Start server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Expected output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

### 7. Test the API

#### Method 1: Using cURL
```bash
# Upload audio file
curl -X POST "http://localhost:8000/api/v1/call/process" \
  -F "audio_file=@interview.mp3" \
  -F "candidate_id=123" \
  -F "job_id=456" \
  -F "language=en-IN"

# Response: {"request_id": "abc123", "status": "processing"}

# Check result (replace abc123 with your request_id)
curl "http://localhost:8000/api/v1/call/result/abc123"
```

#### Method 2: Using Python Script
```python
import requests

# Upload audio
response = requests.post(
    "http://localhost:8000/api/v1/call/process",
    files={'audio_file': open('interview.mp3', 'rb')},
    data={
        'candidate_id': 123,
        'job_id': 456,
        'language': 'en-IN'
    }
)

request_id = response.json()['request_id']
print(f"Request ID: {request_id}")

# Check result
result = requests.get(f"http://localhost:8000/api/v1/call/result/{request_id}")
print(result.json())
```

#### Method 3: Using Swagger UI
1. Open browser: `http://localhost:8000/model/api/docs`
2. Navigate to **Call Processing** section
3. Try out the endpoints interactively

### 8. Run Example Script

```bash
cd AIAGENT14_JOB_AGENTS_SERVICE

# Run the example
python example_usage.py
```

## Verification Checklist

- [ ] FFmpeg installed: `ffmpeg -version`
- [ ] Redis running: `redis-cli ping` → PONG
- [ ] Google credentials set: `echo $GOOGLE_APPLICATION_CREDENTIALS`
- [ ] Python dependencies installed: `pip list | grep pydub`
- [ ] Celery worker running and connected
- [ ] FastAPI server running on port 8000
- [ ] Can access Swagger UI: http://localhost:8000/model/api/docs

## Troubleshooting

### Issue: "FFmpeg not found"
**Solution:**
```bash
# Check if installed
ffmpeg -version

# If not, install it
# Windows: choco install ffmpeg
# Linux: sudo apt-get install ffmpeg
# macOS: brew install ffmpeg

# Restart terminal after installation
```

### Issue: "Google credentials not found"
**Solution:**
```bash
# Check environment variable
echo $GOOGLE_APPLICATION_CREDENTIALS  # Linux/macOS
echo $env:GOOGLE_APPLICATION_CREDENTIALS  # Windows PowerShell

# Verify file exists
ls -la /path/to/credentials/google-credentials.json

# Set it again if needed
export GOOGLE_APPLICATION_CREDENTIALS="/correct/path/to/credentials.json"
```

### Issue: "Celery worker not connecting to Redis"
**Solution:**
```bash
# Check Redis is running
redis-cli ping

# If not running:
# Docker: docker start redis-server
# Linux: sudo systemctl start redis-server
# macOS: brew services start redis

# Check Redis connection in Python
python -c "import redis; r = redis.Redis(); print(r.ping())"
```

### Issue: "Module not found: pydub/google.cloud.speech"
**Solution:**
```bash
# Reinstall dependencies
cd AIAGENT14_JOB_AGENTS_SERVICE
pip install -e .

# Or install individually
pip install pydub google-cloud-speech tiktoken
```

### Issue: "Audio file format not supported"
**Solution:**
- Supported formats: MP3, WAV, M4A
- Try converting with FFmpeg:
```bash
ffmpeg -i input.avi -ac 1 -ar 16000 output.wav
```

### Issue: "Task timeout"
**Solution:**
- Increase timeout in celery config
- For long audio files (> 1 hour), consider splitting
- Check Celery worker logs for details

## Development Setup

### Enable Debug Logging
```python
# In app/main.py
logging.basicConfig(level=logging.DEBUG)
```

### Hot Reload Celery Worker
```bash
# Install watchdog
pip install watchdog

# Start worker with autoreload
celery -A app.celery.celery_config.celery_app worker --loglevel=debug --pool=threads --autoreload
```

### Monitor Tasks
```bash
# Install Flower (Celery monitoring tool)
pip install flower

# Start Flower
celery -A app.celery.celery_config.celery_app flower --port=5555

# Open browser: http://localhost:5555
```

## Production Deployment

### Using Docker Compose

Create `docker-compose.yml`:
```yaml
version: '3.8'

services:
  redis:
    image: redis:latest
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  celery:
    build: .
    command: celery -A app.celery.celery_config.celery_app worker --loglevel=info --pool=threads --concurrency=4
    environment:
      - GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/google-credentials.json
    volumes:
      - ./credentials:/app/credentials
    depends_on:
      - redis

  api:
    build: .
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000
    ports:
      - "8000:8000"
    environment:
      - GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/google-credentials.json
    volumes:
      - ./credentials:/app/credentials
    depends_on:
      - redis
      - celery

volumes:
  redis_data:
```

Start with:
```bash
docker-compose up -d
```

### Environment Variables
Create `.env` file:
```env
GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

## Next Steps

1. ✅ Test with sample audio files
2. ✅ Integrate with your frontend application
3. ✅ Set up monitoring (Flower, Prometheus)
4. ✅ Configure production deployment
5. ✅ Set up logging aggregation
6. ✅ Implement authentication/authorization
7. ✅ Add rate limiting
8. ✅ Set up backup and disaster recovery

## Resources

- [Google Cloud Speech-to-Text Documentation](https://cloud.google.com/speech-to-text/docs)
- [Celery Documentation](https://docs.celeryproject.org/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydub Documentation](https://github.com/jiaaro/pydub)
- [FFmpeg Documentation](https://ffmpeg.org/documentation.html)

## Support

For issues or questions:
1. Check the logs: `tail -f celery.log`
2. Enable debug mode
3. Consult the troubleshooting section
4. Contact: [Your Support Email]
