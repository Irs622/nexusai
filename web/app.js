/**
 * NEXUSAI AGENTIC WEB OS DASHBOARD
 * Core client logic: Real-Time SSE Stream, LangGraph Visualizer, MCP Ecosystem & Chat REPL.
 */

let voiceEnabled = false;
let allTools = [];
let mcpServers = [];
let currentFilter = 'ALL';
let sseSource = null;

// ==============================================================================
// INITIALIZATION
// ==============================================================================

document.addEventListener('DOMContentLoaded', () => {
    updateClock();
    setInterval(updateClock, 1000);

    initSSE();
    fetchStatus();
    fetchTools();
    fetchMcpServers();
});

// Real-Time Clock
function updateClock() {
    const now = new Date();
    const clock = document.getElementById('clockDisplay');
    if (clock) {
        clock.innerText = now.toTimeString().split(' ')[0];
    }
}

// Toggle Voice Mode
function toggleVoiceMode() {
    voiceEnabled = !voiceEnabled;
    const btn = document.getElementById('voiceToggleBtn');
    if (btn) {
        btn.innerHTML = voiceEnabled 
            ? '<span class="icon">🎙</span> [ VOICE: ON ]' 
            : '<span class="icon">🎙</span> [ VOICE: OFF ]';
        btn.className = voiceEnabled ? 'btn btn-alert' : 'btn btn-glass';
    }
}

// ==============================================================================
// SERVER-SENT EVENTS (SSE) REAL-TIME STREAM
// ==============================================================================

function initSSE() {
    const badge = document.getElementById('sseStatusBadge');

    try {
        if (sseSource) {
            sseSource.close();
        }

        sseSource = new EventSource('/api/events/stream');

        sseSource.addEventListener('handshake', (e) => {
            if (badge) {
                badge.className = 'badge badge-sse';
                badge.innerText = '[ SSE: STREAMING ]';
            }
            console.log('[SSE Handshake]', JSON.parse(e.data));
        });

        sseSource.addEventListener('telemetry', (e) => {
            try {
                const data = JSON.parse(e.data);
                updateTelemetryUI(data);
            } catch (err) {
                console.error('[SSE Telemetry Parse Error]', err);
            }
        });

        sseSource.onerror = () => {
            if (badge) {
                badge.className = 'badge badge-cert';
                badge.style.color = 'var(--color-coral)';
                badge.innerText = '[ SSE: RECONNECTING ]';
            }
        };

    } catch (err) {
        console.warn('SSE not supported or failed to initialize:', err);
    }
}

function updateTelemetryUI(data) {
    if (!data) return;

    if (data.active_app) {
        const el = document.getElementById('ctxActiveApp');
        if (el) el.innerText = data.active_app;
    }
    if (data.active_title !== undefined) {
        const el = document.getElementById('ctxActiveTitle');
        if (el) el.innerText = data.active_title || 'Desktop / Idle';
    }
    if (data.git_branch) {
        const el = document.getElementById('ctxGitBranch');
        if (el) el.innerText = data.git_branch;
    }

    if (data.cpu !== undefined) {
        const cpu = Math.round(data.cpu);
        const cpuVal = document.getElementById('cpuVal');
        const cpuBar = document.getElementById('cpuBar');
        if (cpuVal) cpuVal.innerText = `${cpu}%`;
        if (cpuBar) cpuBar.style.width = `${cpu}%`;
    }

    if (data.ram !== undefined) {
        const ram = Math.round(data.ram);
        const ramVal = document.getElementById('ramVal');
        const ramBar = document.getElementById('ramBar');
        if (ramVal) ramVal.innerText = `${ram}%`;
        if (ramBar) ramBar.style.width = `${ram}%`;
    }
}

// Fallback REST Status Sync
async function fetchStatus() {
    try {
        const res = await fetch('/api/status');
        if (!res.ok) return;
        const data = await res.json();
        const ctx = data.context || {};
        updateTelemetryUI({
            active_app: ctx.active_application,
            active_title: ctx.active_window_title,
            git_branch: ctx.git_branch,
            cpu: ctx.cpu_usage_percent,
            ram: ctx.ram_usage_percent,
        });
    } catch (e) {
        console.error("Failed to fetch status:", e);
    }
}

// ==============================================================================
// CAPABILITY TOOLS REGISTRY & MODAL
// ==============================================================================

async function fetchTools() {
    try {
        const res = await fetch('/api/tools');
        if (!res.ok) return;
        allTools = await res.json();
        renderTools();
    } catch (e) {
        console.error("Failed to fetch tools:", e);
    }
}

function filterTools(level) {
    currentFilter = level;
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    renderTools();
}

