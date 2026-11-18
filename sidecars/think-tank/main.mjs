import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Response, SidecarApp } from 'sidecar_sdk';
import { backendProjectHeaders } from './backend-headers.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const app = new SidecarApp();
const API = 'http://127.0.0.1:8780/api';
const PLUGIN_BACKEND_DIR = join(HERE, '..', '..', 'backend');
const GLOBAL_BACKEND_DIR = join(
  process.env.USERPROFILE || process.env.HOME || homedir(),
  '.gemini', 'config', 'thinktank', 'backend',
);
const BACKEND_DIR = process.env.THINKTANK_BACKEND_DIR
  || (existsSync(join(PLUGIN_BACKEND_DIR, 'app.py')) ? PLUGIN_BACKEND_DIR : GLOBAL_BACKEND_DIR);

let backendStartup = null;
let lastBackendHealthyAt = 0;
const HEALTH_CACHE_TTL_MS = 4000;

const readLocal = (name) => readFileSync(join(HERE, name), 'utf8');

function normalizeWorkspaceUri(raw) {
  const src = Array.isArray(raw) ? raw.find((item) => typeof item === 'string' && item.trim()) : raw;
  if (typeof src !== 'string' || !src.trim()) return '';
  let val = src.trim();
  if (val.toLowerCase().startsWith('file://')) {
    try { val = decodeURIComponent(val); } catch (_) {}
  } else if (/^[A-Za-z]:[\\/]/.test(val)) {
    val = `file:///${val.replace(/\\/g, '/')}`;
  } else if (val.startsWith('/')) {
    val = `file://${val}`;
  }
  val = val.replace(/\\/g, '/').replace(/\/+$/, '');
  if (process.platform === 'win32' || /^file:\/\/\/[A-Za-z]:/i.test(val)) {
    val = val.replace(/^(file:\/\/\/)([A-Za-z]):/i, (_, p, d) => `${p}${d.toLowerCase()}:`);
    if (process.platform === 'win32') val = val.toLowerCase();
  }
  return val;
}

function getActiveSessionContext(rawWorkspaceUri = '') {
  const workspaceUri = normalizeWorkspaceUri(rawWorkspaceUri);
  const configDir = (process.env.GEMINI_CONFIG_DIR || '').trim()
    || join(process.env.USERPROFILE || process.env.HOME || homedir(), '.gemini', 'config');
  const envCid = String(app.config?.conversationId || '').trim();
  let cid = envCid && envCid !== 'default' ? envCid : '';
  let pid = app.config?.projectId || '';
  let workspaceMatched = true;

  if (!cid) {
    try {
      const activeFile = join(configDir, 'active_antigravity_session.json');
      if (existsSync(activeFile)) {
        const d = JSON.parse(readFileSync(activeFile, 'utf8'));
        const wsEntry = workspaceUri && d?.sessionsByWorkspace?.[workspaceUri];
        if (wsEntry && wsEntry.conversationId) {
          cid = String(wsEntry.conversationId).trim();
          pid = wsEntry.projectId || pid;
        } else {
          const activeWs = normalizeWorkspaceUri(d?.workspaceUri || '');
          if (workspaceUri && activeWs && activeWs !== workspaceUri) {
            cid = '';
            workspaceMatched = false;
          } else {
            cid = String(d?.parentConversationId || d?.conversationId || '').trim();
            pid = d?.projectId || pid;
          }
        }
      }
    } catch (_) {}
  }

  if (cid) {
    try {
      const linksFile = join(configDir, 'subagent_links.json');
      if (existsSync(linksFile)) {
        const links = JSON.parse(readFileSync(linksFile, 'utf8'));
        const linkedParent = String(links?.[cid]?.parentConversationId || '').trim();
        if (linkedParent) cid = linkedParent;
      }
    } catch (_) {}
  }

  return { conversationId: cid, convId: cid, projectId: pid, workspaceUri, workspaceMatched };
}

