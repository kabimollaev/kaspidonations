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
        
        // Поля форм
        goalTitleInput: document.getElementById('goal-title'),
        goalTargetInput: document.getElementById('goal-target'),
        minAmountInput: document.getElementById('min-amount'),
        ttsEnabledInput: document.getElementById('tts-enabled'),
        ttsVolumeInput: document.getElementById('tts-volume')
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
                console.error(`Ошибка API: ${response.statusText}`);
                return null;
            }
            if (response.headers.get("Content-Type")?.includes("application/json")) {
                return response.json();
            }
            return { status: 'success' };
        } catch (error) {
            console.error('Сетевая ошибка:', error);
            return null;
        }
    }

    // --- Рендеринг данных ---
    function renderAll() {
        if (!currentData) return;
        renderDonationsList();
        renderTopDonators();
        updateForms();
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
        if (donations.length === 0) {
            listEl.innerHTML = '<p>История донатов пуста.</p>';
            return;
        }
        listEl.innerHTML = donations.map(d => `
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
        const listEl = elements.topDonatorsList;

        if (donations.length === 0) {
            listEl.innerHTML = '<p>Донатов пока нет.</p>';
            return;
        }

        const topDonators = donations.reduce((acc, d) => {
            acc[d.name] = (acc[d.name] || 0) + d.amount;
            return acc;
        }, {});

        const sortedTop = Object.entries(topDonators)
            .sort(([, a], [, b]) => b - a)
            .slice(0, 10);

        listEl.innerHTML = sortedTop.map(([name, amount]) => `
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
            elements.goalTargetInput.value = currentData.goal.target_amount;
        }
        if (currentData.settings) {
            elements.minAmountInput.value = currentData.settings.min_amount;
            elements.ttsEnabledInput.checked = currentData.settings.tts_enabled;
            elements.ttsVolumeInput.value = currentData.settings.tts_volume;
        }
    }
    
    function connectWebSocket() {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const user_id = document.querySelector('input[name="api-key-input"]').dataset.userId;
        ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws?user_id=${user_id}`);

        ws.onopen = () => console.log('WebSocket соединение установлено.');
        ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            if (message.type === 'full_update') {
                currentData = message.data;
                renderAll();
            }
        };
        ws.onclose = () => {
            console.log('WebSocket соединение закрыто. Попытка переподключения...');
            setTimeout(connectWebSocket, 3000);
        };
    }

    // --- Обработчики событий ---
    function initEventListeners() {
        elements.addDonationForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = {
                name: formData.get('name') || 'Аноним',
                amount: parseFloat(formData.get('amount')),
                message: formData.get('message')
            };
            await fetchApi('/add_manual_donation', 'POST', data);
            e.target.reset();
        });

        elements.goalForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const data = {
                title: elements.goalTitleInput.value,
                target: parseFloat(elements.goalTargetInput.value)
            };
            await fetchApi('/update_goal', 'POST', data);
        });
        
        elements.settingsForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const data = {
                min_amount: parseFloat(elements.minAmountInput.value),
                tts_enabled: elements.ttsEnabledInput.checked,
                tts_volume: parseFloat(elements.ttsVolumeInput.value)
            };
            await fetchApi('/update_settings', 'POST', data);
        });

        elements.resetDonationsBtn.addEventListener('click', async () => {
            if (confirm('Вы уверены, что хотите сбросить всю историю донатов и обнулить счетчик сбора? Это действие необратимо.')) {
                await fetchApi('/reset_donations', 'POST');
            }
        });
        
        elements.testDonationBtn.addEventListener('click', async () => {
             await fetchApi('/test_donation', 'POST');
        });

        elements.donationsList.addEventListener('click', async (e) => {
            const button = e.target.closest('.action-btn');
            if (!button) return;
            
            const id = button.dataset.id;
            const action = button.dataset.action;

            if (action === 'delete') {
                 if (confirm('Удалить этот донат?')) {
                    await fetchApi(`/delete_donation/${id}`, 'POST');
                }
            } else if (action === 'replay') {
                await fetchApi(`/replay_donation/${id}`, 'POST');
            }
        });
    }

    // --- Инициализация ---
    async function init() {
        // Загружаем начальные данные
        const data = await fetchApi('/get_all_data');
        if (data) {
            currentData = data;
            renderAll();
        }
        
        // Подключаем WebSocket
        connectWebSocket();
        initEventListeners();
    }

    init();
});
