setTimeout(() => {
    if (!window.pywebview || !window.pywebview.api) {
        console.log("🌐 Browser Mode detected! Activating Flask backend.");
        
        window.pywebview = {
            api: {
                select_folder: async () => {
                    let res = await fetch('/api/select_folder', { method: 'POST' });
                    return await res.json();
                },
                get_settings: async () => {
                    let res = await fetch('/api/get_settings');
                    return await res.json();
                },
                save_settings: async (data) => {
                    await fetch('/api/save_settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
                },
                process_queue: async (queueData, folder) => {
                    await fetch('/api/process_queue', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ queue: queueData, folder: folder }) });
                },
                get_status: async () => {
                    let res = await fetch('/api/status');
                    return await res.json();
                },
                delete_music_folder: async (folder, scope, selectedFolders) => {
                    let res = await fetch('/api/delete_music_folder', { 
                        method: 'POST', 
                        headers: { 'Content-Type': 'application/json' }, 
                        body: JSON.stringify({ folder: folder, scope: scope, selectedFolders: selectedFolders }) 
                    });
                    return await res.json();
                },
                enhance_local_music: async (folder, scope, lufs, options, selectedFolders) => {
                    let res = await fetch('/api/enhance_local_music', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ folder: folder, scope: scope, lufs: lufs, options: options, selectedFolders: selectedFolders })
                    });
                    return await res.json();
                },
                test_jellyfin: async (url, api_key) => {
                    let res = await fetch('/api/test_jellyfin', { 
                        method: 'POST', 
                        headers: { 'Content-Type': 'application/json' }, 
                        body: JSON.stringify({ url: url, api_key: api_key }) 
                    });
                    return await res.json();
                },
                get_subfolders: async (folder) => {
                    let res = await fetch('/api/get_subfolders', { 
                        method: 'POST', 
                        headers: { 'Content-Type': 'application/json' }, 
                        body: JSON.stringify({ folder: folder }) 
                    });
                    return await res.json();
                },
                search_youtube: async (query) => {
                    let res = await fetch('/api/search_youtube', { 
                        method: 'POST', 
                        headers: { 'Content-Type': 'application/json' }, 
                        body: JSON.stringify({ query: query }) 
                    });
                    return await res.json();
                }
            }
        };
        window.dispatchEvent(new CustomEvent('pywebviewready'));
    }
}, 500);

let SERVER_MODE = false;  // set by loadAppInfo(): headless server with login and folder browser

// Server mode: an expired login sends the user back to the sign-in page
const nativeFetch = window.fetch.bind(window);
window.fetch = async (...args) => {
    const response = await nativeFetch(...args);
    if (response.status === 401 && SERVER_MODE) {
        window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname + window.location.search);
    }
    return response;
};

async function loadAppInfo() {
    let info = {};
    try {
        info = await (await fetch('/api/app_info')).json();
        SERVER_MODE = !!info.server_mode;
    } catch (err) {
        console.error("Could not load app info:", err);
    }
    if (!SERVER_MODE) return;

    // Opening a local browser window makes no sense on a headless server
    document.getElementById('openBrowserOption').classList.add('hidden');

    document.getElementById('serverUserName').innerText = info.user || '';
    document.getElementById('serverSessionBar').classList.remove('hidden');
}

const NO_FOLDER_TEXT = "No folder selected...";
const START_BTN_IDLE_CLASS = "w-full bg-neutral-800 text-neutral-500 py-3 rounded-md font-bold text-sm mb-3 cursor-not-allowed border border-neutral-700 transition-colors";
const START_BTN_READY_CLASS = "w-full bg-blue-600 hover:bg-blue-500 text-white py-3 rounded-md font-bold text-sm mb-3 cursor-pointer shadow-lg transition-colors";
const SPINNER_SVG = `<svg class="animate-spin h-4 w-4 text-blue-500 ml-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>`;
const EMPTY_QUEUE_HTML = '<div class="flex h-full items-center justify-center text-neutral-600 text-sm">Queue is empty.</div>';

// Escapes text placed inside HTML attributes or element content
function escapeHtml(text) {
    return String(text ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function getMediaFolder() {
    return document.getElementById('folderPath').innerText;
}

function hasMediaFolder() {
    const folder = getMediaFolder();
    return folder !== NO_FOLDER_TEXT && folder.trim() !== "";
}

// Shows the standard toast when no Media Directory is selected
function requireMediaFolder() {
    if (hasMediaFolder()) return true;
    showToast("Please select a Media Directory first!", "error");
    return false;
}

function getCheckedFolders() {
    return Array.from(document.querySelectorAll('.folder-checkbox:checked'), chk => chk.value);
}

// Desktop mode calls the pywebview bridge; browser mode falls back to the Flask route
async function callBackend(method, args, route, body) {
    const api = window.pywebview && window.pywebview.api;
    if (api && api[method]) {
        return api[method](...args);
    }
    const response = await fetch(route, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body || {})
    });
    return response.json();
}

function setStartButton(ready) {
    const btnStart = document.getElementById('btnStart');
    btnStart.className = ready ? START_BTN_READY_CLASS : START_BTN_IDLE_CLASS;
    btnStart.innerText = "▶ START PROCESSING";
    btnStart.disabled = !ready;
}

function resetProgressUI() {
    document.getElementById('progressBar').style.width = "0%";
    document.getElementById('percentText').innerText = "0%";
    document.getElementById('statusText').innerText = "Ready";
}

function toggleTrackFx() {
    const drawer = document.getElementById('trackFxDrawer');
    drawer.classList.toggle('hidden');
}

function toggleFxState(checkboxId, containerId) {
    const isChecked = document.getElementById(checkboxId).checked;
    const container = document.getElementById(containerId);
    if (isChecked) {
        container.classList.remove('opacity-50', 'pointer-events-none');
    } else {
        container.classList.add('opacity-50', 'pointer-events-none');
    }
}

function openDeleteModal() {
    if (!requireMediaFolder()) return;
    document.getElementById('deleteModal').classList.remove('hidden');
}

function closeDeleteModal() {
    document.getElementById('deleteModal').classList.add('hidden');
}

function showToast(message, status) {
    const toast = document.getElementById('toastNotification');
    const toastMsg = document.getElementById('toastMessage');
    const toastIcon = document.getElementById('toastIcon');
    
    toastMsg.innerText = message;

    if (status === 'success') {
        toastIcon.innerText = '✅';
    } else if (status === 'info') {
        toastIcon.innerText = '⏳';
    } else {
        toastIcon.innerText = '❌';
    }
    
    toast.classList.remove('hidden');
    setTimeout(() => {
        toast.classList.remove('translate-y-10', 'opacity-0');
    }, 10);
    
    setTimeout(() => {
        toast.classList.add('translate-y-10', 'opacity-0');
        setTimeout(() => toast.classList.add('hidden'), 300);
    }, 3500);
}

async function triggerDelete(scope) {
    const selectedFolders = getCheckedFolders();

    if (scope === 'all') {
        let doubleCheck = confirm(
            "⚠️ DOUBLE CHECK WARNING ⚠️\n\n" +
            "You are about to permanently delete ALL audio files from ALL MEDIA in the library.\n" +
            "Are you absolutely sure you want to proceed?"
        );
        if (!doubleCheck) {
            closeDeleteModal();
            return; 
        }
    } else if (scope === 'selected') {
        if (selectedFolders.length === 0) {
            showToast("⚠️ No folders selected in the dropdown!", "error");
            closeDeleteModal();
            return;
        }
        
        let singleCheck = confirm(`Proceed with deleting audio files from the ${selectedFolders.length} SELECTED folders?`);
        if (!singleCheck) {
            closeDeleteModal();
            return;
        }
    }

    closeDeleteModal();
    const folder = getMediaFolder();
    showToast("🗑️ Deleting files...", "success");

    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.delete_music_folder(folder, scope, selectedFolders)
        .then(res => {
            showToast(res.message, res.status);
        })
        .catch(err => {
            console.error("Delete Python Error:", err);
            showToast("❌ Server Error (Check Terminal)", "error");
        });
    }
}

function openEnhanceModal() {
    if (!requireMediaFolder()) return;
    document.getElementById('enhanceModal').classList.remove('hidden');
}

function closeEnhanceModal() {
    document.getElementById('enhanceModal').classList.add('hidden');
}

async function triggerEnhance(scope) {
    closeEnhanceModal();
    
    const folder = getMediaFolder();
    const currentLufs = parseInt(document.getElementById('lufsInput').value) || -24;
    const selectedFolders = getCheckedFolders();
    
    const options = {
        normalize: document.getElementById('chkNormalize').checked,
        audio_fx: document.getElementById('chkAudioFx').checked,
        metadata: document.getElementById('chkMetadata').checked,
        organize: document.getElementById('chkOrganize').checked
    };

    showToast("⏳ Processing audio... This might take a while.", "success");

    try {
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.enhance_local_music(folder, scope, currentLufs, options, selectedFolders)
            .then(res => {
                showToast(res.message, res.status);
            })
            .catch(err => {
                console.error("Enhance Python Error:", err);
                showToast("❌ Server Error (Check Terminal)", "error");
            });
        }
    } catch (error) {
        console.error("Error starting Enhance:", error);
        showToast("❌ Failed to start process.", "error");
    }
}

let musicQueue = []; 
let globalDestinationOptions = [];
let dragStartIndex = null; 
let isProcessing = false; 
let isCompleted = false; 
let currentPlayingIndex = null;
let queueAudioTimer = null;
let queueAudioVolume = 0.5;

function toggleModal(modalID) { document.getElementById(modalID).classList.toggle("hidden"); }

function changeVolume(delta) {
    let input = document.getElementById('lufsInput');
    let currentValue = parseInt(input.value) || 0;
    let newValue = currentValue + delta;
    if(newValue > 0) newValue = 0; 
    if(newValue < -70) newValue = -70; 
    input.value = newValue;
    saveAutoSettings();
}

function validateLUFSInput(input) {
    if (input.value === "" || input.value === "-") return;
    let value = parseInt(input.value);
    if (isNaN(value) || value > 0) input.value = "0";
    saveAutoSettings();
}

function toggleLog() {
    const container = document.getElementById('logContainer');
    const btn = document.getElementById('btnToggleLog');
    container.classList.toggle('hidden');
    if(container.classList.contains('hidden')) {
        btn.innerText = '▼ Show Detailed Logs';
    } else {
        btn.innerText = '▲ Hide Detailed Logs';
        container.scrollTop = container.scrollHeight;
    }
}

function addLogText(text) {
    const container = document.getElementById('logContainer');
    container.innerText += text;
    container.scrollTop = container.scrollHeight;
}

