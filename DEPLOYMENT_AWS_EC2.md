# Django Product Importer - AWS EC2 Deployment Guide

This guide covers deploying the Product Importer application to AWS EC2 with all required services.

## Prerequisites

- AWS Account
- Domain name (optional, for SSL)
- Basic Linux command knowledge

---

## Part 1: AWS EC2 Instance Setup

### Step 1: Launch EC2 Instance

1. **Login to AWS Console** → Navigate to EC2 Dashboard

2. **Click "Launch Instance"**

3. **Configure Instance:**
   - **Name:** `product-importer-server`
   - **AMI:** Ubuntu Server 22.04 LTS (Free tier eligible)
   - **Instance Type:** `t2.medium` (minimum recommended)
     - t2.micro: For testing only
     - t2.small: For light usage
     - t2.medium: Recommended (2 vCPU, 4GB RAM)
     - t2.large: For production (2 vCPU, 8GB RAM)

4. **Key Pair:**
   - Click "Create new key pair"
   - Name: `product-importer-key`
   - Type: RSA
   - Format: `.pem` (for Mac/Linux) or `.ppk` (for Windows/PuTTY)
   - **Download and save securely**

5. **Network Settings:**
   - Allow SSH (port 22) from "My IP"
   - Allow HTTP (port 80) from "Anywhere"
   - Allow HTTPS (port 443) from "Anywhere"
   - Allow Custom TCP (port 8000) from "Anywhere" - for testing

6. **Storage:**
   - 20 GB minimum (30 GB recommended)
   - General Purpose SSD (gp3)

7. **Click "Launch Instance"**

### Step 2: Connect to EC2 Instance

**For Mac/Linux:**
```bash
# Set permissions for key file
chmod 400 product-importer-key.pem

# Connect to EC2
ssh -i product-importer-key.pem ubuntu@<YOUR_EC2_PUBLIC_IP>
```

**For Windows (using PuTTY):**
1. Convert .pem to .ppk using PuTTYgen
2. Open PuTTY
3. Enter: `ubuntu@<YOUR_EC2_PUBLIC_IP>`
4. Connection → SSH → Auth → Browse → Select .ppk file
5. Click "Open"

---

## Part 2: Initial Server Setup

### Step 3: Update System

```bash
# Update package list
sudo apt update

# Upgrade installed packages
sudo apt upgrade -y

# Install basic utilities
sudo apt install -y build-essential curl git vim wget
```

### Step 4: Install Python 3.10+

```bash
# Install Python and pip
sudo apt install -y python3.10 python3.10-venv python3-pip python3.10-dev

# Verify installation
python3 --version
pip3 --version
```

---

## Part 3: Install PostgreSQL

### Step 5: Install and Configure PostgreSQL

```bash
# Install PostgreSQL
sudo apt install -y postgresql postgresql-contrib

# Start PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Create database and user
sudo -u postgres psql << EOF
CREATE DATABASE product_importer;
CREATE USER product_user WITH PASSWORD 'YourSecurePassword123!';
ALTER ROLE product_user SET client_encoding TO 'utf8';
ALTER ROLE product_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE product_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE product_importer TO product_user;
\q
EOF

# Verify connection
psql -U product_user -d product_importer -h localhost
# Enter password when prompted
# Type \q to exit
```

---

## Part 4: Install Redis

### Step 6: Install Redis Server

```bash
# Install Redis
sudo apt install -y redis-server

# Configure Redis to start on boot
sudo systemctl enable redis-server

# Start Redis
sudo systemctl start redis-server

# Test Redis
redis-cli ping
# Should return: PONG
```

---

## Part 5: Deploy Application

### Step 7: Clone Repository

```bash
# Navigate to home directory
cd ~

# Clone your repository (replace with your actual repo URL)
git clone <YOUR_REPOSITORY_URL> product-importer
cd product-importer

# Or upload code manually using SCP:
# scp -i product-importer-key.pem -r /local/path/to/FulfIl ubuntu@<EC2_IP>:~/product-importer
```