const serveRoot = () => {
  ensureBackendRunning().catch(() => {});
  const html = readLocal('index.html');
  const ctx = getActiveSessionContext();
  const hostCid = ctx.conversationId;
  const hostPid = ctx.projectId;
  const injection = `<script>
    window.__ANTIGRAVITY_HOST_CONTEXT__ = {
      conversationId: ${JSON.stringify(hostCid)},
      convId: ${JSON.stringify(hostCid)},
      projectId: ${JSON.stringify(hostPid)}
    };
    window.sidecar = window.sidecar || {};
    if (!window.sidecar.conversationId && ${JSON.stringify(hostCid)}) window.sidecar.conversationId = ${JSON.stringify(hostCid)};
    if (!window.sidecar.convId && (window.sidecar.conversationId || ${JSON.stringify(hostCid)})) window.sidecar.convId = window.sidecar.conversationId || ${JSON.stringify(hostCid)};
    if (!window.sidecar.projectId && ${JSON.stringify(hostPid)}) window.sidecar.projectId = ${JSON.stringify(hostPid)};
  </script>`;
  return new Response(html.replace('</head>', `${injection}\n</head>`), {
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-cache',
    },
  });
};

app.page('/', serveRoot);
app.page('/index.html', serveRoot);
app.page('/think-tank/', serveRoot);
app.page('/think-tank/index.html', serveRoot);

const registeredPageRoutes = new Set();
function registerTextAsset(route, relPath, contentType, cacheControl = 'no-cache') {
  if (registeredPageRoutes.has(route)) return;
  const full = join(HERE, relPath);
  registeredPageRoutes.add(route);
  const handler = () => new Response(readFileSync(full, 'utf8'), {
    contentType,
    headers: {
      'Content-Type': contentType,
      'Cache-Control': cacheControl,
    },
  });
  app.page(route, handler);
  app.page(`/think-tank${route}`, handler);
}

registerTextAsset('/fonts.css', 'fonts.css', 'text/css; charset=utf-8', 'public, max-age=3600');
registerTextAsset('/tokens.css', 'tokens.css', 'text/css; charset=utf-8');
registerTextAsset('/app.css', 'app.css', 'text/css; charset=utf-8');
registerTextAsset('/backend-headers.mjs', 'backend-headers.mjs', 'application/javascript; charset=utf-8');
registerTextAsset('/role_catalog.json', 'role_catalog.json', 'application/json; charset=utf-8');

app.page('/think-tank/preload.js', () => {
  let preloadPath = join(HERE, 'preload.js');
  try {
    preloadPath = require.resolve('sidecar_sdk/preload.js');
  } catch (_) {}
  return new Response(readFileSync(preloadPath, 'utf8'), {
    contentType: 'application/javascript; charset=utf-8',
    headers: { 'Content-Type': 'application/javascript; charset=utf-8', 'Cache-Control': 'no-cache' },
  });
});

app.page('/favicon.ico', () => new Response(readFileSync(join(HERE, 'assets', 'thinktank-logo.svg')), {
  contentType: 'image/svg+xml',
  headers: { 'Content-Type': 'image/svg+xml', 'Cache-Control': 'public, max-age=86400' },
}));

const coreModules = [
  'src/app.mjs',
  'src/i18n.mjs',
  'src/roles.mjs',
  'src/store.mjs',
  'src/dom.mjs',
  'src/sync.mjs',
  'src/inspector.mjs',
  'src/boards/command-board.mjs',
  'src/boards/topology-board.mjs',
  'src/boards/chronicle-board.mjs',
  'src/boards/squad-board.mjs',
];
for (const relPath of coreModules) {
  registerTextAsset(`/${relPath}`, relPath, 'application/javascript; charset=utf-8');
}
for (const subDir of ['src', join('src', 'boards')]) {
  const absDir = join(HERE, subDir);
  if (!existsSync(absDir)) continue;
  for (const name of readdirSync(absDir)) {
    if (!name.endsWith('.mjs') && !name.endsWith('.js')) continue;
    const relPath = join(subDir, name);
    registerTextAsset(`/${relPath.replace(/\\/g, '/')}`, relPath, 'application/javascript; charset=utf-8');
  }
}

const fontsDir = join(HERE, 'fonts');
if (existsSync(fontsDir)) {
  for (const name of readdirSync(fontsDir)) {
    if (!name.endsWith('.ttf') && !name.endsWith('.woff2')) continue;
    const file = join(fontsDir, name);
    const ct = name.endsWith('.woff2') ? 'font/woff2' : 'font/ttf';
    const handler = () => new Response(readFileSync(file), {
      contentType: ct,
      headers: {
        'Content-Type': ct,
        'Access-Control-Allow-Origin': '*',
        'Cache-Control': 'public, max-age=31536000, immutable',
      },
    });
    app.page(`/fonts/${name}`, handler);
    app.page(`/think-tank/fonts/${name}`, handler);
  }
}

