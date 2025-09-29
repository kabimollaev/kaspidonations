document.addEventListener('DOMContentLoaded', function() {
    // --- Глобальные переменные и элементы ---
    const API_URL_PREFIX = '/api';
    let ws;
    let currentData = {};

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
        statsContainer: document.getElementById('stats-container'),
        goalTitleInput: document.getElementById('goal-title'),
        goalTargetInput: document.getElementById('goal-target'),
        minAmountInput: document.getElementById('min-amount'),
        apiKeyInput: document.getElementById('api-key-input'),
        modal: document.getElementById('confirm-modal'),
        modalTitle: document.getElementById('modal-title'),
        modalText: document.getElementById('modal-text'),
        modalConfirmBtn: document.getElementById('modal-confirm-btn'),
        modalCancelBtn: document.getElementById('modal-cancel-btn'),
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
        if (body) options.body = JSON.stringify(body);
        
        try {
            const response = await fetch(`${API_URL_PREFIX}${endpoint}`, options);
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: 'Server error' }));
                logToConsole(`Ошибка API ${response.status}: ${errorData.error}`, 'error');
                return null;
            }
            return response.json();
        } catch (error) {
            logToConsole('Сетевая ошибка. Проверьте консоль.', 'error');
            console.error('Fetch error:', error);
            return null;
        }
    }

    // --- WebSocket ---
    function connectWebSocket() {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        // ИСПРАВЛЕНИЕ: Указываем правильный эндпоинт для WebSocket
        const wsUrl = `${wsProtocol}//${window.location.host}/ws`;
        ws = new WebSocket(wsUrl);

        ws.onopen = () => logToConsole('Соединение с WebSocket установлено.', 'success');
        ws.onmessage = (event) => handleWebSocketMessage(JSON.parse(event.data));
        ws.onclose = () => {
            logToConsole('Соединение потеряно. Переподключение...', 'error');
            setTimeout(connectWebSocket, 3000);
        };
        ws.onerror = (error) => {
            logToConsole('WebSocket ошибка.', 'error');
            console.error('WebSocket error:', error);
            ws.close();
        };
    }

    function handleWebSocketMessage(message) {
        if (message.type === 'full_update') {
            currentData = message.data;
            renderAll();
        } else if (message.type === 'phone_status_update') {
            updatePhoneStatus(message.data);
        } else if (message.type === 'show_alert') {
            logToConsole(`📢 Новый донат: ${message.data.name} - ${message.data.amount}₸`, 'success');
        }
    }

    // --- Рендеринг данных ---
    function renderAll() {
        if (!currentData) return;
        renderDonationsList();
        renderTopDonators();
        updateForms();
        updateStats();
        updatePhoneStatus(currentData.phone_status);
    }

    function renderDonationsList() {
        const donations = currentData.donations || [];
        if (!elements.donationsList) return;
        if (donations.length === 0) {
            elements.donationsList.innerHTML = '<p>История донатов пуста.</p>';
            return;
        }
        elements.donationsList.innerHTML = donations.slice(0, 10).map(d => `
            <div class="donation-item">
                <div class="donation-item-header">
                    <span class="donation-name">${escapeHtml(d.name)}</span>
                    <span class="donation-amount">${d.amount.toLocaleString('ru-RU')} ₸</span>
                </div>
                ${d.message ? `<p class="donation-message">${escapeHtml(d.message)}</p>` : ''}
                <div class="donation-actions">
                    <button onclick="window.app.replayDonation(${d.id})" class="btn btn-sm btn-secondary">Повторить</button>
                    <button onclick="window.app.deleteDonation(${d.id})" class="btn btn-sm btn-danger">Удалить</button>
                </div>
            </div>
        `).join('');
    }
    
    function renderTopDonators() {
        const donations = currentData.donations || [];
        if (!elements.topDonatorsList) return;
        const topDonators = donations.reduce((acc, d) => {
            acc[d.name] = (acc[d.name] || 0) + d.amount;
            return acc;
        }, {});
        const sorted = Object.entries(topDonators).sort(([,a],[,b]) => b-a).slice(0, 10);
        if (sorted.length === 0) {
            elements.topDonatorsList.innerHTML = '<p>Донатов пока нет.</p>';
            return;
        }
        elements.topDonatorsList.innerHTML = sorted.map(([name, amount], index) => `
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
        if (elements.goalTitleInput) elements.goalTitleInput.value = goal.title || '';
        if (elements.goalTargetInput) elements.goalTargetInput.value = goal.target_amount || '';
        if (elements.minAmountInput) elements.minAmountInput.value = settings.min_amount || 0;
    }
    
    function updateStats() {
        const stats = currentData.stats || {};
        if (!elements.statsContainer) return;
        elements.statsContainer.innerHTML = `
            <div class="stat-item">
                <span class="stat-label">Сегодня</span>
                <span class="stat-value">${(stats.today?.sum || 0).toFixed(2)} ₸</span>
                <span class="stat-count">${stats.today?.count || 0} донатов</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">За месяц</span>
                <span class="stat-value">${(stats.month?.sum || 0).toFixed(2)} ₸</span>
                <span class="stat-count">${stats.month?.count || 0} донатов</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">Всего</span>
                <span class="stat-value">${(stats.total?.sum || 0).toFixed(2)} ₸</span>
                <span class="stat-count">${stats.total?.count || 0} донатов</span>
            </div>
        `;
    }

    function updatePhoneStatus(status) {
        if (!elements.phoneStatusIndicator) return;
        const dot = elements.phoneStatusIndicator.querySelector('.status-dot');
        const text = elements.phoneStatusIndicator.querySelector('.status-text');
        status = status || { connected: false, message: "Нет данных" };
        dot.className = `status-dot ${status.connected ? 'status-connected' : 'status-disconnected'}`;
        text.textContent = status.message || (status.connected ? 'Подключен' : 'Отключен');
    }

    // --- Модальное окно ---
    function showConfirmationModal(title, text, onConfirm) {
        elements.modalTitle.textContent = title;
        elements.modalText.textContent = text;
        elements.modal.style.display = 'flex';
        
        // Удаляем старые обработчики, чтобы избежать многократного вызова
        const newConfirmBtn = elements.modalConfirmBtn.cloneNode(true);
        elements.modalConfirmBtn.parentNode.replaceChild(newConfirmBtn, elements.modalConfirmBtn);
        elements.modalConfirmBtn = newConfirmBtn;

        elements.modalConfirmBtn.onclick = () => {
            onConfirm();
            elements.modal.style.display = 'none';
        };
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
                if(await fetchApi('/add_manual_donation', 'POST', data)) {
                    logToConsole(`➕ Добавлен донат: ${data.name} - ${data.amount}₸`, 'success');
                    e.target.reset();
                }
            });
        }

        if (elements.goalForm) {
            elements.goalForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const data = { title: elements.goalTitleInput.value, target: parseFloat(elements.goalTargetInput.value) };
                if(await fetchApi('/update_goal', 'POST', data)) {
                    logToConsole(`🎯 Цель обновлена`, 'info');
                }
            });
        }
        
        if (elements.settingsForm) {
            elements.settingsForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const data = { min_amount: parseFloat(elements.minAmountInput.value) };
                if(await fetchApi('/update_settings', 'POST', data)) {
                    logToConsole(`⚙️ Настройки обновлены`, 'info');
                }
            });
        }

        if (elements.resetDonationsBtn) {
            elements.resetDonationsBtn.addEventListener('click', () => {
                showConfirmationModal(
                    'Сброс донатов',
                    'Вы уверены, что хотите удалить всю историю донатов и обнулить счетчик сбора?',
                    async () => {
                        if (await fetchApi('/reset_donations', 'POST')) {
                            logToConsole(`🗑️ История донатов сброшена`, 'warning');
                        }
                    }
                );
            });
        }
        
        if (elements.testDonationBtn) {
            elements.testDonationBtn.addEventListener('click', () => fetchApi('/test_donation', 'POST'));
        }

        if (elements.modalCancelBtn) {
            elements.modalCancelBtn.addEventListener('click', () => elements.modal.style.display = 'none');
        }
    }

    // --- Вспомогательные функции ---
    function logToConsole(message, type = 'info') {
        if (!elements.consoleOutput) return;
        const timestamp = new Date().toLocaleTimeString('ru-RU');
        const entry = document.createElement('div');
        entry.className = `console-entry console-${type}`;
        entry.innerHTML = `<span class="console-time">[${timestamp}]</span> ${message}`;
        elements.consoleOutput.appendChild(entry);
        if (elements.consoleOutput.children.length > 50) {
            elements.consoleOutput.removeChild(elements.consoleOutput.firstChild);
        }
        elements.consoleOutput.scrollTop = elements.consoleOutput.scrollHeight;
    }

    function escapeHtml(unsafe) {
        if (typeof unsafe !== 'string') return '';
        return unsafe.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    }

    // --- Глобальный объект для кнопок в HTML ---
    window.app = {
        replayDonation: async (id) => {
            if (await fetchApi(`/replay_donation/${id}`, 'POST')) {
                logToConsole(`🔄 Повтор доната #${id}`, 'info');
            }
        },
        deleteDonation: (id) => {
            showConfirmationModal(
                'Удаление доната',
                `Вы уверены, что хотите удалить донат #${id}? Это действие необратимо.`,
                async () => {
                    if (await fetchApi(`/delete_donation/${id}`, 'POST')) {
                        logToConsole(`🗑️ Донат #${id} удален`, 'info');
                    }
                }
            );
        }
    };

    // --- Инициализация ---
    logToConsole('🚀 Панель управления загружена', 'info');
    connectWebSocket();
    initEventListeners();
});
