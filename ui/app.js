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
let isDemoMode = false;

// Demo mode: pre-cached responses when no backend is available
const DEMO_RESPONSES = {
    stats: {
        total_chunks: 324,
        companies: [
            { ticker: "AAPL", name: "Apple Inc", chunk_count: 50 },
            { ticker: "MSFT", name: "Microsoft Corp", chunk_count: 274 }
        ]
    },
    answers: [
        {
            keywords: ["revenue", "sales", "income"],
            answer: "Based on Apple's 10-K filing, the company reported **total net revenue of $391.0 billion** for fiscal year 2024, a decrease from $394.3 billion in 2023. Revenue by category:\n\n- **iPhone**: $201.2 billion (51% of total)\n- **Services**: $96.2 billion (25%)\n- **Mac**: $29.4 billion (8%)\n- **iPad**: $28.3 billion (7%)\n- **Wearables, Home & Accessories**: $36.0 billion (9%)\n\nServices revenue continued to grow, reaching an all-time high [1]. The Americas remained the largest geographic segment at $167.0 billion [2].",
            citations: [
                { section: "Item 7 — MD&A | Revenue", text: "Total net revenue was $391.0 billion for 2024, compared to $394.3 billion for 2023. Services revenue reached $96.2 billion, an increase of 9% year-over-year." },
                { section: "Item 7 — MD&A | Segment Information", text: "Americas segment net revenue was $167.0 billion. Europe segment net revenue was $101.3 billion. Greater China was $66.7 billion." }
            ],
            confidence: 0.92
        },
        {
            keywords: ["risk", "threat", "challenge"],
            answer: "Apple's 10-K filing identifies several **key risk factors**:\n\n1. **Macroeconomic conditions** — Global economic uncertainty, inflation, and currency fluctuations could reduce consumer spending [1]\n\n2. **Supply chain concentration** — Heavy reliance on single-source components and manufacturing concentrated in China and East Asia [1]\n\n3. **Competition** — Aggressive competition in smartphones, tablets, and wearables from Samsung, Google, and others [2]\n\n4. **Regulatory & Legal** — Antitrust scrutiny, App Store regulation (EU Digital Markets Act), and ongoing litigation [2]\n\n5. **Cybersecurity** — Increasing sophistication of cyber threats targeting customer data and intellectual property [2]\n\n6. **Product transitions** — Risk of execution failures during major product launches and technology transitions (e.g., Apple Silicon) [1]",
            citations: [
                { section: "Item 1A — Risk Factors", text: "The Company's operations and performance depend significantly on worldwide economic conditions. Uncertainty about global economic conditions poses a risk as consumers and businesses may postpone spending." },
                { section: "Item 1A — Risk Factors", text: "The markets for the Company's products and services are highly competitive and subject to rapid technological change. The Company faces substantial competition in all product categories." }
            ],
            confidence: 0.88
        },
        {
            keywords: ["segment", "business", "division", "product"],
            answer: "Apple operates through several **key business segments** based on products and services:\n\n**Product Segments:**\n- **iPhone** — The flagship product line generating $201.2 billion (51% of revenue) [1]\n- **Mac** — Desktop and laptop computers including MacBook, iMac, Mac Pro ($29.4 billion) [1]\n- **iPad** — Tablet product line ($28.3 billion) [1]\n- **Wearables, Home & Accessories** — Apple Watch, AirPods, HomePod, Apple TV ($36.0 billion) [1]\n\n**Services Segment:**\n- **Services** — App Store, Apple Music, iCloud, Apple TV+, AppleCare, Apple Pay, licensing ($96.2 billion) [2]\n\n**Geographic Segments:**\nThe Americas, Europe, Greater China, Japan, and Rest of Asia Pacific [2].",
            citations: [
                { section: "Item 1 — Business | Products", text: "The Company designs, manufactures and markets smartphones, personal computers, tablets, wearables and accessories. iPhone, Mac, iPad, and Wearables, Home and Accessories are the primary product categories." },
                { section: "Item 7 — MD&A | Segment Information", text: "The Company reports revenue in five geographic segments: Americas, Europe, Greater China, Japan, and Rest of Asia Pacific. Services revenue includes the App Store, AppleCare, cloud services, and licensing." }
            ],
            confidence: 0.90
        },
        {
            keywords: ["cash", "debt", "balance", "liquidity"],
            answer: "Apple's **cash position and debt** from the 10-K filing:\n\n**Cash & Investments:**\n- Cash and cash equivalents: **$29.9 billion** [1]\n- Short-term marketable securities: **$35.2 billion** [1]\n- Long-term marketable securities: **$100.5 billion** [1]\n- **Total liquid assets: ~$165.6 billion**\n\n**Debt:**\n- Total term debt (current + non-current): **$104.6 billion** [2]\n- Commercial paper: **$6.0 billion** [2]\n\n**Net cash position: ~$55 billion** [1]\n\nApple continues its capital return program, returning over $100 billion to shareholders through dividends and share repurchases in fiscal 2024 [2].",
            citations: [
                { section: "Item 8 — Financial Statements | Balance Sheet", text: "Cash and cash equivalents were $29.9 billion. Total marketable securities (short-term and long-term) were $135.7 billion as of the end of fiscal year 2024." },
                { section: "Item 7 — MD&A | Liquidity and Capital Resources", text: "Total term debt was $104.6 billion. The Company returned over $100 billion to shareholders during 2024, including $15.0 billion in dividends and $90.2 billion in share repurchases." }
            ],
            confidence: 0.85
        },
        {
            keywords: ["margin", "operating", "profit", "expense"],
            answer: "Apple's **operating income and margins** from the 10-K filing:\n\n**Key Profitability Metrics:**\n- **Gross margin**: $178.1 billion (45.6% of revenue) [1]\n- **Operating income**: $123.2 billion (31.5% operating margin) [1]\n- **Net income**: $101.0 billion (25.8% net margin) [1]\n\n**Margin by Segment:**\n- **Products gross margin**: 36.9% [2]\n- **Services gross margin**: 74.0% [2]\n\nServices continue to have significantly higher margins than products, and as Services grows as a percentage of revenue, it supports overall margin expansion [2]. Operating expenses totaled $54.8 billion, including $30.0 billion in R&D and $24.8 billion in SG&A [1].",
            citations: [
                { section: "Item 7 — MD&A | Results of Operations", text: "Gross margin was $178.1 billion, or 45.6% of net revenue. Operating income was $123.2 billion. Research and development expense was $30.0 billion. Selling, general and administrative expense was $24.8 billion." },
                { section: "Item 7 — MD&A | Segment Margins", text: "Products gross margin percentage was 36.9%, compared to 36.5% in the prior year. Services gross margin percentage was 74.0%, compared to 70.8% in the prior year." }
            ],
            confidence: 0.87
        }
    ]
};

