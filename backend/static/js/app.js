const content = document.getElementById('content');
const logoutBtn = document.getElementById('logoutBtn');
const themeToggle = document.getElementById('themeToggle');

const api = async (path, opts = {}) => {
  const res = await fetch(path, { credentials: 'include', headers: { 'Content-Type': 'application/json' }, ...opts });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.error || 'Request failed');
  }
  return res.json();
};

const setTheme = (theme) => {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('rpinas_theme', theme);
};

themeToggle.onclick = () => {
  const current = document.documentElement.getAttribute('data-theme') || 'dark';
  setTheme(current === 'dark' ? 'light' : 'dark');
};
setTheme(localStorage.getItem('rpinas_theme') || 'dark');

const card = (inner) => `<section class="glass card">${inner}</section>`;

const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (ch) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[ch]));

function setupWizard(status) {
  content.innerHTML = card(`
    <h2>First Setup Wizard</h2>
    <small>Default access point: <b>${escapeHtml(status.wifi_ssid)}</b> at <b>http://192.168.4.1</b></small>
    <label>Admin Password (min 8)
      <input id="adminPass" type="password" />
    </label>
    <h3>NAS Users (at least one)</h3>
    <div id="wizardUsers"></div>
    <button id="addWizardUser">Add NAS User</button>
    <label><input id="guestEnabled" type="checkbox" style="width:auto" /> Enable guest access to Shared folder</label>
    <label>Storage Type
      <select id="storageTarget">
        <option value="sd" ${status.storage_target === 'sd' ? 'selected' : ''}>SD card</option>
        <option value="external" ${status.storage_target === 'external' ? 'selected' : ''}>External drive</option>
      </select>
    </label>
    <button id="finishSetup">Complete Setup</button>
    <p id="wizardError"></p>
  `);

  const usersDiv = document.getElementById('wizardUsers');
  const addUserRow = () => {
    const row = document.createElement('div');
    row.className = 'grid';
    row.innerHTML = `
      <label>Username<input class="wu" /></label>
      <label>Password<input class="wp" type="password" /></label>
    `;
    usersDiv.appendChild(row);
  };

  addUserRow();
  document.getElementById('addWizardUser').onclick = addUserRow;
  document.getElementById('finishSetup').onclick = async () => {
    const users = [...document.querySelectorAll('.wu')].map((usernameEl, i) => ({
      username: usernameEl.value.trim(),
      password: document.querySelectorAll('.wp')[i].value.trim(),
    })).filter(u => u.username && u.password);

    try {
      await api('/api/setup', {
        method: 'POST',
        body: JSON.stringify({
          admin_password: document.getElementById('adminPass').value,
          users,
          guest_enabled: document.getElementById('guestEnabled').checked,
          storage_target: document.getElementById('storageTarget').value,
        })
      });
      loginScreen('Setup complete. Sign in as administrator.');
    } catch (e) {
      document.getElementById('wizardError').textContent = e.message;
    }
  };
}

function loginScreen(message = '') {
  logoutBtn.classList.add('hidden');
  content.innerHTML = card(`
    <h2>Admin Login</h2>
    ${message ? `<p>${message}</p>` : ''}
    <label>Password<input id="loginPassword" type="password" /></label>
    <button id="loginSubmit">Sign In</button>
    <p id="loginError"></p>
  `);

  document.getElementById('loginSubmit').onclick = async () => {
    try {
      await api('/api/login', { method: 'POST', body: JSON.stringify({ password: document.getElementById('loginPassword').value }) });
      loadDashboard();
    } catch (e) {
      document.getElementById('loginError').textContent = e.message;
    }
  };
}

function renderDashboardShell() {
  content.innerHTML = `
    <nav class="nav">
      <button data-page="dashboard">Dashboard</button>
      <button data-page="users">Users</button>
      <button data-page="storage">Storage</button>
      <button data-page="network">Network</button>
      <button data-page="system">System</button>
    </nav>
    <div id="page"></div>
  `;
  [...document.querySelectorAll('[data-page]')].forEach(btn => {
    btn.onclick = () => pages[btn.dataset.page]();
  });
}

