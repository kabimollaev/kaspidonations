document.addEventListener('DOMContentLoaded', function() {
    const API_URL = '/api';
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
            elements.minAmountInput.value = currentData.settings.min_amount_for_alert;
            elements.ttsEnabledInput.checked = currentData.settings.tts_enabled;
            elements.ttsVolumeInput.value = currentData.settings.tts_volume;
        }
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
            const result = await fetchApi('/add_manual_donation', 'POST', data);
            if (result && result.status === 'success') {
                currentData.donations.unshift(result.donation); // Добавляем новый донат в начало списка
                renderAll();
                e.target.reset();
            }
        });

        elements.goalForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const data = {
                title: elements.goalTitleInput.value,
                target_amount: parseFloat(elements.goalTargetInput.value)
            };
            await fetchApi('/update_goal', 'POST', data);
        });
        
        elements.settingsForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const data = {
                min_amount_for_alert: parseFloat(elements.minAmountInput.value),
                tts_enabled: elements.ttsEnabledInput.checked,
                tts_volume: parseFloat(elements.ttsVolumeInput.value)
            };
            await fetchApi('/update_settings', 'POST', data);
        });

        elements.resetDonationsBtn.addEventListener('click', async () => {
            if (confirm('Вы уверены, что хотите сбросить всю историю донатов и обнулить счетчик сбора? Это действие необратимо.')) {
                await fetchApi('/reset_donations', 'POST');
                loadInitialData(); // Перезагружаем данные после сброса
            }
        });
        
        elements.testDonationBtn.addEventListener('click', () => {
            // TODO: Реализовать отправку тестового доната через WebSocket
            alert('Функция тестового доната будет реализована на следующем этапе.');
        });
    }

    // --- Инициализация ---
    async function loadInitialData() {
        const data = await fetchApi('/get_all_data');
        if (data) {
            currentData = data;
            renderAll();
        }
    }

    function init() {
        loadInitialData();
        initEventListeners();
        // WebSocket будет добавлен на следующих этапах
    }

    init();
});