function findDemoResponse(query) {
    const q = query.toLowerCase();
    const match = DEMO_RESPONSES.answers.find(a =>
        a.keywords.some(kw => q.includes(kw))
    );
    return match || {
        answer: "**Demo Mode:** This is a live portfolio demo running without a backend server. In the full application, this query would search through SEC filings using vector similarity search and return an AI-generated answer with citations.\n\nTry one of these sample queries to see realistic responses:\n- \"What was the total revenue?\"\n- \"What are the main risk factors?\"\n- \"What are the key business segments?\"\n- \"What is the cash position and total debt?\"\n- \"What was the operating income and margins?\"",
        citations: [],
        confidence: 0.50
    };
}

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
        console.error('Backend unavailable, switching to demo mode:', error);
        isDemoMode = true;

        // Load demo stats
        const stats = DEMO_RESPONSES.stats;
        totalDocs.textContent = stats.total_chunks;
        totalCompanies.textContent = stats.companies.length;
        renderCompaniesList(stats.companies);

        // Show demo banner
        showDemoBanner();
    }
}

function showDemoBanner() {
    const banner = document.createElement('div');
    banner.className = 'demo-banner';
    banner.innerHTML = `
        <span class="demo-badge">DEMO</span>
        <span class="demo-text">Live preview with sample data — <a href="https://github.com/amirhshad/edgar-intelligence" target="_blank">View source on GitHub</a></span>
    `;
    document.querySelector('.header').appendChild(banner);

    // Update status indicator
    const statusText = document.querySelector('.status-text');
    const statusDot = document.querySelector('.status-dot');
    if (statusText) statusText.textContent = 'Demo Mode';
    if (statusDot) statusDot.style.background = 'var(--accent)';
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

    if (isDemoMode) {
        // Simulate network delay for realism
        await new Promise(resolve => setTimeout(resolve, 800 + Math.random() * 1200));
        removeLoadingMessage(loadingId);
        const demo = findDemoResponse(query);
        addMessage('assistant', demo.answer, demo.citations, demo.confidence);
        isLoading = false;
        return;
    }

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
