/**
 * NEXUSAI AGENTIC WEB OS DASHBOARD
 * Core client logic: Real-Time SSE Stream, LangGraph Visualizer, MCP Ecosystem & Chat REPL.
 */

let voiceEnabled = false;
let allTools = [];
let mcpServers = [];
let currentFilter = 'ALL';
let sseSource = null;
let currentStudioTab = 'DAG';
let currentPlanId = 'incident_response';
let currentPlanData = null;
let selectedNodeId = null;
let auditEventsList = [];
let governanceBudget = null;
let pendingApprovalsList = [];

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

    // Studio Initializers
    loadPlan('incident_response');
    fetchAuditEvents();
    fetchGovernanceBudget();
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

        // Studio Real-Time Event Handlers
        sseSource.addEventListener('dag_step_update', (e) => {
            try {
                const data = JSON.parse(e.data);
                handleDagStepUpdate(data);
            } catch (err) {
                console.error('[SSE dag_step_update Error]', err);
            }
        });

        sseSource.addEventListener('dag_completed', (e) => {
            try {
                const data = JSON.parse(e.data);
                handleDagCompleted(data);
            } catch (err) {
                console.error('[SSE dag_completed Error]', err);
            }
        });

        sseSource.addEventListener('audit_event_created', (e) => {
            try {
                const data = JSON.parse(e.data);
                handleAuditEventCreated(data);
            } catch (err) {
                console.error('[SSE audit_event_created Error]', err);
            }
        });

        sseSource.addEventListener('audit_tampered', (e) => {
            try {
                const data = JSON.parse(e.data);
                handleAuditTampered(data);
            } catch (err) {
                console.error('[SSE audit_tampered Error]', err);
            }
        });

        sseSource.addEventListener('audit_reset', () => {
            fetchAuditEvents();
        });

        sseSource.addEventListener('governance_updated', (e) => {
            try {
                const data = JSON.parse(e.data);
                handleGovernanceUpdated(data);
            } catch (err) {
                console.error('[SSE governance_updated Error]', err);
            }
        });

        sseSource.addEventListener('budget_updated', (e) => {
            try {
                const data = JSON.parse(e.data);
                handleBudgetUpdated(data);
            } catch (err) {
                console.error('[SSE budget_updated Error]', err);
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

// ==============================================================================
// NEXUSAI STUDIO CORE LOGIC (DAG, AUDIT CHAIN, GOVERNANCE)
// ==============================================================================

// View Switcher
function switchStudioView(view) {
    currentStudioTab = view;
    
    const navBtns = {
        'DAG': document.getElementById('navDagBtn'),
        'AUDIT': document.getElementById('navAuditBtn'),
        'GOV': document.getElementById('navGovBtn'),
        'TERMINAL': document.getElementById('navTermBtn')
    };

    const views = {
        'DAG': document.getElementById('viewDagStudio'),
        'AUDIT': document.getElementById('viewAuditChain'),
        'GOV': document.getElementById('viewGovernance'),
        'TERMINAL': document.getElementById('viewTerminalRepl')
    };

    for (const [key, btn] of Object.entries(navBtns)) {
        if (btn) {
            if (key === view) btn.classList.add('active');
            else btn.classList.remove('active');
        }
    }

    for (const [key, el] of Object.entries(views)) {
        if (el) {
            el.style.display = (key === view) ? 'flex' : 'none';
        }
    }

    if (view === 'DAG' && currentPlanData) {
        renderDagSvg(currentPlanData);
    } else if (view === 'AUDIT') {
        fetchAuditEvents();
    } else if (view === 'GOV') {
        fetchGovernanceBudget();
    }
}

// ------------------------------------------------------------------------------
// 1. DAG PLAN VISUALIZER & SVG RENDERER
// ------------------------------------------------------------------------------

async function loadPlan(planId) {
    currentPlanId = planId;
    closeNodeInspector();

    document.querySelectorAll('.plan-pill').forEach(pill => {
        if (pill.getAttribute('onclick') && pill.getAttribute('onclick').includes(planId)) {
            pill.classList.add('active');
        } else {
            pill.classList.remove('active');
        }
    });

    try {
        const res = await fetch(`/api/v1/dag/current?plan_id=${encodeURIComponent(planId)}`);
        if (!res.ok) return;
        const plan = await res.json();
        currentPlanData = plan;
        renderDagSvg(plan);
        logDagMessage(`Loaded plan template: [${plan.title}] with ${plan.nodes.length} nodes`);
    } catch (err) {
        console.error('Failed to load DAG plan:', err);
    }
}

function renderDagSvg(plan) {
    const nodesLayer = document.getElementById('dagNodesLayer');
    const linksLayer = document.getElementById('dagLinksLayer');
    const svg = document.getElementById('dagSvg');
    if (!nodesLayer || !linksLayer || !svg || !plan || !plan.nodes) return;

    nodesLayer.innerHTML = '';
    linksLayer.innerHTML = '';

    const nodes = plan.nodes;
    const nodeMap = {};
    nodes.forEach(n => { nodeMap[n.id] = n; });

    // Compute topological layers
    const nodeLayers = {};
    function getLayer(nodeId, visited = new Set()) {
        if (nodeLayers[nodeId] !== undefined) return nodeLayers[nodeId];
        if (visited.has(nodeId)) return 0;
        visited.add(nodeId);

        const node = nodeMap[nodeId];
        if (!node || !node.dependencies || node.dependencies.length === 0) {
            nodeLayers[nodeId] = 0;
            return 0;
        }

        let maxDepLayer = 0;
        for (const depId of node.dependencies) {
            maxDepLayer = Math.max(maxDepLayer, getLayer(depId, visited) + 1);
        }
        nodeLayers[nodeId] = maxDepLayer;
        return maxDepLayer;
    }

    nodes.forEach(n => getLayer(n.id));

    // Group nodes by layer
    const layerBuckets = {};
    nodes.forEach(n => {
        const l = nodeLayers[n.id] || 0;
        if (!layerBuckets[l]) layerBuckets[l] = [];
        layerBuckets[l].push(n);
    });

    const totalLayers = Math.max(...Object.keys(layerBuckets).map(Number), 0) + 1;
    const containerW = document.getElementById('dagCanvasContainer')?.clientWidth || 700;
    const svgW = Math.max(containerW, 600);
    const svgH = 320;
    svg.setAttribute('width', '100%');
    svg.setAttribute('height', svgH.toString());

    const nodeW = 160;
    const nodeH = 64;

    const layerSpacing = totalLayers > 1 ? (svgW - 80 - nodeW) / (totalLayers - 1) : 0;
    const nodePositions = {};

    for (const [lStr, bNodes] of Object.entries(layerBuckets)) {
        const l = Number(lStr);
        const x = 40 + l * layerSpacing;
        const count = bNodes.length;
        const totalHeight = count * nodeH + (count - 1) * 24;
        const startY = Math.max(25, (svgH - totalHeight) / 2);

        bNodes.forEach((node, idx) => {
            const y = startY + idx * (nodeH + 24);
            nodePositions[node.id] = { x, y, width: nodeW, height: nodeH, node };
        });
    }

    // Draw Bézier Links between dependencies
    nodes.forEach(node => {
        if (!node.dependencies) return;
        const targetPos = nodePositions[node.id];
        if (!targetPos) return;

        node.dependencies.forEach(depId => {
            const srcPos = nodePositions[depId];
            if (!srcPos) return;

            const x1 = srcPos.x + srcPos.width;
            const y1 = srcPos.y + srcPos.height / 2;
            const x2 = targetPos.x;
            const y2 = targetPos.y + targetPos.height / 2;

            const dx = Math.max((x2 - x1) * 0.5, 30);
            const pathD = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;

            const isLinkActive = node.status === 'RUNNING' || (srcPos.node.status === 'COMPLETED' && node.status === 'COMPLETED');
            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            path.setAttribute('d', pathD);
            path.setAttribute('class', `dag-link ${isLinkActive ? 'active' : ''}`);
            path.setAttribute('marker-end', `url(#${isLinkActive ? 'arrowhead-active' : 'arrowhead'})`);
            linksLayer.appendChild(path);
        });
    });

    // Draw Nodes
    nodes.forEach(node => {
        const pos = nodePositions[node.id];
        if (!pos) return;

        const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        const isSelected = selectedNodeId === node.id;
        g.setAttribute('class', `dag-node status-${node.status} ${isSelected ? 'selected' : ''}`);
        g.setAttribute('data-node-id', node.id);
        g.onclick = () => inspectNode(node.id);

        // Rect
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('class', 'node-box');
        rect.setAttribute('x', pos.x.toString());
        rect.setAttribute('y', pos.y.toString());
        rect.setAttribute('width', pos.width.toString());
        rect.setAttribute('height', pos.height.toString());
        g.appendChild(rect);

        // Status Symbol / Icon
        const statusSymbols = {
            'COMPLETED': '✓',
            'RUNNING': '⚙',
            'PENDING': '⏳',
            'FAILED': '✕'
        };
        const symbol = statusSymbols[node.status] || '●';

        // Title text
        const titleText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        titleText.setAttribute('class', 'node-title-text');
        titleText.setAttribute('x', (pos.x + 10).toString());
        titleText.setAttribute('y', (pos.y + 20).toString());
        const truncatedTitle = node.title.length > 18 ? node.title.substring(0, 16) + '...' : node.title;
        titleText.textContent = `${symbol} ${truncatedTitle}`;
        g.appendChild(titleText);

        // Tool text
        const toolText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        toolText.setAttribute('class', 'node-tool-text');
        toolText.setAttribute('x', (pos.x + 10).toString());
        toolText.setAttribute('y', (pos.y + 38).toString());
        toolText.textContent = `[ ${node.tool} ]`;
        g.appendChild(toolText);

        // Status text & latency
        const statusText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        statusText.setAttribute('class', `node-status-text ${node.status}`);
        statusText.setAttribute('x', (pos.x + 10).toString());
        statusText.setAttribute('y', (pos.y + 53).toString());
        const lat = node.latency_ms ? `${node.latency_ms.toFixed(0)}ms` : '';
        statusText.textContent = `${node.status} ${lat ? '• ' + lat : ''}`;
        g.appendChild(statusText);

        nodesLayer.appendChild(g);
    });
}

function inspectNode(nodeId) {
    if (!currentPlanData || !currentPlanData.nodes) return;
    selectedNodeId = nodeId;
    const node = currentPlanData.nodes.find(n => n.id === nodeId);
    if (!node) return;

    renderDagSvg(currentPlanData);

    const insp = document.getElementById('dagNodeInspector');
    if (!insp) return;

    document.getElementById('inspNodeBadge').innerText = node.id.toUpperCase();
    document.getElementById('inspNodeTitle').innerText = node.title;
    document.getElementById('inspNodeTool').innerText = node.tool;
    
    const statusEl = document.getElementById('inspNodeStatus');
    statusEl.innerText = node.status;
    statusEl.className = `insp-val font-mono text-${node.status === 'COMPLETED' ? 'emerald' : (node.status === 'RUNNING' ? 'cyan' : (node.status === 'FAILED' ? 'coral' : 'muted'))}`;

    document.getElementById('inspNodeLatency').innerText = node.latency_ms ? `${node.latency_ms.toFixed(1)}ms` : '-';
    document.getElementById('inspNodeDeps').innerText = (node.dependencies && node.dependencies.length > 0) ? node.dependencies.join(', ') : 'None (Genesis Step)';
    document.getElementById('inspNodeDesc').innerText = node.description || 'No description';
    document.getElementById('inspNodeOutput').innerText = JSON.stringify(node.output || {}, null, 2);

    insp.style.display = 'flex';
}

function closeNodeInspector() {
    selectedNodeId = null;
    const insp = document.getElementById('dagNodeInspector');
    if (insp) insp.style.display = 'none';
    if (currentPlanData) renderDagSvg(currentPlanData);
}

async function executeCurrentPlan() {
    if (!currentPlanData) return;
    const execBtn = document.getElementById('btnExecuteDag');
    if (execBtn) {
        execBtn.disabled = true;
        execBtn.innerHTML = '<span class="icon">⚙</span> [ RUNNING... ]';
    }

    document.getElementById('dagExecStatus').innerText = 'EXECUTING';
    document.getElementById('dagExecStatus').style.color = 'var(--color-cyan)';
    logDagMessage(`Started autonomous execution run for [${currentPlanId}]`);

    // Reset nodes to pending locally
    currentPlanData.nodes.forEach(n => {
        n.status = 'PENDING';
        n.latency_ms = 0;
    });
    renderDagSvg(currentPlanData);

    try {
        const res = await fetch('/api/v1/dag/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                plan_id: currentPlanId,
                session_id: `studio-run-${Date.now()}`
            })
        });

        if (!res.ok) {
            const err = await res.json();
            logDagMessage(`Execution request error: ${err.detail || 'Unknown error'}`);
            if (execBtn) {
                execBtn.disabled = false;
                execBtn.innerHTML = '<span class="icon">▶</span> [ RUN DAG PLAN ]';
            }
        }
    } catch (err) {
        logDagMessage(`Network error during execution: ${err.message}`);
        if (execBtn) {
            execBtn.disabled = false;
            execBtn.innerHTML = '<span class="icon">▶</span> [ RUN DAG PLAN ]';
        }
    }
}

