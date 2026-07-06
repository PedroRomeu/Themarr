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
                enhance_local_music: async (folder, batchMode, lufs, options) => {
                    let res = await fetch('/api/enhance_local_music', { 
                        method: 'POST', 
                        headers: { 'Content-Type': 'application/json' }, 
                        body: JSON.stringify({ folder: folder, batchMode: batchMode, lufs: lufs, options: options }) 
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
                }
            }
        };
        window.dispatchEvent(new CustomEvent('pywebviewready'));
    }
}, 500);

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
    const folder = document.getElementById('folderPath').innerText; 
    if (folder === "No folder selected..." || folder.trim() === "") {
        showToast("Please select a Media Directory first!", "error");
        return;
    }
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
    toastIcon.innerText = status === 'success' || status === 'sucesso' ? '✅' : '❌';
    
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
    let selectedFolders = [];
    const checkboxes = document.querySelectorAll('.folder-checkbox:checked');
    checkboxes.forEach(chk => selectedFolders.push(chk.value));

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
    const folder = document.getElementById('folderPath').innerText;
    showToast("🗑️ Deleting files...", "success");

    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.delete_music_folder(folder, scope, selectedFolders)
        .then(res => {
            showToast(res.message || res.mensagem, res.status);
        })
        .catch(err => {
            console.error("Delete Python Error:", err);
            showToast("❌ Server Error (Check Terminal)", "error");
        });
    }
}

function openEnhanceModal() {
    const folder = document.getElementById('folderPath').innerText; 
    if (folder === "No folder selected..." || folder.trim() === "") {
        showToast("Please select a Media Directory first!", "error");
        return;
    }
    document.getElementById('enhanceModal').classList.remove('hidden');
}

function closeEnhanceModal() {
    document.getElementById('enhanceModal').classList.add('hidden');
}

async function triggerEnhance(scope) {
    closeEnhanceModal();
    
    const folder = document.getElementById('folderPath').innerText;
    const currentLufs = parseInt(document.getElementById('lufsInput').value) || -24; 
    
    let selectedFolders = [];
    const checkboxes = document.querySelectorAll('.folder-checkbox:checked');
    checkboxes.forEach(chk => selectedFolders.push(chk.value));
    
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
                showToast(res.message || res.mensagem, res.status);
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
            window.updateGlobalProgress(data.percentage, data.statusText || data.textoStatus, data.percentageText || data.textoPorcentagem);
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
            res.folders.forEach(folder => {
                const shouldBeChecked = (res.selected_anime && res.selected_anime === folder) ? 'checked' : '';
                
                container.innerHTML += `
                    <label class="flex items-center gap-2 hover:bg-[#333333] p-1.5 rounded cursor-pointer transition">
                        <input type="checkbox" value="${folder}" class="folder-checkbox w-3.5 h-3.5 accent-blue-500 rounded border-gray-700 bg-gray-800" ${shouldBeChecked}>
                        <span class="text-xs text-gray-300 truncate">${folder}</span>
                    </label>
                `;
            });
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
        document.getElementById('progressBar').style.width = "0%";
        document.getElementById('percentText').innerText = "0%";
        document.getElementById('statusText').innerText = "Ready";
        const btnStart = document.getElementById('btnStart');
        btnStart.className = "w-full bg-neutral-800 text-neutral-500 py-3 rounded-md font-bold text-sm mb-3 cursor-not-allowed border border-neutral-700 transition-colors";
        btnStart.innerText = "▶ START PROCESSING";
        btnStart.disabled = true;
        document.getElementById('logContainer').innerText = "System ready. Awaiting tasks...\n";
        updateQueueUI();
    }

    if(window.pywebview) {
        window.pywebview.api.select_folder().then(response => {
            if(response.success || response.sucesso) {
                let returnedPath = response.path || response.caminho;
                document.getElementById('folderPath').innerText = returnedPath;
                loadFolderCheckboxes(returnedPath);
                globalDestinationOptions = ['Main Theme'];
                
                let returnedSeasons = response.seasons || response.temporadas || [];
                if(returnedSeasons.length === 0) {
                    let folderName = returnedPath.split('\\').pop().split('/').pop();
                    globalDestinationOptions.push(`Season 01. ${folderName}`);
                } else {
                    globalDestinationOptions.push(...returnedSeasons);
                }
                updateMainDropdown();
            }
        });
    } else { alert("Connect to Python first."); }
}

