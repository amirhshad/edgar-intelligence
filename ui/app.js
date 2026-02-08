/**
 * EDGAR Intelligence - Frontend Application
 *
 * Handles user interactions, API communication, and dynamic UI updates
 * for the SEC filing research interface.
 */

const API_BASE = '';  // Same origin, adjust if needed

// DOM Elements
const chatMessages = document.getElementById('chatMessages');
const queryInput = document.getElementById('queryInput');
const sendButton = document.getElementById('sendButton');
const statsGrid = document.getElementById('statsGrid');
const companiesList = document.getElementById('companiesList');
const totalDocs = document.getElementById('totalDocs');
const totalCompanies = document.getElementById('totalCompanies');

// State
let isLoading = false;
let selectedTicker = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initializeApp();
});

async function initializeApp() {
    setupEventListeners();
    await loadStats();
    autoResizeTextarea();
}

function setupEventListeners() {
    // Send button
    sendButton.addEventListener('click', handleSend);

    // Textarea input
    queryInput.addEventListener('input', () => {
        autoResizeTextarea();
        sendButton.disabled = !queryInput.value.trim();
    });

    // Enter to send, Shift+Enter for newline
    queryInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (queryInput.value.trim()) {
                handleSend();
            }
        }
    });

    // Quick query chips
    document.querySelectorAll('.query-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            const query = chip.dataset.query;
            queryInput.value = query;
            autoResizeTextarea();
            sendButton.disabled = false;
            queryInput.focus();
        });
    });
}

function autoResizeTextarea() {
    queryInput.style.height = 'auto';
    queryInput.style.height = Math.min(queryInput.scrollHeight, 200) + 'px';
}

async function loadStats() {
    try {
        const response = await fetch(`${API_BASE}/api/stats`);
        if (!response.ok) throw new Error('Failed to load stats');

        const stats = await response.json();

        // Update stats display
        totalDocs.textContent = stats.total_chunks || 0;
        totalCompanies.textContent = stats.companies?.length || 0;

        // Render companies list
        renderCompaniesList(stats.companies || []);

    } catch (error) {
        console.error('Error loading stats:', error);
        totalDocs.textContent = '0';
        totalCompanies.textContent = '0';
        companiesList.innerHTML = `
            <div class="company-item empty">
                <span class="company-message">No documents indexed yet</span>
            </div>
        `;
    }
}

function renderCompaniesList(companies) {
    if (!companies.length) {
        companiesList.innerHTML = `
            <div class="company-item empty">
                <span class="company-message">No companies indexed</span>
            </div>
        `;
        return;
    }

    companiesList.innerHTML = companies.map(company => `
        <div class="company-item ${selectedTicker === company.ticker ? 'selected' : ''}"
             data-ticker="${company.ticker}">
            <span class="company-ticker">${company.ticker}</span>
            <span class="company-name">${company.name || ''}</span>
            <span class="company-count">${company.chunk_count || 0} chunks</span>
        </div>
    `).join('');

    // Add click handlers
    companiesList.querySelectorAll('.company-item').forEach(item => {
        item.addEventListener('click', () => {
            const ticker = item.dataset.ticker;

            // Toggle selection
            if (selectedTicker === ticker) {
                selectedTicker = null;
                item.classList.remove('selected');
            } else {
                document.querySelectorAll('.company-item').forEach(i => i.classList.remove('selected'));
                selectedTicker = ticker;
                item.classList.add('selected');
            }

            updateFilterIndicator();
        });
    });
}

function updateFilterIndicator() {
    const existingIndicator = document.querySelector('.filter-indicator');
    if (existingIndicator) existingIndicator.remove();

    if (selectedTicker) {
        const indicator = document.createElement('div');
        indicator.className = 'filter-indicator';
        indicator.innerHTML = `
            <span>Filtering: <strong>${selectedTicker}</strong></span>
            <button class="clear-filter" title="Clear filter">&times;</button>
        `;
        document.querySelector('.input-wrapper').insertAdjacentElement('beforebegin', indicator);

        indicator.querySelector('.clear-filter').addEventListener('click', () => {
            selectedTicker = null;
            document.querySelectorAll('.company-item').forEach(i => i.classList.remove('selected'));
            indicator.remove();
        });
    }
}