async function resetCurrentPlan() {
    closeNodeInspector();
    await loadPlan(currentPlanId);
    document.getElementById('dagExecStatus').innerText = 'RESET';
    document.getElementById('dagExecStatus').style.color = 'var(--text-secondary)';
    logDagMessage(`Plan [${currentPlanId}] state reset.`);
}

function handleDagStepUpdate(data) {
    if (!currentPlanData || !currentPlanData.nodes) return;
    const node = currentPlanData.nodes.find(n => n.id === data.node_id);
    if (node) {
        node.status = data.status;
        if (data.latency_ms) node.latency_ms = data.latency_ms;
        if (data.output) node.output = data.output;
        renderDagSvg(currentPlanData);

        if (selectedNodeId === node.id) {
            inspectNode(node.id);
        }
    }

    logDagMessage(`Step [${data.node_id}]: ${data.status} ${data.latency_ms ? '(' + data.latency_ms.toFixed(1) + 'ms)' : ''}`);
}

function handleDagCompleted(data) {
    const execBtn = document.getElementById('btnExecuteDag');
    if (execBtn) {
        execBtn.disabled = false;
        execBtn.innerHTML = '<span class="icon">▶</span> [ RUN DAG PLAN ]';
    }

    const statusEl = document.getElementById('dagExecStatus');
    if (statusEl) {
        statusEl.innerText = data.status || 'COMPLETED';
        statusEl.style.color = 'var(--color-emerald)';
    }

    logDagMessage(`Plan [${data.plan_id}] completed successfully in ${data.total_duration_ms ? data.total_duration_ms.toFixed(1) + 'ms' : 'sub-second'}.`);
    fetchAuditEvents();
    fetchGovernanceBudget();
}