setInterval(async () => {
    if (!window.pywebview || !window.pywebview.api) return;

    try {
        let data = await window.pywebview.api.get_status();

        if (data.logs && data.logs.trim() !== "") {
            addLogText(data.logs);
        }

        if (data.percentage !== undefined && isProcessing) {
            window.updateGlobalProgress(data.percentage, data.statusText, data.percentageText);
        }
        
        if (data.item_statuses && (isProcessing || data.is_processing)) {
            data.item_statuses.forEach((status_item, index) => {
                window.updateItemStatus(index, status_item);
            });
        }

        if (data.is_processing) {
            isProcessing = true;
        } else if (isProcessing && !data.is_processing) {
            isProcessing = false;
            window.finalizeProcessingUI();
        }

    } catch (e) {
        console.error("Error occurred while fetching status:", e);
    }
}, 500);

function toggleFolderDropdown() {
    const dropdown = document.getElementById('folderDropdown');
    dropdown.classList.toggle('hidden');
}

function checkAllFolders(state) {
    const checkboxes = document.querySelectorAll('.folder-checkbox');
    checkboxes.forEach(chk => chk.checked = state);
}

async function loadFolderCheckboxes(path) {
    const container = document.getElementById('folderCheckboxList');
    container.innerHTML = '<p class="text-xs text-gray-500 text-center py-2">Loading...</p>';
    
    if (window.pywebview && window.pywebview.api && window.pywebview.api.get_subfolders) {
        let res = await window.pywebview.api.get_subfolders(path);
        container.innerHTML = '';
        
        if (res.status === 'success' && res.folders && res.folders.length > 0) {
            container.innerHTML = res.folders.map(folder => {
                const shouldBeChecked = (res.selected_anime && res.selected_anime === folder) ? 'checked' : '';

                return `
                    <label class="flex items-center gap-2 hover:bg-[#333333] p-1.5 rounded cursor-pointer transition">
                        <input type="checkbox" value="${folder}" class="folder-checkbox w-3.5 h-3.5 accent-blue-500 rounded border-gray-700 bg-gray-800" ${shouldBeChecked}>
                        <span class="text-xs text-gray-300 truncate">${folder}</span>
                    </label>
                `;
            }).join('');
        } else {
            container.innerHTML = '<p class="text-xs text-gray-500 text-center py-2">No subfolders found.</p>';
        }
    }
}

function selectFolder() {
    if(isProcessing) return; 
    
    if(isCompleted) {
        musicQueue = [];
        isCompleted = false;
        resetProgressUI();
        setStartButton(false);
        document.getElementById('logContainer').innerText = "System ready. Awaiting tasks...\n";
        updateQueueUI();
    }

    if (SERVER_MODE) {
        openFolderBrowser();
        return;
    }

    if(window.pywebview) {
        window.pywebview.api.select_folder().then(response => {
            if(response.success) applySelectedFolder(response);
        });
    } else { alert("Connect to Python first."); }
}

let folderBrowserCurrent = null;
let folderBrowserParent = null;

function openFolderBrowser() {
    document.getElementById('folderBrowserModal').classList.remove('hidden');
    const current = hasMediaFolder() ? getMediaFolder() : null;
    browseServerFolder(current);
}

function closeFolderBrowser() {
    document.getElementById('folderBrowserModal').classList.add('hidden');
}

async function browseServerFolder(folder) {
    const list = document.getElementById('folderBrowserList');
    try {
        const res = await callBackend('browse_media_folders', [folder], '/api/browse_folders', { folder: folder });
        if (!res.success) {
            showToast(res.message || "Could not open this folder.", "error");
            return;
        }
        folderBrowserCurrent = res.path;
        folderBrowserParent = res.parent;
        document.getElementById('folderBrowserPath').innerText = res.path;
        document.getElementById('folderBrowserPath').title = res.path;
        document.getElementById('folderBrowserUp').disabled = !res.parent;

        list.innerHTML = res.folders.length === 0
            ? '<p class="text-xs text-neutral-500 text-center py-6">No subfolders here.</p>'
            : res.folders.map((name, i) => `
                <button data-idx="${i}" class="folder-browser-item w-full text-left px-2.5 py-1.5 rounded text-xs text-neutral-300 hover:bg-neutral-700/60 hover:text-white truncate">
                    📁 ${escapeHtml(name)}
                </button>`).join('');
        list.querySelectorAll('.folder-browser-item').forEach(btn => {
            const name = res.folders[parseInt(btn.dataset.idx)];
            btn.addEventListener('click', () => browseServerFolder(res.path.replace(/[\\/]+$/, '') + '/' + name));
        });
    } catch (err) {
        console.error("Folder browser error:", err);
        showToast("Could not reach the server.", "error");
    }
}

async function chooseServerFolder() {
    if (!folderBrowserCurrent) return;
    const res = await callBackend('select_server_folder', [folderBrowserCurrent], '/api/select_server_folder', { folder: folderBrowserCurrent });
    if (res.success) {
        closeFolderBrowser();
        applySelectedFolder(res);
    } else {
        showToast(res.message || "Could not select this folder.", "error");
    }
}

// Applies a folder returned by select_folder or resolve_jellyfin_item: { path, seasons }
function applySelectedFolder(response) {
    let returnedPath = response.path;
    document.getElementById('folderPath').innerText = returnedPath;
    loadFolderCheckboxes(returnedPath);
    globalDestinationOptions = ['Main Theme'];

    let returnedSeasons = response.seasons || [];
    if(returnedSeasons.length === 0) {
        let folderName = returnedPath.split('\\').pop().split('/').pop();
        globalDestinationOptions.push(`Season 01. ${folderName}`);
    } else {
        globalDestinationOptions.push(...returnedSeasons);
    }
    updateMainDropdown();
}

// Links from Jellyfin open Themarr as /?item=<Jellyfin item id> with that media folder already selected
async function openFromJellyfinLink() {
    const itemId = new URLSearchParams(window.location.search).get('item');
    if (!itemId) return;

    try {
        const res = await callBackend('resolve_jellyfin_item', [itemId], '/api/jellyfin/resolve_item', { item_id: itemId });
        if (res.success) {
            applySelectedFolder(res);
            showToast(`Opened from Jellyfin: ${res.name}`, "success");
        } else {
            showToast(res.message, "error");
        }
    } catch (err) {
        console.error("Jellyfin link error:", err);
        showToast("Could not open the media sent by Jellyfin.", "error");
    }
}

function updateMainDropdown() {
    document.getElementById('destinationSelect').innerHTML = globalDestinationOptions
        .map(op => `<option value="${op}" class="bg-neutral-800 text-white">${op}</option>`)
        .join('');
}

function addToQueue() {
    if(isProcessing) return; 
    
    if(isCompleted) {
        isCompleted = false;
        musicQueue = [];
        resetProgressUI();
        document.getElementById('logContainer').innerText = "System ready. Awaiting tasks...\n";
        updateQueueUI();
    }

    const link = document.getElementById('linkInput').value.trim();
    const name = document.getElementById('nameInput').value.trim();
    const destination = document.getElementById('destinationSelect').value;
    const lufs = document.getElementById('lufsInput').value;

    if(!link || (!link.startsWith("https://") && !link.startsWith("http://"))) {
        showToast("Invalid URL format! The address must start with 'http://' or 'https://'.");
        return;
    }
    if(!name) { showToast("Please enter a track name!"); return; }
    if(!destination || destination === "") { showToast("Please select a target folder!"); return; }
    if(getMediaFolder() === NO_FOLDER_TEXT) { showToast("Please browse for a media folder first!"); return; }

    let customFx = null;
    const fxDrawer = document.getElementById('trackFxDrawer');
    
    if (!fxDrawer.classList.contains('hidden')) {
        customFx = {
            enabled: document.getElementById('trackFxEnable').checked,
            remove_silence: document.getElementById('trackRemoveSilence').checked,
            fade_in: parseInt(document.getElementById('trackFadeIn').value) || 0,
            fade_out: parseInt(document.getElementById('trackFadeOut').value) || 0
        };
    }

    musicQueue.push({ 
        link: link, 
        name: name, 
        destination: destination, 
        lufs: lufs, 
        status: 'pending',
        audio_fx: customFx ,
        startTime: "",
        endTime: ""
    });
    
    document.getElementById('linkInput').value = "";
    document.getElementById('nameInput').value = "";
    
    document.getElementById('trackFxEnable').checked = false;
    toggleFxState('trackFxEnable', 'trackFxContainer');
    document.getElementById('trackRemoveSilence').checked = false;
    document.getElementById('trackFadeIn').value = "";
    document.getElementById('trackFadeOut').value = "";
    fxDrawer.classList.add('hidden');
    
    updateQueueUI();
}

function removeFromQueue(index) {
    if(isProcessing) return;
    
    if (currentPlayingIndex === index) {
        stopQueueAudio();
    } else if (currentPlayingIndex > index) {
        currentPlayingIndex--;
    }
    
    musicQueue.splice(index, 1);
    updateQueueUI();
}

function editQueueName(index, newName) { musicQueue[index].name = newName; }
function editQueueDestination(index, newDestination) { musicQueue[index].destination = newDestination; }

function dragStart(index, event) {
    if(isProcessing) return;
    dragStartIndex = index;
    setTimeout(() => event.target.classList.add('dragging'), 0);
}
function dragEnd(event) { event.target.classList.remove('dragging'); }
function dragOver(event) { if(!isProcessing) event.preventDefault(); }
function drop(index) {
    if (isProcessing || dragStartIndex === null || dragStartIndex === index) return;
    const draggedItem = musicQueue.splice(dragStartIndex, 1)[0];
    musicQueue.splice(index, 0, draggedItem);
    dragStartIndex = null;
    updateQueueUI();
}

