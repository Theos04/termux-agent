#!/usr/bin/env python3
"""
Auto-generated API client from HAR analysis
Generated: 2026-07-31T23:12:38.755736
Total Endpoints: 466
"""

import requests
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

logger = logging.getLogger(__name__)

class MyAPI:
    """Auto-generated API client from HAR analysis"""
    
    BASE_URL = 'https://fonts.gstatic.com'
    
    def __init__(self, 
                 token: Optional[str] = None,
                 api_key: Optional[str] = None,
                 session: Optional[requests.Session] = None,
                 **kwargs):
        """
        Initialize the API client
        
        Args:
            token: Bearer token for authentication
            api_key: API key for authentication
            session: Custom requests session
            **kwargs: Additional headers as keyword arguments
        """
        self.token = token
        self.api_key = api_key
        self.session = session or requests.Session()
        
        # Default headers
        self.default_headers = {
            "User-Agent": "APIClient/1.0",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        # Add common headers from HAR analysis
        self.default_headers['referer'] = 'https://static.zohocdn.com/helpcenter/asapweb/css/efc.eba5ee89309b92562659_.css'
        self.default_headers['user-agent'] = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36'
        self.default_headers['sec-ch-ua'] = '"Chromium";v="149", "Not)A;Brand";v="24"'
        self.default_headers['sec-ch-ua-mobile'] = '?0'
        self.default_headers['sec-ch-ua-platform'] = '"Linux"'
        
        # Add authentication
        if token:
            self.default_headers["Authorization"] = f"Bearer {token}"
        elif api_key:
            self.default_headers["X-API-Key"] = api_key
            
        # Custom headers
        for key, value in kwargs.items():
            if key.startswith('header_'):
                header_name = key.replace('header_', '')
                self.default_headers[header_name] = value
                
        self.session.headers.update(self.default_headers)
        
        # Rate limiting
        self.rate_limit = 50  # requests per second
        self.last_request_time = 0
        
    def _request(self, 
                 method: str, 
                 path: str,
                 params: Optional[Dict] = None,
                 json_data: Optional[Dict] = None,
                 **kwargs) -> Dict[str, Any]:
        """Make API request with error handling"""
        url = f"{self.BASE_URL}{path}"
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                **kwargs
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error: {e}")
            return {"error": str(e), "status_code": response.status_code}
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {e}")
            return {"error": str(e)}
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return {"error": "Invalid JSON response", "text": response.text[:200]}
            
    def _apply_rate_limit(self):
        """Apply rate limiting"""
        import time
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < 1.0 / self.rate_limit:
            time.sleep(1.0 / self.rate_limit - time_since_last)
        self.last_request_time = time.time()

    def get_syncframe(self, 
                          origin: Optional[str] = None,
                          topUrl: Optional[str] = None,
                          gdpr: Optional[str] = None,
                          gdpr_consent: Optional[str] = None,
                          gpp: Optional[str] = None,
                          gpp_sid: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        GET /syncframe
        
        Args:
            origin: Query parameter
            topUrl: Query parameter
            gdpr: Query parameter
            gdpr_consent: Query parameter
            gpp: Query parameter
            gpp_sid: Query parameter
        """
        params = {}
        if origin is not None:
            params["origin"] = origin
        if topUrl is not None:
            params["topUrl"] = topUrl
        if gdpr is not None:
            params["gdpr"] = gdpr
        if gdpr_consent is not None:
            params["gdpr_consent"] = gdpr_consent
        if gpp is not None:
            params["gpp"] = gpp
        if gpp_sid is not None:
            params["gpp_sid"] = gpp_sid
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/syncframe',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def options_script(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        OPTIONS /api/script
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='OPTIONS',
            path='/api/script',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_pcs_view(self, 
                          xai: Optional[str] = None,
                          sai: Optional[str] = None,
                          sig: Optional[str] = None,
                          uach_m: Optional[str] = None,
                          dett: Optional[str] = None,
                          adurl: Optional[str] = None,
                          urlfix: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        GET /pcs/view
        
        Args:
            xai: Query parameter
            sai: Query parameter
            sig: Query parameter
            uach_m: Query parameter
            dett: Query parameter
            adurl: Query parameter
            urlfix: Query parameter
        """
        params = {}
        if xai is not None:
            params["xai"] = xai
        if sai is not None:
            params["sai"] = sai
        if sig is not None:
            params["sig"] = sig
        if uach_m is not None:
            params["uach_m"] = uach_m
        if dett is not None:
            params["dett"] = dett
        if adurl is not None:
            params["adurl"] = adurl
        if urlfix is not None:
            params["urlfix"] = urlfix
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/pcs/view',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_pagead_gen_204(self, 
                          id: Optional[str] = None,
                          type: Optional[str] = None,
                          name: Optional[str] = None,
                          proto: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        GET /pagead/gen_204
        
        Args:
            id: Query parameter
            type: Query parameter
            name: Query parameter
            proto: Query parameter
        """
        params = {}
        if id is not None:
            params["id"] = id
        if type is not None:
            params["type"] = type
        if name is not None:
            params["name"] = name
        if proto is not None:
            params["proto"] = proto
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/pagead/gen_204',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_images_mc_homepage_brd_arwb_jpg(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /images/mc_homepage/brd_arwb.jpg
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/images/mc_homepage/brd_arwb.jpg',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_images_common_premium_crown_png(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /images/common/premium_crown.png
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/images/common/premium_crown.png',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def post_translator(self, 
                          source: Optional[str] = None,
                          gzip: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        POST /translator
        
        Args:
            source: Query parameter
            gzip: Query parameter
        """
        params = {}
        if source is not None:
            params["source"] = source
        if gzip is not None:
            params["gzip"] = gzip
        
        json_data = kwargs.get("json_data", {})
        # Add additional body parameters
        for key, value in kwargs.items():
            if key not in ["json_data"]:
                json_data[key] = value
        
        return self._request(
            method='POST',
            path='/translator',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_location(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /location
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/location',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def post_script(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        POST /api/script
        
        """
        params = {}
        
        json_data = kwargs.get("json_data", {})
        # Add additional body parameters
        for key, value in kwargs.items():
            if key not in ["json_data"]:
                json_data[key] = value
        
        return self._request(
            method='POST',
            path='/api/script',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_lato_v25(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/lato/v25/S6uyw4BMUTPHjxAwXjeu.woff2
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/lato/v25/S6uyw4BMUTPHjxAwXjeu.woff2',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def post_g_collect(self, 
                          v: Optional[str] = None,
                          tid: Optional[str] = None,
                          gtm: Optional[str] = None,
                          _p: Optional[str] = None,
                          gcs: Optional[str] = None,
                          gcd: Optional[str] = None,
                          npa: Optional[str] = None,
                          dma: Optional[str] = None,
                          tcfd: Optional[str] = None,
                          _eu: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        POST /g/collect
        
        Args:
            v: Query parameter
            tid: Query parameter
            gtm: Query parameter
            _p: Query parameter
            gcs: Query parameter
            gcd: Query parameter
            npa: Query parameter
            dma: Query parameter
            tcfd: Query parameter
            _eu: Query parameter
        """
        params = {}
        if v is not None:
            params["v"] = v
        if tid is not None:
            params["tid"] = tid
        if gtm is not None:
            params["gtm"] = gtm
        if _p is not None:
            params["_p"] = _p
        if gcs is not None:
            params["gcs"] = gcs
        if gcd is not None:
            params["gcd"] = gcd
        if npa is not None:
            params["npa"] = npa
        if dma is not None:
            params["dma"] = dma
        if tcfd is not None:
            params["tcfd"] = tcfd
        if _eu is not None:
            params["_eu"] = _eu
        
        json_data = kwargs.get("json_data", {})
        # Add additional body parameters
        for key, value in kwargs.items():
            if key not in ["json_data"]:
                json_data[key] = value
        
        return self._request(
            method='POST',
            path='/g/collect',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_pcs_activeview(self, 
                          xai: Optional[str] = None,
                          sai: Optional[str] = None,
                          sig: Optional[str] = None,
                          id: Optional[str] = None,
                          mcvt: Optional[str] = None,
                          p: Optional[str] = None,
                          tm: Optional[str] = None,
                          tu: Optional[str] = None,
                          mtos: Optional[str] = None,
                          tos: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        GET /pcs/activeview
        
        Args:
            xai: Query parameter
            sai: Query parameter
            sig: Query parameter
            id: Query parameter
            mcvt: Query parameter
            p: Query parameter
            tm: Query parameter
            tu: Query parameter
            mtos: Query parameter
            tos: Query parameter
        """
        params = {}
        if xai is not None:
            params["xai"] = xai
        if sai is not None:
            params["sai"] = sai
        if sig is not None:
            params["sig"] = sig
        if id is not None:
            params["id"] = id
        if mcvt is not None:
            params["mcvt"] = mcvt
        if p is not None:
            params["p"] = p
        if tm is not None:
            params["tm"] = tm
        if tu is not None:
            params["tu"] = tu
        if mtos is not None:
            params["mtos"] = mtos
        if tos is not None:
            params["tos"] = tos
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/pcs/activeview',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_f_agskwxwp_t5kojb4w3e6divegt2mkjjwcl_kjlkeopq7vqd8mzq27wwsexnwvn42opeabnbc0oi4slxi7rqbhetxpbkta3qehdircwnrh8hbuy43xdzryv7tmic_vz4bpcuaptnwiy9puskybid81l4iyexchxpjfrcmblbk221ri91gjr2otuzkvvis_nru_160x600(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /f/AGSKWxWP-t5kojb4W3E6DiVeGt2MkjjwCL-KjlKeOpQ7vQd8mZQ27wwseXnwvN42oPeAbnBc0oi4SlXI7RQBHEtXPBKTa3qEhdircWNRH8hBUY43XdZrYv7TMIc-Vz4bPcUAPtNwIy9puskYBID81l4IyExChXPjfrCMbLbK221rI91gjr2OTuZkVVis-NRU/__160x600./amazon/iframeproxy-_468x60b./adsbyfalcon./welcome_ad.
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/f/AGSKWxWP-t5kojb4W3E6DiVeGt2MkjjwCL-KjlKeOpQ7vQd8mZQ27wwseXnwvN42oPeAbnBc0oi4SlXI7RQBHEtXPBKTa3qEhdircWNRH8hBUY43XdZrYv7TMIc-Vz4bPcUAPtNwIy9puskYBID81l4IyExChXPjfrCMbLbK221rI91gjr2OTuZkVVis-NRU/__160x600./amazon/iframeproxy-_468x60b./adsbyfalcon./welcome_ad.',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def post_el_agskwxx4cqav3krk_s_2nmiuitxmaetmut3bc0hkwryuo8jdrhyfq5c4pqe9ustfisgtgdfq9tw0vb8kvgvlnqd4g4v_nfbktybmwhzgcx5pz3zhuc_uej_rvoo2hl1ocqf3_xgpo_2upa(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        POST /el/AGSKWxX4cQAv3KRK_s-2nmiUiTxMaEtMut3Bc0HkwRyuo8jdRHyFq5C4pqE9UsTfisGTgDfQ9tW0Vb8kVGvLnQD4g4V-nfBkTYBMwhZGCX5pz3zHuc-uEJ_rVoO2hL1ocqf3_xgpo_2upA==
        
        """
        params = {}
        
        json_data = kwargs.get("json_data", {})
        # Add additional body parameters
        for key, value in kwargs.items():
            if key not in ["json_data"]:
                json_data[key] = value
        
        return self._request(
            method='POST',
            path='/el/AGSKWxX4cQAv3KRK_s-2nmiUiTxMaEtMut3Bc0HkwRyuo8jdRHyFq5C4pqE9UsTfisGTgDfQ9tW0Vb8kVGvLnQD4g4V-nfBkTYBMwhZGCX5pz3zHuc-uEJ_rVoO2hL1ocqf3_xgpo_2upA==',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_pagead_js_lidar_js(self, 
                          fcd: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        GET /pagead/js/lidar.js
        
        Args:
            fcd: Query parameter
        """
        params = {}
        if fcd is not None:
            params["fcd"] = fcd
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/pagead/js/lidar.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_roboto_v51(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/roboto/v51/KFO7CnqEu92Fr1ME7kSn66aGLdTylUAMa3yUBA.woff2
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/roboto/v51/KFO7CnqEu92Fr1ME7kSn66aGLdTylUAMa3yUBA.woff2',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_f_agskwxukfrr264w3pyz2s3vrcvlg4xfja8zruchljyvjjxs1vm9xahkda_ju7raw14qr9ntjus54fjt0pnb4d0lliv3anzhlshzin0l1wnnv1jj5hmewwqkc_bf82famgsualwbrdejgzg(self, 
                          fccs: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        GET /f/AGSKWxUKFRR264w3PyZ2S3VRcvLG4xfjA8zRUchLjYvjJxs1vm9XAhkDa_ju7raW14qR9nTJus54fJt0PNB4D0llIv3anzhlshziN0L1wNnv1jj5hMEWWQKc_bf82FamgSUALwBRdEJgzg==
        
        Args:
            fccs: Query parameter
        """
        params = {}
        if fccs is not None:
            params["fccs"] = fccs
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/f/AGSKWxUKFRR264w3PyZ2S3VRcvLG4xfjA8zRUchLjYvjJxs1vm9XAhkDa_ju7raW14qR9nTJus54fJt0PNB4D0llIv3anzhlshziN0L1wNnv1jj5hMEWWQKc_bf82FamgSUALwBRdEJgzg==',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_assets_css_mclogin(self, 
                          v: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        GET /assets/css/mclogin/v2/auth_popup.css
        
        Args:
            v: Query parameter
        """
        params = {}
        if v is not None:
            params["v"] = v
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/assets/css/mclogin/v2/auth_popup.css',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_assets_css_mclogin(self, 
                          v: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        GET /assets/css/mclogin/bootstrap.min.css
        
        Args:
            v: Query parameter
        """
        params = {}
        if v is not None:
            params["v"] = v
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/assets/css/mclogin/bootstrap.min.css',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def post_network18media_moneycontrolenglish_trc_3(self, 
                          llvl: Optional[str] = None,
                          tim: Optional[str] = None,
                          lti: Optional[str] = None,
                          pubit: Optional[str] = None,
                          t: Optional[str] = None,
                          data: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        POST /network18media-moneycontrolenglish/trc/3/json
        
        Args:
            llvl: Query parameter
            tim: Query parameter
            lti: Query parameter
            pubit: Query parameter
            t: Query parameter
            data: Query parameter
        """
        params = {}
        if llvl is not None:
            params["llvl"] = llvl
        if tim is not None:
            params["tim"] = tim
        if lti is not None:
            params["lti"] = lti
        if pubit is not None:
            params["pubit"] = pubit
        if t is not None:
            params["t"] = t
        if data is not None:
            params["data"] = data
        
        json_data = kwargs.get("json_data", {})
        # Add additional body parameters
        for key, value in kwargs.items():
            if key not in ["json_data"]:
                json_data[key] = value
        
        return self._request(
            method='POST',
            path='/network18media-moneycontrolenglish/trc/3/json',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_f_agskwxxnxcenpygwukmiw1_vk1c3hninx8arayqnxqmaqruiyg6gjh1ofygb4ql_ukilaok9tuchtxfduym66abuj0zjbc33zhrt2ixn2xn1wq2ppgkbqtz9ukftiliqff_6buyj22gdzg(self, 
                          fccs: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        GET /f/AGSKWxXNxCeNPyGwukmiw1-vk1c3HNInX8ArAyqNXqMaQrUIyg6gjh1OfyGB4ql_UKIlaOk9TucHTXFDuYM66aBuj0zjbc33zhrT2ixn2xN1wQ2pPgKBqTZ9ukFTilIqff_6buYJ22GDzg==
        
        Args:
            fccs: Query parameter
        """
        params = {}
        if fccs is not None:
            params["fccs"] = fccs
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/f/AGSKWxXNxCeNPyGwukmiw1-vk1c3HNInX8ArAyqNXqMaQrUIyg6gjh1OfyGB4ql_UKIlaOk9TucHTXFDuYM66aBuj0zjbc33zhrT2ixn2xN1wQ2pPgKBqTZ9ukFTilIqff_6buYJ22GDzg==',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/c_crop%2Cf_jpg%2Cq_auto%2Ce_sharpen%2Car_1.7778%2Cw_1263%2Cx_93%2Cy_294/c_fill%2Cw_400%2Ch_223/http%3A//cdn.taboola.com/libtrc/static/thumbnails/STABLE_DIFFUSION_OUTCROP/ESD/5ab95377-2fe9-440d-b016-ddf16a8c1c56__29Rz0y4t.jpg
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/c_crop%2Cf_jpg%2Cq_auto%2Ce_sharpen%2Car_1.7778%2Cw_1263%2Cx_93%2Cy_294/c_fill%2Cw_400%2Ch_223/http%3A//cdn.taboola.com/libtrc/static/thumbnails/STABLE_DIFFUSION_OUTCROP/ESD/5ab95377-2fe9-440d-b016-ddf16a8c1c56__29Rz0y4t.jpg',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/c_crop%2Cf_jpg%2Cq_auto%2Ce_sharpen%2Car_1.7778%2Cw_1000%2Cx_0%2Cy_19/c_fill%2Cw_600%2Ch_334/https%3A//cdn.taboola.com/libtrc/static/thumbnails/80bd2b0b66f0ea033ea0ac2eee444622.jpg
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/c_crop%2Cf_jpg%2Cq_auto%2Ce_sharpen%2Car_1.7778%2Cw_1000%2Cx_0%2Cy_19/c_fill%2Cw_600%2Ch_334/https%3A//cdn.taboola.com/libtrc/static/thumbnails/80bd2b0b66f0ea033ea0ac2eee444622.jpg',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/c_crop%2Cf_jpg%2Cq_auto%2Ce_sharpen%2Car_1.7778%2Cw_1000%2Cx_0%2Cy_14/c_fill%2Cw_400%2Ch_223/https%3A//cdn.taboola.com/libtrc/static/thumbnails/7da148c4c72b9b6698c11d22c0f33d08.jpg
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/c_crop%2Cf_jpg%2Cq_auto%2Ce_sharpen%2Car_1.7778%2Cw_1000%2Cx_0%2Cy_14/c_fill%2Cw_400%2Ch_223/https%3A//cdn.taboola.com/libtrc/static/thumbnails/7da148c4c72b9b6698c11d22c0f33d08.jpg',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/d493bc5f3cf550e252cd36b43d787df7.png
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/d493bc5f3cf550e252cd36b43d787df7.png',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/h_334%2Cw_600%2Cb_auto,c_pad/https%3A//cdn.taboola.com/libtrc/static/thumbnails/bf3946417b508300f4e08e25747420b4.jpg
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/h_334%2Cw_600%2Cb_auto,c_pad/https%3A//cdn.taboola.com/libtrc/static/thumbnails/bf3946417b508300f4e08e25747420b4.jpg',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/http%3A//cdn.taboola.com/libtrc/static/thumbnails/a0d48ae6c82f296bf9083ec8de79ee06.jpg
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/http%3A//cdn.taboola.com/libtrc/static/thumbnails/a0d48ae6c82f296bf9083ec8de79ee06.jpg',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/h_223%2Cw_400%2Cb_auto,c_pad/https%3A//cdn.taboola.com/libtrc/static/thumbnails/d554956e98f5b9d2547f185c8941eba8.png
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/h_223%2Cw_400%2Cb_auto,c_pad/https%3A//cdn.taboola.com/libtrc/static/thumbnails/d554956e98f5b9d2547f185c8941eba8.png',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/c0aab05373abd72993ac606167367bb3.png
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/c0aab05373abd72993ac606167367bb3.png',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/f_jpg%2Cq_auto%2Ch_334%2Cw_600%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/4194b51ef6f09df446a53a7d0d936cfb.png
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_334%2Cw_600%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/4194b51ef6f09df446a53a7d0d936cfb.png',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/f_jpg%2Cq_auto%2Ch_334%2Cw_600%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/http%3A//cdn.taboola.com/libtrc/static/thumbnails/e189cf4ce19fa57a718aa2eca4c63b88.jpg
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_334%2Cw_600%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/http%3A//cdn.taboola.com/libtrc/static/thumbnails/e189cf4ce19fa57a718aa2eca4c63b88.jpg',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/http%3A//cdn.taboola.com/libtrc/static/thumbnails/4006a940471d532557dd9132f5100246.jpg
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/http%3A//cdn.taboola.com/libtrc/static/thumbnails/4006a940471d532557dd9132f5100246.jpg',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/da372deeec7746c771c4511f01fb55fd.png
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/da372deeec7746c771c4511f01fb55fd.png',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/96c23a4daa4de39867f7e63c5face716.png
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/96c23a4daa4de39867f7e63c5face716.png',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/h_334%2Cw_600%2Cc_pad,b_white/https%3A//cdn.taboola.com/libtrc/static/thumbnails/852a11587eea29f6ca2bd65651ea2722.jpg
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/h_334%2Cw_600%2Cc_pad,b_white/https%3A//cdn.taboola.com/libtrc/static/thumbnails/852a11587eea29f6ca2bd65651ea2722.jpg',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/h_334%2Cw_600%2Cc_pad,b_white/https%3A//cdn.taboola.com/libtrc/static/thumbnails/98a4bfad685ac65eb6635723e1b313b4.jpg
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/h_334%2Cw_600%2Cc_pad,b_white/https%3A//cdn.taboola.com/libtrc/static/thumbnails/98a4bfad685ac65eb6635723e1b313b4.jpg',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/25e620271d92576f3b90cde890383607.png
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/25e620271d92576f3b90cde890383607.png',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/5c09b982bbd2b4d1f482f000dcea0b94.png
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/5c09b982bbd2b4d1f482f000dcea0b94.png',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/6990daabc85127acc7789780a92bf9a2.png
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/6990daabc85127acc7789780a92bf9a2.png',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/f_jpg%2Cq_auto%2Ch_334%2Cw_600%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/32b04892958d19ad7b8aaff88098e8e1.jpeg
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_334%2Cw_600%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/32b04892958d19ad7b8aaff88098e8e1.jpeg',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/f_jpg%2Cq_auto%2Ch_334%2Cw_600%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/43ba0f68984d84a7a5a79c43e2d0f530.png
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_334%2Cw_600%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/43ba0f68984d84a7a5a79c43e2d0f530.png',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/f_jpg%2Cq_auto%2Ch_334%2Cw_600%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/http%3A//cdn.taboola.com/libtrc/static/thumbnails/939921ca216d45be30c1545a5ece05c9.jpg
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_334%2Cw_600%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/http%3A//cdn.taboola.com/libtrc/static/thumbnails/939921ca216d45be30c1545a5ece05c9.jpg',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/aefa9a6f9290d6416036915a018e384e.png
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/aefa9a6f9290d6416036915a018e384e.png',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/6c2152a54aa989f9bf7af7fc3affca16.jpeg
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/6c2152a54aa989f9bf7af7fc3affca16.jpeg',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/IMAGE_UPSCALER/EIU/0d9891cc-ebfd-4e2f-9617-7623f4a2e3e9__2TQUPgvn.jpg
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/IMAGE_UPSCALER/EIU/0d9891cc-ebfd-4e2f-9617-7623f4a2e3e9__2TQUPgvn.jpg',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_taboola_image_fetch(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /taboola/image/fetch/f_jpg%2Cq_auto%2Ch_334%2Cw_600%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/b8bad0f6fc71880343cb04217de4572b.png
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_334%2Cw_600%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/b8bad0f6fc71880343cb04217de4572b.png',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_portal_api_web(self, 
                          orgId: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        GET /portal/api/web/asapApp/13108000159188961
        
        Args:
            orgId: Query parameter
        """
        params = {}
        if orgId is not None:
            params["orgId"] = orgId
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/portal/api/web/asapApp/13108000159188961',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_js_clevertap_min_js(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /js/clevertap.min.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/js/clevertap.min.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def post_el_agskwxujq4zhglmv2grmgwd7cloqv9op1svqdyyjllzfyx6_q3kjwhlkczrg8vp1eqtrrtsqhrjbbdzu3witdbp61gppcr49waowdkoalrobinxwgk_rnasomv0t9i5lmrcpa_hp_4unwg(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        POST /el/AGSKWxUJq4ZHgLMV2GRmGwd7cLOqv9OP1svQDYyJLLZfyx6_q3kjwHlKczrG8VP1EQtrRtSqhRJbBdZU3WITdBp61gppCR49waOWdKoalRObInXWGK-rnASoMv0T9I5lmRcpA-hP-4UNwg==
        
        """
        params = {}
        
        json_data = kwargs.get("json_data", {})
        # Add additional body parameters
        for key, value in kwargs.items():
            if key not in ["json_data"]:
                json_data[key] = value
        
        return self._request(
            method='POST',
            path='/el/AGSKWxUJq4ZHgLMV2GRmGwd7cLOqv9OP1svQDYyJLLZfyx6_q3kjwHlKczrG8VP1EQtrRtSqhRJbBdZU3WITdBp61gppCR49waOWdKoalRObInXWGK-rnASoMv0T9I5lmRcpA-hP-4UNwg==',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_f_agskwxumk_s59xaknxmtyjvavf2ngh_mqlbnmyu4_ydppt6ye_x0mfcue7fn5qv3t43h_5ihouohruidsfrz_rtq7d6iw6lb85smtb1hsis19obainpzfz9nsirfuhfa8_enmjytlixlbq(self, 
                          fccs: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        GET /f/AGSKWxUmK-S59xaKNXMtYJVaVF2Ngh-MQLBnmYu4_ydPPT6yE-X0MFCue7fN5QV3T43H-5ihOUOhrUidSfRZ-Rtq7d6iw6LB85sMTB1hsiS19oBAINpzFZ9nsIrFuHfA8_enmJYtlIXLbQ==
        
        Args:
            fccs: Query parameter
        """
        params = {}
        if fccs is not None:
            params["fccs"] = fccs
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/f/AGSKWxUmK-S59xaKNXMtYJVaVF2Ngh-MQLBnmYu4_ydPPT6yE-X0MFCue7fN5QV3T43H-5ihOUOhrUidSfRZ-Rtq7d6iw6LB85sMTB1hsiS19oBAINpzFZ9nsIrFuHfA8_enmJYtlIXLbQ==',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    
    # Utility Methods
    
    def get_all_data(self, max_workers: int = 5) -> Dict[str, Any]:
        """Fetch data from all endpoints in parallel"""
        results = {}
        endpoints = [m for m in dir(self) if callable(getattr(self, m)) and m.startswith(('get_', 'post_', 'put_', 'delete_'))]
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                endpoint: executor.submit(getattr(self, endpoint))
                for endpoint in endpoints
            }
            
            for endpoint, future in futures.items():
                try:
                    results[endpoint] = future.result(timeout=30)
                except Exception as e:
                    results[endpoint] = {"error": str(e)}
                    
        return results
    
    def export_openapi(self) -> Dict[str, Any]:
        """Generate OpenAPI specification"""
        return {
            "openapi": "3.0.0",
            "info": {
                "title": "MyAPI API",
                "version": "1.0.0",
                "description": "Auto-generated from HAR analysis"
            },
            "servers": [{"url": self.BASE_URL}],
            "paths": {
                '/syncframe': {
                    'get': {
                        "summary": 'get_syncframe',
                        "parameters": [
                            {
                                "name": 'origin',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'topUrl',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'gdpr',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'gdpr_consent',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'gpp',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'gpp_sid',
                                "in": "query",
                                "schema": {"type": "string"}
                            }                        ]
                    }
                },                '/api/script': {
                    'options': {
                        "summary": 'options_script',
                        "parameters": [
                        ]
                    }
                },                '/pcs/view': {
                    'get': {
                        "summary": 'get_pcs_view',
                        "parameters": [
                            {
                                "name": 'xai',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'sai',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'sig',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'uach_m',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'dett',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'adurl',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'urlfix',
                                "in": "query",
                                "schema": {"type": "string"}
                            }                        ]
                    }
                },                '/pagead/gen_204': {
                    'get': {
                        "summary": 'get_pagead_gen_204',
                        "parameters": [
                            {
                                "name": 'id',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'type',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'name',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'proto',
                                "in": "query",
                                "schema": {"type": "string"}
                            }                        ]
                    }
                },                '/images/mc_homepage/brd_arwb.jpg': {
                    'get': {
                        "summary": 'get_images_mc_homepage_brd_arwb_jpg',
                        "parameters": [
                        ]
                    }
                },                '/images/common/premium_crown.png': {
                    'get': {
                        "summary": 'get_images_common_premium_crown_png',
                        "parameters": [
                        ]
                    }
                },                '/translator': {
                    'post': {
                        "summary": 'post_translator',
                        "parameters": [
                            {
                                "name": 'source',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'gzip',
                                "in": "query",
                                "schema": {"type": "string"}
                            }                        ]
                    }
                },                '/location': {
                    'get': {
                        "summary": 'get_location',
                        "parameters": [
                        ]
                    }
                },                '/api/script': {
                    'post': {
                        "summary": 'post_script',
                        "parameters": [
                        ]
                    }
                },                '/s/lato/v25/S6uyw4BMUTPHjxAwXjeu.woff2': {
                    'get': {
                        "summary": 'get_s_lato_v25',
                        "parameters": [
                        ]
                    }
                },                '/g/collect': {
                    'post': {
                        "summary": 'post_g_collect',
                        "parameters": [
                            {
                                "name": 'v',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'tid',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'gtm',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": '_p',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'gcs',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'gcd',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'npa',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'dma',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'tcfd',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": '_eu',
                                "in": "query",
                                "schema": {"type": "string"}
                            }                        ]
                    }
                },                '/pcs/activeview': {
                    'get': {
                        "summary": 'get_pcs_activeview',
                        "parameters": [
                            {
                                "name": 'xai',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'sai',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'sig',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'id',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'mcvt',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'p',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'tm',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'tu',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'mtos',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'tos',
                                "in": "query",
                                "schema": {"type": "string"}
                            }                        ]
                    }
                },                '/f/AGSKWxWP-t5kojb4W3E6DiVeGt2MkjjwCL-KjlKeOpQ7vQd8mZQ27wwseXnwvN42oPeAbnBc0oi4SlXI7RQBHEtXPBKTa3qEhdircWNRH8hBUY43XdZrYv7TMIc-Vz4bPcUAPtNwIy9puskYBID81l4IyExChXPjfrCMbLbK221rI91gjr2OTuZkVVis-NRU/__160x600./amazon/iframeproxy-_468x60b./adsbyfalcon./welcome_ad.': {
                    'get': {
                        "summary": 'get_f_agskwxwp_t5kojb4w3e6divegt2mkjjwcl_kjlkeopq7vqd8mzq27wwsexnwvn42opeabnbc0oi4slxi7rqbhetxpbkta3qehdircwnrh8hbuy43xdzryv7tmic_vz4bpcuaptnwiy9puskybid81l4iyexchxpjfrcmblbk221ri91gjr2otuzkvvis_nru_160x600',
                        "parameters": [
                        ]
                    }
                },                '/el/AGSKWxX4cQAv3KRK_s-2nmiUiTxMaEtMut3Bc0HkwRyuo8jdRHyFq5C4pqE9UsTfisGTgDfQ9tW0Vb8kVGvLnQD4g4V-nfBkTYBMwhZGCX5pz3zHuc-uEJ_rVoO2hL1ocqf3_xgpo_2upA==': {
                    'post': {
                        "summary": 'post_el_agskwxx4cqav3krk_s_2nmiuitxmaetmut3bc0hkwryuo8jdrhyfq5c4pqe9ustfisgtgdfq9tw0vb8kvgvlnqd4g4v_nfbktybmwhzgcx5pz3zhuc_uej_rvoo2hl1ocqf3_xgpo_2upa',
                        "parameters": [
                        ]
                    }
                },                '/pagead/js/lidar.js': {
                    'get': {
                        "summary": 'get_pagead_js_lidar_js',
                        "parameters": [
                            {
                                "name": 'fcd',
                                "in": "query",
                                "schema": {"type": "string"}
                            }                        ]
                    }
                },                '/s/roboto/v51/KFO7CnqEu92Fr1ME7kSn66aGLdTylUAMa3yUBA.woff2': {
                    'get': {
                        "summary": 'get_s_roboto_v51',
                        "parameters": [
                        ]
                    }
                },                '/f/AGSKWxUKFRR264w3PyZ2S3VRcvLG4xfjA8zRUchLjYvjJxs1vm9XAhkDa_ju7raW14qR9nTJus54fJt0PNB4D0llIv3anzhlshziN0L1wNnv1jj5hMEWWQKc_bf82FamgSUALwBRdEJgzg==': {
                    'get': {
                        "summary": 'get_f_agskwxukfrr264w3pyz2s3vrcvlg4xfja8zruchljyvjjxs1vm9xahkda_ju7raw14qr9ntjus54fjt0pnb4d0lliv3anzhlshzin0l1wnnv1jj5hmewwqkc_bf82famgsualwbrdejgzg',
                        "parameters": [
                            {
                                "name": 'fccs',
                                "in": "query",
                                "schema": {"type": "string"}
                            }                        ]
                    }
                },                '/assets/css/mclogin/v2/auth_popup.css': {
                    'get': {
                        "summary": 'get_assets_css_mclogin',
                        "parameters": [
                            {
                                "name": 'v',
                                "in": "query",
                                "schema": {"type": "string"}
                            }                        ]
                    }
                },                '/assets/css/mclogin/bootstrap.min.css': {
                    'get': {
                        "summary": 'get_assets_css_mclogin',
                        "parameters": [
                            {
                                "name": 'v',
                                "in": "query",
                                "schema": {"type": "string"}
                            }                        ]
                    }
                },                '/network18media-moneycontrolenglish/trc/3/json': {
                    'post': {
                        "summary": 'post_network18media_moneycontrolenglish_trc_3',
                        "parameters": [
                            {
                                "name": 'llvl',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'tim',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'lti',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'pubit',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 't',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'data',
                                "in": "query",
                                "schema": {"type": "string"}
                            }                        ]
                    }
                },                '/f/AGSKWxXNxCeNPyGwukmiw1-vk1c3HNInX8ArAyqNXqMaQrUIyg6gjh1OfyGB4ql_UKIlaOk9TucHTXFDuYM66aBuj0zjbc33zhrT2ixn2xN1wQ2pPgKBqTZ9ukFTilIqff_6buYJ22GDzg==': {
                    'get': {
                        "summary": 'get_f_agskwxxnxcenpygwukmiw1_vk1c3hninx8arayqnxqmaqruiyg6gjh1ofygb4ql_ukilaok9tuchtxfduym66abuj0zjbc33zhrt2ixn2xn1wq2ppgkbqtz9ukftiliqff_6buyj22gdzg',
                        "parameters": [
                            {
                                "name": 'fccs',
                                "in": "query",
                                "schema": {"type": "string"}
                            }                        ]
                    }
                },                '/taboola/image/fetch/c_crop%2Cf_jpg%2Cq_auto%2Ce_sharpen%2Car_1.7778%2Cw_1263%2Cx_93%2Cy_294/c_fill%2Cw_400%2Ch_223/http%3A//cdn.taboola.com/libtrc/static/thumbnails/STABLE_DIFFUSION_OUTCROP/ESD/5ab95377-2fe9-440d-b016-ddf16a8c1c56__29Rz0y4t.jpg': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/c_crop%2Cf_jpg%2Cq_auto%2Ce_sharpen%2Car_1.7778%2Cw_1000%2Cx_0%2Cy_19/c_fill%2Cw_600%2Ch_334/https%3A//cdn.taboola.com/libtrc/static/thumbnails/80bd2b0b66f0ea033ea0ac2eee444622.jpg': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/c_crop%2Cf_jpg%2Cq_auto%2Ce_sharpen%2Car_1.7778%2Cw_1000%2Cx_0%2Cy_14/c_fill%2Cw_400%2Ch_223/https%3A//cdn.taboola.com/libtrc/static/thumbnails/7da148c4c72b9b6698c11d22c0f33d08.jpg': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/d493bc5f3cf550e252cd36b43d787df7.png': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/h_334%2Cw_600%2Cb_auto,c_pad/https%3A//cdn.taboola.com/libtrc/static/thumbnails/bf3946417b508300f4e08e25747420b4.jpg': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/http%3A//cdn.taboola.com/libtrc/static/thumbnails/a0d48ae6c82f296bf9083ec8de79ee06.jpg': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/h_223%2Cw_400%2Cb_auto,c_pad/https%3A//cdn.taboola.com/libtrc/static/thumbnails/d554956e98f5b9d2547f185c8941eba8.png': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/c0aab05373abd72993ac606167367bb3.png': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_334%2Cw_600%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/4194b51ef6f09df446a53a7d0d936cfb.png': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_334%2Cw_600%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/http%3A//cdn.taboola.com/libtrc/static/thumbnails/e189cf4ce19fa57a718aa2eca4c63b88.jpg': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/http%3A//cdn.taboola.com/libtrc/static/thumbnails/4006a940471d532557dd9132f5100246.jpg': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/da372deeec7746c771c4511f01fb55fd.png': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/96c23a4daa4de39867f7e63c5face716.png': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/h_334%2Cw_600%2Cc_pad,b_white/https%3A//cdn.taboola.com/libtrc/static/thumbnails/852a11587eea29f6ca2bd65651ea2722.jpg': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/h_334%2Cw_600%2Cc_pad,b_white/https%3A//cdn.taboola.com/libtrc/static/thumbnails/98a4bfad685ac65eb6635723e1b313b4.jpg': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/25e620271d92576f3b90cde890383607.png': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/5c09b982bbd2b4d1f482f000dcea0b94.png': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/6990daabc85127acc7789780a92bf9a2.png': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_334%2Cw_600%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/32b04892958d19ad7b8aaff88098e8e1.jpeg': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_334%2Cw_600%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/43ba0f68984d84a7a5a79c43e2d0f530.png': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_334%2Cw_600%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/http%3A//cdn.taboola.com/libtrc/static/thumbnails/939921ca216d45be30c1545a5ece05c9.jpg': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/aefa9a6f9290d6416036915a018e384e.png': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/6c2152a54aa989f9bf7af7fc3affca16.jpeg': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_223%2Cw_400%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/IMAGE_UPSCALER/EIU/0d9891cc-ebfd-4e2f-9617-7623f4a2e3e9__2TQUPgvn.jpg': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/taboola/image/fetch/f_jpg%2Cq_auto%2Ch_334%2Cw_600%2Cc_fill%2Cg_faces:auto%2Ce_sharpen/https%3A//cdn.taboola.com/libtrc/static/thumbnails/b8bad0f6fc71880343cb04217de4572b.png': {
                    'get': {
                        "summary": 'get_taboola_image_fetch',
                        "parameters": [
                        ]
                    }
                },                '/portal/api/web/asapApp/13108000159188961': {
                    'get': {
                        "summary": 'get_portal_api_web',
                        "parameters": [
                            {
                                "name": 'orgId',
                                "in": "query",
                                "schema": {"type": "string"}
                            }                        ]
                    }
                },                '/js/clevertap.min.js': {
                    'get': {
                        "summary": 'get_js_clevertap_min_js',
                        "parameters": [
                        ]
                    }
                },                '/el/AGSKWxUJq4ZHgLMV2GRmGwd7cLOqv9OP1svQDYyJLLZfyx6_q3kjwHlKczrG8VP1EQtrRtSqhRJbBdZU3WITdBp61gppCR49waOWdKoalRObInXWGK-rnASoMv0T9I5lmRcpA-hP-4UNwg==': {
                    'post': {
                        "summary": 'post_el_agskwxujq4zhglmv2grmgwd7cloqv9op1svqdyyjllzfyx6_q3kjwhlkczrg8vp1eqtrrtsqhrjbbdzu3witdbp61gppcr49waowdkoalrobinxwgk_rnasomv0t9i5lmrcpa_hp_4unwg',
                        "parameters": [
                        ]
                    }
                },                '/f/AGSKWxUmK-S59xaKNXMtYJVaVF2Ngh-MQLBnmYu4_ydPPT6yE-X0MFCue7fN5QV3T43H-5ihOUOhrUidSfRZ-Rtq7d6iw6LB85sMTB1hsiS19oBAINpzFZ9nsIrFuHfA8_enmJYtlIXLbQ==': {
                    'get': {
                        "summary": 'get_f_agskwxumk_s59xaknxmtyjvavf2ngh_mqlbnmyu4_ydppt6ye_x0mfcue7fn5qv3t43h_5ihouohruidsfrz_rtq7d6iw6lb85smtb1hsis19obainpzfz9nsirfuhfa8_enmjytlixlbq',
                        "parameters": [
                            {
                                "name": 'fccs',
                                "in": "query",
                                "schema": {"type": "string"}
                            }                        ]
                    }
                }            }
        }

# Example usage
if __name__ == "__main__":
    # Initialize client
    client = MyAPI(token="your_token_here")
    
    # Example: Fetch data from all endpoints
    # all_data = client.get_all_data()
    # print(json.dumps(all_data, indent=2))
    
    print("API Client Generated Successfully!")
    print(f"Base URL: {client.BASE_URL}")
    print(f"Available methods: {[m for m in dir(client) if callable(getattr(client, m)) and not m.startswith('_')]}")