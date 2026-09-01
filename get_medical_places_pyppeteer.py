import asyncio
import subprocess
import os
from pyppeteer import launch
import json

API_KEY = "AIzaSyC8COgFCyVzK5lDTEqp__tEGkTqRPnIjkM"
SPOOFED_REFERER = "https://www.agoda.com/"
SEARCH_QUERY = "medical clinics hospitals Philippines"

# Try to find Chromium automatically
def find_chromium():
    possible_paths = [
        "/data/data/com.termux/files/usr/bin/chromium",
        "/data/data/com.termux/files/usr/bin/chromium-browser",
        "/data/data/com.termux/files/usr/lib/chromium/chromium",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    # Try 'which' command
    try:
        result = subprocess.run(["which", "chromium"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    raise RuntimeError("Chromium not found. Please install chromium via 'pkg install chromium' or set CHROMIUM_PATH env variable.")

CHROMIUM_PATH = os.environ.get("CHROMIUM_PATH") or find_chromium()
print(f"ℹ️ Using Chromium at: {CHROMIUM_PATH}")

async def main():
    browser = await launch(
        headless=True,
        executablePath=CHROMIUM_PATH,
        args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu']
    )
    page = await browser.newPage()
    await page.setExtraHTTPHeaders({'Referer': SPOOFED_REFERER})

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Medical Places Search</title>
        <script async defer
            src="https://maps.googleapis.com/maps/api/js?key={API_KEY}&libraries=places&callback=initMap">
        </script>
        <script>
            let map, service;
            function initMap() {{
                map = new google.maps.Map(document.createElement('div'), {{
                    center: {{lat: 12.8797, lng: 121.7740}},
                    zoom: 6
                }});
                service = new google.maps.places.PlacesService(map);
                const request = {{
                    query: '{SEARCH_QUERY}',
                    fields: ['name', 'formatted_address', 'geometry', 'rating', 'place_id', 'types'],
                }};
                service.textSearch(request, (results, status) => {{
                    if (status === google.maps.places.PlacesServiceStatus.OK) {{
                        const top = results.slice(0, 10);
                        document.getElementById('status').innerText = 'SUCCESS';
                        document.getElementById('results').innerText = JSON.stringify(top, null, 2);
                    }} else {{
                        document.getElementById('status').innerText = 'ERROR: ' + status;
                    }}
                }});
            }}
            window.initMap = initMap;
        </script>
    </head>
    <body>
        <div id="status">Loading...</div>
        <pre id="results" style="display: none;"></pre>
    </body>
    </html>
    """

    await page.setContent(html)

    # Wait for result
    await page.waitForFunction(
        """() => {
            const el = document.getElementById('status');
            return el && (el.innerText === 'SUCCESS' || el.innerText.startsWith('ERROR'));
        }""",
        timeout=15000
    )

    status = await page.evaluate('document.getElementById("status").innerText')
    if status == 'SUCCESS':
        data = await page.evaluate('JSON.parse(document.getElementById("results").innerText)')
        print(f"\n✅ Found {len(data)} medical facilities:\n")
        for i, place in enumerate(data, 1):
            print(f"{i}. {place['name']}")
            print(f"   Address: {place.get('formatted_address', 'N/A')}")
            if place.get('geometry'):
                loc = place['geometry']['location']
                print(f"   Location: {loc.get('lat')}, {loc.get('lng')}")
            if place.get('rating'):
                print(f"   Rating: {place['rating']}")
            print(f"   Place ID: {place.get('place_id')}")
            print(f"   Types: {', '.join(place.get('types', []))}")
            print("-" * 40)
    else:
        print(f"❌ Search failed: {status}")

    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
