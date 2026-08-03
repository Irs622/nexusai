/* Hacker Typer Inspired JavaScript App Logic for NexusAI Dashboard */

let voiceEnabled = false;
let allTools = [];
let currentFilter = 'ALL';

// Initialize Dashboard
document.addEventListener('DOMContentLoaded', () => {
    updateClock();
    setInterval(updateClock, 1000);
    
    fetchStatus();
    setInterval(fetchStatus, 3000);

    fetchTools();
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
        btn.innerText = voiceEnabled ? '[ VOICE: ON ]' : '[ VOICE: OFF ]';
        btn.className = voiceEnabled ? 'btn btn-alert' : 'btn btn-accent';
    }
}

// Fetch System Status & Context
async function fetchStatus() {
    try {
        const res = await fetch('/api/status');
        if (!res.ok) return;
        const data = await res.json();
        
        const ctx = data.context || {};
        document.getElementById('ctxActiveApp').innerText = ctx.active_application || 'N/A';
        document.getElementById('ctxActiveTitle').innerText = ctx.active_window_title || 'N/A';
        document.getElementById('ctxGitBranch').innerText = ctx.git_branch || 'main';

        const cpu = Math.round(ctx.cpu_usage_percent || 0);
        const ram = Math.round(ctx.ram_usage_percent || 0);

        document.getElementById('cpuVal').innerText = `${cpu}%`;
        document.getElementById('cpuBar').style.width = `${cpu}%`;

        document.getElementById('ramVal').innerText = `${ram}%`;
        document.getElementById('ramBar').style.width = `${ram}%`;

    } catch (e) {
        console.error("Failed to fetch status:", e);
    }
}

// Fetch Capability Tools
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

// Render Tool Cards
function renderTools() {
    const feed = document.getElementById('toolsListFeed');
    if (!feed) return;

    const filtered = currentFilter === 'ALL' 
        ? allTools 
        : allTools.filter(t => t.risk_level === currentFilter);

    if (filtered.length === 0) {
        feed.innerHTML = `<div class="text-muted">No tools matching risk level ${currentFilter}</div>`;
        return;
    }

    feed.innerHTML = filtered.map(t => `
        <div class="tool-card">
            <div class="tool-card-head">
                <span class="tool-name">${t.name}</span>
                <span class="risk-tag risk-${t.risk_level}">${t.risk_level}</span>
            </div>
            <div class="tool-desc">${t.description}</div>
            <button class="btn btn-accent" style="margin-top: 4px;" onclick="openToolModal('${t.name}')">[ RUN TOOL ]</button>
        </div>
    `).join('');
}

function filterTools(level) {
    currentFilter = level;
    document.querySelectorAll('.filter-btn').forEach(b => {
        b.classList.toggle('active', b.innerText === level);
    });
    renderTools();
}

// Send Preset Prompt
function sendPresetPrompt(promptText) {
    const input = document.getElementById('promptInput');
    if (input) {
        input.value = promptText;
        document.getElementById('chatForm').dispatchEvent(new Event('submit'));
    }
}