function logDagMessage(msg) {
    const feed = document.getElementById('dagLogFeed');
    if (!feed) return;
    const timeStr = new Date().toTimeString().split(' ')[0];
    const span = document.createElement('span');
    span.className = 'log-line';
    span.innerHTML = `<span class="text-cyan">[${timeStr}]</span> ${escapeHtml(msg)}`;
    feed.appendChild(span);
    feed.scrollTop = feed.scrollHeight;
}

// ------------------------------------------------------------------------------
// 2. CRYPTOGRAPHIC AUDIT CHAIN INSPECTOR
// ------------------------------------------------------------------------------

async function fetchAuditEvents() {
    try {
        const res = await fetch('/api/v1/audit/events');
        if (!res.ok) return;
        const data = await res.json();
        auditEventsList = data.events || [];
        renderAuditChain(auditEventsList);
    } catch (err) {
        console.error('Failed to fetch audit events:', err);
    }
}

function renderAuditChain(events, tamperedIdx = -1) {
    const flow = document.getElementById('auditChainFlow');
    const countBadge = document.getElementById('auditChainCount');
    if (!flow) return;

    if (countBadge) {
        countBadge.innerText = `${events.length} EVENTS RECORDED`;
    }

    if (events.length === 0) {
        flow.innerHTML = '<div class="loading-text">No cryptographic audit events recorded.</div>';
        return;
    }

    flow.innerHTML = events.map((ev, idx) => {
        const isTampered = tamperedIdx === ev.sequence_number || ev.is_tampered;
        const isGenesis = ev.sequence_number === 1;
        const timeStr = new Date(ev.timestamp * 1000).toLocaleTimeString();
        const shortPrev = ev.previous_event_hash ? `${ev.previous_event_hash.substring(0, 12)}...${ev.previous_event_hash.substring(56)}` : 'GENESIS';
        const shortHash = ev.event_hash ? `${ev.event_hash.substring(0, 16)}...${ev.event_hash.substring(52)}` : 'UNKNOWN';

        const arrowDown = idx < events.length - 1 
            ? `<div class="audit-arrow-down">▼ [ SHA-256 HASH LINKAGE ] ▼</div>` 
            : '';

        return `
            <div class="audit-block-card ${isTampered ? 'tampered' : ''}" id="auditCard_${ev.sequence_number}">
                <div class="audit-block-header">
                    <div class="audit-block-seq">
                        <span class="seq-num">#${ev.sequence_number}</span>
                        ${isGenesis ? '<span class="genesis-badge">GENESIS BLOCK</span>' : ''}
                        <span class="audit-event-type">${ev.event_type}</span>
                    </div>
                    <div style="display: flex; gap: 8px; align-items: center;">
                        <span class="risk-pill ${ev.severity === 'HIGH' ? 'risk-HIGH' : ''}" style="border: 1px solid var(--border-glass);">${ev.severity}</span>
                        <span class="badge badge-node" style="color: var(--color-emerald);">${ev.outcome}</span>
                    </div>
                </div>

                <div class="audit-block-meta">
                    <span><strong>ACTOR:</strong> <span class="text-cyan font-mono">${ev.actor || 'system'}</span></span>
                    <span><strong>TOOL:</strong> <span class="text-white font-mono">${ev.tool_id || '-'}</span></span>
                    <span><strong>TIMESTAMP:</strong> <span class="font-mono">${timeStr}</span></span>
                </div>

                <div class="audit-hash-tray font-mono">
                    <div class="hash-row">
                        <span class="hash-label">PREV HASH:</span>
                        <span class="hash-val text-muted" title="${ev.previous_event_hash}">${shortPrev}</span>
                    </div>
                    <div class="hash-row">
                        <span class="hash-label">HASH:</span>
                        <span class="hash-val" style="color: ${isTampered ? 'var(--color-coral)' : 'var(--color-cyan)'};" title="${ev.event_hash}">${shortHash}</span>
                    </div>
                </div>
            </div>
            ${arrowDown}
        `;
    }).join('');
}

