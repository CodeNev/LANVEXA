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
    const raw = await response.text();

    let data = null;
    if (raw) {
      try {
        data = JSON.parse(raw);
      } catch (parseError) {
        const preview = raw.slice(0, 120).replace(/\s+/g, ' ');
        throw new Error('Server error ' + response.status + ': ' + preview);
      }
    }

    if (!response.ok) {
      const message = (data && data.detail) || (data && data.error) || 'request_failed';
      throw new Error(message);
    }
    return data;
  },

  get(path) {
    return this.request(path);
  },

  post(path, body) {
    return this.request(path, { method: 'POST', body: JSON.stringify(body) });
  },

  del(path) {
    return this.request(path, { method: 'DELETE' });
  },
};