### Step 8: Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip
```

### Step 9: Install Dependencies

```bash
# Install Python packages
pip install -r requirements.txt

# Install additional production packages
pip install gunicorn
```

### Step 10: Configure Environment Variables

```bash
# Create .env file
nano .env
```

**Add the following (replace with your actual values):**

```env
# Django Settings
DJANGO_SECRET_KEY=your-super-secret-key-here-change-this
DEBUG=False
ALLOWED_HOSTS=<YOUR_EC2_PUBLIC_IP>,<YOUR_DOMAIN>

# AWS S3 Configuration
AWS_S3_ACCESS_KEY_ID=your-aws-access-key-id
AWS_S3_SECRET_ACCESS_KEY=your-aws-secret-access-key
AWS_S3_BUCKET=your-bucket-name
AWS_S3_REGION_NAME=ap-south-1

# Database Configuration
DB_NAME=product_importer
DB_USER=product_user
DB_PASSWORD=YourSecurePassword123!
DB_HOST=localhost
DB_PORT=5432

# Celery Configuration
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Django Channels (WebSocket)
REDIS_HOST=localhost
REDIS_PORT=6379
```

**Save and exit:** Press `Ctrl+X`, then `Y`, then `Enter`

### Step 11: Update Django Settings for Production

```bash
nano core/settings.py
```

**Update the ALLOWED_HOSTS:**
```python
import os
from dotenv import load_dotenv

load_dotenv()

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost').split(',')
```

**Update DATABASES:**
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'product_importer'),
        'USER': os.getenv('DB_USER', 'product_user'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}
```

### Step 12: Collect Static Files & Migrate

```bash
# Collect static files
python manage.py collectstatic --noinput

# Run migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser (optional)
python manage.py createsuperuser
```

---

## Part 6: Configure Nginx

### Step 13: Install and Configure Nginx

```bash
# Install Nginx
sudo apt install -y nginx

# Create Nginx configuration
sudo nano /etc/nginx/sites-available/product-importer
```

**Add the following configuration:**

```nginx
upstream django_app {
    server 127.0.0.1:8000;
}

upstream daphne_app {
    server 127.0.0.1:8001;
}

server {
    listen 80;
    server_name <YOUR_EC2_PUBLIC_IP> <YOUR_DOMAIN>;

    client_max_body_size 100M;

    location = /favicon.ico { access_log off; log_not_found off; }

    location /static/ {
        alias /home/ubuntu/product-importer/staticfiles/;
    }

    location /media/ {
        alias /home/ubuntu/product-importer/media/;
    }

    # WebSocket connections
    location /ws/ {
        proxy_pass http://daphne_app;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Regular HTTP requests
    location / {
        proxy_pass http://django_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Enable the site:**

```bash
# Create symbolic link
sudo ln -s /etc/nginx/sites-available/product-importer /etc/nginx/sites-enabled/

# Remove default site
sudo rm /etc/nginx/sites-enabled/default

# Test Nginx configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx
sudo systemctl enable nginx
```

---

## Part 7: Configure Systemd Services

### Step 14: Create Gunicorn Service

```bash
sudo nano /etc/systemd/system/gunicorn.service
```

**Add:**

```ini
[Unit]
Description=Gunicorn daemon for Product Importer
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=/home/ubuntu/product-importer
Environment="PATH=/home/ubuntu/product-importer/venv/bin"
ExecStart=/home/ubuntu/product-importer/venv/bin/gunicorn \
    --workers 3 \
    --bind 127.0.0.1:8000 \
    core.wsgi:application