async function verifyAuditChain() {
    try {
        const res = await fetch('/api/v1/audit/verify', { method: 'POST' });
        const data = await res.json();
        const banner = document.getElementById('auditStatusBanner');
        const bannerDesc = document.getElementById('auditBannerDesc');

        if (data.valid) {
            if (banner) {
                banner.className = 'audit-status-banner banner-intact';
                banner.querySelector('.banner-icon').innerText = '✓';
                banner.querySelector('.banner-title').innerText = 'CRYPTOGRAPHIC INTEGRITY INTACT';
            }
            if (bannerDesc) {
                bannerDesc.innerText = `All ${data.events_checked} audit events cryptographically verified with SHA-256 genesis hash linkage. Zero tampering detected.`;
            }
            renderAuditChain(auditEventsList, -1);
        } else {
            if (banner) {
                banner.className = 'audit-status-banner banner-tampered';
                banner.querySelector('.banner-icon').innerText = '⚠️';
                banner.querySelector('.banner-title').innerText = 'INTEGRITY VIOLATION DETECTED';
            }
            if (bannerDesc) {
                bannerDesc.innerText = `CRITICAL: Hash mismatch detected at sequence #${data.tampered_sequence}! Recalculated hash does not match stored block hash.`;
            }
            renderAuditChain(auditEventsList, data.tampered_sequence);
        }
    } catch (err) {
        alert(`Verification failed: ${err.message}`);
    }
}