function renderTools() {
    const feed = document.getElementById('toolsListFeed');
    if (!feed) return;

    const filtered = currentFilter === 'ALL' 
        ? allTools 
        : allTools.filter(t => t.risk_level === currentFilter);

    if (filtered.length === 0) {
        feed.innerHTML = '<div class="loading-text">No tools matching filter.</div>';
        return;
    }

    feed.innerHTML = filtered.map(t => `
        <div class="tool-card" onclick="openToolModal('${t.name}')">
            <div class="tool-card-header">
                <span class="tool-name">${t.name}</span>
                <span class="risk-tag risk-${t.risk_level}">${t.risk_level}</span>
            </div>
            <div class="tool-desc">${t.description || 'No description provided.'}</div>
        </div>
    `).join('');
}

function openToolModal(toolName) {
    const tool = allTools.find(t => t.name === toolName);
    if (!tool) return;

    document.getElementById('modalToolTitle').innerText = `// EXECUTE: ${tool.name}`;
    document.getElementById('modalToolDesc').innerText = tool.description || '';
    document.getElementById('modalToolName').value = tool.name;

    const container = document.getElementById('modalParamsContainer');
    container.innerHTML = '';

    const params = tool.parameters?.properties || {};
    const required = tool.parameters?.required || [];

    for (const [pName, pProp] of Object.entries(params)) {
        const isReq = required.includes(pName);
        const div = document.createElement('div');
        div.className = 'param-field';
        div.innerHTML = `
            <label class="param-label">${pName}${isReq ? ' *' : ''} (${pProp.type || 'any'})</label>
            <input type="text" name="${pName}" class="param-input" placeholder="${pProp.description || ''}" ${isReq ? 'required' : ''}>
        `;
        container.appendChild(div);
    }

    document.getElementById('toolModal').style.display = 'flex';
}

function closeToolModal() {
    document.getElementById('toolModal').style.display = 'none';
}

async function submitToolExecution(e) {
    e.preventDefault();
    const toolName = document.getElementById('modalToolName').value;
    const confirmHigh = document.getElementById('modalUserConfirm').checked;

    const form = document.getElementById('toolExecForm');
    const formData = new FormData(form);
    const args = {};

    formData.forEach((val, key) => {
        if (key && val.trim() !== '') {
            try {
                args[key] = JSON.parse(val);
            } catch {
                args[key] = val;
            }
        }
    });

    closeToolModal();
    appendChatMessage('user', `[MANUAL EXECUTION] ${toolName} with ${JSON.stringify(args)}`);

    try {
        animateGraphNode('nodeExecutor');
        const res = await fetch('/api/tools/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tool_name: toolName,
                arguments: args,
                user_confirmed: confirmHigh,
            })
        });

        const data = await res.json();
        if (res.ok) {
            appendChatMessage('ai', `Output:\n${JSON.stringify(data.output, null, 2)}`);
        } else {
            appendChatMessage('system', `Error: ${data.detail || 'Failed to execute tool'}`);
        }
    } catch (err) {
        appendChatMessage('system', `Execution Error: ${err.message}`);
    } finally {
        resetGraphNodes();
    }
}

// ==============================================================================
// MODEL CONTEXT PROTOCOL (MCP) ECOSYSTEM
// ==============================================================================

function switchRightTab(tab) {
    const tabToolsBtn = document.getElementById('tabToolsBtn');
    const tabMcpBtn = document.getElementById('tabMcpBtn');
    const viewTools = document.getElementById('viewToolsRegistry');
    const viewMcp = document.getElementById('viewMcpEcosystem');

    if (tab === 'TOOLS') {
        tabToolsBtn.classList.add('active');
        tabMcpBtn.classList.remove('active');
        viewTools.style.display = 'flex';
        viewMcp.style.display = 'none';
    } else {
        tabMcpBtn.classList.add('active');
        tabToolsBtn.classList.remove('active');
        viewTools.style.display = 'none';
        viewMcp.style.display = 'flex';
        fetchMcpServers();
    }
}

async function fetchMcpServers() {
    const feed = document.getElementById('mcpServersFeed');
    if (!feed) return;

    try {
        const res = await fetch('/api/mcp/servers');
        if (!res.ok) {
            feed.innerHTML = '<div class="loading-text">Failed to load MCP servers.</div>';
            return;
        }

        const data = await res.json();
        mcpServers = data.servers || [];

        if (mcpServers.length === 0) {
            feed.innerHTML = `
                <div class="loading-text" style="color: var(--text-secondary); text-align: center; padding: 20px;">
                    No MCP servers connected.<br>
                    Configure in <code>config/mcp_servers.yaml</code>
                </div>
            `;
            return;
        }

        feed.innerHTML = mcpServers.map(s => {
            const isConn = s.is_connected;
            const statusClass = isConn ? 'mcp-online' : 'mcp-offline';
            const statusText = isConn ? '● ONLINE' : '○ OFFLINE';

            const toolsHtml = s.tools && s.tools.length > 0
                ? s.tools.map(t => `<span class="mcp-tool-pill">${t.name}</span>`).join('')
                : '<span style="font-size: 10px; color: var(--text-muted);">No tools discovered</span>';

            return `
                <div class="mcp-card">
                    <div class="mcp-card-header">
                        <span class="mcp-name">${s.name}</span>
                        <div style="display: flex; gap: 6px; align-items: center;">
                            <span class="mcp-status-pill ${statusClass}">${statusText}</span>
                            <button class="btn btn-sm btn-glass" onclick="pingMcpServer('${s.name}', event)">[ PING ]</button>
                        </div>
                    </div>
                    <div style="font-size: 10.5px; color: var(--text-muted); margin-bottom: 6px; font-family: var(--font-mono);">
                        ${s.command || 'stdio'} (${s.tools_count || 0} tools)
                    </div>
                    <div class="mcp-tools-list">
                        ${toolsHtml}
                    </div>
                </div>
            `;
        }).join('');

    } catch (err) {
        console.error("Failed to fetch MCP servers:", err);
        feed.innerHTML = `<div class="loading-text">Error: ${err.message}</div>`;
    }
}