[Install]
WantedBy=multi-user.target
```

### Step 15: Create Daphne Service (for WebSockets)

```bash
sudo nano /etc/systemd/system/daphne.service
```

**Add:**

```ini
[Unit]
Description=Daphne daemon for Product Importer WebSockets
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=/home/ubuntu/product-importer
Environment="PATH=/home/ubuntu/product-importer/venv/bin"
ExecStart=/home/ubuntu/product-importer/venv/bin/daphne \
    -b 127.0.0.1 \
    -p 8001 \
    core.asgi:application

[Install]
WantedBy=multi-user.target
```

### Step 16: Create Celery Worker Service

```bash
sudo nano /etc/systemd/system/celery.service
```

**Add:**

```ini
[Unit]
Description=Celery Worker for Product Importer
After=network.target redis.service

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=/home/ubuntu/product-importer
Environment="PATH=/home/ubuntu/product-importer/venv/bin"
ExecStart=/home/ubuntu/product-importer/venv/bin/celery -A core worker --loglevel=info

[Install]
WantedBy=multi-user.target
```

### Step 17: Start All Services

```bash
# Reload systemd daemon
sudo systemctl daemon-reload

# Start and enable Gunicorn
sudo systemctl start gunicorn
sudo systemctl enable gunicorn

# Start and enable Daphne
sudo systemctl start daphne
sudo systemctl enable daphne

# Start and enable Celery
sudo systemctl start celery
sudo systemctl enable celery

# Check status of all services
sudo systemctl status gunicorn
sudo systemctl status daphne
sudo systemctl status celery
```

---

## Part 8: Configure Firewall

### Step 18: Setup UFW Firewall

```bash
# Allow SSH
sudo ufw allow OpenSSH

# Allow Nginx
sudo ufw allow 'Nginx Full'

# Enable firewall
sudo ufw --force enable

# Check status
sudo ufw status
```

---

## Part 9: SSL Setup (Optional but Recommended)

### Step 19: Install SSL Certificate with Let's Encrypt

**Prerequisites:** You must have a domain name pointing to your EC2 IP

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Obtain SSL certificate
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Follow the prompts:
# - Enter email address
# - Agree to terms
# - Choose whether to redirect HTTP to HTTPS (recommended: yes)

# Test automatic renewal
sudo certbot renew --dry-run
```

---

## Part 10: Access Your Application

### Step 20: Access the Application

**HTTP Access:**
```
http://<YOUR_EC2_PUBLIC_IP>/product/
```

**With Domain (if configured):**
```
https://yourdomain.com/product/
```

**Admin Panel:**
```
https://yourdomain.com/admin/
```

---

## Common Commands

### View Logs

```bash
# Gunicorn logs
sudo journalctl -u gunicorn -f

# Daphne logs
sudo journalctl -u daphne -f

# Celery logs
sudo journalctl -u celery -f

# Nginx error logs
sudo tail -f /var/log/nginx/error.log

# Nginx access logs
sudo tail -f /var/log/nginx/access.log
```

### Restart Services

```bash
# Restart Gunicorn
sudo systemctl restart gunicorn

# Restart Daphne
sudo systemctl restart daphne

# Restart Celery
sudo systemctl restart celery

# Restart Nginx
sudo systemctl restart nginx

# Restart all services
sudo systemctl restart gunicorn daphne celery nginx
```

### Update Application

```bash
# Navigate to project directory
cd ~/product-importer

# Activate virtual environment
source venv/bin/activate

# Pull latest changes
git pull origin main

# Install new dependencies (if any)
pip install -r requirements.txt

# Collect static files
python manage.py collectstatic --noinput

# Run migrations
python manage.py migrate

# Restart services
sudo systemctl restart gunicorn daphne celery
```

---

## Troubleshooting

### Issue: 502 Bad Gateway

```bash
# Check Gunicorn status
sudo systemctl status gunicorn

# Check Gunicorn logs
sudo journalctl -u gunicorn -n 50

# Restart Gunicorn
sudo systemctl restart gunicorn
```

### Issue: WebSocket Connection Failed

