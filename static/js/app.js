// Themarr web UI: shared helpers, router and the background polling of the queue and logs.
// Each page lives in its own file and registers itself in App.pages with a render(view, arg) function.

const App = {
    info: {},
    settings: {},
    library: null,          // { libraries, media } from /api/library
    queue: { paused: false, items: [] },
    status: {},
    logs: [],
    pages: {},
    route: { name: null, arg: null },
    search: '',
};

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------
function esc(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function icon(name, cls = '') {
    return `<i data-lucide="${name}" class="${cls}"></i>`;
}

function refreshIcons() {
    if (window.lucide) lucide.createIcons();
}

function fmtTime(seconds) {
    if (seconds == null || isNaN(seconds)) return '0:00';
    seconds = Math.max(0, Math.round(seconds));
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

// "75", "1:15" or "0:01:15" -> 75. Empty or invalid -> null
function parseTime(text) {
    text = String(text ?? '').trim();
    if (!text) return null;
    if (/^\d+(\.\d+)?$/.test(text)) return parseFloat(text);
    const parts = text.split(':').map(Number);
    if (parts.some(isNaN) || parts.length > 3) return null;
    return parts.reduce((total, part) => total * 60 + part, 0);
}

async function api(path, body) {
    const options = body === undefined ? {} : {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    };
    const response = await fetch(path, options);
    if (response.status === 401) {
        location.href = '/login';
        throw new Error('Login required');
    }
    const data = await response.json().catch(() => null);
    if (data === null) throw new Error(`Unexpected answer from the server (${response.status})`);
    return data;
}

// ---------------------------------------------------------------------------
// Toasts, dialogs and menus
// ---------------------------------------------------------------------------
function toast(message, type = 'info') {
    const colors = { success: 'text-green-400', error: 'text-red-400', info: 'text-accent-text' };
    const icons = { success: 'circle-check', error: 'circle-alert', info: 'info' };
    const el = document.createElement('div');
    el.className = 'toast-enter pointer-events-auto card shadow-2xl px-4 py-3 flex items-start gap-3 max-w-sm text-[13px]';
    el.innerHTML = `<span class="${colors[type] || colors.info} mt-0.5">${icon(icons[type] || 'info')}</span><span>${esc(message)}</span>`;
    document.getElementById('toasts').appendChild(el);
    refreshIcons();
    setTimeout(() => el.remove(), type === 'error' ? 7000 : 4000);
}

function openDialog(html, { wide = false } = {}) {
    const dialog = document.getElementById('dialog');
    dialog.className = `card w-full ${wide ? 'max-w-2xl' : 'max-w-md'} shadow-2xl`;
    dialog.innerHTML = html;
    document.getElementById('dialogOverlay').classList.remove('hidden');
    refreshIcons();
    return dialog;
}

function closeDialog() {
    document.getElementById('dialogOverlay').classList.add('hidden');
    document.getElementById('dialog').innerHTML = '';
}

// Promise<boolean>. Replaces window.confirm, which would freeze the desktop window
function confirmDialog({ title, message, confirmLabel = 'Confirm', danger = false }) {
    return new Promise(resolve => {
        const dialog = openDialog(`
            <div class="p-5">
                <h2 class="font-semibold text-[15px]">${esc(title)}</h2>
                <p class="text-muted mt-2 leading-relaxed">${message}</p>
            </div>
            <div class="px-5 py-3 border-t border-line flex justify-end gap-2">
                <button data-answer="no" class="btn btn-ghost">Cancel</button>
                <button data-answer="yes" class="btn ${danger ? 'btn-danger' : 'btn-primary'}">${esc(confirmLabel)}</button>
            </div>`);
        dialog.querySelectorAll('[data-answer]').forEach(button => button.onclick = () => {
            closeDialog();
            resolve(button.dataset.answer === 'yes');
        });
    });
}

let openMenuEl = null;

function closeMenu() {
    if (openMenuEl) openMenuEl.remove();
    openMenuEl = null;
}

// items: [{ label, icon, onClick, danger }] or 'divider'
function showMenu(anchor, items) {
    closeMenu();
    const menu = document.createElement('div');
    menu.className = 'menu';
    items.forEach(item => {
        if (item === 'divider') {
            menu.appendChild(document.createElement('hr'));
            return;
        }
        const button = document.createElement('button');
        if (item.danger) button.className = 'danger';
        button.innerHTML = `${icon(item.icon)}<span>${esc(item.label)}</span>`;
        button.onclick = event => { event.stopPropagation(); closeMenu(); item.onClick(); };
        menu.appendChild(button);
    });
    document.body.appendChild(menu);
    const rect = anchor.getBoundingClientRect();
    const left = Math.min(rect.left, window.innerWidth - menu.offsetWidth - 8);
    const below = rect.bottom + 4 + menu.offsetHeight < window.innerHeight;
    menu.style.left = `${Math.max(8, left)}px`;
    menu.style.top = below ? `${rect.bottom + 4}px` : `${rect.top - menu.offsetHeight - 4}px`;
    openMenuEl = menu;
    refreshIcons();
}

document.addEventListener('click', event => {
    if (openMenuEl && !openMenuEl.contains(event.target)) closeMenu();
});
document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    closeMenu();
    if (!document.getElementById('dialogOverlay').classList.contains('hidden')) closeDialog();
    else if (App.pages.addTheme) App.pages.addTheme.close();
});

