# StoreSignal — Public Business Email Finder

A starter web app for checking user-supplied public store pages and collecting publicly listed business email addresses. It supports pasted store URLs, CSV upload, two shared page paths (defaults `/policies/privacy-policy` and `/pages/contact`), per-store `source_url` values, progress, and CSV/XLSX export.

## Run locally

1. Install Python 3.10 or newer.
2. Open a terminal in this folder.
3. Create and activate a virtual environment (recommended).
4. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

5. Start the server:

   ```bash
   python app.py
   ```

6. Open `http://127.0.0.1:5000` in your browser.

## CSV format

A CSV can contain a `store_url` column and an optional `source_url` column. Each `source_url` should be a page on that store's own domain; it is checked along with the other configured page. By default, both `/policies/privacy-policy` and `/pages/contact` are checked for each store. You can edit the two comma-separated paths in the UI. If a CSV includes `source_url`, that page is checked along with the other configured default page.

```csv
store_url,source_url
https://example-store.com,https://example-store.com/pages/contact
https://another-store.com,https://another-store.com/pages/contact-us
```

## Important limitations before production

- This is a local starter, not a deployed public website. It has no accounts, database, persistent jobs, or hosted URL yet.
- Jobs are held in memory and disappear when the server stops. Export results before restarting.
- Scanning respects `robots.txt` and avoids cross-domain source URLs/redirects; inaccessible pages are marked rather than bypassed. Some sites may block automated access.
- For production use, add a durable queue and database, stronger SSRF/network protections, authentication, per-domain rate limits, monitoring, retention controls, and review applicable privacy/anti-spam requirements.
- Only use this for publicly listed business contact information and appropriate outreach. Do not use it to collect private credentials or bypass technical restrictions.
