document.addEventListener('DOMContentLoaded', function() {
    const API_URL = '/api';
    let ws;
    let currentData = {};
    
    // --- Элементы DOM ---
    const elements = {
        addDonationForm: document.getElementById('add-donation-form'),
        goalForm: document.getElementById('goal-form'),
        settingsForm: document.getElementById('settings-form'),
        resetDonationsBtn: document.getElementById('reset-donations-btn'),
        testDonationBtn: document.getElementById('test-donation-btn'),
        donationsList: document.getElementById('donations-list'),
        topDonatorsList: document.getElementById('top-donators-list'),
        phoneStatusIndicator: document.getElementById('phone-status-indicator'),
        consoleOutput: document.getElementById('console-output'),
        
        // Поля форм
        goalTitleInput: document.getElementById('goal-title'),
        goalTargetInput: document.getElementById('goal-target'),
        minAmountInput: document.getElementById('min-amount'),
        // ПОЛЯ TTS УДАЛЕНЫ
        apiKeyInput: document.getElementById('api-key-input')
    };

    // --- API запросы ---
    async function fetchApi(endpoint, method = 'GET', body = null) {
        const options = {
            method,
            headers: { 
                'Content-Type': 'application/json',
                'X-API-Key': elements.apiKeyInput ? elements.apiKeyInput.value : '' 
            },
        };
        if (body) {
            options.body = JSON.stringify(body);
        }
        try {
            const url = endpoint.startsWith(API_URL) ? endpoint : `${API_URL}${endpoint}`;
            const response = await fetch(url, options);
            if (!response.ok) {
                console.error(`Ошибка API: ${response.statusText}`);
                const errorData = await response.json().catch(() => null);
                logToConsole(`Ошибка API ${response.status}: ${errorData?.error || response.statusText}`, 'error');
                return null;
            }
            if (response.headers.get("Content-Type")?.includes("application/json")) {
                return response.json();
            }
            return { status: 'success' };
        } catch (error) {
            console.error('Сетевая ошибка:', error);
            logToConsole('Сетевая ошибка. Проверьте консоль браузера.', 'error');
            return null;
        }
    }

    // --- Обновление статуса Phone Link ---
    function updatePhoneStatus(status) {
        if (!elements.phoneStatusIndicator) return;
        
        const indicator = elements.phoneStatusIndicator;
        const dot = indicator.querySelector('.status-dot');
        const text = indicator.querySelector('.status-text');
        
        if (!status || status.connected === undefined) {
             dot.className = 'status-dot status-disconnected';
             text.textContent = 'Нет данных';
             return;
        }

        if (status.connected) {
            dot.className = 'status-dot status-connected';
            text.textContent = status.message || 'Подключен';
        } else {
            dot.className = 'status-dot status-disconnected';
            text.textContent = status.message || 'Отключен';
        }
    }

    // --- Рендеринг данных ---
    function renderAll() {
        if (!currentData) return;
        renderDonationsList();
        renderTopDonators();
        updateForms();
        updateStats();
        if (currentData.phone_status) {
            updatePhoneStatus(currentData.phone_status);
        } else {
             updatePhoneStatus({ connected: undefined });
        }
    }

    function escapeHtml(unsafe) {
        if (typeof unsafe !== 'string') return '';
        return unsafe
             .replace(/&/g, "&amp;")
             .replace(/</g, "&lt;")
             .replace(/>/g, "&gt;")
             .replace(/"/g, "&quot;")
             .replace(/'/g, "&#039;");
    }

    function renderDonationsList() {
        const donations = currentData.donations || [];
        const listEl = elements.donationsList;
        if (!listEl) return;
        if (donations.length === 0) {
            listEl.innerHTML = '<p>История донатов пуста.</p>';
            return;
        }
        listEl.innerHTML = donations.slice(0, 10).map(d => `
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
    
    function renderTopDonators() {
        const donations = currentData.donations || [];
        const listEl = elements.topDonatorsList;
        if (!listEl) return;
    
        const topDonators = donations.reduce((acc, d) => {
            acc[d.name] = (acc[d.name] || 0) + d.amount;
            return acc;
        }, {});
    
        const sorted = Object.entries(topDonators)
            .sort(([, a], [, b]) => b - a)
            .slice(0, 10);
    
        if (sorted.length === 0) {
            listEl.innerHTML = '<p>Донатов пока нет.</p>';
            return;
        }
    
        listEl.innerHTML = sorted.map(([name, amount], index) => `
            <div class="top-donator-item">
                <span class="donator-rank">#${index + 1}</span>
                <span class="donator-name">${escapeHtml(name)}</span>
                <span class="donator-amount">${amount.toLocaleString('ru-RU')} ₸</span>
            </div>
        `).join('');
    }

    function updateForms() {
        const settings = currentData.settings || {};
        const goal = currentData.goal || {};

        if (elements.goalTitleInput) {
            elements.goalTitleInput.value = goal.title || '';
            elements.goalTargetInput.value = goal.target_amount || '';
        }
        
        if (elements.minAmountInput) {
            elements.minAmountInput.value = settings.min_amount || 0;
        }
    }
    
    function updateStats() {
        const stats = currentData.stats || {};
        if (stats) {
            document.querySelector('.stat-item:nth-child(1) .stat-value').textContent = `${(stats.today.sum || 0).toFixed(2)} ₸`;
            document.querySelector('.stat-item:nth-child(1) .stat-count').textContent = `${stats.today.count || 0} донатов`;
            document.querySelector('.stat-item:nth-child(2) .stat-value').textContent = `${(stats.month.sum || 0).toFixed(2)} ₸`;
            document.querySelector('.stat-item:nth-child(2) .stat-count').textContent = `${stats.month.count || 0} донатов`;
            document.querySelector('.stat-item:nth-child(3) .stat-value').textContent = `${(stats.total.sum || 0).toFixed(2)} ₸`;
            document.querySelector('.stat-item:nth-child(3) .stat-count').textContent = `${stats.total.count || 0} донатов`;
        }
    }

    // --- Глобальные функции для кнопок ---
    window.replayDonation = async function(donationId) {
        const result = await fetchApi(`/api/replay_donation/${donationId}`, 'POST');
        if (result && result.status === 'success') {
            logToConsole(`🔄 Повторное воспроизведение доната #${donationId}`, 'info');
        }
    };

    window.deleteDonation = async function(donationId) {
        console.log(`[ACTION] Запрос на удаление доната #${donationId}`); 
        const result = await fetchApi(`/api/delete_donation/${donationId}`, 'POST');
        if (result && result.status === 'success') {
            logToConsole(`🗑️ Донат #${donationId} удален`, 'info');
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
        
        const entries = consoleEl.querySelectorAll('.console-entry');
        if (entries.length > 10) {
            entries[0].remove();
        }
        
        consoleEl.scrollTop = consoleEl.scrollHeight;
    }

    // --- WebSocket ---
    function connectWebSocket() {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws`);

        ws.onopen = () => {
            console.log('Соединение с WebSocket установлено.');
            logToConsole('Соединение с WebSocket установлено.', 'success');
        };

        ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            handleWebSocketMessage(message);
        };

        ws.onclose = () => {
            console.log('Соединение с WebSocket закрыто. Попытка переподключения...');
            logToConsole('Соединение с WebSocket закрыто. Попытка переподключения...', 'error');
            setTimeout(connectWebSocket, 3000);
        };

        ws.onerror = (error) => {
            console.error('WebSocket ошибка.', 'error');
            logToConsole('WebSocket ошибка.', 'error');
            ws.close();
        };
    }

    // --- Обработчик сообщений WebSocket ---
    function handleWebSocketMessage(message) {
        if (message.type === 'full_update') {
            currentData = message.data;
            renderAll();
        } else if (message.type === 'phone_status_update') {
            updatePhoneStatus(message.data);
        } else if (message.type === 'show_alert') {
            logToConsole(`📢 Новый донат: ${message.data.name} - ${message.data.amount}₸`, 'success');
            loadData();
        }
    }

    // --- Обработчики событий ---
    function initEventListeners() {
        if (elements.addDonationForm) {
            elements.addDonationForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const formData = new FormData(e.target);
                const data = {
                    name: formData.get('name') || 'Аноним',
                    amount: parseFloat(formData.get('amount')),
                    message: formData.get('message')
                };
                const result = await fetchApi('/add_manual_donation', 'POST', data);
                if (result && result.status === 'success') {
                    logToConsole(`➕ Добавлен донат: ${data.name} - ${data.amount}₸`, 'success');
                    e.target.reset();
                }
            });
        }

        if (elements.goalForm) {
            elements.goalForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const data = {
                    title: elements.goalTitleInput.value,
                    target: parseFloat(elements.goalTargetInput.value)
                };
                const result = await fetchApi('/update_goal', 'POST', data);
                if (result && result.status === 'success') {
                    logToConsole(`🎯 Цель обновлена`, 'info');
                }
            });
        }
        
        if (elements.settingsForm) {
            elements.settingsForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const data = {
                    min_amount: parseFloat(elements.minAmountInput.value),
                };
                const result = await fetchApi('/update_settings', 'POST', data);
                if (result && result.status === 'success') {
                    logToConsole(`⚙️ Настройки обновлены`, 'info');
                }
            });
        }
        
        if (elements.resetDonationsBtn) {
            elements.resetDonationsBtn.addEventListener('click', async () => {
                console.log('[ACTION] Запрос на сброс истории донатов.');
                const result = await fetchApi('/reset_donations', 'POST');
                if (result && result.status === 'success') {
                    logToConsole(`🗑️ История донатов сброшена`, 'warning');
                }
            });
        }
        
        if (elements.testDonationBtn) {
            elements.testDonationBtn.addEventListener('click', async () => {
                const result = await fetchApi('/test_donation', 'POST');
                if (result && result.status === 'success') {
                    logToConsole('🧪 Тестовый донат отправлен', 'info');
                }
            });
        }
    }

    // --- Загрузка данных ---
    async function loadData() {
        updatePhoneStatus({ connected: undefined });
        
        const data = await fetchApi('/get_all_data');
        if (data) {
            currentData = data;
            renderAll();
        }
    }

    // --- Инициализация ---
    logToConsole('🚀 Панель управления загружена', 'info');
    connectWebSocket();
    loadData();
    initEventListeners();
});