// ---------------------------------------------------------------------------
// Posters
// ---------------------------------------------------------------------------
const POSTER_COLORS = ['#3b2a6b', '#1e4d5c', '#5c3a1e', '#2a4d2a', '#5c1e3a', '#2a3a5c', '#4d4d1e', '#1e5c4d'];

function posterHtml(media, extraClass = '') {
    const name = media.jellyfin?.name || media.media_name;
    let hash = 0;
    for (const ch of media.media_name) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
    const color = POSTER_COLORS[hash % POSTER_COLORS.length];
    const image = media.jellyfin?.id
        ? `<img src="/api/jellyfin/image/${media.jellyfin.id}" alt="" loading="lazy" onerror="this.remove()">`
        : '';
    return `<div class="poster ${extraClass}" style="background: linear-gradient(160deg, ${color}, #14141c)">
        <span class="poster-letter">${esc(name.trim()[0] || '?')}</span>${image}</div>`;
}

function mediaTitle(media) {
    return media.jellyfin?.name || media.media_name;
}

// ---------------------------------------------------------------------------
// Audio player: one <audio> for the whole app, so only one preview plays at a time
// ---------------------------------------------------------------------------
const Player = {
    el: null,
    key: null,
    listeners: new Set(),

    init() {
        this.el = document.getElementById('player');
        ['timeupdate', 'play', 'pause', 'ended', 'loadedmetadata'].forEach(type =>
            this.el.addEventListener(type, () => this.notify()));
        this.el.addEventListener('error', () => {
            if (this.key) toast('Could not play this audio.', 'error');
            this.stop();
        });
    },

    // Plays url for `key`; calling again with the same key pauses or resumes
    toggle(key, url, startAt = null) {
        if (this.key === key && this.el.src) {
            this.el.paused ? this.el.play() : this.el.pause();
            return;
        }
        this.key = key;
        this.el.src = url;
        if (startAt != null) this.el.addEventListener('loadedmetadata', () => { this.el.currentTime = startAt; }, { once: true });
        this.el.play().catch(() => {});
        this.notify();
    },

    seek(seconds) {
        if (this.el.src) this.el.currentTime = Math.max(0, seconds);
    },

    stop() {
        this.el.pause();
        this.el.removeAttribute('src');
        this.el.load();
        this.key = null;
        this.notify();
    },

    isPlaying(key) {
        return this.key === key && !this.el.paused;
    },

    notify() {
        this.listeners.forEach(listener => listener(this));
    },
};

// ---------------------------------------------------------------------------
// Data shared by the pages
// ---------------------------------------------------------------------------
App.loadLibrary = async function (force = false) {
    if (App.library && !force) return App.library;
    const result = await api('/api/library');
    App.library = result.success ? result : { libraries: [], media: [] };
    const missing = App.library.media.filter(m => m.tracks.length === 0).length;
    const badge = document.getElementById('navMissingCount');
    badge.textContent = missing;
    badge.classList.toggle('hidden', missing === 0);
    return App.library;
};

App.saveSettings = async function (changes) {
    Object.assign(App.settings, changes);
    const result = await api('/api/save_settings', App.settings);
    if (!result.success) toast('Could not save the settings.', 'error');
    return result.success;
};

App.mediaAction = async function (folders, action, describe) {
    const labels = { normalize: 'normalize', fx: 'apply audio effects to', retag: 're-tag', organize: 'organize', remove: 'remove themes from' };
    if (action === 'remove') {
        const ok = await confirmDialog({
            title: 'Remove themes',
            message: `This permanently deletes every theme file of ${esc(describe)}. Your videos and other files are not touched.`,
            confirmLabel: 'Remove themes', danger: true,
        });
        if (!ok) return;
    }
    const result = await api('/api/media/action', { folders, action });
    toast(result.message || `Could not ${labels[action]} ${describe}.`, result.success ? 'info' : 'error');
};

// ---------------------------------------------------------------------------
// Router: #/library, #/media/<path>, #/missing, #/activity, #/settings
// ---------------------------------------------------------------------------
App.go = function (name, arg) {
    location.hash = arg != null ? `#/${name}/${encodeURIComponent(arg)}` : `#/${name}`;
};