function updateQueueUI() {
    const container = document.getElementById('queueContainer');

    if (musicQueue.length === 0) {
        container.innerHTML = EMPTY_QUEUE_HTML;
        if (!isCompleted) setStartButton(false);
        return;
    }

    if (!isProcessing && !isCompleted) setStartButton(true);

    const itemsHTML = musicQueue.map((item, index) => {
        const optionsHTML = globalDestinationOptions.map(op =>
            `<option value="${op}" class="bg-neutral-800 text-white" ${op === item.destination ? 'selected' : ''}>${op}</option>`
        ).join('');

        let statusIcon = "";
        let itemOpacity = "";
        if (item.status === 'processing') {
            statusIcon = SPINNER_SVG;
        } else if (item.status === 'completed') {
            statusIcon = `<span class="text-green-500 ml-2 font-bold">✅</span>`;
            itemOpacity = "opacity-60"; 
        } else if (item.status === 'error') {
            statusIcon = `
                <div class="group relative flex items-center justify-center w-6 h-6 ml-1">
                    <span class="block group-hover:hidden text-red-500 font-bold text-xs select-none">❌</span>
                    <button onclick="retrySingleQueueItem(${index})" 
                            class="hidden group-hover:flex items-center justify-center text-blue-400 hover:text-blue-300 transition-colors" 
                            title="Retry Task">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor" class="w-4 h-4 animate-pulse">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
                        </svg>
                    </button>
                </div>
            `;
            itemOpacity = "opacity-60 text-red-400"; 
        }

        let pointerState = isProcessing ? "pointer-events-none" : "";
        let dragEnable = isProcessing ? "false" : "true";
        let cursorState = isProcessing ? "cursor-default" : "cursor-move";

        let buttonsHTML = '';
        if (!isProcessing) {
            buttonsHTML = `
                <div class="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity ml-1">
                    <button onclick="toggleTrimDrawer(${index})" class="text-neutral-400 hover:text-blue-400 transition-colors p-1 cursor-pointer" title="Trim/Preview Audio">
                        ✂️
                    </button>
                    <button onclick="removeFromQueue(${index})" class="text-neutral-500 hover:text-red-400 font-bold p-1 cursor-pointer">
                        ✕
                    </button>
                </div>
            `;
        }

        let dragHandleHTML = '';
        if (!isProcessing) {
            dragHandleHTML = '<span class="text-neutral-600 group-hover:text-neutral-400 mr-2 text-xs select-none">⋮⋮</span>';
        }

        return `
        <div id="queue-item-${index}" data-status="${item.status}" draggable="${dragEnable}" 
                ondragstart="dragStart(${index}, event)" 
                ondragend="dragEnd(event)"
                ondragover="dragOver(event)" 
                ondrop="drop(${index})"
                class="group flex flex-col bg-neutral-800/50 hover:bg-neutral-800 border border-neutral-700/50 hover:border-neutral-600 p-2 rounded text-sm transition-colors ${cursorState} ${itemOpacity} mb-2">
            
            <div class="flex items-center justify-between w-full">
                
                ${dragHandleHTML}
                
                <div class="status-icon flex items-center">${statusIcon}</div>

                <input type="text" value="${escapeHtml(item.name)}" onchange="editQueueName(${index}, this.value)" ${isProcessing ? 'disabled' : ''}
                        class="bg-transparent text-white font-semibold focus:outline-none focus:border-b focus:border-blue-500 w-1/4 px-1 truncate cursor-text ml-2 ${pointerState}">
                
                <select onchange="editQueueDestination(${index}, this.value)" ${isProcessing ? 'disabled' : ''}
                        class="bg-transparent text-neutral-400 text-xs focus:outline-none cursor-pointer w-1/4 px-1 appearance-none hover:text-neutral-300 ${pointerState}">
                    ${optionsHTML}
                </select>
                
                <span class="text-blue-400 text-xs truncate flex-grow text-right px-2 opacity-60">${escapeHtml(item.link)}</span>
                
                ${buttonsHTML}
            </div>

            <div id="trimDrawer-${index}" class="trim-drawer w-full border-t border-neutral-700/50" 
                 draggable="false" 
                 onmousedown="event.stopPropagation()" 
                 onpointerdown="event.stopPropagation()"
                 onmouseenter="document.getElementById('queue-item-${index}').setAttribute('draggable', 'false')"
                 onmouseleave="document.getElementById('queue-item-${index}').setAttribute('draggable', '${dragEnable}')">
                <div class="flex flex-col gap-2 mt-2">
                    
                     <div class="flex items-center gap-3 bg-neutral-900/60 p-2 rounded border border-neutral-800">
                        <button id="trimPlayBtn-${index}" onclick="toggleQueuePlay(${index}, musicQueue[${index}].link)" class="trim-play-btn" title="Play Preview">
                            ▶
                        </button>
                        
                        <input type="range" id="trimSlider-${index}" min="0" max="100" value="0" step="0.1" 
                               oninput="seekQueueAudio(${index}, this.value)"
                               class="trim-slider flex-1">
                        
                        <span id="trimTimeLabel-${index}" class="text-[10px] text-neutral-400 font-mono min-w-[65px] text-right">
                            0:00 / 0:00
                        </span>

                        <div class="h-4 w-[1px] bg-neutral-700/50"></div>

                        <div class="flex items-center gap-1.5 pl-1">
                            <span class="text-[11px] text-neutral-500 select-none" title="Volume">🔊</span>
                            <input type="range" id="trimVolume-${index}" min="0" max="1" step="0.05" value="${queueAudioVolume}" 
                                   oninput="adjustQueueVolume(this.value)"
                                   class="w-12 h-1 rounded bg-neutral-700 cursor-pointer accent-blue-500"
                                   style="height: 4px;">
                        </div>
                    </div>

                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-[10px] uppercase tracking-wider text-neutral-400 font-bold mb-1">Start Time (s / MM:SS)</label>
                            <input type="text" id="trimStart-${index}" value="${item.startTime || ''}" 
                                   onchange="updateTrimTime(${index}, 'startTime', this.value)"
                                   placeholder="e.g. 5 or 0:05" 
                                   class="w-full bg-neutral-900 border border-neutral-700 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500">
                        </div>
                        <div>
                            <label class="block text-[10px] uppercase tracking-wider text-neutral-400 font-bold mb-1">End Time (s / MM:SS)</label>
                            <input type="text" id="trimEnd-${index}" value="${item.endTime || ''}" 
                                   onchange="updateTrimTime(${index}, 'endTime', this.value)"
                                   placeholder="e.g. 68 or 1:08" 
                                   class="w-full bg-neutral-900 border border-neutral-700 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500">
                        </div>
                    </div>
                </div>
            </div>

        </div>
        `;
    });

    container.innerHTML = itemsHTML.join('');
}

function retrySingleQueueItem(index) {
    const music = musicQueue[index]; 
    if (!music) return;
    
    const mainCount = musicQueue.filter(m => m.destination === 'Main Theme').length;
    music.has_multi_main = mainCount > 1;

    const folderPath = getMediaFolder();
    if (!folderPath || folderPath === NO_FOLDER_TEXT) {
        showToast("❌ Please select a valid folder first.", "error");
        return;
    }

    fetch('/api/retry_item', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            index: index,
            music: music,
            folder: folderPath
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            console.log(`[SYSTEM] Sent retry command for item index: ${index}`);
        } else {
            console.error('[ERROR] Failed to execute retry action:', data.message);
            showToast("❌ Failed to initiate retry process.", "error");
        }
    })
    .catch(err => {
        console.error('[ERROR] Network exception communicating with server:', err);
    });
}

function startProcessing() {
    stopQueueAudio();
    if (isCompleted) {
        musicQueue = [];
        document.getElementById('queueContainer').innerHTML = EMPTY_QUEUE_HTML;
        resetProgressUI();
        setStartButton(false);
        isCompleted = false;
        return;
    }

    if(musicQueue.length === 0 || isProcessing) return;

    isProcessing = true;
    isCompleted = false;
    
    const btnStart = document.getElementById('btnStart');
    btnStart.className = "w-full bg-purple-900/50 text-purple-300 py-3 rounded-md font-bold text-sm mb-3 cursor-not-allowed border border-purple-700/50 shadow-[0_0_15px_rgba(168,85,247,0.2)] flex items-center justify-center gap-2";
    btnStart.innerHTML = `<svg class="animate-spin h-4 w-4 text-purple-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> PROCESSING...`;
    btnStart.disabled = true;

    const mainFolder = getMediaFolder().trim();
    if (!mainFolder || mainFolder === NO_FOLDER_TEXT) {
            alert("Please select a directory first!");
            isProcessing = false;
            updateQueueUI();
            return;
    }

    window.pywebview.api.process_queue(musicQueue, mainFolder).catch(err => {
        console.error("Error starting queue:", err);
    });
}

window.updateGlobalProgress = function(percentage, statusText, percentageText) {
    document.getElementById('progressBar').style.width = percentage + "%";
    document.getElementById('percentText').innerText = percentageText || (percentage + "%");
    document.getElementById('statusText').innerText = statusText;
};

window.updateItemStatus = function(index, newStatus) {
    let item = document.getElementById(`queue-item-${index}`);
    if(!item) return;

    let currentStatus = item.getAttribute('data-status') || 'pending';
    if (currentStatus === newStatus) return; 

    item.setAttribute('data-status', newStatus);
    
    let statusDiv = item.querySelector('.status-icon');
    if(!statusDiv) return;

    if(newStatus === 'processing') {
        statusDiv.innerHTML = SPINNER_SVG;
        item.classList.remove('opacity-60', 'text-red-400');
        item.classList.add('opacity-100');
    } else if(newStatus === 'completed') {
        statusDiv.innerHTML = `<span class="text-green-500 ml-2 font-bold">✅</span>`;
        item.classList.remove('opacity-100', 'text-red-400');
        item.classList.add('opacity-60');
        if(musicQueue[index]) musicQueue[index].status = 'completed';
    } else if(newStatus === 'error') {
        statusDiv.innerHTML = `<span class="text-red-500 ml-2 text-xs font-bold">❌</span>`;
        item.classList.remove('opacity-100');
        item.classList.add('opacity-60', 'text-red-400');
        if(musicQueue[index]) musicQueue[index].status = 'error';
    }
};

window.finalizeProcessingUI = function() {
    isProcessing = false;
    isCompleted = true; 
    
    window.updateGlobalProgress(100, "All Done!", "100%");
    
    const btnStart = document.getElementById('btnStart');
    btnStart.className = "w-full bg-green-600 text-white py-3 rounded-md font-bold text-sm mb-3 cursor-pointer shadow-lg transition-colors";
    btnStart.innerText = "✅ COMPLETED!";
    btnStart.disabled = false;
    
    musicQueue.forEach((item) => {
        if(item.status === 'pending' || item.status === 'processing') {
            item.status = 'completed';
        }
    });

    updateQueueUI();

    if (!document.getElementById('libraryModal').classList.contains('hidden')) {
        loadLibraryData(true);
    }
};

async function testConnection() {
    const msgEl = document.getElementById('testMsg');
    msgEl.className = "text-sm font-bold text-center mt-2 transition-opacity block text-neutral-400";
    
    let url = document.getElementById('jellyUrl').value.trim();
    const api = document.getElementById('jellyApi').value.trim();

    if(!url || !api) {
        msgEl.innerText = "Please fill in both the URL and the API Key.";
        msgEl.className = "text-sm font-bold text-center mt-2 transition-opacity block text-red-500";
        return;
    }

    if (!url.startsWith('http://') && !url.startsWith('https://')) {
        url = 'http://' + url;
        document.getElementById('jellyUrl').value = url; 
        saveAutoSettings(); 
    }

    msgEl.innerText = "Testing connection...";

    try {
        let response = await window.pywebview.api.test_jellyfin(url, api);

        msgEl.innerText = response.message;
        if(response.status === 'success') {
            msgEl.className = "text-sm font-bold text-center mt-2 transition-opacity block text-green-500";
        } else {
            msgEl.className = "text-sm font-bold text-center mt-2 transition-opacity block text-red-500";
        }
    } catch (error) {
        msgEl.innerText = "❌ Connection failed. Check if the URL is correct and the server is online.";
        msgEl.className = "text-sm font-bold text-center mt-2 transition-opacity block text-red-500";
        console.error("Connection test error:", error);
    }
}