// Handle Chat Submit
async function handleChatSubmit(event) {
    event.preventDefault();
    const input = document.getElementById('promptInput');
    const prompt = input.value.trim();
    if (!prompt) return;

    input.value = '';
    appendMessage('USER', prompt, 'msg-user');

    // Trigger LangGraph Visualizer Highlight: Reasoner Node Active
    setGraphState('reasoner', 'Node: Reasoner evaluating prompt & tools...');

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: prompt })
        });

        const data = await res.json();
        if (!res.ok) {
            appendMessage('SYSTEM ERROR', data.detail || 'Execution failed', 'msg-system');
            setGraphState('end', 'Workflow ended with error.');
            return;
        }

        const content = data.content || 'Execution completed.';
        const iterations = data.iterations || 1;

        document.getElementById('graphIterCount').innerText = iterations;

        // If iterations > 1, show that Tool Executor was invoked
        if (iterations > 1) {
            setGraphState('executor', `Executed tool iterations (${iterations}). Updating state graph...`);
            await new Promise(r => setTimeout(r, 600));
        }

        setGraphState('end', 'LangGraph state transition reached END successfully.');
        appendMessage('ASSISTANT', content, 'msg-assistant');

        // TTS synthesis if voice enabled
        if (voiceEnabled && 'speechSynthesis' in window) {
            const cleanText = content.replace(/[`*#]/g, '');
            const utter = new SpeechSynthesisUtterance(cleanText);
            window.speechSynthesis.speak(utter);
        }

    } catch (e) {
        appendMessage('SYSTEM ERROR', e.message, 'msg-system');
        setGraphState('end', 'Workflow crashed.');
    }
}

// Append Chat Message
function appendMessage(sender, text, msgClass) {
    const feed = document.getElementById('chatFeed');
    if (!feed) return;

    const div = document.createElement('div');
    div.className = `chat-msg ${msgClass}`;
    div.innerHTML = `
        <div class="msg-sender">[ ${sender} ]</div>
        <div class="msg-body">${escapeHtml(text)}</div>
    `;
    feed.appendChild(div);
    feed.scrollTop = feed.scrollHeight;
}

function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Update LangGraph Node Highlights
function setGraphState(node, logText) {
    const r = document.getElementById('nodeReasoner');
    const e = document.getElementById('nodeExecutor');
    const end = document.getElementById('nodeEnd');
    const feed = document.getElementById('graphLogFeed');

    r.className = 'graph-node';
    e.className = 'graph-node';
    end.className = 'graph-node';

    if (node === 'reasoner') r.className = 'graph-node active-node';
    if (node === 'executor') e.className = 'graph-node active-node';
    if (node === 'end') end.className = 'graph-node node-done';

    if (feed) feed.innerText = `> ${logText}`;
}

// Tool Execution Modal
function openToolModal(toolName) {
    const tool = allTools.find(t => t.name === toolName);
    if (!tool) return;

    document.getElementById('modalToolTitle').innerText = `// EXECUTE TOOL: ${tool.name}`;
    document.getElementById('modalToolDesc').innerText = tool.description;
    document.getElementById('modalToolName').value = tool.name;

    const container = document.getElementById('modalParamsContainer');
    container.innerHTML = '';

    const props = tool.parameters?.properties || {};
    const required = tool.parameters?.required || [];

    for (const [key, prop] of Object.entries(props)) {
        const isReq = required.includes(key);
        const div = document.createElement('div');
        div.className = 'param-field';
        div.innerHTML = `
            <label class="context-label">${key.toUpperCase()} ${isReq ? '*' : ''} (${prop.type || 'string'})</label>
            <input type="text" name="${key}" class="param-input" placeholder="${prop.description || ''}" ${isReq ? 'required' : ''}>
        `;
        container.appendChild(div);
    }

    document.getElementById('toolModal').style.display = 'flex';
}

function closeToolModal() {
    document.getElementById('toolModal').style.display = 'none';
}

async function submitToolExecution(event) {
    event.preventDefault();
    const toolName = document.getElementById('modalToolName').value;
    const userConfirmed = document.getElementById('modalUserConfirm').checked;

    const container = document.getElementById('modalParamsContainer');
    const inputs = container.querySelectorAll('.param-input');
    const args = {};

    inputs.forEach(inp => {
        if (inp.value.trim()) {
            args[inp.name] = inp.value.trim();
        }
    });

    closeToolModal();
    appendMessage('USER (MANUAL EXEC)', `Run Tool: ${toolName} with args: ${JSON.stringify(args)}`, 'msg-user');

    setGraphState('executor', `Direct tool dispatch: ${toolName}...`);

    try {
        const res = await fetch('/api/tools/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tool_name: toolName,
                arguments: args,
                user_confirmed: userConfirmed
            })
        });

        const data = await res.json();
        if (!res.ok) {
            appendMessage('SYSTEM ERROR', data.detail || 'Tool execution denied/failed', 'msg-system');
            setGraphState('end', 'Tool execution failed.');
            return;
        }

        setGraphState('end', `Tool ${toolName} executed successfully.`);
        const outStr = typeof data.output === 'object' ? JSON.stringify(data.output, null, 2) : String(data.output);
        appendMessage(`TOOL OUTPUT [${toolName}]`, outStr, 'msg-assistant');

    } catch (e) {
        appendMessage('SYSTEM ERROR', e.message, 'msg-system');
        setGraphState('end', 'Tool execution crashed.');
    }
}