async function handleSend() {
    const query = queryInput.value.trim();
    if (!query || isLoading) return;

    // Clear input
    queryInput.value = '';
    autoResizeTextarea();
    sendButton.disabled = true;

    // Remove welcome message if present
    const welcomeMsg = document.querySelector('.welcome-message');
    if (welcomeMsg) welcomeMsg.remove();

    // Add user message
    addMessage('user', query);

    // Add loading indicator
    const loadingId = addLoadingMessage();
    isLoading = true;

    try {
        const response = await fetch(`${API_BASE}/api/query`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query: query,
                ticker: selectedTicker,
            }),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Query failed');
        }

        const result = await response.json();

        // Remove loading indicator
        removeLoadingMessage(loadingId);

        // Add assistant response
        addMessage('assistant', result.answer, result.citations, result.confidence);

    } catch (error) {
        console.error('Query error:', error);
        removeLoadingMessage(loadingId);
        addMessage('error', `Error: ${error.message}`);
    }

    isLoading = false;
}

function addMessage(type, content, citations = [], confidence = null) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message message-${type}`;

    const timestamp = new Date().toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit'
    });

    if (type === 'user') {
        messageDiv.innerHTML = `
            <div class="message-header">
                <span class="message-author">You</span>
                <span class="message-time">${timestamp}</span>
            </div>
            <div class="message-content">${escapeHtml(content)}</div>
        `;
    } else if (type === 'assistant') {
        const confidenceClass = confidence >= 0.8 ? 'high' : confidence >= 0.5 ? 'medium' : 'low';
        const confidencePercent = confidence ? Math.round(confidence * 100) : null;

        messageDiv.innerHTML = `
            <div class="message-header">
                <span class="message-author">EDGAR AI</span>
                <span class="message-time">${timestamp}</span>
                ${confidencePercent ? `<span class="confidence-badge ${confidenceClass}">${confidencePercent}% confidence</span>` : ''}
            </div>
            <div class="message-content">${formatMarkdown(content)}</div>
            ${citations.length ? renderCitations(citations) : ''}
        `;
    } else if (type === 'error') {
        messageDiv.innerHTML = `
            <div class="message-header">
                <span class="message-author">System</span>
                <span class="message-time">${timestamp}</span>
            </div>
            <div class="message-content error-content">${escapeHtml(content)}</div>
        `;
    }

    chatMessages.appendChild(messageDiv);
    scrollToBottom();
}

function addLoadingMessage() {
    const id = 'loading-' + Date.now();
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message message-assistant loading';
    messageDiv.id = id;

    messageDiv.innerHTML = `
        <div class="message-header">
            <span class="message-author">EDGAR AI</span>
        </div>
        <div class="message-content">
            <div class="loading-indicator">
                <span class="loading-dot"></span>
                <span class="loading-dot"></span>
                <span class="loading-dot"></span>
            </div>
            <span class="loading-text">Searching documents...</span>
        </div>
    `;

    chatMessages.appendChild(messageDiv);
    scrollToBottom();

    return id;
}

function removeLoadingMessage(id) {
    const loadingMsg = document.getElementById(id);
    if (loadingMsg) loadingMsg.remove();
}

function renderCitations(citations) {
    if (!citations || !citations.length) return '';

    return `
        <div class="citations">
            <div class="citations-header">
                <svg viewBox="0 0 20 20" fill="currentColor" width="14" height="14">
                    <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z"/>
                    <path fill-rule="evenodd" d="M4 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm3 4a1 1 0 000 2h.01a1 1 0 100-2H7zm3 0a1 1 0 000 2h3a1 1 0 100-2h-3zm-3 4a1 1 0 100 2h.01a1 1 0 100-2H7zm3 0a1 1 0 100 2h3a1 1 0 100-2h-3z" clip-rule="evenodd"/>
                </svg>
                <span>Sources (${citations.length})</span>
            </div>
            <div class="citations-list">
                ${citations.map((cite, i) => `
                    <div class="citation-item">
                        <span class="citation-number">[${i + 1}]</span>
                        <div class="citation-content">
                            <span class="citation-section">${cite.section || 'Document'}</span>
                            <p class="citation-text">${escapeHtml(truncate(cite.text, 200))}</p>
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Utility functions
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function truncate(text, maxLength) {
    if (!text) return '';
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

function formatMarkdown(text) {
    // Basic markdown formatting
    let html = escapeHtml(text);

    // Bold
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

    // Italic
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');

    // Code inline
    html = html.replace(/`(.*?)`/g, '<code>$1</code>');

    // Line breaks
    html = html.replace(/\n/g, '<br>');

    // Citation references [1], [2], etc.
    html = html.replace(/\[(\d+)\]/g, '<span class="citation-ref">[$1]</span>');

    return html;
}