async function loadSettings() {
    try {
        let config = await window.pywebview.api.get_settings();
        
        if(config) {
            document.getElementById('lufsInput').value = config.lufs !== undefined ? config.lufs : -24;
            document.getElementById('jellyfinCheck').checked = config.jelly_check;
            document.getElementById('jellyUrl').value = config.jelly_url || "";
            document.getElementById('jellyApi').value = config.jelly_api || "";

            if(config.open_browser !== undefined) {
                document.getElementById('openBrowserCheck').checked = config.open_browser;
            } else {
                document.getElementById('openBrowserCheck').checked = true;
            }

            if (config.audio_fx) {
                document.getElementById('globalFxEnable').checked = config.audio_fx.enabled || false;
                document.getElementById('removeSilenceCheck').checked = config.audio_fx.remove_silence || false;
                document.getElementById('fadeInInput').value = config.audio_fx.fade_in || 0;
                document.getElementById('fadeOutInput').value = config.audio_fx.fade_out || 0;
            } else {
                document.getElementById('globalFxEnable').checked = false;
                document.getElementById('removeSilenceCheck').checked = false;
                document.getElementById('fadeInInput').value = 0;
                document.getElementById('fadeOutInput').value = 0;
            }
            toggleFxState('globalFxEnable', 'globalFxContainer');
        }
    } catch (error) {
        console.error("Error loading settings:", error);
    }
}

window.addEventListener('pywebviewready', async function() {
    await loadAppInfo();
    loadSettings();
    openFromJellyfinLink();
});

async function saveAutoSettings() {
    const data = {
        lufs: document.getElementById('lufsInput').value,
        jelly_check: document.getElementById('jellyfinCheck').checked,
        jelly_url: document.getElementById('jellyUrl').value,
        jelly_api: document.getElementById('jellyApi').value,
        open_browser: document.getElementById('openBrowserCheck').checked,
        audio_fx: {
            enabled: document.getElementById('globalFxEnable').checked,
            remove_silence: document.getElementById('removeSilenceCheck').checked,
            fade_in: parseInt(document.getElementById('fadeInInput').value) || 0,
            fade_out: parseInt(document.getElementById('fadeOutInput').value) || 0
        }
    };

    try {
        if (window.pywebview && window.pywebview.api) {
            await window.pywebview.api.save_settings(data);
        }
    } catch (error) {
        console.error("Error auto-saving settings:", error);
    }
}

let ytLocalCache = [];
let ytCurrentlyShown = 0;
let ytSelectedTitle = "";
let ytSelectedUrl = "";

function openYoutubeSearchModal() {
    document.getElementById('youtubeSearchModal').classList.remove('hidden');
    setTimeout(() => {
        document.getElementById('ytSearchQuery').focus();
    }, 50);
}

function closeYoutubeSearchModal() {
    const player = document.getElementById('ytPreviewPlayer');
    if (player) player.src = "";
    
    const previewContainer = document.getElementById('ytPreviewContainer');
    if (previewContainer) previewContainer.classList.add('hidden');
    
    const modalContainer = document.getElementById('ytModalContainer');
    if (modalContainer) {
        modalContainer.classList.remove('max-w-3xl');
        modalContainer.classList.add('max-w-lg');
    }
    
    ytSelectedTitle = "";
    ytSelectedUrl = "";
    
    document.getElementById('youtubeSearchModal').classList.add('hidden');
}

async function executeYoutubeSearch() {
    const queryInput = document.getElementById('ytSearchQuery');
    const container = document.getElementById('ytResultsContainer');
    const loadMoreBtn = document.getElementById('btnYtLoadMore');
    
    const query = queryInput.value.trim();
    if (!query) {
        showToast("⚠️ Please type something to search!", "error");
        return;
    }

    container.innerHTML = `
        <div class="text-center py-12 text-xs text-neutral-400 flex flex-col items-center justify-center gap-2">
            <span class="animate-spin text-lg">⏳</span>
            <span>Searching YouTube for "${query}"...</span>
        </div>
    `;
    loadMoreBtn.classList.add('hidden');
    
    ytLocalCache = [];
    ytCurrentlyShown = 0;

    if (window.pywebview && window.pywebview.api) {
        try {
            const results = await window.pywebview.api.search_youtube(query);
            
            if (!results || results.length === 0) {
                container.innerHTML = `<div class="text-center py-8 text-xs text-neutral-500">❌ No results found. Try changing your keywords.</div>`;
                return;
            }

            ytLocalCache = results;
            container.innerHTML = "";
            
            renderMoreYoutubeResults();

        } catch (err) {
            console.error("YouTube Search Error:", err);
            container.innerHTML = `<div class="text-center py-8 text-xs text-red-400">❌ Error connecting to backend search.</div>`;
        }
    }
}

function renderMoreYoutubeResults() {
    const container = document.getElementById('ytResultsContainer');
    const loadMoreBtn = document.getElementById('btnYtLoadMore');
    
    const itemsToLoad = (ytCurrentlyShown === 0) ? 15 : 5;
    const nextLimit = Math.min(ytCurrentlyShown + itemsToLoad, ytLocalCache.length);
    
    const sliceToRender = ytLocalCache.slice(ytCurrentlyShown, nextLimit);
    
    sliceToRender.forEach(item => {
        const row = document.createElement('div');
        row.className = "flex items-center justify-between p-2.5 bg-neutral-900/40 hover:bg-neutral-700/40 border border-neutral-700/30 rounded-md transition-all cursor-pointer group";
        
        row.addEventListener('click', () => selectYoutubeResult(item.title, item.url));
        
        row.innerHTML = `
            <div class="flex items-center gap-3 overflow-hidden">
                <div class="flex-shrink-0 relative">
                    <img src="${escapeHtml(item.thumbnail)}" alt="Capa" class="w-14 h-10 object-cover rounded shadow-sm border border-neutral-700/50">
                </div>
                
                <div class="flex flex-col pr-3 truncate">
                    <span class="text-xs font-medium text-neutral-200 group-hover:text-white transition truncate">${escapeHtml(item.title)}</span>
                    <span class="text-[10px] text-neutral-500 truncate">${escapeHtml(item.channel)}</span>
                </div>
            </div>

            <span class="text-[11px] font-mono text-neutral-500 bg-neutral-900 px-1.5 py-0.5 rounded flex-shrink-0">${item.duration || '0:00'}</span>
        `;
        container.appendChild(row);
    });

    ytCurrentlyShown = nextLimit;

    if (ytCurrentlyShown < ytLocalCache.length) {
        loadMoreBtn.classList.remove('hidden');
    } else {
        loadMoreBtn.classList.add('hidden');
    }
}

function selectYoutubeResult(title, url) {
    previewYoutubeResult(title, url);
}

