document.addEventListener('DOMContentLoaded', function() {
    const API_URL = '/api';
    let ws;
    let currentData = {};
    let lastPhoneStatus = '';
    
    // --- Элементы DOM ---
    const elements = {
        addDonationForm: document.getElementById('add-donation-form'),
        goalForm: document.getElementById('goal-form'),
        settingsForm: document.getElementById('settings-form'),
        resetDonationsBtn: document.getElementById('reset-donations-btn'),
        testDonationBtn: document.getElementById('test-donation-btn'),
        donationsList: document.getElementById('donations-list'),
        phoneStatusIndicator: document.getElementById('phone-status-indicator'),
        consoleOutput: document.getElementById('console-output'),
        goalTitleInput: document.getElementById('goal-title'),
        goalTargetInput: document.getElementById('goal-target'),
        minAmountInput: document.getElementById('min-amount'),
        ttsEnabledInput: document.getElementById('tts-enabled'),
        ttsVolumeInput: document.getElementById('tts-volume'),
    };

    // --- API запросы ---
    async function fetchApi(endpoint, method = 'GET', body = null) {
        const options = {
            method,
            headers: { 'Content-Type': 'application/json' },
        };
        if (body) {
            options.body = JSON.stringify(body);
        }
        try {
            const response = await fetch(`${API_URL}${endpoint}`, options);
            if (!response.ok) {
                const errorData = await response.json();
                logToConsole(`Ошибка API ${response.status}: ${errorData.error || response.statusText}`, 'error');
                return null;
            }
            if (response.headers.get("Content-Type")?.includes("application/json")) {
                return response.json();
            }
            return { status: 'success' };
        } catch (error) {
            logToConsole(`Сетевая ошибка: ${error}`, 'error');
            return null;
        }
    }

    // --- Обновление статуса Phone Link ---
    function updatePhoneStatus(status) {
        if (!elements.phoneStatusIndicator) return;
        const indicator = elements.phoneStatusIndicator;
        const dot = indicator.querySelector('.status-dot');
        const text = indicator.querySelector('.status-text');
        
        if (status && status.connected) {
            dot.className = 'status-dot status-connected';
            text.textContent = status.message || 'Подключен';
        } else if (status) {
            dot.className = 'status-dot status-disconnected';
            text.textContent = status.message || 'Отключен';
        } else {
            dot.className = 'status-dot status-disconnected';
            text.textContent = 'Нет данных';
        }
    }

    // --- Рендеринг данных ---
    function renderAll() {
        if (!currentData) return;
        renderDonationsList();
        updateForms();
        if (currentData.phone_status) {
            updatePhoneStatus(currentData.phone_status);
        }
    }

    function escapeHtml(unsafe) {
        if (typeof unsafe !== 'string') return '';
        return unsafe.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    }

    function renderDonationsList() {
        const donations = currentData.donations || [];
        const listEl = elements.donationsList;
        if (donations.length === 0) {
            listEl.innerHTML = '<p>История донатов пуста.</p>';
            return;
        }
        listEl.innerHTML = donations.slice(0, 20).map(d => `
            <div class="donation-item">
                <div class="donation-item-header">
                    <span class="donation-name">${escapeHtml(d.name)}</span>
                    <span class="donation-amount">${d.amount.toLocaleString('ru-RU')} ₸</span>
                </div>
                ${d.message ? `<p class="donation-message">${escapeHtml(d.message)}</p>` : ''}
                <div class="donation-actions">
                    <button onclick="replayDonation(${d.id})" class="btn btn-sm btn-secondary">Повторить</button>
                    <button onclick="deleteDonation(${d.id})" class="btn btn-sm btn-danger">Удалить</button>
                </div>
            </div>
        `).join('');
    }

    function updateForms() {
        if (currentData.goal && elements.goalTitleInput) {
            elements.goalTitleInput.value = currentData.goal.title || '';
            elements.goalTargetInput.value = currentData.goal.target || '';
        }
        if (currentData.settings && elements.minAmountInput) {
            elements.minAmountInput.value = currentData.settings.min_amount || 0;
            elements.ttsEnabledInput.checked = currentData.settings.tts_enabled || false;
            elements.ttsVolumeInput.value = currentData.settings.tts_volume || 0.7;
        }
    }

    // --- Глобальные функции для кнопок ---
    window.replayDonation = async (donationId) => fetchApi(`/replay_donation/${donationId}`, 'POST');
    window.deleteDonation = async (donationId) => {
        if (confirm('Удалить этот донат?')) {
            await fetchApi(`/delete_donation/${donationId}`, 'POST');
        }
    };

    // --- Логирование в консоль ---
    function logToConsole(message, type = 'info') {
        const consoleEl = elements.consoleOutput;
        if (!consoleEl) return;
        
        const timestamp = new Date().toLocaleTimeString('ru-RU');
        const logEntry = document.createElement('div');
        logEntry.className = `console-entry console-${type}`;
        logEntry.innerHTML = `<span class="console-time">[${timestamp}]</span> ${message}`;
        consoleEl.appendChild(logEntry);
        
        while (consoleEl.children.length > 50) {
            consoleEl.removeChild(consoleEl.firstChild);
        }
        consoleEl.scrollTop = consoleEl.scrollHeight;
    }

    // --- WebSocket ---
    function handleWebSocketMessage(message) {
        if (message.type === 'full_update') {
            logToConsole('🔄 Получено полное обновление данных от сервера.', 'info');
            currentData = message.data;
            renderAll();
        } else if (message.type === 'show_alert') {
            const d = message.data;
            logToConsole(`🔔 Новый донат: ${escapeHtml(d.name)} - ${d.amount}₸`, 'success');
        } else if (message.type === 'phone_status_update') {
            const status = message.data;
            if (JSON.stringify(status) !== lastPhoneStatus) {
                logToConsole(`📱 Статус Phone Link: ${status.message}`, 'info');
                updatePhoneStatus(status);
                lastPhoneStatus = JSON.stringify(status);
            }
        }
    }

    function connectWebSocket() {
        const userIdInput = document.querySelector('input[data-user-id]');
        if (!userIdInput) {
            logToConsole('Критическая ошибка: не удалось найти user ID на странице.', 'error');
            return;
        }
        const userId = userIdInput.dataset.userId;
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws?user_id=${userId}`);

        ws.onopen = () => logToConsole('WebSocket соединение установлено.', 'success');
        ws.onmessage = (event) => handleWebSocketMessage(JSON.parse(event.data));
        ws.onclose = () => {
            logToConsole('WebSocket соединение закрыто. Попытка переподключения...', 'error');
            setTimeout(connectWebSocket, 3000);
        };
        ws.onerror = (error) => {
            logToConsole('WebSocket ошибка.', 'error');
            console.error('WebSocket Error:', error);
            ws.close();
        };
    }

    // --- Обработчики событий ---
    function initEventListeners() {
        elements.addDonationForm?.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = {
                name: formData.get('name') || 'Аноним',
                amount: parseFloat(formData.get('amount')),
                message: formData.get('message')
            };
            const result = await fetchApi('/add_manual_donation', 'POST', data);
            if(result) e.target.reset();
        });

        elements.goalForm?.addEventListener('submit', (e) => {
            e.preventDefault();
            const data = {
                title: elements.goalTitleInput.value,
                target: parseFloat(elements.goalTargetInput.value)
            };
            fetchApi('/update_goal', 'POST', data);
        });
        
        elements.settingsForm?.addEventListener('submit', (e) => {
            e.preventDefault();
            const data = {
                min_amount: parseFloat(elements.minAmountInput.value),
                tts_enabled: elements.ttsEnabledInput.checked,
                tts_volume: parseFloat(elements.ttsVolumeInput.value)
            };
            fetchApi('/update_settings', 'POST', data);
        });

        elements.resetDonationsBtn?.addEventListener('click', () => {
            if (confirm('Вы уверены, что хотите сбросить всю историю донатов и обнулить счетчик сбора? Это действие необратимо.')) {
                fetchApi('/reset_donations', 'POST');
            }
        });
        
        elements.testDonationBtn?.addEventListener('click', () => fetchApi('/test_donation', 'POST'));
    }

    // --- Инициализация ---
    logToConsole('🚀 Панель управления загружена', 'info');
    connectWebSocket();
    loadData();
    initEventListeners();
    setInterval(() => fetchApi('/get_phone_status').then(status => updatePhoneStatus(status)), 10000);
    
    async function loadData() {
        const data = await fetchApi('/get_all_data');
        if (data) {
            currentData = data;
            renderAll();
        }
    }
});

