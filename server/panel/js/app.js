(function () {
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => document.querySelectorAll(s);

  function formatBytes(value) {
    if (!value) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;
    let v = value;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return v.toFixed(v >= 10 || i === 0 ? 0 : 1) + ' ' + units[i];
  }

  const authForm = document.getElementById('auth-form');

  if (authForm) {
    let mode = 'login';
    const errorBox = document.getElementById('auth-error');
    const submitBtn = document.getElementById('submit-btn');

    $$('.tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        $$('.tab').forEach((t) => t.classList.remove('active'));
        tab.classList.add('active');
        mode = tab.dataset.mode;
        submitBtn.textContent = mode === 'login' ? 'Sign In' : 'Sign Up';
        errorBox.hidden = true;
      });
    });

    authForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      errorBox.hidden = true;

      const data = new FormData(authForm);
      const body = {
        username: data.get('username'),
        password: data.get('password'),
      };

      try {
        const result = await API.post(
          mode === 'login' ? '/api/auth/login' : '/api/auth/register',
          body
        );
        API.setToken(result.token);
        window.location.href = '/app';
      } catch (error) {
        errorBox.textContent = error.message;
        errorBox.hidden = false;
      }
    });

    return;
  }

  if (!API.token()) {
    window.location.href = '/';
    return;
  }

  function renderTunnelRow(tunnel) {
    const address = tunnel.public_host + ':' + tunnel.public_port;
    const online = tunnel.status === 'online';
    return `
      <div class="tunnel-row" data-id="${tunnel.id}">
        <div>
          <div class="name">${tunnel.name}</div>
          <div class="addr">${address}</div>
        </div>
        <span class="proto">${tunnel.protocol}</span>
        <span class="badge ${online ? 'online' : 'offline'}">
          <span class="dot ${online ? 'online' : ''}"></span>${online ? 'ONLINE' : 'OFFLINE'}
        </span>
        <div class="row">
          <button class="btn small" data-copy="${address}" type="button">Copy</button>
          <button class="btn small danger" data-delete="${tunnel.id}" type="button">Delete</button>
        </div>
      </div>
    `;
  }

  function bindTunnelActions(container) {
    container.querySelectorAll('[data-copy]').forEach((button) => {
      button.addEventListener('click', () => {
        navigator.clipboard.writeText(button.getAttribute('data-copy'));
        const original = button.textContent;
        button.textContent = 'OK';
        setTimeout(() => { button.textContent = original; }, 1000);
      });
    });
    container.querySelectorAll('[data-delete]').forEach((button) => {
      button.addEventListener('click', async () => {
        if (!window.confirm('Delete this tunnel?')) return;
        await API.del('/api/tunnels/' + button.getAttribute('data-delete'));
        refreshAll();
      });
    });
  }

  async function refreshTunnels() {
    const tunnels = await API.get('/api/tunnels');
    const list = document.getElementById('tunnels-list');
    if (tunnels.length === 0) {
      list.innerHTML = '<div class="empty">No tunnels yet. Create your first game tunnel.</div>';
      return;
    }
    list.innerHTML = tunnels.map(renderTunnelRow).join('');
    bindTunnelActions(list);
  }

  async function refreshStats() {
    const stats = await API.get('/api/stats');
    document.getElementById('stat-active').textContent = stats.active_tunnels;
    document.getElementById('stat-conn').textContent = stats.online_connections;
    document.getElementById('stat-bw').textContent = formatBytes(stats.bandwidth);
    document.getElementById('stat-uptime').textContent = stats.uptime.toFixed(2) + '%';
  }

  async function refreshActivity() {
    const items = await API.get('/api/activity');
    const container = document.getElementById('activity-list');
    if (items.length === 0) {
      container.innerHTML = '<div class="empty">-</div>';
      return;
    }
    container.innerHTML = items.map((item) => `
      <div class="tunnel-row">
        <div class="name">${item.action}</div>
        <div class="addr">${item.created_at.replace('T', ' ').slice(0, 19)}</div>
        <span class="badge online"><span class="dot online"></span>${item.status}</span>
        <div></div>
      </div>
    `).join('');
  }

  function refreshAll() {
    refreshTunnels();
    refreshStats();
    refreshActivity();
  }

  function showPage(name) {
    $$('.page').forEach((p) => { p.hidden = true; });
    const target = document.getElementById('page-' + name);
    if (target) target.hidden = false;
    $$('.nav-item').forEach((item) => {
      item.classList.toggle('active', item.dataset.page === name);
    });
  }

  $$('.nav-item').forEach((item) => {
    item.addEventListener('click', (event) => {
      event.preventDefault();
      showPage(item.dataset.page);
    });
  });

  $$('[data-goto]').forEach((btn) => {
    btn.addEventListener('click', () => showPage(btn.dataset.goto));
  });

  document.getElementById('logout').addEventListener('click', () => {
    API.clear();
    window.location.href = '/';
  });

  const createForm = document.getElementById('create-form');
  createForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = new FormData(createForm);
    const body = {
      name: data.get('name'),
      game: data.get('game'),
      protocol: data.get('protocol'),
      local_host: data.get('local_host'),
      local_port: parseInt(data.get('local_port'), 10),
    };
    try {
      const tunnel = await API.post('/api/tunnels', body);
      createForm.reset();
      showPage('dashboard');
      refreshAll();
      window.alert('Tunnel created\n\nToken:\n' + tunnel.token + '\n\nPublic address:\n' + tunnel.public_host + ':' + tunnel.public_port);
    } catch (error) {
      window.alert('Error: ' + error.message);
    }
  });

  async function boot() {
    try {
      const user = await API.get('/api/auth/me');
      document.getElementById('user-name').textContent = user.username;
      await Promise.all([refreshTunnels(), refreshStats(), refreshActivity()]);
      showPage('dashboard');
    } catch (error) {
      API.clear();
      window.location.href = '/';
    }
  }

  boot();
})();