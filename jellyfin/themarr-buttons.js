// Themarr buttons for the Jellyfin 10.10 web UI, loaded through the JavaScript Injector plugin.
//  - Series, season, episode and movie pages get a "Themarr" button that opens that media in Themarr
//  - The header gets a button that opens Themarr
// Only administrators see them. Themarr's Settings can install this script (it fills THEMARR_URL_SETTING
// from THEMARR_PUBLIC_URL); to install it by hand, paste it into Dashboard > Plugins > JavaScript Injector.
(function () {
    'use strict';

    // Where Themarr is. Empty: the same host Jellyfin was opened on, port THEMARR_PORT, same http/https.
    // That covers http://<server-ip>:8096 -> http://<server-ip>:8686 and a VPN name such as Tailscale serve.
    // Set a full address (e.g. 'https://themarr.example.com') when Themarr sits behind a reverse proxy.
    const THEMARR_URL_SETTING = '';
    const THEMARR_PORT = 8686;
    const THEMARR_URL = THEMARR_URL_SETTING.replace(/\/+$/, '')
        || `${window.location.protocol}//${window.location.hostname}:${THEMARR_PORT}`;
    const ITEM_TYPES = ['Series', 'Season', 'Episode', 'Movie'];
    const DETAIL_BUTTON_CLASS = 'themarrDetailButton';
    const HEADER_BUTTON_ID = 'themarrHeaderButton';

    let isAdmin = null;
    const itemTypes = {};

    function openThemarr(itemId) {
        const url = itemId ? `${THEMARR_URL}/?item=${encodeURIComponent(itemId)}` : `${THEMARR_URL}/`;
        window.open(url, '_blank', 'noopener');
    }

    async function checkAdmin() {
        if (isAdmin !== null) return isAdmin;
        try {
            const user = await window.ApiClient.getCurrentUser();
            isAdmin = !!(user && user.Policy && user.Policy.IsAdministrator);
        } catch (err) {
            return false;  // not signed in yet: try again on the next page
        }
        return isAdmin;
    }

    async function getItemType(itemId) {
        if (!(itemId in itemTypes)) {
            const item = await window.ApiClient.getItem(window.ApiClient.getCurrentUserId(), itemId);
            itemTypes[itemId] = item ? item.Type : null;
        }
        return itemTypes[itemId];
    }

    function currentItemId() {
        const hash = window.location.hash || '';
        if (!hash.includes('details')) return null;
        const query = hash.split('?')[1] || '';
        return new URLSearchParams(query).get('id');
    }

    function addHeaderButton() {
        const headerRight = document.querySelector('.headerRight');
        if (!headerRight || document.getElementById(HEADER_BUTTON_ID)) return;

        const button = document.createElement('button');
        button.id = HEADER_BUTTON_ID;
        button.type = 'button';
        button.setAttribute('is', 'paper-icon-button-light');
        button.className = 'headerButton headerButtonRight paper-icon-button-light';
        button.title = 'Open Themarr';
        button.innerHTML = '<span class="material-icons music_note" aria-hidden="true"></span>';
        button.addEventListener('click', () => openThemarr(null));
        headerRight.insertBefore(button, headerRight.firstChild);
    }

    async function addDetailButton() {
        const itemId = currentItemId();
        if (!itemId) return;

        // Jellyfin keeps old pages hidden in the DOM: only the visible one gets the button
        const container = document.querySelector('.itemDetailPage:not(.hide) .mainDetailButtons');
        if (!container) return;

        // While pages swap, the previous one can still be visible: drop buttons that belong to another item
        document.querySelectorAll('.' + DETAIL_BUTTON_CLASS).forEach(old => {
            if (old.dataset.itemId !== itemId && !old.closest('.hide')) old.remove();
        });
        if (container.querySelector(`.${DETAIL_BUTTON_CLASS}[data-item-id="${itemId}"]`)) return;

        const type = await getItemType(itemId).catch(() => null);
        if (!ITEM_TYPES.includes(type) || currentItemId() !== itemId) return;
        if (container.querySelector(`.${DETAIL_BUTTON_CLASS}[data-item-id="${itemId}"]`)) return;

        const button = document.createElement('button');
        button.type = 'button';
        button.dataset.itemId = itemId;
        button.setAttribute('is', 'emby-button');
        button.className = `button-flat detailButton emby-button ${DETAIL_BUTTON_CLASS}`;
        button.title = 'Open in Themarr';
        button.innerHTML = '<div class="detailButton-content"><span class="material-icons detailButton-icon music_note" aria-hidden="true"></span></div>';
        button.addEventListener('click', () => openThemarr(itemId));
        container.appendChild(button);
    }

    let pending = null;
    function refresh() {
        clearTimeout(pending);
        pending = setTimeout(async () => {
            if (!window.ApiClient || !(await checkAdmin())) return;
            addHeaderButton();
            addDetailButton();
        }, 300);
    }

    document.addEventListener('viewshow', refresh);
    window.addEventListener('hashchange', refresh);
    new MutationObserver(refresh).observe(document.body, { childList: true, subtree: true });
    refresh();
})();