function extractYoutubeId(url) {
    if (!url) return null;
    const regExp = /^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|\&v=)([^#\&\?]*).*/;
    const match = url.match(regExp);
    if (match && match[2] && match[2].length === 11) {
        return match[2];
    }
    return null;
}

function previewYoutubeResult(title, url) {
    ytSelectedTitle = title;
    ytSelectedUrl = url;
    
    const videoId = extractYoutubeId(url);
    const player = document.getElementById('ytPreviewPlayer');
    
    if (videoId && player) {
        const appOrigin = window.location.origin;
        
        player.src = `https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1&origin=${encodeURIComponent(appOrigin)}&enablejsapi=1`;
    }
    
    const titleEl = document.getElementById('ytPreviewTitle');
    if (titleEl) titleEl.innerText = title;
    
    const metaEl = document.getElementById('ytPreviewMeta');
    if (metaEl) metaEl.innerText = "Click 'Add Theme' to confirm selection.";
    
    const container = document.getElementById('ytModalContainer');
    if (container) {
        container.classList.remove('max-w-lg');
        container.classList.add('max-w-3xl');
    }
    
    const previewContainer = document.getElementById('ytPreviewContainer');
    if (previewContainer) previewContainer.classList.remove('hidden');
}

function closeYtPreview() {
    const player = document.getElementById('ytPreviewPlayer');
    if (player) player.src = "";
    
    const previewContainer = document.getElementById('ytPreviewContainer');
    if (previewContainer) previewContainer.classList.add('hidden');
    
    const container = document.getElementById('ytModalContainer');
    if (container) {
        container.classList.remove('max-w-3xl');
        container.classList.add('max-w-lg');
    }
    
    ytSelectedTitle = "";
    ytSelectedUrl = "";
}

function confirmYoutubeSelection() {
    if (!ytSelectedUrl || !ytSelectedTitle) return;
    
    document.getElementById('linkInput').value = ytSelectedUrl;
    document.getElementById('nameInput').value = ytSelectedTitle;
    
    closeYoutubeSearchModal();
    
    showToast("Theme successfully selected!", "success");
}

function toggleTrimDrawer(index) {
    const drawer = document.getElementById(`trimDrawer-${index}`);
    if (!drawer) return;
    
    if (!drawer.classList.contains('active') && currentPlayingIndex !== null && currentPlayingIndex !== index) {
        stopQueueAudio();
    }
    
    drawer.classList.toggle('active');
}

function updateTrimTime(index, field, value) {
    if (musicQueue[index]) {
        musicQueue[index][field] = value.trim();
        console.log(`[QUEUE] Updated music ${index} ${field} to:`, value);
    }
}

async function toggleQueuePlay(index, url) {
    const audioEl = document.getElementById('globalQueueAudio');
    const playBtn = document.getElementById(`trimPlayBtn-${index}`);
    const slider = document.getElementById(`trimSlider-${index}`);
    const timeLabel = document.getElementById(`trimTimeLabel-${index}`);
    
    if (currentPlayingIndex === index) {
        if (!audioEl.paused) {
            audioEl.pause();
            playBtn.innerText = "▶";
            clearInterval(queueAudioTimer);
        } else {
            audioEl.play();
            playBtn.innerText = "⏸";
            startQueueAudioSync(index);
        }
        return;
    }
    
    if (currentPlayingIndex !== null) {
        stopQueueAudio();
    }
    
    playBtn.innerText = "⏳";
    playBtn.disabled = true;
    timeLabel.innerText = "Loading...";
    
    try {
        const streamData = await callBackend('get_stream_info', [url], '/api/get_stream_info', { url: url });
        
        if (streamData && streamData.success) {
            currentPlayingIndex = index;
            audioEl.src = streamData.url;
            audioEl.volume = queueAudioVolume;
            
            audioEl.oncanplay = () => {
                playBtn.disabled = false;
                playBtn.innerText = "⏸";
                audioEl.play();
                
                slider.max = audioEl.duration;
                slider.value = 0;
                
                startQueueAudioSync(index);
            };
            
            audioEl.onended = () => {
                stopQueueAudio();
            };
            
        } else {
            alert("Não foi possível carregar a prévia desta música.");
            playBtn.innerText = "▶";
            playBtn.disabled = false;
            timeLabel.innerText = "Error";
        }
    } catch (err) {
        console.error("Erro no player da fila:", err);
        playBtn.innerText = "▶";
        playBtn.disabled = false;
        timeLabel.innerText = "Error";
    }
}

function startQueueAudioSync(index) {
    const audioEl = document.getElementById('globalQueueAudio');
    const slider = document.getElementById(`trimSlider-${index}`);
    const timeLabel = document.getElementById(`trimTimeLabel-${index}`);
    
    clearInterval(queueAudioTimer);
    queueAudioTimer = setInterval(() => {
        if (!audioEl.paused) {
            slider.value = audioEl.currentTime;
            timeLabel.innerText = `${formatSeconds(audioEl.currentTime)} / ${formatSeconds(audioEl.duration)}`;
        }
    }, 100);
}

function seekQueueAudio(index, value) {
    const audioEl = document.getElementById('globalQueueAudio');
    if (currentPlayingIndex === index) {
        audioEl.currentTime = value;
    }
}

function stopQueueAudio() {
    const audioEl = document.getElementById('globalQueueAudio');
    audioEl.pause();
    audioEl.src = "";
    clearInterval(queueAudioTimer);
    
    if (currentPlayingIndex !== null) {
        const playBtn = document.getElementById(`trimPlayBtn-${currentPlayingIndex}`);
        const slider = document.getElementById(`trimSlider-${currentPlayingIndex}`);
        const timeLabel = document.getElementById(`trimTimeLabel-${currentPlayingIndex}`);
        
        if (playBtn) playBtn.innerText = "▶";
        if (slider) slider.value = 0;
        if (timeLabel) timeLabel.innerText = "0:00 / 0:00";
    }
    
    currentPlayingIndex = null;
}

function formatSeconds(seconds) {
    if (isNaN(seconds) || !isFinite(seconds)) return "0:00";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
}

function adjustQueueVolume(value) {
    queueAudioVolume = parseFloat(value);
    const audioEl = document.getElementById('globalQueueAudio');
    if (audioEl) {
        audioEl.volume = queueAudioVolume;
    }
    musicQueue.forEach((item, idx) => {
        const volSlider = document.getElementById(`trimVolume-${idx}`);
        if (volSlider) {
            volSlider.value = queueAudioVolume;
        }
    });
}

let libraryScope = 'selected';
let libraryData = [];         
let libraryAudio = new Audio();
let currentLibPlayingAnimeIdx = null;
let currentLibPlayingTrackIdx = null;

function openLibraryModal() {
    if (!requireMediaFolder()) return;

        
    document.getElementById('libraryModal').classList.remove('hidden');
    
    document.getElementById('libLufsInput').value = document.getElementById('lufsInput').value;
    document.getElementById('libFadeInInput').value = document.getElementById('fadeInInput').value;
    document.getElementById('libFadeOutInput').value = document.getElementById('fadeOutInput').value;
    
    loadLibraryData();
}

function closeLibraryModal() {
    stopLibraryAudio();
    document.getElementById('libraryModal').classList.add('hidden');
}

function setLibraryScope(scope) {
    libraryScope = scope;
    
    const btnSelected = document.getElementById('libScopeSelected');
    const btnAll = document.getElementById('libScopeAll');
    
    if (scope === 'selected') {
        btnSelected.className = "px-3 py-1 rounded font-medium text-white bg-blue-600 transition-colors";
        btnAll.className = "px-3 py-1 rounded font-medium text-neutral-400 hover:text-white transition-colors";
    } else {
        btnAll.className = "px-3 py-1 rounded font-medium text-white bg-blue-600 transition-colors";
        btnSelected.className = "px-3 py-1 rounded font-medium text-neutral-400 hover:text-white transition-colors";
    }
    
    loadLibraryData();
}

async function loadLibraryData(preserveState = false) {
    const container = document.getElementById('libraryContainer');
    
    let openMediaNames = [];
    if (preserveState) {
        document.querySelectorAll('[id^="lib-accordion-body-"]').forEach(body => {
            if (!body.classList.contains('hidden')) {
                const animeIdx = parseInt(body.id.replace('lib-accordion-body-', ''));
                if (libraryData[animeIdx]) {
                    openMediaNames.push(libraryData[animeIdx].anime_name);
                }
            }
        });
    }

    if (!preserveState) {
        container.innerHTML = `
            <div class="flex flex-col h-full items-center justify-center text-neutral-500 text-xs gap-2">
                <div class="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
                Scanning local files...
            </div>
        `;
    }
    
    const baseFolder = getMediaFolder();
    const selectedFolders = hasMediaFolder() ? getLibrarySelection() : getCheckedFolders();
    
    try {
        const response = await fetch('/api/library/list', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                base_path: baseFolder,
                scope: libraryScope,
                selected_folders: selectedFolders
            })
        });
        
        const data = await response.json();
        if (data.success) {
            libraryData = data.library;
            renderLibrary(openMediaNames);
        } else {
            container.innerHTML = `
                <div class="flex h-full items-center justify-center text-red-500 text-xs">
                    Error: ${data.message}
                </div>
            `;
        }
    } catch (err) {
        console.error("Error loading library data:", err);
        container.innerHTML = `
            <div class="flex h-full items-center justify-center text-red-500 text-xs">
                Could not connect to local server.
            </div>
        `;
    }
}