```bash
# Check Daphne status
sudo systemctl status daphne

# Check Daphne logs
sudo journalctl -u daphne -n 50

# Check Redis status
sudo systemctl status redis

# Restart Daphne
sudo systemctl restart daphne
```

### Issue: Celery Tasks Not Processing

```bash
# Check Celery status
sudo systemctl status celery

# Check Celery logs
sudo journalctl -u celery -n 50

# Check Redis connection
redis-cli ping

# Restart Celery
sudo systemctl restart celery
```

### Issue: Database Connection Error

```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Test database connection
psql -U product_user -d product_importer -h localhost

# Restart PostgreSQL
sudo systemctl restart postgresql
```

### Issue: Static Files Not Loading

```bash
# Verify static files collected
ls -la /home/ubuntu/product-importer/staticfiles/

# Re-collect static files
cd ~/product-importer
source venv/bin/activate
python manage.py collectstatic --noinput

# Check Nginx configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx
```

---

## Security Best Practices

1. **Change default passwords** for PostgreSQL and create strong passwords
2. **Use environment variables** for all sensitive data (never hardcode)
3. **Enable firewall** (UFW) and only allow necessary ports
4. **Setup SSL/HTTPS** using Let's Encrypt
5. **Regular updates:** `sudo apt update && sudo apt upgrade`
6. **Backup database regularly:**
   ```bash
   pg_dump -U product_user product_importer > backup_$(date +%Y%m%d).sql
   ```
7. **Monitor logs** regularly for suspicious activity
8. **Disable DEBUG mode** in production (`DEBUG=False`)
9. **Use strong SECRET_KEY** (generate new one for production)
10. **Setup automated backups** to S3

---

## Monitoring & Maintenance

### Setup Log Rotation

```bash
sudo nano /etc/logrotate.d/product-importer
```

**Add:**
```
/var/log/nginx/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 www-data adm
    sharedscripts
    postrotate
        [ -f /var/run/nginx.pid ] && kill -USR1 `cat /var/run/nginx.pid`
    endscript
}
```

### Setup Automated Backups

```bash
# Create backup script
nano ~/backup_db.sh
```

**Add:**
```bash
#!/bin/bash
BACKUP_DIR="/home/ubuntu/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup database
pg_dump -U product_user product_importer > $BACKUP_DIR/db_backup_$DATE.sql

# Keep only last 7 days of backups
find $BACKUP_DIR -name "db_backup_*.sql" -mtime +7 -delete

echo "Backup completed: $DATE"
```

```bash
# Make executable
chmod +x ~/backup_db.sh

# Add to crontab (daily at 2 AM)
crontab -e
```

**Add line:**
```
0 2 * * * /home/ubuntu/backup_db.sh >> /home/ubuntu/backup.log 2>&1
```

---

## Cost Optimization

1. **Stop instance when not in use** (for development/testing)
2. **Use Reserved Instances** for production (save up to 75%)
3. **Use S3 lifecycle policies** to move old files to cheaper storage
4. **Monitor usage** with AWS CloudWatch
5. **Right-size your instance** based on actual usage

---

## Next Steps

After successful deployment:
1. ✅ Test all features (upload, CRUD, webhooks)
2. ✅ Configure domain name and SSL
3. ✅ Setup monitoring and alerts
4. ✅ Configure automated backups
5. ✅ Document any custom configurations
6. ✅ Setup CI/CD pipeline (optional)

---

## Support Resources

- **AWS EC2 Documentation:** https://docs.aws.amazon.com/ec2/
- **Django Deployment:** https://docs.djangoproject.com/en/stable/howto/deployment/
- **Nginx Documentation:** https://nginx.org/en/docs/
- **Let's Encrypt:** https://letsencrypt.org/getting-started/

---

**Deployment Complete! 🎉**

Your Product Importer application should now be live and accessible at your EC2 public IP or domain name.
