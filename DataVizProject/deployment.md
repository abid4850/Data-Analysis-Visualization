
````md
# Django Data Visualization App Deployment Guide  
### Hostinger KVM VPS — dataviz.abidnexus.com
---

# Step 1: Connect & Install Packages

## 1.1 SSH into VPS
```bash
ssh root@168.231.80.98
````

## 1.2 Update & Install Required Packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y gcc python3-dev python3.12-venv nginx postgresql libpq-dev
```

---

# Step 2: Create Application User

## 2.1 Create dataviz_user

```bash
sudo useradd -m -s /bin/bash -G www-data dataviz_user
sudo passwd dataviz_user
```

Add sudo:

```bash
sudo usermod -aG sudo dataviz_user
```

Switch:

```bash
sudo su - dataviz_user
```

## 2.2 Fix Permissions

```bash
chmod 711 /home/dataviz_user
```

---

# Step 3: PostgreSQL Setup

Login:

```bash
sudo -u postgres psql
```

Run:

```sql
CREATE DATABASE dataviz_db;
CREATE USER dataviz_user WITH PASSWORD 'Dataviz@4850';
ALTER ROLE dataviz_user SET client_encoding TO 'utf8';
ALTER ROLE dataviz_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE dataviz_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE dataviz_db TO dataviz_user;
```

Switch DB:

```sql
\c dataviz_db;
```

Permissions:

```sql
GRANT ALL PRIVILEGES ON SCHEMA public TO dataviz_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO dataviz_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO dataviz_user;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO dataviz_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO dataviz_user;
```

Exit:

```
\q
```

---

# Step 4: Clone Project & Setup Python

## 4.1 Clone the Repo

```bash
sudo su - dataviz_user
cd
chmod 711 .
git clone https://github.com/abid4850/Data-Analysis-Visualization
```

## 4.2 Setup Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 4.3 Add requirements.txt

```bash
nano requirements.txt
```

Paste:

```
Django==5.2.9
matplotlib==3.10.7
numpy==2.3.5
pandas==2.3.3
plotly==6.5.0
seaborn==0.13.2
openpyxl==3.1.5
Pillow==12.0.0
asgiref==3.11.0
contourpy==1.3.3
cycler==0.12.1
et-xmlfile==2.0.0
fonttools==4.61.0
kiwisolver==1.4.9
narwhals==2.13.0
packaging==25.0
pyparsing==3.2.5
python-dateutil==2.9.0.post0
pytz==2025.2
six==1.17.0
sqlparse==0.5.4
tzdata==2025.2

uwsgi
psycopg2-binary
```

Install:

```bash
pip install -r requirements.txt
```

## 4.4 Auto-activate venv

```bash
nano ~/.bashrc
```

Add:

```bash
cd
source .venv/bin/activate
```

---

# Step 5: Configure Django Production Settings

Project path:

```
DataVizProject/DataVizProject/settings.py
```

Create production settings:

```bash
cd ~/Data-Analysis-Visualization/DataVizProject/DataVizProject
nano settings_prod.py
```

Paste:

```python
from .settings import *

DEBUG = False

ALLOWED_HOSTS = [
    'dataviz.abidnexus.com',
    'abidnexus.com',
    '168.231.80.98',
    'localhost'
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'dataviz_db',
        'USER': 'dataviz_user',
        'PASSWORD': 'dataviz@4850',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

STATIC_ROOT = '/home/dataviz_user/Data-Analysis-Visualization/staticfiles'
MEDIA_ROOT = '/home/dataviz_user/Data-Analysis-Visualization/media'
```

---

# Step 6: Migrations & Static Files

```bash
export DJANGO_SETTINGS_MODULE=DataVizProject.settings_prod
cd ~/Data-Analysis-Visualization/DataVizProject

python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

Password:

```
dataviz@4850
```

---

# Step 7: Configure uWSGI

Create config:

```bash
cd /home/dataviz_user
nano uwsgi.ini
```

Add:

```ini
[uwsgi]
chdir = /home/dataviz_user/Data-Analysis-Visualization/DataVizProject
module = DataVizProject.wsgi:application
home = /home/dataviz_user/.venv
env = DJANGO_SETTINGS_MODULE=DataVizProject.settings_prod

master = true
processes = 2
threads = 2

socket = /home/dataviz_user/uwsgi.sock
chmod-socket = 660
chown-socket = dataviz_user:www-data
vacuum = true
die-on-term = true

daemonize = /home/dataviz_user/dataviz.log
pidfile = /home/dataviz_user/dataviz.pid
```

Start:

```bash
uwsgi --ini uwsgi.ini
```

---

# Step 8: Configure Nginx

Create conf:

```bash
sudo nano /etc/nginx/conf.d/dataviz.conf
```

Add:

```nginx
server {
    listen 80;
    server_name dataviz.abidnexus.com 168.231.80.98;

    location / {
        include uwsgi_params;
        uwsgi_pass unix:/home/dataviz_user/uwsgi.sock;
    }

    location /static/ {
        alias /home/dataviz_user/Data-Analysis-Visualization/staticfiles/;
    }

    location /media/ {
        alias /home/dataviz_user/Data-Analysis-Visualization/media/;
    }
}
```

Test & reload:

```bash
sudo nginx -t
sudo systemctl restart nginx
```

---

# Step 9: Enable SSL (Certbot)

Install:

```bash
sudo apt install certbot python3-certbot-nginx -y
```

Generate SSL:

```bash
sudo certbot --nginx -d dataviz.abidnexus.com
```

---

# Step 10: Auto Update Script (Cron Job)

Create:

```bash
sudo su - dataviz_user
nano update_app.sh
```

Add:

```bash
#!/bin/bash
LOG_FILE="/home/dataviz_user/update_app.log"

echo "$(date): Updating app..." >> $LOG_FILE

cd /home/dataviz_user/Data-Analysis-Visualization
git pull origin main >> $LOG_FILE 2>&1

pip install -r requirements.txt >> $LOG_FILE 2>&1

cd DataVizProject
export DJANGO_SETTINGS_MODULE=DataVizProject.settings_prod
python manage.py migrate >> $LOG_FILE 2>&1
python manage.py collectstatic --noinput >> $LOG_FILE 2>&1

uwsgi --reload /home/dataviz_user/dataviz.pid
```

Make executable:

```bash
chmod +x update_app.sh
```

Cron job:

```bash
crontab -e
```

Add:

```
0 2 * * * /home/dataviz_user/update_app.sh
```

---

# Deployment Completed

Visit:

* **[https://dataviz.abidnexus.com](https://dataviz.abidnexus.com)**
* **[https://dataviz.abidnexus.com/admin](https://dataviz.abidnexus.com/admin)**

```

---

If you want this **as a downloadable .md file**, I can generate it for you as an attachment.
```