function renderLibrary(openMediaNames = []) {
    const container = document.getElementById('libraryContainer');
    const summaryLabel = document.getElementById('libSummaryLabel');
    
    if (libraryData.length === 0) {
        container.innerHTML = `
            <div class="flex h-full items-center justify-center text-neutral-600 text-xs">
                No folders found matching the current criteria.
            </div>
        `;
        summaryLabel.innerText = "0 folders loaded";
        return;
    }
    
    summaryLabel.innerText = `${libraryData.length} folder(s) loaded`;
    container.innerHTML = "";
    
    libraryData.forEach((anime, animeIdx) => {
        const hasTracks = anime.tracks && anime.tracks.length > 0;
        const trackCount = hasTracks ? anime.tracks.length : 0;

        const isExpanded = openMediaNames.includes(anime.anime_name);
        
        const animeCard = document.createElement('div');
        animeCard.className = "bg-neutral-900/40 border border-neutral-850 rounded-lg overflow-hidden library-anime-card";
        animeCard.id = `lib-anime-card-${animeIdx}`;
        
        animeCard.innerHTML = `
            <div class="flex items-center justify-between px-4 py-3.5 cursor-pointer select-none" onclick="toggleLibraryAccordion(${animeIdx})">
                <div class="flex items-center gap-3 min-w-0 flex-1">
                    <span id="lib-chevron-${animeIdx}" class="text-neutral-500 text-[10px] transition-transform duration-200 flex-shrink-0" style="${isExpanded ? 'transform: rotate(90deg);' : ''}">❯</span>
                    <span class="font-semibold text-neutral-200 text-sm tracking-wide truncate" title="${escapeHtml(anime.anime_name)}">${escapeHtml(anime.anime_name)}</span>
                    <span class="text-[10px] bg-neutral-800 text-neutral-400 px-2 py-0.5 rounded-full font-medium flex-shrink-0 whitespace-nowrap">
                        ${trackCount} ${trackCount === 1 ? 'track' : 'tracks'}
                    </span>
                </div>

                <div class="flex items-center gap-2 flex-shrink-0 ml-3" onclick="event.stopPropagation()">
                    ${hasTracks ? `
                    <button onclick="applyAllTracksInMedia(${animeIdx})" class="px-2.5 py-1 bg-neutral-800 hover:bg-neutral-700 border border-neutral-700/50 text-neutral-300 hover:text-white rounded text-[11px] font-medium transition-colors">
                        ⚡ Apply All
                    </button>
                    ` : ''}
                    <button onclick="runLocalFolderAction('structure', ${animeIdx})" class="px-2.5 py-1 bg-neutral-850 hover:bg-neutral-800 border border-neutral-800 text-neutral-400 hover:text-white rounded text-[11px] transition-colors">
                        📂 Organize Folder
                    </button>
                </div>
            </div>
            
            <div id="lib-accordion-body-${animeIdx}" class="library-accordion-content ${isExpanded ? '' : 'hidden'} border-t border-neutral-850 bg-neutral-950/40 px-4 py-3 space-y-2">
                ${hasTracks ? '' : `<p class="text-xs text-neutral-600 py-1 text-center">No downloaded tracks inside this anime folder.</p>`}
                
                <div class="space-y-2" id="lib-tracks-list-${animeIdx}"></div>
            </div>
        `;
        
        container.appendChild(animeCard);
        
        if (hasTracks) {
            const tracksList = document.getElementById(`lib-tracks-list-${animeIdx}`);
            anime.tracks.forEach((track, trackIdx) => {
                track.normalize = (track.normalize !== undefined) ? track.normalize : true;
                track.fades = (track.fades !== undefined) ? track.fades : true;
                track.tag = (track.tag !== undefined) ? track.tag : true;
                
                const trackRow = document.createElement('div');
                trackRow.className = "flex flex-col gap-2 bg-neutral-900/30 border border-neutral-850/60 p-3 rounded-md";
                
                trackRow.innerHTML = `
                    <div class="flex items-center justify-between gap-3 flex-wrap">
                        <div class="flex items-center gap-3 min-w-[200px] flex-1">
                            <button id="libPlayBtn-${animeIdx}-${trackIdx}" onclick="toggleLibraryTrackPlay(${animeIdx}, ${trackIdx})" class="lib-play-btn" title="Play Preview">
                                ▶
                            </button>
                            <div class="flex flex-col">
                                <input type="text" value="${escapeHtml(track.file_name)}"  
                                oninput="updateLibraryTrackNameInMemory(${animeIdx}, ${trackIdx}, this.value)"
                                onmousedown="event.stopPropagation()"
                                onpointerdown="event.stopPropagation()"
                                class="bg-transparent border-b border-transparent hover:border-neutral-800/80 focus:border-blue-500 focus:outline-none text-xs font-semibold text-neutral-200 px-1 py-0.5 rounded transition-all max-w-xs break-all"
                                title="Click to rename file">
                                <span class="text-[9px] text-neutral-500 font-bold uppercase tracking-wider">${track.location_type}</span>
                            </div>
                        </div>
                        
                        <div class="flex items-center gap-1.5 bg-neutral-950/60 p-1 rounded border border-neutral-850 text-[10px]">
                            <span onclick="toggleLibPill(${animeIdx}, ${trackIdx}, 'normalize')" id="pill-norm-${animeIdx}-${trackIdx}" class="fx-pill px-2 py-0.5 rounded cursor-pointer border border-neutral-800 text-neutral-500 font-medium ${track.normalize ? 'active' : ''}">
                                LUFS
                            </span>
                            <span onclick="toggleLibPill(${animeIdx}, ${trackIdx}, 'fades')" id="pill-fade-${animeIdx}-${trackIdx}" class="fx-pill px-2 py-0.5 rounded cursor-pointer border border-neutral-800 text-neutral-500 font-medium ${track.fades ? 'active' : ''}">
                                FADES
                            </span>
                            <span onclick="toggleLibPill(${animeIdx}, ${trackIdx}, 'tag')" id="pill-tag-${animeIdx}-${trackIdx}" class="fx-pill px-2 py-0.5 rounded cursor-pointer border border-neutral-800 text-neutral-500 font-medium ${track.tag ? 'active' : ''}">
                                TAGS
                            </span>
                        </div>
                        
                        <div class="flex items-center gap-2">
                            <button onclick="toggleLibTrimDrawer(${animeIdx}, ${trackIdx})" class="p-1.5 hover:bg-neutral-800 border border-transparent hover:border-neutral-800 text-neutral-400 hover:text-blue-400 rounded transition-colors" title="Trim Audio">
                                ✂️
                            </button>
                            <button onclick="processSingleLibraryTrack(${animeIdx}, ${trackIdx})" class="px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded text-[11px] font-semibold transition-colors">
                                Apply
                            </button>
                            <button onclick="deleteSingleLibraryTrack(${animeIdx}, ${trackIdx})" class="p-1.5 hover:bg-red-950/30 border border-transparent hover:border-red-900/30 text-neutral-500 hover:text-red-400 rounded transition-colors" title="Delete Track">
                                ✕
                            </button>
                        </div>
                    </div>
                    
                    <div id="libPlaybackPanel-${animeIdx}-${trackIdx}" class="hidden flex items-center gap-3 bg-neutral-950/50 p-2 rounded border border-neutral-850 text-xs"
                         onmousedown="event.stopPropagation()"
                         onpointerdown="event.stopPropagation()">
                        <input type="range" id="libSlider-${animeIdx}-${trackIdx}" min="0" max="100" value="0" step="0.1" 
                               oninput="seekLibraryAudio(${animeIdx}, ${trackIdx}, this.value)"
                               class="trim-slider flex-1">
                        
                        <span id="libTimeLabel-${animeIdx}-${trackIdx}" class="text-[10px] text-neutral-400 font-mono min-w-[65px] text-right">
                            0:00 / 0:00
                        </span>

                        <div class="h-4 w-[1px] bg-neutral-800"></div>

                        <div class="flex items-center gap-1.5 pl-1">
                            <span class="text-[11px] text-neutral-500 select-none" title="Volume">🔊</span>
                            <input type="range" id="libVolume-${animeIdx}-${trackIdx}" min="0" max="1" step="0.05" value="${queueAudioVolume}" 
                                   oninput="adjustLibraryVolume(this.value)"
                                   class="w-12 h-1 rounded bg-neutral-700 cursor-pointer accent-blue-500"
                                   style="height: 4px;">
                        </div>
                    </div>

                    <div id="libTrimDrawer-${animeIdx}-${trackIdx}" class="hidden border-t border-neutral-850/60 pt-2.5 mt-1">
                        <div class="grid grid-cols-2 gap-3">
                            <div>
                                <label class="block text-[9px] uppercase tracking-wider text-neutral-400 font-bold mb-1">Start Time (s / MM:SS)</label>
                                <input type="text" id="libTrimStart-${animeIdx}-${trackIdx}" value="${track.startTime || '0'}" 
                                       onchange="updateLibTrimTime(${animeIdx}, ${trackIdx}, 'startTime', this.value)"
                                       placeholder="e.g. 5 or 0:05" 
                                       class="w-full bg-neutral-950 border border-neutral-800 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500">
                            </div>
                            <div>
                                <label class="block text-[9px] uppercase tracking-wider text-neutral-400 font-bold mb-1">End Time (s / MM:SS)</label>
                                <input type="text" id="libTrimEnd-${animeIdx}-${trackIdx}" value="${track.endTime || ''}" 
                                       onchange="updateLibTrimTime(${animeIdx}, ${trackIdx}, 'endTime', this.value)"
                                       placeholder="e.g. 68 or 1:08" 
                                       class="w-full bg-neutral-950 border border-neutral-800 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500">
                            </div>
                        </div>
                    </div>
                `;
                
                tracksList.appendChild(trackRow);
            });
        }
    });
}

function toggleLibraryAccordion(animeIdx) {
    const body = document.getElementById(`lib-accordion-body-${animeIdx}`);
    const chevron = document.getElementById(`lib-chevron-${animeIdx}`);
    
    if (body.classList.contains('hidden')) {
        body.classList.remove('hidden');
        chevron.style.transform = "rotate(90deg)";
    } else {
        body.classList.add('hidden');
        chevron.style.transform = "rotate(0deg)";
    }
}

function toggleLibPill(animeIdx, trackIdx, type) {
    const track = libraryData[animeIdx].tracks[trackIdx];
    track[type] = !track[type];
    
    const pillId = type === 'normalize' ? `pill-norm-${animeIdx}-${trackIdx}` :
                   type === 'fades' ? `pill-fade-${animeIdx}-${trackIdx}` :
                   `pill-tag-${animeIdx}-${trackIdx}`;
                   
    const pill = document.getElementById(pillId);
    if (track[type]) {
        pill.classList.add('active');
    } else {
        pill.classList.remove('active');
    }
}

function toggleLibTrimDrawer(animeIdx, trackIdx) {
    const drawer = document.getElementById(`libTrimDrawer-${animeIdx}-${trackIdx}`);
    drawer.classList.toggle('hidden');
}

function updateLibTrimTime(animeIdx, trackIdx, boundType, value) {
    libraryData[animeIdx].tracks[trackIdx][boundType] = value;
}

function toggleLibraryTrackPlay(animeIdx, trackIdx) {
    const isSameTrack = (currentLibPlayingAnimeIdx === animeIdx && currentLibPlayingTrackIdx === trackIdx);
    const playBtn = document.getElementById(`libPlayBtn-${animeIdx}-${trackIdx}`);
    const playbackPanel = document.getElementById(`libPlaybackPanel-${animeIdx}-${trackIdx}`);
    
    if (isSameTrack && !libraryAudio.paused) {
        libraryAudio.pause();
        playBtn.innerText = "▶";
        return;
    }
    
    if (isSameTrack && libraryAudio.paused) {
        libraryAudio.play();
        playBtn.innerText = "⏸";
        return;
    }
    
    stopLibraryAudio();
    
    currentLibPlayingAnimeIdx = animeIdx;
    currentLibPlayingTrackIdx = trackIdx;
    
    playbackPanel.classList.remove('hidden');
    playBtn.innerText = "⏸";
    
    const slider = document.getElementById(`libSlider-${animeIdx}-${trackIdx}`);
    const timeLabel = document.getElementById(`libTimeLabel-${animeIdx}-${trackIdx}`);

    libraryAudio.onloadedmetadata = () => {
        timeLabel.innerText = `0:00 / ${formatSeconds(libraryAudio.duration)}`;
    };

    libraryAudio.ontimeupdate = () => {
        if (!libraryAudio.duration || !isFinite(libraryAudio.duration)) return;
        const current = libraryAudio.currentTime;
        const total = libraryAudio.duration;
        slider.value = (current / total) * 100;
        timeLabel.innerText = `${formatSeconds(current)} / ${formatSeconds(total)}`;
    };

    libraryAudio.onended = () => {
        stopLibraryAudio();
    };

    const encodedPath = encodeURIComponent(libraryData[animeIdx].tracks[trackIdx].file_path);
    libraryAudio.src = `/api/library/stream?path=${encodedPath}&v=${Date.now()}`;
    libraryAudio.volume = queueAudioVolume;
    libraryAudio.play();
}

function stopLibraryAudio() {
    libraryAudio.pause();
    
    if (currentLibPlayingAnimeIdx !== null && currentLibPlayingTrackIdx !== null) {
        const playBtn = document.getElementById(`libPlayBtn-${currentLibPlayingAnimeIdx}-${currentLibPlayingTrackIdx}`);
        const playbackPanel = document.getElementById(`libPlaybackPanel-${currentLibPlayingAnimeIdx}-${currentLibPlayingTrackIdx}`);
        
        if (playBtn) playBtn.innerText = "▶";
        if (playbackPanel) playbackPanel.classList.add('hidden');
    }
    
    currentLibPlayingAnimeIdx = null;
    currentLibPlayingTrackIdx = null;
}

function seekLibraryAudio(animeIdx, trackIdx, value) {
    if (currentLibPlayingAnimeIdx === animeIdx && currentLibPlayingTrackIdx === trackIdx && libraryAudio.duration) {
        const targetTime = (parseFloat(value) / 100) * libraryAudio.duration;
        libraryAudio.currentTime = targetTime;
    }
}

function syncLibrarySettings() {
    document.getElementById('lufsInput').value = document.getElementById('libLufsInput').value;
    document.getElementById('fadeInInput').value = document.getElementById('libFadeInInput').value;
    document.getElementById('fadeOutInput').value = document.getElementById('libFadeOutInput').value;
    saveAutoSettings();
}

function updateLibraryTrackNameInMemory(animeIdx, trackIdx, newName) {
    if (!libraryData[animeIdx] || !libraryData[animeIdx].tracks[trackIdx]) return;
    libraryData[animeIdx].tracks[trackIdx].new_name = newName.trim();
}

