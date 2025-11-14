# GitHub Actions CI/CD Setup

This guide explains how to set up automatic deployment to AWS EC2 using GitHub Actions.

## Prerequisites

1. Your Django application is already deployed on AWS EC2 (follow `DEPLOYMENT_AWS_EC2.md`)
2. All services (Gunicorn, Daphne, Celery, Nginx) are configured and running
3. You have your EC2 SSH private key (`.pem` file)

---

## Setup GitHub Secrets

GitHub Actions needs access to your EC2 instance. You must add these secrets to your GitHub repository:

### Step 1: Go to Repository Settings

1. Navigate to your GitHub repository
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**

### Step 2: Add Required Secrets

Add the following 3 secrets:

#### 1. **SSH_PRIVATE_KEY**
- **Name:** `SSH_PRIVATE_KEY`
- **Value:** Your EC2 private key content (entire `.pem` file)

**How to get it:**
```bash
# On your local machine, open the .pem file
cat product-importer-key.pem

# Copy the ENTIRE content including:
# -----BEGIN RSA PRIVATE KEY-----
# ... (all the key content)
# -----END RSA PRIVATE KEY-----
```

Paste the entire content into the GitHub secret.

#### 2. **EC2_HOST**
- **Name:** `EC2_HOST`
- **Value:** Your EC2 public IP or domain name

**Examples:**
```
13.233.123.45
```
or
```
yourdomain.com
```

#### 3. **EC2_USER**
- **Name:** `EC2_USER`
- **Value:** `ubuntu` (for Ubuntu EC2 instances)

If you're using Amazon Linux, use `ec2-user` instead.

---

## How It Works

The workflow (`.github/workflows/deploy.yml`) automatically runs when you push code to the `main` branch.

### Deployment Steps:

1. ✅ Checks out your code from GitHub
2. ✅ Connects to EC2 via SSH
3. ✅ Pulls latest code from GitHub
4. ✅ Activates virtual environment
5. ✅ Installs/updates Python dependencies
6. ✅ Collects static files
7. ✅ Runs database migrations
8. ✅ Restarts all services (Gunicorn, Daphne, Celery, Nginx)
9. ✅ Verifies all services are running

---

## EC2 Setup (One-Time)

On your EC2 instance, ensure the `ubuntu` user can restart services without a password:

```bash
# SSH into your EC2 instance
ssh -i product-importer-key.pem ubuntu@<YOUR_EC2_IP>

# Create sudoers file for passwordless service restarts
sudo nano /etc/sudoers.d/ubuntu-services
```

**Add this content:**
```
ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl restart gunicorn
ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl restart daphne
ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl restart celery
ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl restart nginx
ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl is-active gunicorn
ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl is-active daphne
ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl is-active celery
ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl is-active nginx
```

**Save and set permissions:**
```bash
sudo chmod 0440 /etc/sudoers.d/ubuntu-services
sudo visudo -c  # Validate sudoers configuration
```

---

## Usage

Once everything is set up, deployment is automatic:

```bash
# Make changes to your code
git add .
git commit -m "Add new feature"
git push origin main

# GitHub Actions will automatically:
# 1. Detect the push to main branch
# 2. Run the deployment workflow
# 3. Deploy to your EC2 instance
```

---

## Monitoring Deployment

### View Deployment Logs:

1. Go to your GitHub repository
2. Click **Actions** tab
3. Click on the latest workflow run
4. Expand "Deploy to EC2" step to see logs

### Check Deployment Status on EC2:

```bash
# SSH into EC2
ssh -i product-importer-key.pem ubuntu@<YOUR_EC2_IP>

# Check service status
sudo systemctl status gunicorn
sudo systemctl status daphne
sudo systemctl status celery
sudo systemctl status nginx

# View application logs
sudo journalctl -u gunicorn -f
sudo journalctl -u daphne -f
sudo journalctl -u celery -f
```

---

## Troubleshooting

### Issue: "Permission denied (publickey)"

**Solution:**
- Verify `SSH_PRIVATE_KEY` secret is set correctly
- Ensure you copied the ENTIRE `.pem` file content including header/footer
- Check that `EC2_HOST` and `EC2_USER` are correct

### Issue: "sudo: a password is required"

**Solution:**
- Follow the "EC2 Setup (One-Time)" section above
- Ensure `/etc/sudoers.d/ubuntu-services` file is created with correct permissions

### Issue: "git pull failed"

**Solution:**
```bash
# SSH into EC2 and ensure git repo is clean
cd ~/product-importer
git status
git stash  # If there are local changes
```

### Issue: Services not restarting

**Solution:**
```bash
# Check service status manually
sudo systemctl status gunicorn
sudo journalctl -u gunicorn -n 50

# Check for errors in logs
sudo journalctl -u daphne -n 50
sudo journalctl -u celery -n 50
```

---

## Customization

### Deploy to Different Branch:

Edit `.github/workflows/deploy.yml`:
```yaml
on:
  push:
    branches:
      - production  # Change from 'main' to your branch
```

### Deploy Only on Tags:

```yaml
on:
  push:
    tags:
      - 'v*'  # Trigger only on version tags (v1.0.0, v2.1.3, etc.)
```

### Add Deployment Notifications:

You can add Slack/Discord notifications by adding steps:
```yaml
- name: Notify Slack
  if: success()
  uses: slackapi/slack-github-action@v1
  with:
    payload: |
      {
        "text": "✅ Deployment to EC2 succeeded!"
      }
  env:
    SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
```

---

## Security Best Practices

1. ✅ Never commit `.pem` files or secrets to GitHub
2. ✅ Use GitHub Secrets for all sensitive data
3. ✅ Limit sudoers permissions to only required commands
4. ✅ Use SSH key authentication (no passwords)
5. ✅ Regularly rotate SSH keys
6. ✅ Review deployment logs for any suspicious activity

---

## Manual Rollback

If deployment fails and you need to rollback:

```bash
# SSH into EC2
ssh -i product-importer-key.pem ubuntu@<YOUR_EC2_IP>

cd ~/product-importer

# Rollback to previous commit
git log  # Find the commit hash you want to rollback to
git reset --hard <commit-hash>

# Restart services
sudo systemctl restart gunicorn daphne celery nginx
```

---

**Your CI/CD pipeline is now ready! 🚀**

Every push to `main` branch will automatically deploy your application to AWS EC2.