function updateMainDropdown() {
    const select = document.getElementById('destinationSelect');
    select.innerHTML = '';
    globalDestinationOptions.forEach(op => {
        select.innerHTML += `<option value="${op}" class="bg-neutral-800 text-white">${op}</option>`;
    });
}

function addToQueue() {
    if(isProcessing) return; 
    
    if(isCompleted) {
        isCompleted = false;
        musicQueue = [];
        document.getElementById('progressBar').style.width = "0%";
        document.getElementById('percentText').innerText = "0%";
        document.getElementById('statusText').innerText = "Ready";
        document.getElementById('logContainer').innerText = "System ready. Awaiting tasks...\n";
        updateQueueUI();
    }

    const link = document.getElementById('linkInput').value.trim();
    const name = document.getElementById('nameInput').value.trim();
    const destination = document.getElementById('destinationSelect').value;
    const lufs = document.getElementById('lufsInput').value;
    const pathTxt = document.getElementById('folderPath').innerText;

    if(!link || (!link.startsWith("https://") && !link.startsWith("http://"))) {
        showToast("Invalid URL format! The address must start with 'http://' or 'https://'.");
        return;
    }
    if(!name) { showToast("Please enter a track name!"); return; }
    if(!destination || destination === "") { showToast("Please select a target folder!"); return; }
    if(pathTxt === "No folder selected...") { showToast("Please browse for a media folder first!"); return; }

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
        audio_fx: customFx 
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
    const btnStart = document.getElementById('btnStart');

    if (musicQueue.length === 0) {
        container.innerHTML = '<div class="flex h-full items-center justify-center text-neutral-600 text-sm">Queue is empty.</div>';
        if (!isCompleted) {
            btnStart.className = "w-full bg-neutral-800 text-neutral-500 py-3 rounded-md font-bold text-sm mb-3 cursor-not-allowed border border-neutral-700 transition-colors";
            btnStart.disabled = true;
            btnStart.innerText = "▶ START PROCESSING";
        }
        return;
    }

    if (!isProcessing && !isCompleted) {
        btnStart.className = "w-full bg-blue-600 hover:bg-blue-500 text-white py-3 rounded-md font-bold text-sm mb-3 cursor-pointer shadow-lg transition-colors";
        btnStart.disabled = false;
        btnStart.innerText = "▶ START PROCESSING";
    }

    container.innerHTML = "";
    musicQueue.forEach((item, index) => {
        let optionsHTML = '';
        globalDestinationOptions.forEach(op => {
            let selected = (op === item.destination) ? 'selected' : '';
            optionsHTML += `<option value="${op}" class="bg-neutral-800 text-white" ${selected}>${op}</option>`;
        });

        let statusIcon = "";
        let itemOpacity = "";
        if (item.status === 'processing' || item.status === 'processando') {
            statusIcon = `<svg class="animate-spin h-4 w-4 text-blue-500 ml-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>`;
        } else if (item.status === 'completed' || item.status === 'concluido') {
            statusIcon = `<span class="text-green-500 ml-2 font-bold">✅</span>`;
            itemOpacity = "opacity-60"; 
        } else if (item.status === 'error' || item.status === 'erro') {
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

        const queueItemHTML = `
        <div id="queue-item-${index}" data-status="${item.status}" draggable="${dragEnable}" 
                ondragstart="dragStart(${index}, event)" 
                ondragend="dragEnd(event)"
                ondragover="dragOver(event)" 
                ondrop="drop(${index})"
                class="group flex items-center justify-between bg-neutral-800/50 hover:bg-neutral-800 border border-neutral-700/50 hover:border-neutral-600 p-2 rounded text-sm transition-colors ${cursorState} ${itemOpacity}">
            
            ${!isProcessing ? '<span class="text-neutral-600 group-hover:text-neutral-400 mr-2 text-xs select-none">⋮⋮</span>' : ''}
            
            <div class="status-icon flex items-center">${statusIcon}</div>

            <input type="text" value="${item.name}" onchange="editQueueName(${index}, this.value)" ${isProcessing ? 'disabled' : ''}
                    class="bg-transparent text-white font-semibold focus:outline-none focus:border-b focus:border-blue-500 w-1/4 px-1 truncate cursor-text ml-2 ${pointerState}">
            
            <select onchange="editQueueDestination(${index}, this.value)" ${isProcessing ? 'disabled' : ''}
                    class="bg-transparent text-neutral-400 text-xs focus:outline-none cursor-pointer w-1/4 px-1 appearance-none hover:text-neutral-300 ${pointerState}">
                ${optionsHTML}
            </select>
            
            <span class="text-blue-400 text-xs truncate flex-grow text-right px-2 opacity-60">${item.link}</span>
            
            ${!isProcessing ? `<button onclick="removeFromQueue(${index})" class="text-neutral-500 hover:text-red-400 font-bold ml-1 opacity-0 group-hover:opacity-100 transition-opacity px-2 cursor-pointer">✕</button>` : ''}
        </div>
        `;
        container.innerHTML += queueItemHTML;
    });
}

function retrySingleQueueItem(index) {
    const music = musicQueue[index]; 
    if (!music) return;
    
    const mainCount = musicQueue.filter(m => m.destination === 'Main Theme').length;
    music.has_multi_main = mainCount > 1;

    const folderPath = document.getElementById('folderPath').innerText;
    if (!folderPath || folderPath === "No folder selected...") {
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
    if (isCompleted) {
        musicQueue = [];
        document.getElementById('queueContainer').innerHTML = '<div class="flex h-full items-center justify-center text-neutral-600 text-sm">Queue is empty.</div>';
        
        document.getElementById('progressBar').style.width = "0%";
        document.getElementById('percentText').innerText = "0%";
        document.getElementById('statusText').innerText = "Ready";
        
        const btnStart = document.getElementById('btnStart');
        btnStart.className = "w-full bg-neutral-800 text-neutral-500 py-3 rounded-md font-bold text-sm mb-3 cursor-not-allowed border border-neutral-700 transition-colors";
        btnStart.innerText = "▶ START PROCESSING";
        btnStart.disabled = true;
        
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

    const mainFolder = document.getElementById('folderPath').innerText.trim();
    if (!mainFolder || mainFolder === "No folder selected...") {
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

    if(newStatus === 'processing' || newStatus === 'processando') {
        statusDiv.innerHTML = `<svg class="animate-spin h-4 w-4 text-blue-500 ml-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>`;
        item.classList.remove('opacity-60', 'text-red-400');
        item.classList.add('opacity-100');
    } else if(newStatus === 'completed' || newStatus === 'concluido') {
        statusDiv.innerHTML = `<span class="text-green-500 ml-2 font-bold">✅</span>`;
        item.classList.remove('opacity-100', 'text-red-400');
        item.classList.add('opacity-60');
        if(musicQueue[index]) musicQueue[index].status = 'completed';
    } else if(newStatus === 'error' || newStatus === 'erro') {
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
        if(item.status === 'pending' || item.status === 'processing' || item.status === 'pendente' || item.status === 'processando') {
            item.status = 'completed';
        }
    });

    updateQueueUI();
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

        msgEl.innerText = response.message || response.mensagem;
        if(response.status === 'success' || response.status === 'sucesso') {
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

window.addEventListener('pywebviewready', function() {
    loadSettings();
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