async function processSingleLibraryTrack(animeIdx, trackIdx, autoReload = true) {
    stopLibraryAudio();
    const track = libraryData[animeIdx].tracks[trackIdx];
    
    let finalNewName = track.new_name || track.file_name;
    if (finalNewName && !finalNewName.toLowerCase().endsWith('.mp3')) {
        finalNewName += '.mp3';
    }

    const btn = document.querySelector(`#lib-tracks-list-${animeIdx} > div:nth-child(${trackIdx + 1}) button[onclick^="processSingleLibraryTrack"]`);
    if (!btn || btn.disabled) return;

    const originalText = btn.innerText;
    btn.disabled = true;
    btn.innerText = "⏳";
    btn.className = "px-3 py-1 bg-neutral-800 text-neutral-500 rounded text-[11px] font-semibold cursor-not-allowed";

    showToast(`Processing track: ${track.file_name}...`, "info");

    try {
        const response = await fetch('/api/library/process', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_path: track.file_path,
                new_name: finalNewName,
                normalize: track.normalize,
                fades: track.fades,
                tag: track.tag,
                startTime: track.startTime,
                endTime: track.endTime
            })
        });
        
        const data = await response.json();
        if (data.success) {
            showToast(`${finalNewName} processed successfully!`, "success");
            btn.innerText = "✅";
            btn.className = "px-3 py-1 bg-green-900/30 border border-green-800 text-green-400 rounded text-[11px] font-semibold";
            
            if (autoReload) {
                setTimeout(() => {
                    loadLibraryData(true);
                }, 1000);
            }
            
            setTimeout(() => {
                btn.disabled = false;
                btn.innerText = originalText;
                btn.className = "px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded text-[11px] font-semibold transition-colors";
            }, 3000);
            
            return true;
        } else {
            showToast(`Error: ${data.message}`, "error");
            btn.disabled = false;
            btn.innerText = "❌";
            btn.className = "px-3 py-1 bg-red-900/30 border border-red-800 text-red-400 rounded text-[11px] font-semibold";
            return false;
        }
    } catch (err) {
        console.error(err);
        showToast("Connection to server failed.", "error");
        btn.disabled = false;
        btn.innerText = originalText;
        btn.className = "px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded text-[11px] font-semibold transition-colors";
        return false;
    }
}

async function deleteSingleLibraryTrack(animeIdx, trackIdx) {
    const track = libraryData[animeIdx].tracks[trackIdx];
    if (confirm(`Are you sure you want to permanently delete: ${track.file_name}?`)) {
        try {
            const response = await fetch('/api/library/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: track.file_path })
            });
            const data = await response.json();
            if (data.success) {
                showToast("File deleted successfully.", "success");
                loadLibraryData();
            } else {
                showToast(`Error deleting file: ${data.message}`, "error");
            }
        } catch (err) {
            console.error(err);
            showToast("Connection error.", "error");
        }
    }
}

const LIBRARY_ACTIONS = {
    normalize: { label: "normalize the volume of", options: { normalize: true, audio_fx: false, metadata: false, organize: false } },
    metadata: { label: "embed metadata and artwork into", options: { normalize: false, audio_fx: false, metadata: true, organize: false } },
    structure: { label: "organize the folder structure of", options: { normalize: false, audio_fx: false, metadata: false, organize: true } }
};

// Folders the Library Manager is showing: checked folders, or the current one when nothing is checked
function getLibrarySelection() {
    const selectedFolders = getCheckedFolders();
    if (selectedFolders.length === 0) {
        const lastPart = getMediaFolder().split(/[\\/]/).pop();
        if (lastPart) selectedFolders.push(lastPart);
    }
    return selectedFolders;
}

async function startLibraryEnhance(actionType, scope, selectedFolders, targetDescription) {
    const action = LIBRARY_ACTIONS[actionType];
    if (!action) return;
    if (isProcessing) {
        showToast("Themarr is busy with another task. Please wait.", "error");
        return;
    }
    if (!confirm(`This will ${action.label} ${targetDescription}.\n\nDo you want to proceed?`)) return;

    stopLibraryAudio();
    const lufs = parseInt(document.getElementById('libLufsInput').value) || -24;

    try {
        const res = await window.pywebview.api.enhance_local_music(getMediaFolder(), scope, lufs, action.options, selectedFolders);
        showToast(res.message, res.status);
    } catch (err) {
        console.error("Library action error:", err);
        showToast("❌ Server Error (Check Terminal)", "error");
    }
}

async function runBulkLibraryAction(actionType) {
    const selectedFolders = libraryScope === 'all' ? [] : getLibrarySelection();
    const target = libraryScope === 'all' ? "ALL media folders" : `${selectedFolders.length} selected folder(s)`;
    await startLibraryEnhance(actionType, libraryScope, selectedFolders, target);
}

async function runLocalFolderAction(actionType, animeIdx) {
    const media = libraryData[animeIdx];
    if (!media) return;
    await startLibraryEnhance(actionType, 'selected', [media.anime_name], `'${media.anime_name}'`);
}

function adjustLibraryVolume(value) {
    queueAudioVolume = parseFloat(value);
    libraryAudio.volume = queueAudioVolume;
    
    document.querySelectorAll('[id^="libVolume-"]').forEach(slider => {
        slider.value = queueAudioVolume;
    });
    document.querySelectorAll('[id^="trimVolume-"]').forEach(slider => {
        slider.value = queueAudioVolume;
    });
}

async function applyAllTracksInMedia(mediaIdx) {
    const media = libraryData[mediaIdx];
    if (!media || !media.tracks || media.tracks.length === 0) return;
    
    showToast(`Applying changes to all tracks in: ${media.anime_name}...`, "info");
    
    stopLibraryAudio();
    
    const promises = media.tracks.map((_, trackIdx) => processSingleLibraryTrack(mediaIdx, trackIdx, false));
    await Promise.all(promises);
    
    setTimeout(() => {
        loadLibraryData(true);
    }, 1000);
}

let activeTempImportId = null;
let activeMissingFolders = [];

async function exportLibraryBackup() {
    if (!requireMediaFolder()) return;
    const baseFolder = getMediaFolder();

    const confirmMessage = "You are about to export a backup of your media folders along with their theme music tracks.\n\nA compressed ZIP file will be created inside the 'backups' directory.\n\nDo you want to proceed?";
    if (!confirm(confirmMessage)) {
        return; 
    }
    
    const selectedFolders = getCheckedFolders();

    if (selectedFolders.length === 0 && libraryScope === 'selected') {
        const parts = baseFolder.split(/[\\/]/);
        const lastPart = parts[parts.length - 1];
        if (lastPart) {
            selectedFolders.push(lastPart);
        }
    }
    
    showToast("Generating compressed backup zip...", "info");
    
    try {
        const response = await callBackend('export_media_backup', [baseFolder, libraryScope, selectedFolders], '/api/library/backup/export',
            { base_path: baseFolder, scope: libraryScope, selected_folders: selectedFolders });
        if (response.success) {
            if (SERVER_MODE) {
                window.location.href = `/api/library/backup/download?name=${encodeURIComponent(response.filename)}`;
                showToast(`Exported! Downloading ${response.filename}`, "success");
            } else {
                showToast(`Exported! Saved to backups/${response.filename}`, "success");
            }
        } else {
            showToast(`Export failed: ${response.message}`, "error");
        }
    } catch (err) {
        console.error(err);
        showToast("Backup export failed.", "error");
    }
}

async function importLibraryBackup() {
    if (!requireMediaFolder()) return;
    const baseFolder = getMediaFolder();

    showToast("📂 Select backup ZIP file...", "info");

    try {
        const selectRes = SERVER_MODE
            ? await uploadBackupFile()
            : await callBackend('select_backup_file', [], '/api/library/backup/select_file');

        if (!selectRes || !selectRes.success || !selectRes.file_path) {
            showToast("Import cancelled or no file selected.", "info");
            return;
        }

        const zipPath = selectRes.file_path;
        showToast("⏳ Analyzing backup files...", "info");

        const analyzeRes = await callBackend('analyze_backup', [zipPath, baseFolder], '/api/library/backup/analyze',
            { zip_path: zipPath, base_path: baseFolder });

        if (!analyzeRes.success) {
            showToast("Error analyzing backup: " + analyzeRes.message, "error");
            return;
        }

        activeTempImportId = analyzeRes.temp_import_id;
        activeMissingFolders = analyzeRes.missing_folders;

        if (activeMissingFolders && activeMissingFolders.length > 0) {
            const listEl = document.getElementById('importMissingFoldersList');
            if (listEl) {
                listEl.innerHTML = activeMissingFolders.map(folder => `
                        <div class="flex items-center gap-2 text-xs text-neutral-300 py-0.5">
                            <span class="text-neutral-500 text-[11px]">📁</span>
                            <span class="truncate font-medium">${folder}</span>
                        </div>
                    `).join('');
            }
            document.getElementById('importBackupModal').classList.remove('hidden');
        } else {
            await finalizeImportDecision("create_all");
        }

    } catch (err) {
        console.error("Backup import error:", err);
        showToast("Backup import analysis failed.", "error");
    }
}

// Server mode: lets the user pick a zip in the browser and uploads it; same shape as select_backup_file
function uploadBackupFile() {
    return new Promise(resolve => {
        const input = document.getElementById('backupUploadInput');
        input.value = '';
        input.onchange = async () => {
            const file = input.files[0];
            if (!file) return resolve({ success: false });
            showToast(`⏳ Uploading ${file.name}...`, "info");
            const form = new FormData();
            form.append('file', file);
            try {
                resolve(await (await fetch('/api/library/backup/upload', { method: 'POST', body: form })).json());
            } catch (err) {
                console.error("Backup upload error:", err);
                resolve({ success: false });
            }
        };
        input.click();
    });
}

async function finalizeImportDecision(decision) {
    const modal = document.getElementById('importBackupModal');
    if (modal) modal.classList.add('hidden');

    if (!activeTempImportId) return;

    if (decision === 'cancel') {
        showToast("Import cancelled.", "info");
        await callBackend('finalize_backup_import', [activeTempImportId, "", 'cancel', []], '/api/library/backup/finalize',
            { temp_import_id: activeTempImportId, base_path: "", decision: 'cancel', missing_folders: [] });
        activeTempImportId = null;
        activeMissingFolders = [];
        return;
    }

    showToast("Restoring music tracks...", "info");
    const baseFolder = getMediaFolder();

    try {
        const res = await callBackend('finalize_backup_import', [activeTempImportId, baseFolder, decision, activeMissingFolders], '/api/library/backup/finalize',
            { temp_import_id: activeTempImportId, base_path: baseFolder, decision: decision, missing_folders: activeMissingFolders });

        if (res.success) {
            showToast(res.message, "success");
            loadLibraryData(true);
        } else {
            showToast("Import failed: " + res.message, "error");
        }
    } catch (err) {
        console.error("Finalize import error:", err);
        showToast("Import execution failed.", "error");
    } finally {
        activeTempImportId = null;
        activeMissingFolders = [];
    }
}

let assistantAudio = new Audio();
let assistantPlayingRow = null;
let assistantMediaList = [];

