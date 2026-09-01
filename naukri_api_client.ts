/**
 * Auto-generated TypeScript API client from HAR analysis
 * Generated: 2026-08-02T14:55:33.864181
 * Total Endpoints: 274
 */

interface RequestOptions {
  headers?: Record<string, string>;
  params?: Record<string, string>;
  body?: any;
}

class APIError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public data?: any
  ) {
    super(`API Error: ${status} ${statusText}`);
    this.name = 'APIError';
  }
}

export class NaukriAPIClient {
  private baseURL: string = 'https://img.naukimg.com';
  private defaultHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'User-Agent': 'APIClient/1.0'
  };
  private token?: string;
  private apiKey?: string;

  constructor(options: {
    token?: string;
    apiKey?: string;
    baseURL?: string;
    headers?: Record<string, string>;
  } = {}) {
    if (options.token) {
      this.token = options.token;
      this.defaultHeaders['Authorization'] = `Bearer ${options.token}`;
    }
    if (options.apiKey) {
      this.apiKey = options.apiKey;
      this.defaultHeaders['X-API-Key'] = options.apiKey;
    }
    if (options.baseURL) {
      this.baseURL = options.baseURL;
    }
    if (options.headers) {
      this.defaultHeaders = { ...this.defaultHeaders, ...options.headers };
    }
  }

  private async request<T = any>(
    method: string,
    path: string,
    options: RequestOptions = {}
  ): Promise<T> {
    const url = `${this.baseURL}${path}`;
    const headers = { ...this.defaultHeaders, ...options.headers };

    // Build query string
    let queryString = '';
    if (options.params) {
      const params = new URLSearchParams();
      for (const [key, value] of Object.entries(options.params)) {
        if (value !== undefined && value !== null) {
          params.append(key, String(value));
        }
      }
      queryString = params.toString() ? `?${params.toString()}` : '';
    }

    const init: RequestInit = {
      method,
      headers,
    };

    if (options.body) {
      init.body = JSON.stringify(options.body);
    }

    try {
      const response = await fetch(`${url}${queryString}`, init);
      
      if (!response.ok) {
        let errorData;
        try {
          errorData = await response.json();
        } catch {
          errorData = undefined;
        }
        throw new APIError(response.status, response.statusText, errorData);
      }

      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        return await response.json();
      }
      
      return await response.text() as any;
    } catch (error) {
      if (error instanceof APIError) {
        throw error;
      }
      throw new Error(`Request failed: ${error.message}`);
    }
  }

  /**
   * GET /mnjuser/homepage
   */
  async get_mnjuser_homepage(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/mnjuser/homepage',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/chunks/webpack-98e018d7172db6f5.js
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/chunks/webpack-98e018d7172db6f5.js',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/chunks/main-app-e7ed7af89c05b048.js
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/chunks/main-app-e7ed7af89c05b048.js',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/chunks/8139-c0e2d93233a1284f.js
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/chunks/8139-c0e2d93233a1284f.js',
      {
        ...options
      }
    );
  }
  /**
   * GET /akam/13/3ce348e8
   */
  async get_akam_13_3ce348e8(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/akam/13/3ce348e8',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/chunks/2443530c-05f5f9c36d9c0116.js
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/chunks/2443530c-05f5f9c36d9c0116.js',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/css/c336e61763b75ee6.css
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/css/c336e61763b75ee6.css',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/css/2672c06d114cdca9.css
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/css/2672c06d114cdca9.css',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/css/7ac4a6950080226a.css
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/css/7ac4a6950080226a.css',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/css/2bc43d26759e2966.css
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/css/2bc43d26759e2966.css',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/css/510d7db3becc8c35.css
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/css/510d7db3becc8c35.css',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/css/58d48825c3950e2f.css
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/css/58d48825c3950e2f.css',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/chunks/fac3a283-5be48d7829be91b5.js
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/chunks/fac3a283-5be48d7829be91b5.js',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/chunks/2435-10acfd04b1985d7e.js
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/chunks/2435-10acfd04b1985d7e.js',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/chunks/8940-3d6fc7d7063ec781.js
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/chunks/8940-3d6fc7d7063ec781.js',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/chunks/5469-2fcd77d0a70a2abf.js
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/chunks/5469-2fcd77d0a70a2abf.js',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/chunks/325-e40e8199495baf76.js
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/chunks/325-e40e8199495baf76.js',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/chunks/6394-c68cffa6ce9625fb.js
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/chunks/6394-c68cffa6ce9625fb.js',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/chunks/4224-ceb3c883028a84c4.js
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/chunks/4224-ceb3c883028a84c4.js',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/chunks/app/layout-47b460cbe6b487db.js
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/chunks/app/layout-47b460cbe6b487db.js',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/chunks/app/mnjuser/homepage/error-4ba54ae51df7f94f.js
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/chunks/app/mnjuser/homepage/error-4ba54ae51df7f94f.js',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/chunks/app/mnjuser/homepage/page-c1cf2614aa81e776.js
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/chunks/app/mnjuser/homepage/page-c1cf2614aa81e776.js',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/0/0/i/transparentImg.png
   */
  async get_s_0(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/0/0/i/transparentImg.png',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/0/0/c/fonts/static/satoshi/KFIAZD4RUMEZIYV6FQ3T3GP5PDBDB6JY.woff2
   */
  async get_s_0(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/0/0/c/fonts/static/satoshi/KFIAZD4RUMEZIYV6FQ3T3GP5PDBDB6JY.woff2',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/0/0/c/fonts/static/satoshi/7AHDUZ4A7LFLVFUIFSARGIWCRQJHISQP.woff2
   */
  async get_s_0(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/0/0/c/fonts/static/satoshi/7AHDUZ4A7LFLVFUIFSARGIWCRQJHISQP.woff2',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/0/0/c/fonts/static/satoshi/GHM6WVH6MILNYOOCXHXB5GTSGNTMGXZR.woff2
   */
  async get_s_0(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/0/0/c/fonts/static/satoshi/GHM6WVH6MILNYOOCXHXB5GTSGNTMGXZR.woff2',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/0/0/c/fonts/static/satoshi/J64QX5IPOHK56I2KYUNBQ5M2XWZEYKYX.woff2
   */
  async get_s_0(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/0/0/c/fonts/static/satoshi/J64QX5IPOHK56I2KYUNBQ5M2XWZEYKYX.woff2',
      {
        ...options
      }
    );
  }
  /**
   * POST /akam/13/pixel_3ce348e8
   * @param body - Request body
   */
  async post_akam_13_pixel_3ce348e8(
    body?: any,
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'POST',
      '/akam/13/pixel_3ce348e8',
      {
        body: body,
        ...options
      }
    );
  }
  /**
   * GET /s/0/1/j/ub_v1.16.min.js
   */
  async get_s_0_1(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/0/1/j/ub_v1.16.min.js',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/0/0/j/nLoggerJB_v3.4.min.js
   */
  async get_s_0(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/0/0/j/nLoggerJB_v3.4.min.js',
      {
        ...options
      }
    );
  }
  /**
   * GET /favicon.ico
   */
  async get_favicon_ico(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/favicon.ico',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/chunks/1963.7d9d77914a8664cc.js
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/chunks/1963.7d9d77914a8664cc.js',
      {
        ...options
      }
    );
  }
  /**
   * GET /cloudgateway-mynaukri/resman-aggregator-services/v1/users/self/dashboard
   * @param params - Query parameters
   */
  async get_cloudgateway_mynaukri_resman_aggregator_services_v1(
    params: {
      properties?: string;
    } = {},
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/cloudgateway-mynaukri/resman-aggregator-services/v1/users/self/dashboard',
      {
        params: params,
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/chunks/1778.be1aabf1dc75b363.js
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/chunks/1778.be1aabf1dc75b363.js',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/chunks/647.9e6b82b3bbda979d.js
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/chunks/647.9e6b82b3bbda979d.js',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/assets/info.svg
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/assets/info.svg',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/assets/arrow.svg
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/assets/arrow.svg',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/assets/home.svg
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/assets/home.svg',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/assets/jobs.svg
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/assets/jobs.svg',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/assets/company.svg
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/assets/company.svg',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/assets/blog.svg
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/assets/blog.svg',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/7/0/j/widget-client-ni.min.js
   */
  async get_s_7_0(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/7/0/j/widget-client-ni.min.js',
      {
        ...options
      }
    );
  }
  /**
   * GET //uba
   * @param params - Query parameters
   */
  async get_uba(
    params: {
      data?: string;
      rad?: string;
    } = {},
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '//uba',
      {
        params: params,
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/chunks/tracking.4c548c0510ae6df1.js
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/chunks/tracking.4c548c0510ae6df1.js',
      {
        ...options
      }
    );
  }
  /**
   * GET /gtm.js
   * @param params - Query parameters
   */
  async get_gtm_js(
    params: {
      id?: string;
    } = {},
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/gtm.js',
      {
        params: params,
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/chunks/9813.fe6320f6733a0e9d.js
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/chunks/9813.fe6320f6733a0e9d.js',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/9/105/_next/static/chunks/4506.14ae4ffaecf6088e.js
   */
  async get_s_9_105(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/9/105/_next/static/chunks/4506.14ae4ffaecf6088e.js',
      {
        ...options
      }
    );
  }
  /**
   * GET /s/7/0/j/naukri-widget_v12.36-modern.min.js
   */
  async get_s_7_0(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/s/7/0/j/naukri-widget_v12.36-modern.min.js',
      {
        ...options
      }
    );
  }
  /**
   * GET /cloudgateway-mynaukri/resman-aggregator-services/v0/users/self/profiles/18e6c5f2b2d6f71cb1abe71e0a70ccc5c0234cac14d1dd83b679862093b973de/photo
   */
  async get_cloudgateway_mynaukri_resman_aggregator_services_v0(
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/cloudgateway-mynaukri/resman-aggregator-services/v0/users/self/profiles/18e6c5f2b2d6f71cb1abe71e0a70ccc5c0234cac14d1dd83b679862093b973de/photo',
      {
        ...options
      }
    );
  }
  /**
   * GET /cloudgateway-mynaukri/resman-aggregator-services/v2/users/self
   * @param params - Query parameters
   */
  async get_cloudgateway_mynaukri_resman_aggregator_services_v2(
    params: {
      expand_level?: string;
      properties?: string;
    } = {},
    options: Omit<RequestOptions, 'params' | 'body'> = {}
  ): Promise<any> {
    return this.request(
      'GET',
      '/cloudgateway-mynaukri/resman-aggregator-services/v2/users/self',
      {
        params: params,
        ...options
      }
    );
  }

  /**
   * Fetch data from all endpoints in parallel
   */
  async getAllData(maxWorkers: number = 5): Promise<Record<string, any>> {
    const methods = Object.getOwnPropertyNames(Object.getPrototypeOf(this))
      .filter(m => m.startsWith('get') && typeof this[m] === 'function');
    
    const results: Record<string, any> = {};
    const batchSize = maxWorkers;
    
    for (let i = 0; i < methods.length; i += batchSize) {
      const batch = methods.slice(i, i + batchSize);
      const promises = batch.map(async (method) => {
        try {
          results[method] = await this[method]();
        } catch (error) {
          results[method] = { error: error.message };
        }
      });
      await Promise.all(promises);
    }
    
    return results;
  }

  /**
   * Generate OpenAPI specification
   */
  toOpenAPI(): Record<string, any> {
    return {
      openapi: '3.0.0',
      info: {
        title: 'NaukriAPIClient API',
        version: '1.0.0',
        description: 'Auto-generated from HAR analysis'
      },
      servers: [{ url: this.baseURL }],
      paths: {
        '/mnjuser/homepage': {
          'get': {
            summary: 'get_mnjuser_homepage',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/chunks/webpack-98e018d7172db6f5.js': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/chunks/main-app-e7ed7af89c05b048.js': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/chunks/8139-c0e2d93233a1284f.js': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/akam/13/3ce348e8': {
          'get': {
            summary: 'get_akam_13_3ce348e8',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/chunks/2443530c-05f5f9c36d9c0116.js': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/css/c336e61763b75ee6.css': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/css/2672c06d114cdca9.css': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/css/7ac4a6950080226a.css': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/css/2bc43d26759e2966.css': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/css/510d7db3becc8c35.css': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/css/58d48825c3950e2f.css': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/chunks/fac3a283-5be48d7829be91b5.js': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/chunks/2435-10acfd04b1985d7e.js': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/chunks/8940-3d6fc7d7063ec781.js': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/chunks/5469-2fcd77d0a70a2abf.js': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/chunks/325-e40e8199495baf76.js': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/chunks/6394-c68cffa6ce9625fb.js': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/chunks/4224-ceb3c883028a84c4.js': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/chunks/app/layout-47b460cbe6b487db.js': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/chunks/app/mnjuser/homepage/error-4ba54ae51df7f94f.js': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/chunks/app/mnjuser/homepage/page-c1cf2614aa81e776.js': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/0/0/i/transparentImg.png': {
          'get': {
            summary: 'get_s_0',
            parameters: [
            ]
          }
        },        '/s/0/0/c/fonts/static/satoshi/KFIAZD4RUMEZIYV6FQ3T3GP5PDBDB6JY.woff2': {
          'get': {
            summary: 'get_s_0',
            parameters: [
            ]
          }
        },        '/s/0/0/c/fonts/static/satoshi/7AHDUZ4A7LFLVFUIFSARGIWCRQJHISQP.woff2': {
          'get': {
            summary: 'get_s_0',
            parameters: [
            ]
          }
        },        '/s/0/0/c/fonts/static/satoshi/GHM6WVH6MILNYOOCXHXB5GTSGNTMGXZR.woff2': {
          'get': {
            summary: 'get_s_0',
            parameters: [
            ]
          }
        },        '/s/0/0/c/fonts/static/satoshi/J64QX5IPOHK56I2KYUNBQ5M2XWZEYKYX.woff2': {
          'get': {
            summary: 'get_s_0',
            parameters: [
            ]
          }
        },        '/akam/13/pixel_3ce348e8': {
          'post': {
            summary: 'post_akam_13_pixel_3ce348e8',
            parameters: [
            ]
          }
        },        '/s/0/1/j/ub_v1.16.min.js': {
          'get': {
            summary: 'get_s_0_1',
            parameters: [
            ]
          }
        },        '/s/0/0/j/nLoggerJB_v3.4.min.js': {
          'get': {
            summary: 'get_s_0',
            parameters: [
            ]
          }
        },        '/favicon.ico': {
          'get': {
            summary: 'get_favicon_ico',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/chunks/1963.7d9d77914a8664cc.js': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/cloudgateway-mynaukri/resman-aggregator-services/v1/users/self/dashboard': {
          'get': {
            summary: 'get_cloudgateway_mynaukri_resman_aggregator_services_v1',
            parameters: [
              {
                name: 'properties',
                in: 'query',
                schema: { type: 'string' }
              }            ]
          }
        },        '/s/9/105/_next/static/chunks/1778.be1aabf1dc75b363.js': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/chunks/647.9e6b82b3bbda979d.js': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/assets/info.svg': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/assets/arrow.svg': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/assets/home.svg': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/assets/jobs.svg': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/assets/company.svg': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/assets/blog.svg': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/7/0/j/widget-client-ni.min.js': {
          'get': {
            summary: 'get_s_7_0',
            parameters: [
            ]
          }
        },        '//uba': {
          'get': {
            summary: 'get_uba',
            parameters: [
              {
                name: 'data',
                in: 'query',
                schema: { type: 'string' }
              },              {
                name: 'rad',
                in: 'query',
                schema: { type: 'string' }
              }            ]
          }
        },        '/s/9/105/_next/static/chunks/tracking.4c548c0510ae6df1.js': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/gtm.js': {
          'get': {
            summary: 'get_gtm_js',
            parameters: [
              {
                name: 'id',
                in: 'query',
                schema: { type: 'string' }
              }            ]
          }
        },        '/s/9/105/_next/static/chunks/9813.fe6320f6733a0e9d.js': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/9/105/_next/static/chunks/4506.14ae4ffaecf6088e.js': {
          'get': {
            summary: 'get_s_9_105',
            parameters: [
            ]
          }
        },        '/s/7/0/j/naukri-widget_v12.36-modern.min.js': {
          'get': {
            summary: 'get_s_7_0',
            parameters: [
            ]
          }
        },        '/cloudgateway-mynaukri/resman-aggregator-services/v0/users/self/profiles/18e6c5f2b2d6f71cb1abe71e0a70ccc5c0234cac14d1dd83b679862093b973de/photo': {
          'get': {
            summary: 'get_cloudgateway_mynaukri_resman_aggregator_services_v0',
            parameters: [
            ]
          }
        },        '/cloudgateway-mynaukri/resman-aggregator-services/v2/users/self': {
          'get': {
            summary: 'get_cloudgateway_mynaukri_resman_aggregator_services_v2',
            parameters: [
              {
                name: 'expand_level',
                in: 'query',
                schema: { type: 'string' }
              },              {
                name: 'properties',
                in: 'query',
                schema: { type: 'string' }
              }            ]
          }
        }      }
    };
  }
}