const pages = {
  async dashboard() {
    const data = await api('/api/dashboard');
    document.getElementById('page').innerHTML = `
      <div class="grid">
        ${card(`<h3>Storage Usage</h3><p>${data.storage_usage.used_pct}% used</p><small>${data.storage_usage.used} / ${data.storage_usage.total} bytes</small>`) }
        ${card(`<h3>Connected Users</h3><p>${data.users.length}</p>`) }
        ${card(`<h3>Network Status</h3><p>${escapeHtml(data.network.ssid)}</p><small>${escapeHtml(data.network.ip)}</small>`) }
        ${card(`<h3>System Status</h3><span class="badge">${escapeHtml(data.system.service)}</span>`) }
      </div>
      ${card(`<h3>Recent Logs</h3><pre>${data.logs.map(l => `[${escapeHtml(l.created_at)}] ${escapeHtml(l.event_type)} ${escapeHtml(l.details)}`).join('\n')}</pre>`) }
    `;
  },

  async users() {
    const data = await api('/api/users');
    document.getElementById('page').innerHTML = `
      ${card(`
        <h3>NAS Users</h3>
        <table class="table">
          <thead><tr><th>Username</th><th>Created</th><th>Actions</th></tr></thead>
          <tbody>
            ${data.users.map(u => `<tr><td>${escapeHtml(u.username)}</td><td>${escapeHtml(u.created_at)}</td><td>
              <button class="reset-user-btn" data-username="${escapeHtml(u.username)}">Reset Password</button>
              <button class="delete-user-btn" data-username="${escapeHtml(u.username)}">Remove</button>
            </td></tr>`).join('')}
          </tbody>
        </table>
      `)}
      ${card(`
        <h3>Add User</h3>
        <label>Username<input id="newUser"/></label>
        <label>Password<input id="newUserPass" type="password"/></label>
        <button id="addUserBtn">Add User</button>
        <label><input id="guestSwitch" type="checkbox" style="width:auto" ${data.guest_enabled ? 'checked' : ''}/> Enable guest access for Shared</label>
      `)}
    `;

    document.querySelectorAll('.reset-user-btn').forEach((button) => {
      button.addEventListener('click', () => resetUser(button.dataset.username));
    });
    document.querySelectorAll('.delete-user-btn').forEach((button) => {
      button.addEventListener('click', () => deleteUser(button.dataset.username));
    });
    document.getElementById('addUserBtn').onclick = async () => {
      await api('/api/users', { method: 'POST', body: JSON.stringify({ username: document.getElementById('newUser').value, password: document.getElementById('newUserPass').value }) });
      pages.users();
    };
    document.getElementById('guestSwitch').onchange = async (e) => {
      await api('/api/users/guest', { method: 'POST', body: JSON.stringify({ enabled: e.target.checked }) });
    };
  },

  async storage() {
    const [storage, devices] = await Promise.all([api('/api/storage'), api('/api/storage/devices')]);
    document.getElementById('page').innerHTML = card(`
      <h3>Storage</h3>
      <p>Current target: <b>${escapeHtml(storage.storage_target)}</b></p>
      <p>Current path: <b>${escapeHtml(storage.storage_path)}</b></p>
      <p>Used: ${storage.usage.used_pct}%</p>
      <label>Storage Type
        <select id="storageTarget">
          <option value="sd" ${storage.storage_target === 'sd' ? 'selected' : ''}>SD card</option>
          <option value="external" ${storage.storage_target === 'external' ? 'selected' : ''}>External drive</option>
        </select>
      </label>
      <button id="saveStorage">Apply Storage</button>
      <h4>Detected Devices</h4>
      <pre>${devices.devices.map(d => `${escapeHtml(d.path)} (${escapeHtml(d.size)}) mount=${escapeHtml(d.mountpoint || '-')} removable=${d.removable}`).join('\n') || 'No devices detected'}</pre>
    `);
    document.getElementById('saveStorage').onclick = async () => {
      await api('/api/storage', { method: 'POST', body: JSON.stringify({ storage_target: document.getElementById('storageTarget').value }) });
      pages.storage();
    };
  },

  async network() {
    const net = await api('/api/network');
    document.getElementById('page').innerHTML = card(`
      <h3>Network</h3>
      <label>WiFi Name (SSID)<input id="ssid" value="${escapeHtml(net.ssid)}"/></label>
      <label>WiFi Password (optional)<input id="wifiPass" type="password" placeholder="${net.password_set ? 'Already configured' : 'Open network'}"/></label>
      <button id="saveNetwork">Apply (reboot required)</button>
      <p>Current admin panel URL: <b>http://192.168.4.1</b></p>
    `);
    document.getElementById('saveNetwork').onclick = async () => {
      const payload = await api('/api/network', { method: 'POST', body: JSON.stringify({ ssid: document.getElementById('ssid').value.trim(), password: document.getElementById('wifiPass').value }) });
      alert(payload.reboot_required ? 'Network saved. Reboot is required.' : 'Saved.');
    };
  },

  async system() {
    const logs = await api('/api/system/logs');
    document.getElementById('page').innerHTML = card(`
      <h3>System</h3>
      <div class="grid">
        <button id="rebootBtn">Reboot</button>
        <button id="shutdownBtn">Shutdown</button>
      </div>
      <h4>Backend Logs</h4>
      <pre>${logs.logs.map(escapeHtml).join('\n')}</pre>
    `);
    document.getElementById('rebootBtn').onclick = async () => {
      if (!confirm('Reboot the NAS now? Active file transfers will be interrupted.')) return;
      try {
        await api('/api/system/reboot', { method: 'POST' });
        alert('Rebooting now. The admin panel will be unreachable for a minute or two.');
      } catch (e) {
        alert(e.message);
      }
    };
    document.getElementById('shutdownBtn').onclick = async () => {
      if (!confirm('Shut down the NAS now? You will need physical access to power it back on.')) return;
      try {
        await api('/api/system/shutdown', { method: 'POST' });
        alert('Shutting down now.');
      } catch (e) {
        alert(e.message);
      }
    };
  }
};

window.deleteUser = async (username) => {
  if (!confirm(`Remove ${username}?`)) return;
  await api(`/api/users/${username}`, { method: 'DELETE' });
  pages.users();
};

window.resetUser = async (username) => {
  const password = prompt(`New password for ${username}:`);
  if (!password) return;
  await api(`/api/users/${username}/reset-password`, { method: 'POST', body: JSON.stringify({ password }) });
  alert('Password updated');
};

async function loadDashboard() {
  logoutBtn.classList.remove('hidden');
  renderDashboardShell();
  await pages.dashboard();
}

logoutBtn.onclick = async () => {
  await api('/api/logout', { method: 'POST' });
  loginScreen();
};

(async () => {
  const status = await api('/api/status');
  if (!status.setup_complete) {
    setupWizard(status);
    return;
  }
  try {
    await api('/api/dashboard');
    loadDashboard();
  } catch {
    loginScreen();
  }
})();