App.render = function () {
    const [, name = 'library', ...rest] = location.hash.replace(/^#/, '').split('/');
    const page = App.pages[name] ? name : 'library';
    const arg = rest.length ? decodeURIComponent(rest.join('/')) : null;
    const changedPage = App.route.name !== page || App.route.arg !== arg;
    App.route = { name: page, arg };

    document.querySelectorAll('.nav-item').forEach(item =>
        item.classList.toggle('active', item.dataset.nav === page || (page === 'media' && item.dataset.nav === 'library')));
    if (changedPage) {
        closeMenu();
        Player.stop();
        App.pages.addTheme?.close();
        document.getElementById('view').scrollTop = 0;
    }
    App.pages[page].render(document.getElementById('view'), arg);
    refreshIcons();
};

// ---------------------------------------------------------------------------
// Polling: queue, task progress and logs
// ---------------------------------------------------------------------------
let lastQueueSignature = '';
let taskWasRunning = false;

App.poll = async function () {
    try {
        const [queue, status] = await Promise.all([api('/api/queue'), api('/api/status')]);

        if (status.logs) {
            App.logs.push(...status.logs.split('\n').filter(line => line.trim()));
            if (App.logs.length > 3000) App.logs.splice(0, App.logs.length - 3000);
            App.pages[App.route.name]?.onLogs?.();
        }

        const previous = new Map(App.queue.items.map(item => [item.id, item.status]));
        App.queue = queue;
        App.status = status;
        const finishedMedia = new Set(queue.items
            .filter(item => item.status === 'completed' && previous.get(item.id) && previous.get(item.id) !== 'completed')
            .map(item => item.media_folder));

        const signature = JSON.stringify([queue.paused, queue.items.map(i => [i.id, i.status, i.stage]), status.is_processing, status.statusText]);
        const changed = signature !== lastQueueSignature;
        lastQueueSignature = signature;

        if (finishedMedia.size) App.library = null;
        if (taskWasRunning && !status.is_processing) {
            App.library = null;
            toast(status.statusText || 'Task finished.', status.statusText?.startsWith('Error') ? 'error' : 'success');
            App.pages[App.route.name]?.onTaskDone?.();
        }
        taskWasRunning = status.is_processing;

        App.updateIndicator();
        if (changed) App.pages[App.route.name]?.onQueue?.(finishedMedia);
    } catch (err) {
        console.error('Polling failed:', err);
    }
    const active = App.queue.items.some(i => i.status === 'waiting' || i.status === 'processing') || App.status.is_processing;
    setTimeout(App.poll, active ? 1000 : 3000);
};

App.updateIndicator = function () {
    const items = App.queue.items;
    const pending = items.filter(i => i.status === 'waiting' || i.status === 'processing');
    const current = items.find(i => i.status === 'processing');
    const indicator = document.getElementById('activityIndicator');
    let text = '';
    if (current) {
        const done = items.filter(i => i.status === 'completed' || i.status === 'error').length;
        text = `${current.stage || 'Working'} ${done + 1} of ${items.length}`;
    } else if (App.status.is_processing) {
        text = App.status.statusText;
    } else if (pending.length && App.queue.paused) {
        text = `Queue paused (${pending.length})`;
    }
    document.getElementById('activityIndicatorText').textContent = text;
    indicator.classList.toggle('hidden', !text);
    indicator.classList.toggle('flex', !!text);

    const badge = document.getElementById('navQueueCount');
    badge.textContent = pending.length;
    badge.classList.toggle('hidden', pending.length === 0);
};

// Queue items of one media folder that are not done yet (shown on its page)
App.pendingFor = function (folder) {
    return App.queue.items.filter(i => i.media_folder === folder && i.status !== 'completed');
};

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------
App.start = async function () {
    Player.init();
    const [info, settings] = await Promise.all([api('/api/app_info'), api('/api/get_settings')]);
    App.info = info;
    App.settings = settings;
    document.getElementById('appVersion').textContent = `v${info.version}`;

    const search = document.getElementById('globalSearch');
    search.addEventListener('input', () => {
        App.search = search.value.trim().toLowerCase();
        if (App.route.name !== 'library') App.go('library');
        else App.pages.library.applyFilters();
    });

    window.addEventListener('hashchange', App.render);
    document.getElementById('dialogOverlay').addEventListener('mousedown', event => {
        if (event.target.id === 'dialogOverlay') closeDialog();
    });

    // Links from the Jellyfin buttons: /?item=<Jellyfin item id> opens that media
    const itemId = new URLSearchParams(location.search).get('item');
    if (itemId) {
        history.replaceState(null, '', location.pathname + location.hash);
        const result = await api('/api/jellyfin/resolve_item', { item_id: itemId }).catch(() => ({}));
        if (result.success) {
            App.go('media', result.path);
        } else {
            toast(result.message || 'Could not open the media sent by Jellyfin.', 'error');
        }
    }

    if (!location.hash) location.hash = '#/library';
    App.render();
    App.poll();
};