async function openAssistantModal() {
    if (!requireMediaFolder()) return;
    const baseFolder = getMediaFolder();

    assistantMediaList = [];
    stopAssistantAudio();

    document.getElementById('assistantModal').classList.remove('hidden');
    document.getElementById('assistantScanLoader').classList.remove('hidden');
    document.getElementById('assistantEmptyState').classList.add('hidden');
    document.getElementById('assistantContent').classList.add('hidden');
    document.getElementById('assistantFooter').classList.add('hidden');

    try {
        const res = await callBackend('scan_missing_themes', [baseFolder, "all"], '/api/library/assistant/scan',
            { base_path: baseFolder, scope: "all" });

        if (!res.success) {
            showToast("Failed to scan library: " + res.message, "error");
            closeAssistantModal();
            return;
        }

        assistantMediaList = res.missing_media || [];
        document.getElementById('assistantScanLoader').classList.add('hidden');

        if (assistantMediaList.length === 0) {
            document.getElementById('assistantEmptyState').classList.remove('hidden');
            return;
        }

        document.getElementById('assistantContent').classList.remove('hidden');
        document.getElementById('assistantFooter').classList.remove('hidden');

        const container = document.getElementById('assistantMediaList');
        container.innerHTML = assistantMediaList.map((media, idx) => `
                <div id="assistant-row-${idx}" class="flex flex-col gap-2 p-3 bg-neutral-900/40 hover:bg-neutral-850/30 border border-neutral-800 rounded-md transition-all">
                    <div class="flex items-center justify-between gap-3 flex-wrap">
                        <div class="flex items-center gap-2.5 min-w-[200px] flex-1">
                            <input type="checkbox" id="assistant-check-${idx}" checked class="w-3.5 h-3.5 accent-blue-500 rounded border-gray-700 bg-gray-800 cursor-pointer">
                            <span class="text-neutral-500 text-[11px]">📁</span>
                            <div class="flex flex-col min-w-0">
                                <span class="text-xs font-semibold text-neutral-200 truncate" title="${escapeHtml(media.folder_name)}">${escapeHtml(media.folder_name)}</span>
                                <span id="assistant-meta-${idx}" class="text-[9px] text-neutral-500 font-bold uppercase tracking-wider text-blue-500">Resolving official metadata...</span>
                            </div>
                        </div>
                        
                        <!-- Dynamic Suggestions area -->
                        <div id="assistant-sugg-container-${idx}" class="flex items-center gap-2 min-w-[280px] flex-1 justify-end">
                            <div class="flex items-center gap-1.5 text-[10px] text-neutral-500">
                                <div class="w-3 h-3 border border-neutral-600 border-t-transparent rounded-full animate-spin"></div>
                                <span>Finding themes...</span>
                            </div>
                        </div>
                    </div>
                </div>
            `).join('');

        assistantMediaList.forEach((media, idx) => {
            fetchSuggestionsForMediaRow(media.folder_name, idx, media.folder_path);
        });

    } catch (err) {
        console.error("Theme Assistant scan error:", err);
        showToast("Error connecting to local server.", "error");
        closeAssistantModal();
    }
}

function closeAssistantModal() {
    stopAssistantAudio();
    document.getElementById('assistantModal').classList.add('hidden');
}

async function fetchSuggestionsForMediaRow(folderName, idx, folderPath) {
    try {
        const res = await callBackend('get_media_theme_suggestions', [folderName, folderPath], '/api/library/assistant/suggestions',
            { folder_name: folderName, folder_path: folderPath });

        const suggContainer = document.getElementById(`assistant-sugg-container-${idx}`);
        const metaEl = document.getElementById(`assistant-meta-${idx}`);

        if (!res.success || !res.suggestions || res.suggestions.length === 0) {
            metaEl.innerText = "No suggestions found";
            metaEl.className = "text-[9px] text-red-500 font-bold uppercase tracking-wider";
            suggContainer.innerHTML = `
                <span class="text-[10px] text-neutral-500 italic">No themes found. Skip or search manually.</span>
            `;
            const chk = document.getElementById(`assistant-check-${idx}`);
            if (chk) chk.checked = false;
            return;
        }

        metaEl.innerText = res.genres ? `${res.genres}` : "Media (No genres)";
        metaEl.title = `Official Name: ${res.official_name}`;

        const optionsHTML = res.suggestions.map((sugg, sIdx) => {
            return `
                <option value="${escapeHtml(sugg.url)}" data-title="${escapeHtml(sugg.title)}" class="bg-neutral-900 text-neutral-200">
                    #${sIdx + 1}: ${escapeHtml(sugg.title.substring(0, 42))}... (${sugg.duration})
                </option>
            `;
        }).join('');

        const defaultFilename = `${res.official_name} - Theme`;

        suggContainer.innerHTML = `
            <div class="flex items-center gap-2 w-full justify-end flex-wrap">
                <input type="text" id="assistant-input-name-${idx}" value="${escapeHtml(defaultFilename)}"  
                       class="bg-neutral-950 border border-neutral-800 text-[10px] text-neutral-300 rounded px-2 py-1 w-44 focus:outline-none focus:border-blue-500" 
                       placeholder="Custom MP3 file name...">
                       
                <select id="assistant-select-${idx}" onchange="updateAssistantInputName(${idx})" 
                        class="bg-neutral-950 border border-neutral-800 text-[10px] text-neutral-400 rounded px-2 py-1 w-48 focus:outline-none cursor-pointer">
                    ${optionsHTML}
                </select>
                
                <button id="assistant-play-${idx}" onclick="toggleAssistantPreview(${idx})" 
                        class="w-6 h-6 rounded-full bg-neutral-800 hover:bg-blue-600 border border-neutral-700/50 hover:border-blue-500 text-neutral-400 hover:text-white flex items-center justify-center text-[10px] transition-all cursor-pointer shadow-sm" 
                        title="Preview Audio">
                    ▶
                </button>
            </div>
        `;

        updateAssistantInputName(idx);

    } catch (err) {
        console.error(`Error suggestions for index ${idx}:`, err);
        const suggContainer = document.getElementById(`assistant-sugg-container-${idx}`);
        if (suggContainer) {
            suggContainer.innerHTML = `<span class="text-[10px] text-red-500">Error fetching suggestions</span>`;
        }
    }
}

function updateAssistantInputName(idx) {
    const select = document.getElementById(`assistant-select-${idx}`);
    if (!select) return;
    const selectedOption = select.options[select.selectedIndex];
    const originalTitle = selectedOption.getAttribute('data-title');
    const input = document.getElementById(`assistant-input-name-${idx}`);
    
    if (input) {
        input.value = originalTitle
            .replace(/[\[(]\s*(Official (Music )?Video|Official Audio)\s*[\])]|Official Music Video|\b(HD|1080p|Full)\b/gi, '')
            .replace(/[\[(]\s*[\])]/g, '')
            .replace(/[\\/|*?:"<>]/g, '-')
            .replace(/\s+/g, ' ')
            .trim();
    }
}

async function toggleAssistantPreview(idx) {
    const select = document.getElementById(`assistant-select-${idx}`);
    if (!select) return;
    const url = select.value;
    const playBtn = document.getElementById(`assistant-play-${idx}`);

    if (assistantPlayingRow === idx) {
        if (!assistantAudio.paused) {
            assistantAudio.pause();
            playBtn.innerText = "▶";
            playBtn.classList.remove('bg-blue-600', 'text-white', 'border-blue-500');
            playBtn.classList.add('bg-neutral-800', 'text-neutral-400', 'border-neutral-700/50');
        } else {
            assistantAudio.play();
            playBtn.innerText = "⏸";
        }
        return;
    }

    stopAssistantAudio();
    playBtn.innerText = "⏳";
    playBtn.disabled = true;

    try {
        const streamData = await callBackend('get_stream_info', [url], '/api/get_stream_info', { url: url });

        if (streamData && streamData.success) {
            assistantPlayingRow = idx;
            assistantAudio.src = streamData.url;
            assistantAudio.volume = queueAudioVolume;
            
            assistantAudio.oncanplay = () => {
                playBtn.disabled = false;
                playBtn.innerText = "⏸";
                playBtn.classList.add('bg-blue-600', 'text-white', 'border-blue-500');
                playBtn.classList.remove('bg-neutral-800', 'text-neutral-400', 'border-neutral-700/50');
                assistantAudio.play();
            };

            assistantAudio.onended = () => {
                stopAssistantAudio();
            };
        } else {
            showToast("Could not load preview stream.", "error");
            playBtn.innerText = "▶";
            playBtn.disabled = false;
        }
    } catch (err) {
        console.error("Assistant preview play error:", err);
        playBtn.innerText = "▶";
        playBtn.disabled = false;
    }
}

function stopAssistantAudio() {
    assistantAudio.pause();
    assistantAudio.src = "";
    if (assistantPlayingRow !== null) {
        const playBtn = document.getElementById(`assistant-play-${assistantPlayingRow}`);
        if (playBtn) {
            playBtn.innerText = "▶";
            playBtn.classList.remove('bg-blue-600', 'text-white', 'border-blue-500');
            playBtn.classList.add('bg-neutral-800', 'text-neutral-400', 'border-neutral-700/50');
            playBtn.disabled = false;
        }
    }
    assistantPlayingRow = null;
}

async function triggerAssistantDownloads() {
    const baseFolder = getMediaFolder();
    const downloadList = [];

    assistantMediaList.forEach((media, idx) => {
        const chk = document.getElementById(`assistant-check-${idx}`);
        if (chk && chk.checked) {
            const select = document.getElementById(`assistant-select-${idx}`);
            const input = document.getElementById(`assistant-input-name-${idx}`);
            if (select && input) {
                downloadList.push({
                    folder_name: media.folder_name,
                    folder_path: media.folder_path,
                    track_name: input.value.trim(),
                    youtube_url: select.value
                });
            }
        }
    });

    if (downloadList.length === 0) {
        showToast("⚠️ Please select at least one media folder to download!", "error");
        return;
    }

    closeAssistantModal();
    showToast("🤖 Auto-downloads started in the background!", "success");

    try {
        const options = {
            normalize: document.getElementById('assistantChkNormalize').checked,
            fades: document.getElementById('assistantChkFades').checked,
            tags: document.getElementById('assistantChkTags').checked
        };
        const res = await callBackend('process_assistant_downloads', [downloadList, baseFolder, options], '/api/library/assistant/download',
            { download_list: downloadList, base_folder: baseFolder, options: options });

        if (res.success) {
            isProcessing = true;
            isCompleted = false;
        } else {
            showToast("Failed to initiate downloads: " + res.message, "error");
        }
    } catch (err) {
        console.error("Trigger assistant downloads error:", err);
        showToast("Server communication error.", "error");
    }
}