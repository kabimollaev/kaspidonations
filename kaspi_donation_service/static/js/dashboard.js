document.addEventListener('DOMContentLoaded', function() {
    const API_URL = '/api';
    let ws;
    let currentData = {};
    
    // --- Элементы DOM ---
    const elements = {
        addDonationForm: document.getElementById('add-donation-form'),
        goalForm: document.getElementById('goal-form'),
        settingsForm: document.getElementById('settings-form'),
        widgetCustomizationForm: document.getElementById('widget-customization-form'), // НОВЫЙ ЭЛЕМЕНТ
        resetDonationsBtn: document.getElementById('reset-donations-btn'),
        testDonationBtn: document.getElementById('test-donation-btn'),
        donationsList: document.getElementById('donations-list'),
        topDonatorsList: document.getElementById('top-donators-list'), // НОВЫЙ ЭЛЕМЕНТ
        phoneStatusIndicator: document.getElementById('phone-status-indicator'),
        consoleOutput: document.getElementById('console-output'),
        
        // Поля форм
        goalTitleInput: document.getElementById('goal-title'),
        goalTargetInput: document.getElementById('goal-target'),
        minAmountInput: document.getElementById('min-amount'),
        ttsEnabledInput: document.getElementById('tts-enabled'),
        ttsVolumeInput: document.getElementById('tts-volume'),
        alertPresetSelect: document.getElementById('alert-preset'), // НОВЫЙ ЭЛЕМЕНТ
        soundPresetSelect: document.getElementById('sound-preset'), // НОВЫЙ ЭЛЕМЕНТ
        alertCustomUrlInput: document.getElementById('alert-custom-url'), // НОВЫЙ ЭЛЕМЕНТ
        soundCustomUrlInput: document.getElementById('sound-custom-url'), // НОВЫЙ ЭЛЕМЕНТ
        userIdInput: document.querySelector('input[name="api-key-input"]')
    };

    let lastPhoneStatus = '';

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
        renderTopDonators(); // НОВЫЙ ВЫЗОВ
        updateForms();
        if (currentData.phone_status) {
            updatePhoneStatus(currentData.phone_status);
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
    
    // НОВАЯ ФУНКЦИЯ ДЛЯ РЕНДЕРИНГА ТОП ДОНАТЕРОВ
    function renderTopDonators() {
        const donations = currentData.donations || [];
        const donatorsList = elements.topDonatorsList;
        if (!donatorsList) return;

        const topDonators = donations.reduce((acc, d) => {
            acc[d.name] = (acc[d.name] || 0) + d.amount;
            return acc;
        }, {});

        const sorted = Object.entries(topDonators)
            .sort(([, a], [, b]) => b - a)
            .slice(0, 10);

        if (sorted.length === 0) {
            donatorsList.innerHTML = '<p style="text-align: center; color: #A0AEC0;">Донатов пока нет.</p>';
            return;
        }
        
        donatorsList.innerHTML = sorted.map(([name, amount], index) => `
            <div class="donator-item">
                <span class="donator-rank">#${index + 1}</span>
                <span class="donator-name">${escapeHtml(name)}</span>
                <span class="donator-amount">${amount.toLocaleString('ru-RU')} ₸</span>
            </div>
        `).join('');
    }


    function updateForms() {
        if (currentData.goal && elements.goalTitleInput) {
            elements.goalTitleInput.value = currentData.goal.title || '';
            elements.goalTargetInput.value = currentData.goal.target_amount || '';
        }
        if (currentData.settings && elements.minAmountInput) {
            elements.minAmountInput.value = currentData.settings.min_amount || 0;
            elements.ttsEnabledInput.checked = currentData.settings.tts_enabled || false;
            elements.ttsVolumeInput.value = currentData.settings.tts_volume || 0.7;
            
            // НОВОЕ: Обновление формы кастомизации
            elements.alertPresetSelect.value = currentData.settings.alert_preset || 'kaspi_default';
            elements.soundPresetSelect.value = currentData.settings.sound_preset || 'default';
            elements.alertCustomUrlInput.value = currentData.settings.alert_custom_url || '';
            elements.soundCustomUrlInput.value = currentData.settings.sound_custom_url || '';
            
            toggleCustomUrlInputs();
        }
    }
    
    // НОВАЯ ФУНКЦИЯ для переключения полей ввода URL
    function toggleCustomUrlInputs() {
        if (elements.alertPresetSelect.value === 'custom') {
            elements.alertCustomUrlInput.style.display = 'block';
        } else {
            elements.alertCustomUrlInput.style.display = 'none';
        }
        
        if (elements.soundPresetSelect.value === 'custom') {
            elements.soundCustomUrlInput.style.display = 'block';
        } else {
            elements.soundCustomUrlInput.style.display = 'none';
        }
    }


    // --- Глобальные функции для кнопок ---
    window.replayDonation = async function(donationId) {
        const result = await fetchApi(`/replay_donation/${donationId}`, 'POST');
        if (result && result.status === 'success') {
            logToConsole(`🔄 Повторное воспроизведение доната #${donationId}`, 'info');
        }
    };

    window.deleteDonation = async function(donationId) {
        if (confirm('Удалить этот донат?')) {
            const result = await fetchApi(`/delete_donation/${donationId}`, 'POST');
            if (result && result.status === 'success') {
                logToConsole(`🗑️ Донат #${donationId} удален`, 'info');
            }
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
        if (entries.length > 10) { // Увеличим лимит для наглядности
            entries[0].remove();
        }
        
        consoleEl.scrollTop = consoleEl.scrollHeight;
    }

    // --- WebSocket ---
    function connectWebSocket() {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws`);

        ws.onopen = () => {
            console.log('WebSocket соединение установлено.');
            logToConsole('WebSocket соединение установлено.', 'success');
        };

        ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            handleWebSocketMessage(message);
        };

        ws.onclose = () => {
            console.log('WebSocket соединение закрыто. Попытка переподключения...');
            logToConsole('WebSocket соединение закрыто. Попытка переподключения...', 'error');
            setTimeout(connectWebSocket, 3000);
        };

        ws.onerror = (error) => {
            console.error('WebSocket Error:', error);
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
            // ИЗМЕНЕНИЕ: Только обновляем индикатор, без спама в консоль
            updatePhoneStatus(message.data);
            // Строка logToConsole удалена
        } else if (message.type === 'show_alert') {
            logToConsole(`📢 Новый донат: ${message.data.name} - ${message.data.amount}₸`, 'success');
            // Обновляем данные, чтобы список донатов сразу обновился
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
                    tts_enabled: elements.ttsEnabledInput.checked,
                    tts_volume: parseFloat(elements.ttsVolumeInput.value)
                };
                const result = await fetchApi('/update_settings', 'POST', data);
                if (result && result.status === 'success') {
                    logToConsole(`⚙️ Настройки обновлены`, 'info');
                }
            });
        }
        
        // НОВОЕ: Обработчик для формы кастомизации виджетов
        if (elements.widgetCustomizationForm) {
            elements.widgetCustomizationForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const data = {
                    alert_preset: elements.alertPresetSelect.value,
                    sound_preset: elements.soundPresetSelect.value,
                    alert_custom_url: elements.alertCustomUrlInput.value || null,
                    sound_custom_url: elements.soundCustomUrlInput.value || null
                };
                const result = await fetchApi('/update_widget_settings', 'POST', data);
                if (result && result.status === 'success') {
                    logToConsole(`🎨 Настройки виджетов обновлены`, 'info');
                }
            });
            
            elements.alertPresetSelect.addEventListener('change', toggleCustomUrlInputs);
            elements.soundPresetSelect.addEventListener('change', toggleCustomUrlInputs);
        }

        if (elements.resetDonationsBtn) {
            elements.resetDonationsBtn.addEventListener('click', async () => {
                if (confirm('Вы уверены, что хотите сбросить всю историю донатов и обнулить счетчик сбора? Это действие необратимо.')) {
                    const result = await fetchApi('/reset_donations', 'POST');
                    if (result && result.status === 'success') {
                        logToConsole(`🗑️ История донатов сброшена`, 'warning');
                    }
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
