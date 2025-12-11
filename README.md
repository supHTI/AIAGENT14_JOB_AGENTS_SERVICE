# AIAGENT14_JOB_AGENTS_SERVICE

Job Agents Service API for generating job posts with AI-powered HTML generation.

## Features

- Job post creation with dimension mapping for social media platforms
- AI-powered HTML generation using Google Gemini
- Background task processing with Celery and Redis
- Real-time status updates via WebSocket
- File upload and storage system
- Support for multiple design types and languages

## Prerequisites

- Python 3.13+
- Redis server running
- MySQL database
- Google API key for Gemini
- UV package manager

## Installation

1. Install dependencies using UV:
```bash
uv sync
```

2. Set up environment variables in `.env` file:
```env
# Database
DB_HOST=localhost
DB_PORT=3306
DB_NAME=your_database
DB_USER=your_user
DB_PASSWORD=your_password

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# Google API
GOOGLE_API_KEY=your_google_api_key
GOOGLE_MODEL_NAME=gemini-pro

# Application
IMAGE_PATH=./uploads/images
BASE_URL=http://localhost:8115

# Other settings...
```

## Running the Application

### 1. Start the FastAPI Server

Run the Uvicorn server on port 8115:

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8115 --reload
```

Or using Python directly:
```bash
uv run python -m uvicorn app.main:app --host 0.0.0.0 --port 8115 --reload
```

The API will be available at:
- API: `http://localhost:8115`
- API Documentation: `http://localhost:8115/model/api/docs`
- Swagger UI: `http://localhost:8115/model/api/docs`

### 2. Start Celery Workers

Start Celery workers with 4 threads:

```bash
uv run celery -A celery_worker worker --loglevel=info --pool=threads --concurrency=4
```

Or with more verbose logging:
```bash
uv run celery -A celery_worker worker --loglevel=debug --pool=threads --concurrency=4
```

**Note:** Make sure Redis is running before starting Celery workers.

### 3. Start Celery Beat (Optional - for scheduled tasks)

If you need scheduled tasks:
```bash
uv run celery -A celery_worker beat --loglevel=info
```

### 4. Monitor Celery (Optional)

To monitor Celery tasks in real-time:
```bash
uv run celery -A celery_worker flower
```

Then access Flower at `http://localhost:5555`

## API Endpoints

### Job Post Creation
- **POST** `/job-post/{job_id}` - Create a new job post
  - Accepts: dimension, instructions, language, logo (URL or file), type, generate_image, images, cta
  - Returns: task_id, job_post_id, job_id, status

### File Retrieval
- **GET** `/files/{file_id}` - Retrieve a stored file (images, logos, HTML)

### WebSocket
- **WS** `/ws/task/{task_id}` - Real-time task status updates

## WebSocket Access

### Using JavaScript/TypeScript (Browser)

```javascript
const taskId = 'your-task-id-here';
const ws = new WebSocket(`ws://localhost:8115/ws/task/${taskId}`);

ws.onopen = () => {
    console.log('WebSocket connected');
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Status update:', data);
    // data contains: { status, progress, message, timestamp }
    
    if (data.status === 'completed' || data.status === 'failed') {
        ws.close();
    }
};

ws.onerror = (error) => {
    console.error('WebSocket error:', error);
};

ws.onclose = () => {
    console.log('WebSocket disconnected');
};
```

### Using Python

```python
import asyncio
import websockets
import json

async def listen_to_task_status(task_id):
    uri = f"ws://localhost:8115/ws/task/{task_id}"
    async with websockets.connect(uri) as websocket:
        while True:
            try:
                message = await websocket.recv()
                data = json.loads(message)
                print(f"Status: {data['status']}, Progress: {data['progress']}%")
                
                if data['status'] in ['completed', 'failed']:
                    break
            except websockets.exceptions.ConnectionClosed:
                break

# Usage
asyncio.run(listen_to_task_status('your-task-id-here'))
```

### Using curl (for testing)

```bash
# Note: curl doesn't support WebSocket directly, use wscat or similar tool
# Install wscat: npm install -g wscat

wscat -c ws://localhost:8115/ws/task/your-task-id-here
```

### Using Postman/Insomnia

1. Create a new WebSocket request
2. URL: `ws://localhost:8115/ws/task/{task_id}`
3. Replace `{task_id}` with your actual task ID
4. Connect and you'll receive real-time updates

## Example Usage

### 1. Create a Job Post

```bash
curl -X POST "http://localhost:8115/job-post/1" \
  -F "dimension=instagram" \
  -F "instructions=Create a vibrant and modern job posting" \
  -F "language=English" \
  -F "type=vibrant" \
  -F "generate_image=true" \
  -F "cta=true" \
  -F "created_by=1" \
  -F "logo_file=@/path/to/logo.png"
```

Response:
```json
{
  "task_id": "uuid-here",
  "job_post_id": "JP_1_1_20241219120000",
  "job_id": 1,
  "status": "pending",
  "message": "Job post creation started"
}
```

### 2. Connect to WebSocket for Status Updates

Use the `task_id` from the response above to connect to the WebSocket endpoint.

### 3. Retrieve Generated HTML File

After task completion, you can retrieve the HTML file using the file_id returned in the task result:
```bash
curl "http://localhost:8115/files/{file_id}"
```

## Development

### Project Structure

```
app/
├── api/
│   └── endpoints/          # API endpoints
├── cache_db/               # Redis configuration
├── celery/                 # Celery configuration and tasks
├── core/                   # Application settings
├── database_layer/         # Database models and config
├── models/                 # AI model configurations
├── prompt_templates/       # AI prompt templates
└── utils/                  # Utility functions
```

### Running Tests

```bash
uv run pytest
```

## Troubleshooting

### Redis Connection Issues
- Ensure Redis is running: `redis-cli ping`
- Check Redis host and port in `.env`

### Celery Worker Issues
- Ensure Redis is accessible
- Check Celery logs for errors
- Verify task imports are correct

### WebSocket Connection Issues
- Ensure the FastAPI server is running
- Check CORS settings if connecting from browser
- Verify the task_id exists

## License

[Your License Here]