async function tamperAuditChain() {
    try {
        const res = await fetch('/api/v1/audit/tamper', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sequence_number: 3,
                corrupted_payload: {
                    outcome: 'TAMPERED_ROOT_EXPLOIT',
                    actor: 'malicious-attacker'
                }
            })
        });

        const data = await res.json();
        const banner = document.getElementById('auditStatusBanner');
        const bannerDesc = document.getElementById('auditBannerDesc');
        if (banner) {
            banner.className = 'audit-status-banner banner-tampered';
            banner.querySelector('.banner-icon').innerText = '⚠️';
            banner.querySelector('.banner-title').innerText = 'SIMULATED TAMPER INJECTED';
        }
        if (bannerDesc) {
            bannerDesc.innerText = `Injected unauthorized payload into block sequence #3 without cryptographic re-signing. Click [ VERIFY INTEGRITY ] to inspect cryptographic tripwire detection!`;
        }

        await fetchAuditEvents();
        renderAuditChain(auditEventsList, 3);
    } catch (err) {
        alert(`Tamper simulation failed: ${err.message}`);
    }
}

async function resetAuditChain() {
    try {
        const res = await fetch('/api/v1/audit/reset', { method: 'POST' });
        const banner = document.getElementById('auditStatusBanner');
        const bannerDesc = document.getElementById('auditBannerDesc');
        if (banner) {
            banner.className = 'audit-status-banner banner-intact';
            banner.querySelector('.banner-icon').innerText = '✓';
            banner.querySelector('.banner-title').innerText = 'CRYPTOGRAPHIC INTEGRITY INTACT';
        }
        if (bannerDesc) {
            bannerDesc.innerText = 'Restored clean 5-event cryptographic audit chain linked to GENESIS_HASH.';
        }
        await fetchAuditEvents();
    } catch (err) {
        alert(`Reset failed: ${err.message}`);
    }
}