const assetsDir = join(HERE, 'assets');
if (existsSync(assetsDir)) {
  for (const name of readdirSync(assetsDir)) {
    if (name.endsWith('.svg') || name.endsWith('.png') || name.endsWith('.ico')) {
      const file = join(assetsDir, name);
      const ct = name.endsWith('.svg') ? 'image/svg+xml' : (name.endsWith('.png') ? 'image/png' : 'image/x-icon');
      const handler = () => new Response(readFileSync(file), {
        contentType: ct,
        headers: {
          'Content-Type': ct,
          'Cache-Control': 'public, max-age=86400',
        },
      });
      app.page(`/assets/${name}`, handler);
      app.page(`/think-tank/assets/${name}`, handler);
    }
  }
}

const avatarsDir = join(HERE, 'assets', 'avatars');
if (existsSync(avatarsDir)) {
  for (const name of readdirSync(avatarsDir)) {
    if (!name.endsWith('.svg')) continue;
    const file = join(avatarsDir, name);
    const handler = () => new Response(readFileSync(file, 'utf8'), {
      contentType: 'image/svg+xml',
      headers: {
        'Content-Type': 'image/svg+xml',
        'Cache-Control': 'public, max-age=86400',
      },
    });
    app.page(`/assets/avatars/${name}`, handler);
    app.page(`/think-tank/assets/avatars/${name}`, handler);
  }
}

let roleCatalog = [];
const catalogPath = join(HERE, 'role_catalog.json');
if (existsSync(catalogPath)) {
  try {
    roleCatalog = JSON.parse(readFileSync(catalogPath, 'utf8'));
  } catch (err) {
    console.error('Failed to parse role_catalog.json', err);
  }
}
app.api('/api/roles', () => ({ roles: roleCatalog }), 'GET');
app.api('/roles', () => ({ roles: roleCatalog }), 'GET');

const resolveHostContextHandler = async (data) => {
  const wsUri = normalizeWorkspaceUri(data?.workspaceUri || data?.workspace || '');
  const envCid = String(app.config?.conversationId || '').trim();
  if (envCid && envCid !== 'default' && !wsUri) return getActiveSessionContext(wsUri);
  const query = wsUri ? `?workspaceUri=${encodeURIComponent(wsUri)}` : '';
  const live = await forward(`/host/context${query}`, 'GET');
  if (live && !live.error && live.status !== 'offline' && 'conversationId' in live) {
    return { ...live, convId: live.conversationId || '' };
  }
  return getActiveSessionContext(wsUri);
};
app.api('/api/host/context', resolveHostContextHandler, 'GET');
app.api('/host/context', resolveHostContextHandler, 'GET');

async function forward(path, method, data) {
  try {
    const backend = await ensureBackendRunning();
    if (!backend.ok) return { status: 'offline', syncMode: 'disconnected', error: backend.error };
    const eventId = data?.eventId || crypto.randomUUID();
    const response = await fetch(`${API}${path}`, {
      method,
      headers: {
        ...backendProjectHeaders(app.config?.projectId),
        ...(data ? { 'Content-Type': 'application/json', 'X-ThinkTank-Event-Id': eventId } : {}),
      },
      body: data ? JSON.stringify(data) : undefined,
      signal: AbortSignal.timeout(10000),
    });
    const body = await response.json().catch(() => ({}));
    return response.ok ? body : {
      status: 'error',
      httpStatus: response.status,
      detail: body.detail || body.error || `Backend returned HTTP ${response.status}`,
      error: body.detail || body.error || `Backend returned HTTP ${response.status}`,
    };
  } catch (error) {
    lastBackendHealthyAt = 0;
    return { status: 'offline', syncMode: 'disconnected', error: error.message };
  }
}