async function pingMcpServer(serverName, event) {
    if (event) event.stopPropagation();
    const startTime = performance.now();

    try {
        const res = await fetch(`/api/mcp/servers/${encodeURIComponent(serverName)}/ping`, {
            method: 'POST'
        });
        const elapsed = Math.round(performance.now() - startTime);
        const data = await res.json();

        if (res.ok && data.is_alive) {
            alert(`MCP Server '${serverName}' is ONLINE (${elapsed}ms)`);
        } else {
            alert(`MCP Server '${serverName}' ping returned OFFLINE`);
        }
    } catch (err) {
        alert(`Failed to ping '${serverName}': ${err.message}`);
    }
}

async function reloadMcpConfig() {
    try {
        const res = await fetch('/api/mcp/reload', { method: 'POST' });
        const data = await res.json();
        alert(`MCP Config Reloaded: ${data.status} (Total: ${data.total_servers} servers)`);
        fetchMcpServers();
    } catch (err) {
        alert(`Reload error: ${err.message}`);
    }
}

// ==============================================================================
// CHAT REPL & WORKFLOW GRAPH ANIMATION
// ==============================================================================

function sendPresetPrompt(text) {
    const input = document.getElementById('promptInput');
    if (input) {
        input.value = text;
        input.focus();
    }
}

function appendChatMessage(sender, text) {
    const feed = document.getElementById('chatFeed');
    if (!feed) return;

    const div = document.createElement('div');
    div.className = `chat-msg msg-${sender}`;
    const label = sender === 'user' ? 'YOU' : (sender === 'ai' ? 'NEXUSAI AGENT' : 'SYSTEM');
    
    div.innerHTML = `
        <span class="msg-sender">[ ${label} ]</span>
        <div class="msg-body" style="white-space: pre-wrap;">${escapeHtml(text)}</div>
    `;

    feed.appendChild(div);
    feed.scrollTop = feed.scrollHeight;
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

async function handleChatSubmit(e) {
    e.preventDefault();
    const input = document.getElementById('promptInput');
    const prompt = input.value.trim();
    if (!prompt) return;

    input.value = '';
    appendChatMessage('user', prompt);

    // Sequence graph nodes
    animateGraphNode('nodeReasoner', '> Reasoner analyzing execution graph...');
    document.getElementById('graphIterCount').innerText = '1';

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                prompt: prompt,
                session_id: 'web_session_' + Date.now(),
                user_confirmed: true,
            })
        });

        animateGraphNode('nodeExecutor', '> Tool executor running authorized actions...');
        document.getElementById('graphIterCount').innerText = '2';

        const data = await res.json();

        animateGraphNode('nodeOutbox', '> Committing state to transactional persistence outbox...');
        document.getElementById('graphIterCount').innerText = '3';

        await new Promise(r => setTimeout(r, 200));

        if (res.ok) {
            appendChatMessage('ai', data.response || JSON.stringify(data, null, 2));
        } else {
            appendChatMessage('system', `Error: ${data.detail || 'Chat request failed'}`);
        }

        animateGraphNode('nodeEnd', '> Workflow execution complete.');
        await new Promise(r => setTimeout(r, 600));

    } catch (err) {
        appendChatMessage('system', `Network Error: ${err.message}`);
    } finally {
        resetGraphNodes();
    }
}

function animateGraphNode(nodeId, logText) {
    document.querySelectorAll('.graph-node').forEach(n => {
        n.classList.remove('node-active');
    });

    const target = document.getElementById(nodeId);
    if (target) {
        target.classList.add('node-active');
    }

    if (logText) {
        const logFeed = document.getElementById('graphLogFeed');
        if (logFeed) {
            logFeed.innerHTML = `<span class="log-prefix">&gt;</span> ${logText}`;
        }
    }
}

function resetGraphNodes() {
    document.querySelectorAll('.graph-node').forEach(n => {
        n.classList.remove('node-active');
    });
    const nodeStart = document.getElementById('nodeStart');
    if (nodeStart) nodeStart.classList.add('node-done');

    const logFeed = document.getElementById('graphLogFeed');
    if (logFeed) {
        logFeed.innerHTML = `<span class="log-prefix">&gt;</span> System standby. Real-time DAG ready for execution.`;
    }
}