function handleAuditEventCreated(data) {
    fetchAuditEvents();
}

function handleAuditTampered(data) {
    const banner = document.getElementById('auditStatusBanner');
    const bannerDesc = document.getElementById('auditBannerDesc');
    if (banner) {
        banner.className = 'audit-status-banner banner-tampered';
        banner.querySelector('.banner-icon').innerText = '⚠️';
        banner.querySelector('.banner-title').innerText = 'TAMPER DETECTED VIA EVENT STREAM';
    }
    if (bannerDesc) {
        bannerDesc.innerText = `Block sequence #${data.sequence_number} payload was modified without valid cryptographic signature.`;
    }
    fetchAuditEvents();
}

// ------------------------------------------------------------------------------
// 3. GOVERNANCE QUOTA & HITL APPROVALS
// ------------------------------------------------------------------------------

async function fetchGovernanceBudget() {
    try {
        const [bRes, aRes] = await Promise.all([
            fetch('/api/v1/governance/budget'),
            fetch('/api/v1/governance/approvals')
        ]);

        if (bRes.ok) {
            const bData = await bRes.json();
            governanceBudget = bData;
            renderGovernanceBudget(bData);
        }

        if (aRes.ok) {
            const aData = await aRes.json();
            pendingApprovalsList = aData;
            renderApprovals(aData);
        }
    } catch (err) {
        console.error('Failed to fetch governance status:', err);
    }
}

