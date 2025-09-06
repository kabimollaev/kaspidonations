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
        resetGoalBtn: document.getElementById('reset-goal-btn'),
        testDonationBtn: document.getElementById('test-donation-btn'),
        donationsList: document.getElementById('donations-list'),
        topDonatorsList: document.getElementById('top-donators-list'),
        phoneStatusIndicator: document.getElementById('phone-status-indicator'),
        popoutLink: document.getElementById('popout-link'),
        consoleOutput: document.getElementById('console-output'),
        goalTitleInput: document.getElementById('goal-title'),
        goalTargetInput: document.getElementById('goal-target'),
        minAmountInput: document.getElementById('min-amount'),
        ttsEnabledInput: document.getElementById('tts-enabled'),
        ttsVolumeInput: document.getElementById('tts-volume')
    };
    
    // --- Логирование в консоль на странице ---
    function logToConsole(message, type = 'info') {
        const now = new Date();
        const timestamp = `[${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}]`;
        
        const p = document.createElement('p');
        p.className = `log-${type}`;
        
        const timeSpan = document.createElement('span');
        timeSpan.className = 'log-time';
        timeSpan.textContent = `${timestamp} `;
        
        p.appendChild(timeSpan);
        p.appendChild(document.createTextNode(message));
        
        elements.consoleOutput.appendChild(p);
        elements.consoleOutput.scrollTop = elements.consoleOutput.scrollHeight;
    }

    // --- WebSocket ---
    function connectWebSocket() {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws`);

        ws.onopen = () => {
            logToConsole('WebSocket соединение установлено.', 'success');
        };

        ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            handleWebSocketMessage(message);
        };

        ws.onclose = () => {
            logToConsole('WebSocket соединение закрыто. Попытка переподключения...', 'error');
            setTimeout(connectWebSocket, 3000);
        };

        ws.onerror = (error) => {
            logToConsole('WebSocket ошибка.', 'error');
            console.error('WebSocket Error:', error);
        };
    }

    function handleWebSocketMessage(message) {
        switch (message.type) {
            case 'full_update':
                currentData = message.data;
                renderAll();
                break;
            // Другие типы сообщений (tts, show_alert) обрабатываются в виджетах
        }
    }

    // --- Рендеринг ---
    function renderAll() {
        renderDonationsList();
        renderTopDonators();
        updateForms();
    }

    function escapeHtml(unsafe) {
        return unsafe
             .replace(/&/g, "&amp;")
             .replace(/</g, "&lt;")
             .replace(/>/g, "&gt;")
             .replace(/"/g, "&quot;")
             .replace(/'/g, "&#039;");
    }

    function renderDonationsList() {
        const donations = currentData.donations || [];
        if (donations.length === 0) {
            elements.donationsList.innerHTML = '<p>История пуста.</p>';
            return;
        }
        elements.donationsList.innerHTML = donations.map(d => `
            <div class="donation-item">
                <div class="donation-item-header">
                    <span class="donation-name">${escapeHtml(d.name)}</span>
                    <span class="donation-amount">${d.amount.toLocaleString('ru-RU')} ₸</span>
                </div>
                ${d.message ? `<p class="donation-message">${escapeHtml(d.message)}</p>` : ''}
                <div class="donation-actions">
                    <button class="action-btn" data-id="${d.id}" data-action="replay" title="Повторить">
                        <i class="fas fa-redo"></i>
                    </button>
                    <button class="action-btn" data-id="${d.id}" data-action="delete" title="Удалить">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `).join('');
    }

    function renderTopDonators() {
        const donations = currentData.donations || [];
        if (donations.length === 0) {
            elements.topDonatorsList.innerHTML = '<p>Донатов пока нет.</p>';
            return;
        }

        const topDonators = donations.reduce((acc, d) => {
            acc[d.name] = (acc[d.name] || 0) + d.amount;
            return acc;
        }, {});

        const sortedTop = Object.entries(topDonators)
            .sort(([, a], [, b]) => b - a)
            .slice(0, 10);

        elements.topDonatorsList.innerHTML = sortedTop.map(([name, amount]) => `
             <div class="donation-item">
                <div class="donation-item-header">
                    <span class="donation-name">${escapeHtml(name)}</span>
                    <span class="donation-amount">${amount.toLocaleString('ru-RU')} ₸</span>
                </div>
            </div>
        `).join('');
    }
    
    function updateForms() {
        if (currentData.goal) {
            elements.goalTitleInput.value = currentData.goal.title;
            elements.goalTargetInput.value = currentData.goal.target;
        }
        if (currentData.settings) {
            elements.minAmountInput.value = currentData.settings.min_amount;
            elements.ttsEnabledInput.checked = currentData.settings.tts_enabled;
            elements.ttsVolumeInput.value = currentData.settings.tts_volume;
        }
    }
    
    // --- Обработчики событий ---
    async function handleFormSubmit(url, body, successMessage) {
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (response.ok) {
                logToConsole(successMessage, 'success');
            } else {
                logToConsole(`Ошибка сервера: ${response.status}`, 'error');
            }
        } catch (error) {
            logToConsole('Сетевая ошибка.', 'error');
        }
    }
    
    function initEventListeners() {
        elements.addDonationForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData.entries());
            data.amount = parseFloat(data.amount);
            handleFormSubmit(`${API_URL}/add_donation`, data, `Донат от ${data.name || 'Аноним'} добавлен.`);
            e.target.reset();
        });

        elements.goalForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = {
                title: formData.get('goal-title'),
                target: parseFloat(formData.get('goal-target'))
            };
            handleFormSubmit(`${API_URL}/update_goal`, data, 'Настройки сбора сохранены.');
        });
        
        elements.settingsForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = {
                min_amount: parseFloat(formData.get('min-amount')),
                tts_enabled: formData.get('tts-enabled') === 'on',
                tts_volume: parseFloat(formData.get('tts-volume'))
            };
            handleFormSubmit(`${API_URL}/update_settings`, data, 'Общие настройки сохранены.');
        });

        elements.resetGoalBtn.addEventListener('click', () => {
            if (confirm('Вы уверены, что хотите сбросить всю статистику (донаты и прогресс сбора)?')) {
                handleFormSubmit(`${API_URL}/reset_goal`, {}, 'Вся статистика сброшена.');
            }
        });
        
        elements.testDonationBtn.addEventListener('click', () => {
            handleFormSubmit(`${API_URL}/test_donation`, {}, 'Тестовый донат отправлен.');
        });

        elements.donationsList.addEventListener('click', (e) => {
            const button = e.target.closest('.action-btn');
            if (!button) return;
            
            const id = button.dataset.id;
            const action = button.dataset.action;

            if (action === 'delete') {
                 if (confirm('Удалить этот донат?')) {
                    handleFormSubmit(`${API_URL}/delete_donation/${id}`, {}, `Донат #${id} удален.`);
                }
            } else if (action === 'replay') {
                handleFormSubmit(`${API_URL}/replay_donation/${id}`, {}, `Повтор доната #${id}.`);
            }
        });

        elements.popoutLink.addEventListener('click', (e) => {
            e.preventDefault();
            const url = e.currentTarget.href;
            window.open(url, 'DonationsHistory', 'width=420,height=800,scrollbars=yes,resizable=yes');
        });
    }

    // --- Статус Phone Link ---
    async function checkPhoneStatus() {
        try {
            const response = await fetch(`${API_URL}/get_phone_status`);
            const status = await response.json();
            
            const indicator = elements.phoneStatusIndicator;
            indicator.className = 'status-indicator'; // Reset classes
            indicator.classList.add(status.connected ? 'connected' : 'disconnected');
            indicator.querySelector('.status-text').textContent = status.message;

            if (status.message !== lastPhoneStatus) {
                logToConsole(`Статус Phone Link: ${status.message}`, 'info');
                lastPhoneStatus = status.message;
            }
        } catch (error) {
            const message = 'Не удалось проверить статус Phone Link.';
            if (message !== lastPhoneStatus) {
                logToConsole(message, 'error');
                lastPhoneStatus = message;
            }
        }
    }
    
    // --- Инициализация ---
    function init() {
        logToConsole('Инициализация панели управления...');
        connectWebSocket();
        initEventListeners();
        setInterval(checkPhoneStatus, 5000); // Check status every 5 seconds
        checkPhoneStatus(); // Initial check
    }

    init();
});

