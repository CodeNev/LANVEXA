const API = {
  base: '',

  token() {
    return localStorage.getItem('lanvexa.token');
  },

  setToken(value) {
    localStorage.setItem('lanvexa.token', value);
  },

  clear() {
    localStorage.removeItem('lanvexa.token');
  },

  async request(path, options = {}) {
    const headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
    const token = this.token();
    if (token) headers.Authorization = 'Bearer ' + token;

    const response = await fetch(this.base + path, Object.assign({}, options, { headers }));
    const text = await response.text();
    const data = text ? JSON.parse(text) : null;

    if (!response.ok) {
      const message = (data && data.detail) || 'request_failed';
      throw new Error(message);
    }
    return data;
  },

  get(path) { return this.request(path); },
  post(path, body) { return this.request(path, { method: 'POST', body: JSON.stringify(body) }); },
  del(path) { return this.request(path, { method: 'DELETE' }); },
};