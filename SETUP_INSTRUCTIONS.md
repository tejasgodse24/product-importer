# Product Importer - Setup Instructions

## What Has Been Created

### 1. **Upload Page** (`templates/product/upload.html`)
- Clean, modern HTML/CSS/JS interface
- Drag-and-drop file upload
- Real-time progress tracking
- Supports CSV and Excel files (.csv, .xlsx)
- Client-side validation (file type, size limit 100MB)

### 2. **Django Views** (`product/views.py`)
- `upload_page()` - Renders the upload interface
- `upload_file()` - Handles file upload to S3 and triggers Celery task

### 3. **Celery Tasks** (`product/tasks.py`)
- `process_csv_file()` - Async task to process uploaded files
- Handles large files (500k+ records)
- Batch processing with progress tracking
- Supports both CSV and Excel formats

### 4. **Database Models** (`product/models.py`)
- `Product` - Stores product data (SKU, name, description, is_active)
- `UploadHistory` - Tracks upload progress and status
- `Webhook` - Manages webhook configurations

### 5. **Celery Configuration** (`core/celery.py`)
- Redis as message broker
- Auto-discovery of tasks
- 30-minute task timeout

---

## Installation & Setup

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 2: Ensure Redis is Running

You need Redis running locally for Celery to work.

**Windows:**
```bash
# Download Redis from https://github.com/microsoftarchive/redis/releases
# Or use WSL/Docker
docker run -d -p 6379:6379 redis
```

**Mac/Linux:**
```bash
redis-server
```

### Step 3: Run Database Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### Step 4: Create Superuser (Optional)

```bash
python manage.py createsuperuser
```

### Step 5: Start Django Development Server

```bash
python manage.py runserver
```

The app will be available at: **http://localhost:8000/**

### Step 6: Start Celery Worker (In a New Terminal)

```bash
celery -A core worker --loglevel=info
```

**Windows users:** Use this command instead:
```bash
celery -A core worker --loglevel=info --pool=solo
```

---

## How to Use

### 1. **Upload CSV/Excel File**
- Visit http://localhost:8000/
- Click or drag-and-drop your CSV/Excel file
- File format should have columns: `sku`, `name`, `desc` (or `description`)
- Click "Upload and Process"

### 2. **Monitor Progress**
- Progress bar shows upload progress
- After upload completes, Celery task processes the file in background
- Check Celery worker terminal for processing logs

### 3. **Check Results**
- Visit Django admin: http://localhost:8000/admin/
- Login with superuser credentials
- View imported products in "Products" section
- View upload history in "Upload Histories" section

---

## File Format Requirements

Your CSV/Excel file should have these columns:

| Column | Required | Description |
|--------|----------|-------------|
| `sku` | Yes | Stock Keeping Unit (unique identifier) |
| `name` | Yes | Product name |
| `desc` or `description` | No | Product description |

**Example CSV:**
```csv
sku,name,desc
ABC123,Product 1,This is product 1
XYZ456,Product 2,This is product 2
```

**Important Notes:**
- SKU is **case-insensitive** (ABC123 = abc123 = aBc123)
- Duplicate SKUs will be **overwritten** with latest data
- Products are marked as **active** by default

---

## Architecture Flow

```
User uploads file
    ↓
Django view validates file
    ↓
File uploaded to AWS S3
    ↓
UploadHistory record created (status: 'pending')
    ↓
Celery task triggered (process_csv_file.delay())
    ↓
Task downloads file from S3
    ↓
File parsed (CSV or Excel)
    ↓
Products created/updated in batches
    ↓
Progress tracked in UploadHistory
    ↓
Status updated to 'completed' or 'failed'
```

---

## Environment Variables

Current configuration in `.env`:

```env
# Django
DJANGO_SECRET_KEY=your-secret-key

# AWS S3
AWS_S3_ACCESS_KEY_ID=your-access-key
AWS_S3_SECRET_ACCESS_KEY=your-secret-key
AWS_S3_BUCKET=product-importer-csv
AWS_S3_REGION_NAME=ap-south-1

# Celery & Redis
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

---

## URL Routes

| URL | View | Description |
|-----|------|-------------|
| `/` | `upload_page` | Upload interface |
| `/upload/` | `upload_file` | File upload API endpoint |
| `/admin/` | Django admin | Admin panel |

---

## Troubleshooting

### Issue: Celery task not running
**Solution:** Make sure Celery worker is running in a separate terminal

### Issue: Redis connection error
**Solution:** Ensure Redis server is running on port 6379

### Issue: S3 upload fails
**Solution:** Check your AWS credentials in `.env` file and S3 bucket permissions

### Issue: File parsing errors
**Solution:** Ensure CSV/Excel has required columns: `sku`, `name`, `desc`

---

## Next Steps

To complete the full assignment, you still need to:

1. ✅ File upload with S3 and Celery ← **DONE**
2. ⏳ Real-time progress tracking with SSE/WebSockets
3. ⏳ Product management UI (view, create, update, delete)
4. ⏳ Bulk delete functionality
5. ⏳ Webhook configuration UI
6. ⏳ PostgreSQL database setup
7. ⏳ Deployment to Heroku/Render/AWS

---

## Technology Stack

- **Backend:** Django 5.2.8
- **Task Queue:** Celery 5.5.3
- **Message Broker:** Redis 5.2.1
- **Database:** SQLite (development) → PostgreSQL (production)
- **Storage:** AWS S3
- **Frontend:** Vanilla HTML/CSS/JavaScript
- **File Processing:** pandas, openpyxl

---

## Contact

For issues or questions, refer to the project documentation or assignment requirements.
