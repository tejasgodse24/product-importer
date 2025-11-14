# Product Importer - Local Setup Instructions

This guide will walk you through setting up the Product Importer application on your local machine.

## Prerequisites

Before you begin, ensure you have the following installed on your machine:

- **Python 3.10 or higher** - [Download Python](https://www.python.org/downloads/)
- **PostgreSQL 12 or higher** - [Download PostgreSQL](https://www.postgresql.org/download/)
- **Redis** - [Download Redis](https://redis.io/download/)
- **Git** - [Download Git](https://git-scm.com/downloads)

### Installing Redis (Windows)

For Windows users, you can use:
- [Memurai](https://www.memurai.com/) (Redis-compatible)
- Or use WSL (Windows Subsystem for Linux) with Redis

## Step 1: Clone the Repository

```bash
git clone <repository-url>
cd FulfIl
```

## Step 2: Create Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate

# On macOS/Linux:
source venv/bin/activate
```

## Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

This will install all required packages including:
- Django 5.2.8
- Celery 5.5.3
- Channels 4.2.0
- PostgreSQL adapter (psycopg2)
- boto3 (AWS S3)
- And more...

## Step 4: Set Up Environment Variables

Create a `.env` file in the project root directory with the following variables:

```env
# Django Settings
DJANGO_SECRET_KEY=your-secret-key-here

# AWS S3 Configuration (for file storage)
AWS_S3_ACCESS_KEY_ID=your-aws-access-key-id
AWS_S3_SECRET_ACCESS_KEY=your-aws-secret-access-key
AWS_S3_BUCKET=your-bucket-name
AWS_S3_REGION_NAME=ap-south-1

# Celery Configuration
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Django Channels (WebSocket)
REDIS_HOST=localhost
REDIS_PORT=6379
```

**Note:** Replace the placeholder values with your actual credentials.

### Generating Django Secret Key

```python
# Run in Python shell
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
```

## Step 5: Database Setup

### Option A: Using PostgreSQL (Recommended)

1. **Create PostgreSQL Database:**

```sql
-- Connect to PostgreSQL
psql -U postgres

-- Create database
CREATE DATABASE product_importer;

-- Create user (optional)
CREATE USER product_user WITH PASSWORD 'your_password';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE product_importer TO product_user;
```

2. **Update `core/settings.py`** with your database credentials:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'product_importer',
        'USER': 'postgres',  # or 'product_user'
        'PASSWORD': 'your_password',
        'HOST': 'localhost',
        'PORT': '5432'
    }
}
```

### Option B: Using SQLite (For Testing Only)

If you want to use SQLite for quick testing, update `core/settings.py`:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
```

**Warning:** SQLite is not recommended for production or large datasets.

## Step 6: Run Database Migrations

```bash
# Create database tables
python manage.py makemigrations
python manage.py migrate
```

## Step 7: Create Superuser (Optional)

```bash
python manage.py createsuperuser
```

Follow the prompts to create an admin user for accessing Django admin panel.

## Step 8: Start Redis Server

### On Windows (using Memurai):
```bash
# Start Memurai service from Services or:
memurai.exe
```

### On macOS/Linux:
```bash
redis-server
```

**Verify Redis is running:**
```bash
redis-cli ping
# Should return: PONG
```

## Step 9: Start the Application

You need to start **3 services** in separate terminal windows:

### Terminal 1: Start Django with Daphne (ASGI Server for WebSockets)

```bash
# Activate virtual environment
venv\Scripts\activate  # Windows
# or
source venv/bin/activate  # macOS/Linux

# Start Daphne server
daphne -b 127.0.0.1 -p 8000 core.asgi:application
```

**Alternative:** For development without WebSockets, you can use:
```bash
python manage.py runserver
```

### Terminal 2: Start Celery Worker

```bash
# Activate virtual environment
venv\Scripts\activate  # Windows
# or
source venv/bin/activate  # macOS/Linux

# Start Celery worker
celery -A core worker --loglevel=info

# On Windows, if you get an error, use:
celery -A core worker --loglevel=info --pool=solo
```

### Terminal 3: Start Celery Beat (Optional - for scheduled tasks)

```bash
# Activate virtual environment
venv\Scripts\activate  # Windows
# or
source venv/bin/activate  # macOS/Linux

# Start Celery beat
celery -A core beat --loglevel=info
```

## Step 10: Access the Application

Open your browser and navigate to:

- **Main Application:** http://localhost:8000/product/
- **Admin Panel:** http://localhost:8000/admin/

## Application Features

### 1. Product Management
- **URL:** http://localhost:8000/product/
- View all products with pagination
- Create, update, delete products
- Search by SKU, name, or description
- Bulk delete with checkboxes

### 2. Bulk Upload
- **URL:** http://localhost:8000/product/upload/
- Upload CSV files (supports 500k+ records)
- Real-time progress tracking via WebSockets
- Automatic SKU deduplication (case-insensitive)

### 3. Webhook Management
- **URL:** http://localhost:8000/product/webhooks/
- Configure webhooks for events:
  - Bulk Upload Complete
  - Bulk Upload Failed
  - Bulk Delete Complete
- Test webhooks with live HTTP requests
- View response codes and response times

## CSV File Format

Your CSV file should have the following columns:

```csv
sku,name,description
PROD001,Product Name,Product Description
PROD002,Another Product,Another Description
```

**Required Fields:**
- `sku` - Unique identifier (case-insensitive)
- `name` - Product name

**Optional Fields:**
- `description` or `desc` - Product description

## Troubleshooting

### Issue: Redis Connection Error
```
Error: Redis connection failed
```

**Solution:** Make sure Redis is running:
```bash
redis-cli ping
```

### Issue: Celery Worker Not Starting (Windows)
```
Error: Task handler raised error: ValueError('need more than 0 values to unpack')
```

**Solution:** Use solo pool on Windows:
```bash
celery -A core worker --loglevel=info --pool=solo
```

### Issue: Database Connection Error
```
Error: could not connect to server
```

**Solution:**
- Verify PostgreSQL is running
- Check database credentials in `core/settings.py`
- Ensure database exists

### Issue: Module Not Found
```
ModuleNotFoundError: No module named 'X'
```

**Solution:**
```bash
pip install -r requirements.txt
```

### Issue: WebSocket Connection Failed
```
WebSocket connection failed
```

**Solution:**
- Make sure you're using Daphne instead of runserver
- Verify Redis is running (required for Django Channels)

### Issue: AWS S3 Upload Failed
```
Error: Unable to locate credentials
```

**Solution:**
- Verify AWS credentials in `.env` file
- Make sure S3 bucket exists and is accessible
- Check bucket permissions

## Testing the Application

### 1. Test Product CRUD
1. Go to http://localhost:8000/product/
2. Click "+ Create Product"
3. Fill in SKU and Name
4. Click "Create Product"

### 2. Test CSV Upload
1. Prepare a CSV file with product data
2. Go to http://localhost:8000/product/upload/
3. Click "Upload New CSV File"
4. Select your CSV file
5. Watch real-time progress updates

### 3. Test Webhooks
1. Go to http://localhost:8000/product/webhooks/
2. Click "+ Create Webhook"
3. Enter webhook URL (e.g., https://webhook.site/unique-url)
4. Select event type
5. Click "Test" to verify webhook works

## Stopping the Application

1. **Stop Daphne:** Press `Ctrl+C` in Terminal 1
2. **Stop Celery Worker:** Press `Ctrl+C` in Terminal 2
3. **Stop Celery Beat:** Press `Ctrl+C` in Terminal 3 (if running)
4. **Stop Redis:**
   - On Windows: Stop Memurai service
   - On macOS/Linux: `redis-cli shutdown`

## Next Steps

After successful local setup:
- Review the codebase
- Test all features
- Configure webhooks for your endpoints
- Prepare for deployment

## Additional Resources

- **Django Documentation:** https://docs.djangoproject.com/
- **Celery Documentation:** https://docs.celeryproject.org/
- **Django Channels Documentation:** https://channels.readthedocs.io/
- **Redis Documentation:** https://redis.io/documentation

## Support

For issues or questions, please check:
- Application logs in the terminal
- Celery worker logs
- Django error messages in the browser
