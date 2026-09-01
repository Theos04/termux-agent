from scraper_framework.storage.google_sheets import GoogleSheetsStorage

storage = GoogleSheetsStorage("default")
results = storage.get_results("indeed_jobs", limit=5)
print(f"Found {len(results)} results")
for r in results:
    print(r)
