# Deploying Apply Track to a Linux server

This puts the app on the public internet at its own HTTPS address, as a demo anyone can click through. It was written for an Ubuntu 24.04 server that already runs Apache and has a working Let's Encrypt setup, and it adds Apply Track beside whatever else is on that machine without touching it.

```
browser ──HTTPS──> Apache (certificate, proxy) ──> gunicorn on 127.0.0.1:8001 ──> Django + SQLite
                                                   (systemd keeps it running)     (/var/lib/applytrack)
```

gunicorn listens on the loopback address only, so the app can't be reached except through Apache, and no new firewall ports are needed.

| What | Where |
|---|---|
| Code | `/opt/applytrack` (owned by your login user) |
| Settings and secrets | `/etc/applytrack.env` (owner root, group `www-data`, mode 640) |
| Database, cache, reset log | `/var/lib/applytrack` (writable only by `www-data`) |
| Service | `/etc/systemd/system/applytrack.service` |
| Apache site | `/etc/apache2/sites-available/applytrack.conf` |

Run the commands one at a time, and check each one worked before the next. All of them are run from `/opt/applytrack` unless stated.

## Read this first

- **This is a demo, not a place for real data.** The demo login is public, and visitors can add, edit and delete records, including the shared company list. The nightly reset in step 10 wipes all of that. Don't keep your real job search in the same instance: companies are shared between users, so a visitor could see names you added.
- **Choose a strong password for the admin account** in step 6. `/admin/` is on the public internet.
- The app refuses to start with `DJANGO_DEBUG=False` unless `DJANGO_SECRET_KEY` is a real key. That is deliberate. The development key is in the public repository, and anyone who knows the key can forge a login token.

## 1. A name that points at the server

You need a hostname that resolves to the server's public IP, for example a free subdomain from DuckDNS, or a record on a domain you own. Create it and confirm it resolves:

```
nslookup applytrack.duckdns.org
```

It should print your server's IP address. Then set the name once for the rest of the session. **If your SSH session drops, set it again.**

```
HOST=applytrack.duckdns.org
```

## 2. Install what's needed

```
sudo apt update
```
```
sudo apt install -y python3-venv python3-pip git apache2 certbot python3-certbot-apache
```

## 3. Get the code

```
sudo mkdir -p /opt/applytrack
```
```
sudo chown $USER:$USER /opt/applytrack
```
```
git clone https://github.com/akachukwuchukwu/apply-track.git /opt/applytrack
```
```
cd /opt/applytrack
```

## 4. Python environment

```
python3 -m venv .venv
```
```
.venv/bin/pip install -r requirements-prod.txt
```

It should end with `Successfully installed ...`, including `gunicorn` and `Django`.

## 5. Data folders

The service runs as `www-data`, which can write only here, never to the code.

```
sudo install -d -o www-data -g www-data -m 750 /var/lib/applytrack
```
```
sudo install -d -o www-data -g www-data /opt/applytrack/staticfiles
```

## 6. Settings and the first run

Generate a secret key and write the environment file, without opening an editor. The key is generated and written in one step, so you never see or paste it:

```
SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
```
```
sed -e "s|__HOST__|$HOST|g" -e "s|__SECRET_KEY__|$SECRET|" deploy/applytrack.env.example | sudo tee /etc/applytrack.env > /dev/null
```
```
sudo chown root:www-data /etc/applytrack.env
```
```
sudo chmod 640 /etc/applytrack.env
```

Check that no placeholders were left behind (the answer must be `0`):

```
sudo grep -c "__" /etc/applytrack.env
```

From here on, use `deploy/manage.sh` instead of `python manage.py`. It runs the command as `www-data` with the production settings, so the database file always gets the right owner.

```
bash deploy/manage.sh migrate
```
```
bash deploy/manage.sh collectstatic --noinput
```
```
bash deploy/manage.sh seed_demo_data
```
```
bash deploy/manage.sh createsuperuser
```

## 7. Start the service

```
sudo cp deploy/applytrack.service /etc/systemd/system/applytrack.service
```
```
sudo systemctl daemon-reload
```
```
sudo systemctl enable --now applytrack
```
```
sudo systemctl status applytrack --no-pager
```