function renderGovernanceBudget(b) {
    if (!b || !b.limits || !b.usage) return;

    const toolUsed = b.usage.tool_calls_count || 0;
    const toolMax = b.limits.max_tool_calls || 50;
    const toolPct = Math.min(Math.round((toolUsed / toolMax) * 100), 100);
    document.getElementById('govToolCalls').innerText = `${toolUsed} / ${toolMax}`;
    document.getElementById('govToolBar').style.width = `${toolPct}%`;

    const tokUsed = b.usage.token_budget_consumed || 0;
    const tokMax = b.limits.max_tokens || 100000;
    const tokPct = Math.min(Math.round((tokUsed / tokMax) * 100), 100);
    document.getElementById('govTokens').innerText = `${(tokUsed / 1000).toFixed(1)}k / ${(tokMax / 1000).toFixed(0)}k`;
    document.getElementById('govTokenBar').style.width = `${tokPct}%`;

    const costUsed = b.usage.cost_usd || 0;
    const costMax = b.limits.max_cost_usd || 5.0;
    const costPct = Math.min(Math.round((costUsed / costMax) * 100), 100);
    document.getElementById('govCost').innerText = `$${costUsed.toFixed(2)} / $${costMax.toFixed(2)}`;
    document.getElementById('govCostBar').style.width = `${costPct}%`;

    const memUsed = b.usage.memory_mb_used || 0;
    const memMax = b.limits.max_memory_mb || 512;
    const memPct = Math.min(Math.round((memUsed / memMax) * 100), 100);
    document.getElementById('govMem').innerText = `${Math.round(memUsed)} / ${memMax} MB`;
    document.getElementById('govMemBar').style.width = `${memPct}%`;
}

function renderApprovals(approvals) {
    const feed = document.getElementById('approvalsListFeed');
    const badge = document.getElementById('approvalsCountBadge');
    if (!feed) return;

    const pending = approvals.filter(a => a.status === 'PENDING');
    if (badge) {
        badge.innerText = `${pending.length} PENDING`;
    }

    if (pending.length === 0) {
        feed.innerHTML = '<div class="loading-text" style="color: var(--color-emerald);">✓ Zero pending approvals. All security gates resolved.</div>';
        return;
    }

    feed.innerHTML = pending.map(app => `
        <div class="approval-item-card" id="approvalCard_${app.approval_id}">
            <div class="appr-info">
                <div class="appr-top-row">
                    <span class="risk-pill risk-${app.risk_level}">${app.risk_level} RISK</span>
                    <span class="appr-tool">${app.tool_name}</span>
                    <span class="badge badge-node font-mono">${app.approval_id}</span>
                </div>
                <div class="appr-desc">${app.reason || 'Restricted system operation requiring operator confirmation.'}</div>
                <div class="appr-meta font-mono">REQUESTER: ${app.requested_by} • PARAMS: ${JSON.stringify(app.parameters || {})}</div>
            </div>
            <div class="appr-actions">
                <button class="btn-approve" onclick="submitApprovalDecision('${app.approval_id}', 'APPROVED')">
                    [ ✓ APPROVE ]
                </button>
                <button class="btn-deny" onclick="submitApprovalDecision('${app.approval_id}', 'DENIED')">
                    [ ✕ DENY ]
                </button>
            </div>
        </div>
    `).join('');
}

async function submitApprovalDecision(approvalId, decision) {
    const card = document.getElementById(`approvalCard_${approvalId}`);
    if (card) {
        card.style.opacity = '0.5';
    }

    try {
        const res = await fetch(`/api/v1/governance/approvals/${approvalId}/decision`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                decision: decision,
                actor: 'lead-sec-operator'
            })
        });

        if (res.ok) {
            const data = await res.json();
            if (card) {
                card.className = `approval-item-card ${decision.toLowerCase()}`;
                card.innerHTML = `
                    <div style="padding: 6px 0; font-family: var(--font-mono);">
                        <strong>[ ${decision} ]</strong> Approval ${approvalId} resolved by ${data.actor}. Grant ID: ${data.grant_id || 'N/A'}
                    </div>
                `;
                setTimeout(() => {
                    fetchGovernanceBudget();
                }, 1000);
            }
        } else {
            const err = await res.json();
            alert(`Approval submission failed: ${err.detail || 'Unknown error'}`);
        }
    } catch (err) {
        alert(`Error: ${err.message}`);
    }
}

function handleGovernanceUpdated(data) {
    fetchGovernanceBudget();
}

function handleBudgetUpdated(data) {
    if (governanceBudget && governanceBudget.usage) {
        if (data.cost_usd !== undefined) governanceBudget.usage.cost_usd = data.cost_usd;
        if (data.tokens_consumed !== undefined) governanceBudget.usage.token_budget_consumed = data.tokens_consumed;
        renderGovernanceBudget(governanceBudget);
    }
}

