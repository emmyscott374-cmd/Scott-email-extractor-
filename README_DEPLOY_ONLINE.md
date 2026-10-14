# StoreSignal — Put the website online (no Python installation on your laptop)

This is a web app with a server-side scanner. Python is used by the hosting server, not installed or run by you locally.

## Easiest available route: GitHub + Render

You will need free accounts on GitHub and Render. Render's free web services can sleep after inactivity and may take about a minute to wake up. This starter is suitable for testing, not high-volume production use.

### 1. Create a GitHub repository
1. Open https://github.com/new and sign in or create an account.
2. Repository name: `storesignal-email-finder`.
3. Choose **Public** (needed for the simplest Render setup) and click **Create repository**.
4. In the new repository, choose **Add file → Upload files**.
5. Open the `shopify_email_finder` folder from this ZIP on your laptop and upload the *contents* of that folder, not the outer folder itself. Include `app.py`, `requirements.txt`, `render.yaml`, `Procfile`, `templates/`, and the README files. If uploading a folder is awkward, upload `app.py`, `requirements.txt`, `render.yaml`, `Procfile`, then upload `templates/index.html` by creating the `templates` folder in GitHub first.
6. Click **Commit changes**.

### 2. Deploy on Render
1. Open https://render.com/ and sign up.
2. Choose **New → Web Service** and connect GitHub if prompted.
3. Select `storesignal-email-finder`.
4. Render should read `render.yaml`. If asked for settings, use:
   - Runtime: Python
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120`
   - Plan: Free
5. Click **Deploy Web Service** and wait for the build to finish.
6. Open the `onrender.com` URL Render gives you. That is your website link.

## What it does
- Accepts pasted store URLs and CSV uploads.
- Checks `/policies/privacy-policy` and `/pages/contact` by default.
- Finds publicly listed email addresses, deduplicates them, records source URLs/status, and exports CSV/XLSX.
- Does not bypass logins, CAPTCHA, access controls, or robots.txt restrictions. Some shops may block automated requests or not list an email.

## Important limitations
- A free Render service may sleep after 15 minutes without traffic and take about a minute to wake.
- The app's current job results are held in memory and can be lost when the service restarts. Download your results when each scan completes.
- Scanning 500–2,000 stores can take a long time and may be interrupted by hosting timeouts or store rate limits. This starter is not yet a robust background-job production system. For reliable large batches, it needs a persistent job queue, job storage, per-domain rate limits, and monitoring.
- Only collect public business contact information and use it responsibly in line with applicable privacy and anti-spam rules.
