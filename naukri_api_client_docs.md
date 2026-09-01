# API from HAR Analysis

**Generated from HAR analysis on 2026-08-02 14:55:35**

## Overview

- **Base URL**: `https://img.naukimg.com`
- **Total Endpoints**: 274
- **Authentication**: BEARER

## Authentication

- **Type**: BEARER
- **Header**: `Authorization`

## Common Headers

- `user-agent`: `Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36...`
- `sec-ch-ua`: `"Chromium";v="149", "Not)A;Brand";v="24"`
- `sec-ch-ua-mobile`: `?0`
- `sec-ch-ua-platform`: `"Linux"`
- `referer`: `https://www.naukri.com/`

## Endpoints

### GET Methods (260)

| Path | Frequency | Query Params |
|------|-----------|--------------|
| `/mnjuser/homepage` | 1 |  |
| `/s/9/105/_next/static/chunks/webpack-98e018d7172db6f5.js` | 1 |  |
| `/s/9/105/_next/static/chunks/main-app-e7ed7af89c05b048.js` | 1 |  |
| `/s/9/105/_next/static/chunks/8139-c0e2d93233a1284f.js` | 1 |  |
| `/akam/13/3ce348e8` | 1 |  |
| `/s/9/105/_next/static/chunks/2443530c-05f5f9c36d9c0116.js` | 1 |  |
| `/s/9/105/_next/static/css/c336e61763b75ee6.css` | 1 |  |
| `/s/9/105/_next/static/css/2672c06d114cdca9.css` | 1 |  |
| `/s/9/105/_next/static/css/7ac4a6950080226a.css` | 1 |  |
| `/s/9/105/_next/static/css/2bc43d26759e2966.css` | 1 |  |
| `/s/9/105/_next/static/css/510d7db3becc8c35.css` | 1 |  |
| `/s/9/105/_next/static/css/58d48825c3950e2f.css` | 1 |  |
| `/s/9/105/_next/static/chunks/fac3a283-5be48d7829be91b5.js` | 1 |  |
| `/s/9/105/_next/static/chunks/2435-10acfd04b1985d7e.js` | 1 |  |
| `/s/9/105/_next/static/chunks/8940-3d6fc7d7063ec781.js` | 1 |  |
| `/s/9/105/_next/static/chunks/5469-2fcd77d0a70a2abf.js` | 1 |  |
| `/s/9/105/_next/static/chunks/325-e40e8199495baf76.js` | 1 |  |
| `/s/9/105/_next/static/chunks/6394-c68cffa6ce9625fb.js` | 1 |  |
| `/s/9/105/_next/static/chunks/4224-ceb3c883028a84c4.js` | 1 |  |
| `/s/9/105/_next/static/chunks/app/layout-47b460cbe6b487db.js` | 1 |  |
| ... and 240 more | | |

### POST Methods (14)

| Path | Frequency | Query Params |
|------|-----------|--------------|
| `/akam/13/pixel_3ce348e8` | 1 |  |
| `/cloudgateway-nc-js/nc-services/v0/template/ni-inbox-mail-widget-svc-tmpl_v0` | 1 |  |
| `/jobapi/v2/search/recom-jobs` | 5 |  |
| `/uba` | 34 |  |
| `/cloudgateway-nc-js/nc-services/v0/template/ni-inboxusermails-svc-tmpl_v0` | 1 |  |
| `/cloudgateway-ccs/inventory-management-services/v2/page/pagename/ni-desktop-dashboard-v2` | 1 | partial, rules, sync |
| `/ccm/s/collect` | 1 | auid, gtm |
| `/rmkt/collect/854187457/` | 2 | random, cv, fst, fmt, bg... |
| `/ccm/collect` | 4 | rcb, frm, auid, dt, en... |
| `/rmkt/collect/10857553821/` | 2 | random, cv, fst, fmt, bg... |
| `/collectorapi/v1/uba/bulk` | 3 |  |
| `/g/collect` | 3 | v, tid, gtm, _p, gcd... |
| `/cloudgateway-ccs/inventory-management-services/v2/page/pagename/ni-desktop-reco-v2` | 5 | partial, rules, sync |
| `/cloudgateway-mynaukri/jobseeker-follow-services/v0/users/self/companygroups-follow-status` | 1 |  |

## Usage Example

```python
from moneycontrol_client import MoneyControlAPI

# Initialize client
client = MoneyControlAPI(token='your_token_here')

# Get all data
# data = client.get_all_data()

# Or call specific endpoints
# result = client.get_syncframe()
```

## Notes

- This client was auto-generated from HAR analysis
- Some endpoints may require authentication
- Rate limiting may apply to API calls
- Check the actual API documentation for detailed parameters