async function backendHealthy() {
  if (Date.now() - lastBackendHealthyAt < HEALTH_CACHE_TTL_MS) return true;
  try {
    let response = await fetch(`${API}/health`, { signal: AbortSignal.timeout(900) });
    if (response.status === 404) {
      response = await fetch(`${API}/status`, { signal: AbortSignal.timeout(1200) });
    }
    if (!response.ok) return false;
    const body = await response.json().catch(() => ({}));
    const healthy = body.syncMode === 'durable-websocket' && (Boolean(body.ok) || Boolean(body.sync?.generation));
    if (healthy) lastBackendHealthyAt = Date.now();
    return healthy;
  } catch {
    lastBackendHealthyAt = 0;
    return false;
  }
}

function resolveBackendPython() {
  const explicit = (process.env.THINKTANK_PYTHON || process.env.PYTHON || '').trim();
  if (explicit) return explicit;
  const configDir = (process.env.GEMINI_CONFIG_DIR || '').trim()
    || join(process.env.USERPROFILE || process.env.HOME || homedir(), '.gemini', 'config');
  try {
    const runtimePath = join(configDir, 'thinktank', 'runtime.json');
    if (existsSync(runtimePath)) {
      const meta = JSON.parse(readFileSync(runtimePath, 'utf8'));
      const recorded = String(meta?.pythonExecutable || '').trim();
      if (recorded && existsSync(recorded)) return recorded;
    }
  } catch (_) {}
  return process.platform === 'win32' ? 'python' : 'python3';
}

async function ensureBackendRunning() {
  if (await backendHealthy()) return { ok: true };
  if (['0', 'false', 'no'].includes(String(process.env.THINKTANK_AUTO_START || '1').toLowerCase())) {
    return { ok: false, error: 'Backend auto-start is disabled.' };
  }
  if (!existsSync(join(BACKEND_DIR, 'app.py'))) {
    return { ok: false, error: 'ThinkTank backend app.py was not found.' };
  }
  if (!backendStartup) {
    backendStartup = (async () => {
      try {
        const python = resolveBackendPython();
        const child = spawn(python, [
          '-m', 'uvicorn', 'app:app', '--host', '127.0.0.1', '--port', '8780', '--no-use-colors',
        ], {
          cwd: BACKEND_DIR,
          detached: true,
          stdio: 'ignore',
          windowsHide: true,
          env: process.env,
        });
        child.on('error', () => {});
        child.unref();
      } catch (error) {
        return { ok: false, error: `Could not start ThinkTank backend: ${error.message}` };
      }

      for (let attempt = 0; attempt < 30; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 150));
        if (await backendHealthy()) return { ok: true };
      }
      return { ok: false, error: 'ThinkTank backend did not become healthy on 127.0.0.1:8780.' };
    })().finally(() => { backendStartup = null; });
  }
  return backendStartup;
}

for (const endpoint of ['/status', '/conversations', '/telemetry', '/health']) {
  const handleGetEndpoint = async (data) => {
    const wsUri = normalizeWorkspaceUri(data?.workspaceUri || data?.workspace || '');
    const explicitCid = data?.convId || data?.conversationId || '';
    let cid = explicitCid;
    if (!cid && endpoint === '/status') {
      const ctx = getActiveSessionContext(wsUri);
      cid = ctx.workspaceMatched === false ? 'default' : (ctx.conversationId || '');
    }
    const qParts = [];
    if (cid) qParts.push(`convId=${encodeURIComponent(cid)}`);
    if (wsUri && endpoint === '/status') qParts.push(`workspaceUri=${encodeURIComponent(wsUri)}`);
    const query = qParts.length ? `?${qParts.join('&')}` : '';
    return forward(`${endpoint}${query}`, 'GET');
  };
  app.api(`/api${endpoint}`, handleGetEndpoint, 'GET');
  app.api(endpoint, handleGetEndpoint, 'GET');
}

const handleStatusQuery = async (data) => {
  const wsUri = normalizeWorkspaceUri(data?.workspaceUri || data?.workspace || '');
  let cid = data?.convId || data?.conversationId || '';
  if (!cid) {
    const ctx = getActiveSessionContext(wsUri);
    cid = ctx.workspaceMatched === false ? 'default' : (ctx.conversationId || '');
  }
  const qParts = [];
  if (cid) qParts.push(`convId=${encodeURIComponent(cid)}`);
  if (wsUri) qParts.push(`workspaceUri=${encodeURIComponent(wsUri)}`);
  const query = qParts.length ? `?${qParts.join('&')}` : '';
  return forward(`/status${query}`, 'POST', { convId: cid || undefined, workspaceUri: wsUri || undefined });
};
app.api('/api/status/query', handleStatusQuery, 'POST');
app.api('/status/query', handleStatusQuery, 'POST');