You want `active (running)`. Then check that gunicorn answers locally. The `Host` header matters, because the app only answers to the names in `DJANGO_ALLOWED_HOSTS`:

```
curl -s -o /dev/null -w "%{http_code}\n" -H "Host: $HOST" http://127.0.0.1:8001/
```

Expected: `200`.

## 8. Put Apache in front

```
sudo a2enmod proxy proxy_http headers
```
```
sed "s|__HOST__|$HOST|g" deploy/apache-applytrack.conf | sudo tee /etc/apache2/sites-available/applytrack.conf > /dev/null
```
```
sudo a2ensite applytrack
```
```
sudo apache2ctl configtest
```

It must say `Syntax OK`. Then:

```
sudo systemctl reload apache2
```

## 9. HTTPS

```
sudo certbot --apache -d $HOST
```

If it asks whether to redirect HTTP to HTTPS, choose the redirect. Certbot copies the proxy settings into a new HTTPS site for you.

Now open `https://<your host>/` in a browser, click **Fill demo account**, and sign in. Then open `/admin/` and sign in with the account you created in step 6.

## 10. Reset the demo every night

```
sudo cp deploy/applytrack-demo-reset.cron /etc/cron.d/applytrack-demo-reset
```
```
sudo chmod 644 /etc/cron.d/applytrack-demo-reset
```

Try the command once by hand to see it work:

```
bash deploy/manage.sh reset_demo_data --yes
```

## Updating later

```
cd /opt/applytrack
```
```
git pull
```
```
.venv/bin/pip install -r requirements-prod.txt
```
```
bash deploy/manage.sh migrate
```
```
bash deploy/manage.sh collectstatic --noinput
```
```
sudo systemctl restart applytrack
```

The database lives outside the code folder, so a `git pull` can never overwrite it.

## When something is wrong

First look: `sudo systemctl status applytrack --no-pager` and `sudo journalctl -u applytrack -n 50 --no-pager`.

| What you see | Likely cause |
|---|---|
| **503 Service Unavailable** from Apache | gunicorn isn't running. Check the service status and journal. |
| **400 Bad Request** on every page | The host name isn't in `DJANGO_ALLOWED_HOSTS` in `/etc/applytrack.env`. |
| The service won't start and the journal says `DJANGO_SECRET_KEY must be set` | The env file is missing, still contains placeholders, or `www-data` can't read it. Check `sudo grep -c "__" /etc/applytrack.env` and the owner and mode from step 6. |
| **403 CSRF verification failed** on the admin login | `DJANGO_CSRF_TRUSTED_ORIGINS` must be `https://` plus your exact host name. |
| Admin pages have no styling | `collectstatic` wasn't run, or `/opt/applytrack/staticfiles` isn't owned by `www-data`. |
| `attempt to write a readonly database` | `/var/lib/applytrack` or the database file isn't writable by `www-data`. Re-run the `install -d` command in step 5 and `sudo chown -R www-data:www-data /var/lib/applytrack`. |
| Everyone gets **429 Too Many Requests** on login | Rate limiting sees all visitors as one address. `DJANGO_NUM_PROXIES` must be `1` behind Apache. |
| Certbot says it couldn't validate the domain | The name doesn't point at this server yet, or port 80 is blocked in the cloud firewall or the host firewall. |
| You changed `/etc/applytrack.env` and nothing changed | The service reads it only at start: `sudo systemctl restart applytrack`. |

## Optional hardening, once HTTPS works

Two more settings, both off by default and set in `/etc/applytrack.env`:

- `DJANGO_SSL_REDIRECT=True` makes Django itself redirect any plain-HTTP request. Apache already does this, so it's belt and braces. The local check in step 7 will then return `301` unless you add `-H "X-Forwarded-Proto: https"`.
- `DJANGO_HSTS_SECONDS=3600` tells browsers to refuse plain HTTP for that long. Raise it only when you're sure the domain and certificate will stay put, because it's hard to undo.

Restart the service after changing either one.