app.api('/api/host/send-message', async (data) => {
  const convId = String(data?.convId || '').trim();
  const prompt = String(data?.prompt || '').trim();
  if (!convId || convId === 'default') return { status: 'error', error: 'Active host conversation ID is unavailable.' };
  if (!prompt) return { status: 'error', error: 'Message cannot be empty.' };
  if (prompt.length > 4000) return { status: 'error', error: 'Message exceeds the 4000 character limit.' };
  try {
    const result = app.sendMessage(convId, prompt);
    if (result?.success === false || result?.status === 'error') {
      return { status: 'error', convId, error: String(result.error || result.message || 'Antigravity rejected the message.') };
    }
    return { status: 'sent', convId, hostResult: result };
  } catch (error) {
    const detail = String(error.message || 'Antigravity could not accept the message.').trim();
    return { status: 'error', convId, error: detail.slice(0, 1200) };
  }
}, 'POST');

app.api('/api/governance/review_decision', async (data) => {
  const convId = String(data?.convId || '').trim();
  const decision = String(data?.decision || '').trim();
  if (!convId || convId === 'default') return { status: 'error', error: 'Active host conversation ID is unavailable.' };
  if (!['continue', 'stop'].includes(decision)) return { status: 'error', error: 'Review decision must be continue or stop.' };
  const recorded = await forward('/governance/review_decision', 'POST', data);
  if (recorded.status === 'offline' || recorded.status === 'error') return recorded;
  const choice = decision === 'continue' ? 'ادامهٔ کار' : 'توقف کار';
  const prompt = `تصمیم قطعی کاربر در بازبینی اتاق فکر: ${choice}. این تصمیم را در همین گفتگوی میزبان اجرا کن. شناسهٔ نشست اتاق فکر ${JSON.stringify(convId)} است؛ همهٔ فرمان‌های thinktank_bridge.py را با --conv-id ${JSON.stringify(convId)} اجرا کن.`;
  try {
    const hostResult = app.sendMessage(convId, prompt);
    if (hostResult?.success === false || hostResult?.status === 'error') {
      throw new Error(String(hostResult.error || hostResult.message || 'Antigravity rejected the decision.'));
    }
    const delivery = await forward('/governance/review_decision_dispatch', 'POST', { convId, status: 'sent' });
    return { ...recorded, status: 'sent', review: delivery.review || recorded.review };
  } catch (error) {
    const detail = String(error.message || 'Antigravity could not accept the decision.').slice(0, 800);
    const delivery = await forward('/governance/review_decision_dispatch', 'POST', { convId, status: 'failed', error: detail });
    return { ...recorded, status: 'recorded_not_dispatched', error: detail, review: delivery.review || recorded.review };
  }
}, 'POST');

const postRoutes = [
  '/api/host/active-session', '/api/agent/update', '/api/agent/collaborate',
  '/api/task/update', '/api/subtasks/upsert', '/api/proposal/update',
  '/api/proposal/action', '/api/proposal/vote', '/api/chat/send',
  '/api/messages/send', '/api/governance/extend_rounds', '/api/governance/reopen',
  '/api/governance/compress_final', '/api/governance/review_dispatch',
  '/api/governance/review_decision_dispatch', '/api/governance/submit_review',
  '/api/findings/action', '/api/telemetry/host_tool', '/api/telemetry/tool_call',
  '/api/telemetry/terminal_log', '/api/telemetry/task', '/api/tools/execute',
];

for (const route of postRoutes) {
  const backendPath = route.replace('/api', '');
  app.api(route, (data) => forward(backendPath, 'POST', data || {}), 'POST');
  app.api(backendPath, (data) => forward(backendPath, 'POST', data || {}), 'POST');
}

app.api('/api/dispatch', (data) => forward('/tools/execute', 'POST', data || {}), 'POST');
app.api('/dispatch', (data) => forward('/tools/execute', 'POST', data || {}), 'POST');

ensureBackendRunning().catch(() => {});
app.run();
