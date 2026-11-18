const DEFAULT_HTTP_BASE = 'http://127.0.0.1:8780/api';
const DEFAULT_WS_BASE = 'ws://127.0.0.1:8780/ws';

export function buildWsUrl(wsBase, { convId, generation, afterSeq }) {
  const cid = convId || 'default';
  const params = new URLSearchParams({ convId: cid });
  if (generation) params.set('generation', String(generation));
  if (Number.isFinite(afterSeq) && afterSeq >= 0) params.set('afterSeq', String(afterSeq));
  return `${wsBase}?${params.toString()}`;
}

export function createSyncClient(options = {}) {
  const {
    store,
    fetchImpl = typeof fetch === 'function' ? fetch.bind(globalThis) : null,
    WebSocketImpl = typeof WebSocket === 'function' ? WebSocket : null,
    httpBase = DEFAULT_HTTP_BASE,
    wsBase = DEFAULT_WS_BASE,
    sidecarObj = typeof globalThis !== 'undefined' ? globalThis.sidecar : null,
  } = options;

  let ws = null;
  let reconnectTimer = null;
  let backoffMs = 800;
  let destroyed = false;
  let pinnedConv = false;

  async function callApi(path, method = 'GET', payload = undefined) {
    const cleanPath = path.startsWith('/') ? path : `/${path}`;
    const relRoute = `/api${cleanPath}`;
    const absRoute = `${httpBase}${cleanPath}`;
    if (sidecarObj && typeof sidecarObj.invoke === 'function') {
      try {
        const res = await sidecarObj.invoke(relRoute, payload || {});
        if (res && res.status !== 'offline') return res;
      } catch (_) {}
    }
    const sidecarFetch = (sidecarObj && typeof sidecarObj.fetch === 'function')
      ? sidecarObj.fetch.bind(sidecarObj)
      : null;
    if (!fetchImpl && !sidecarFetch) return { status: 'offline', error: 'Fetch unavailable' };
    const urls = [relRoute, absRoute];
    for (let i = 0; i < urls.length; i += 1) {
      const url = urls[i];
      const isLast = i === urls.length - 1;
      const doFetch = (url === relRoute && sidecarFetch) ? sidecarFetch : fetchImpl;
      if (!doFetch) continue;
      try {
        const resp = await doFetch(url, {
          method,
          headers: payload !== undefined ? { 'Content-Type': 'application/json' } : undefined,
          body: payload !== undefined ? JSON.stringify(payload) : undefined,
        });
        const data = await resp.json().catch(() => ({}));
        if (resp.ok) {
          if (!isLast && data && (data.status === 'offline' || data.httpStatus === 401 || data.httpStatus === 403 || data.httpStatus === 404)) {
            continue;
          }
          return data;
        }
        if (!isLast && (resp.status === 401 || resp.status === 403 || resp.status === 404)) {
          continue;
        }
        return {
          status: 'error',
          httpStatus: resp.status,
          detail: data.detail || data.error || `HTTP ${resp.status}`,
          ...data,
        };
      } catch (_) {}
    }
    return { status: 'offline', error: 'Local backend unreachable' };
  }

  async function fetchStatus(explicitCid = '') {
    const cid = explicitCid || store.state.convId || '';
    const q = new URLSearchParams();
    if (cid) q.set('convId', cid);
    if (store.state.workspaceUri) q.set('workspaceUri', store.state.workspaceUri);
    const qs = q.toString() ? `?${q.toString()}` : '';
    const res = await callApi(`/status${qs}`, 'GET');
    if (!res || res.status === 'offline') {
      store.setConnection('offline', res?.error || '');
      return res;
    }
    if (res.status === 'error' || (Number.isFinite(res.httpStatus) && res.httpStatus >= 400)) {
      return res;
    }
    store.applySnapshot(res);
    return res;
  }

  function handleFrame(frame = {}) {
    if (!frame || typeof frame !== 'object') return;
    const type = String(frame.type || '').toUpperCase();
    if (type === 'SYNC_READY' || type === 'SYNC_PONG' || type === 'PONG') return;

    if (type === 'SYNC_SNAPSHOT') {
      backoffMs = 800;
      store.applySnapshot(frame.snapshot || frame);
      return;
    }

    if (type === 'SYNC_REPLAY') {
      backoffMs = 800;
      if (frame.generation && store.state.generation && frame.generation !== store.state.generation) {
        fetchStatus(frame.convId || store.state.convId);
        return;
      }
      const events = Array.isArray(frame.events) ? frame.events : [];
      for (const ev of events) {
        const evSeq = Number(ev?.seq || 0);
        const curSeq = Number(store.state.seq || 0);
        if (evSeq > curSeq + 1) {
          fetchStatus(frame.convId || store.state.convId);
          return;
        }
        store.applyCaseEvent(ev);
      }
      if (!store.state.thinkTank.isClosed) store.setConnection('live');
      return;
    }

    if (type === 'TRANSIENT_PULSE' || type === 'TELEMETRY_UPDATE') {
      if (frame.pulseKind === 'HOST_FOCUS' && !pinnedConv && frame.convId && frame.convId !== store.state.convId) {
        const myWs = store.state.workspaceUri || '';
        const frameWs = frame.workspaceUri || '';
        const myPid = store.state.projectId || '';
        const framePid = frame.projectId || '';
        const wsMatch = myWs ? (frameWs === myWs) : (!frameWs);
        const pidMatch = !myPid || !framePid || (myPid === framePid);
        if (wsMatch && pidMatch) {
          switchConversation(frame.convId, false);
          return;
        }
      }
      store.applyTransientPulse(frame);
      return;
    }

    if (frame.convId && store.state.convId && frame.convId !== store.state.convId) return;
    if (frame.generation && store.state.generation && frame.generation !== store.state.generation) {
      fetchStatus(store.state.convId);
      return;
    }
    const nextSeq = Number(frame.seq || 0);
    const curSeq = Number(store.state.seq || 0);
    if (nextSeq > curSeq + 1) {
      fetchStatus(store.state.convId);
      return;
    }
    store.applyCaseEvent(frame);
  }

  function scheduleReconnect() {
    if (destroyed || reconnectTimer) return;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      backoffMs = Math.min(6000, Math.round(backoffMs * 1.6));
      connectWs();
    }, backoffMs);
  }

  function closeSocket(targetWs) {
    if (!targetWs) return;
    try {
      targetWs.onopen = null;
      targetWs.onmessage = null;
      targetWs.onerror = null;
      targetWs.onclose = null;
      targetWs.close();
    } catch (_) {}
  }

  function connectWs() {
    if (destroyed || !WebSocketImpl) return;
    if (ws) {
      closeSocket(ws);
      ws = null;
    }
    const url = buildWsUrl(wsBase, {
      convId: store.state.convId || 'default',
      generation: store.state.generation,
      afterSeq: store.state.seq,
    });
    try {
      const sock = new WebSocketImpl(url);
      ws = sock;
      sock.onmessage = (ev) => {
        if (ws !== sock) return;
        try { handleFrame(JSON.parse(typeof ev.data === 'string' ? ev.data : '{}')); } catch (_) {}
      };
      sock.onerror = () => {};
      sock.onclose = () => {
        if (ws !== sock) return;
        ws = null;
        if (!destroyed) {
          if (store.state.connState !== 'offline') store.setConnection('syncing');
          scheduleReconnect();
        }
      };
    } catch (_) {
      scheduleReconnect();
    }
  }

  async function switchConversation(nextCid, manual = true) {
    if (!nextCid) return;
    pinnedConv = Boolean(manual);
    store.state.convId = nextCid;
    store.state.generation = '';
    store.state.seq = 0;
    store.setConnection('syncing');
    await fetchStatus(nextCid);
    connectWs();
  }

  async function syncActiveTab() {
    pinnedConv = false;
    const wsQuery = store.state.workspaceUri ? `?workspaceUri=${encodeURIComponent(store.state.workspaceUri)}` : '';
    const ctx = await callApi(`/host/context${wsQuery}`, 'GET');
    const cid = ctx?.conversationId || ctx?.convId || '';
    if (cid && (ctx?.workspaceMatched !== false || !store.state.workspaceUri)) {
      await switchConversation(cid, false);
    } else {
      await fetchStatus();
    }
  }

  async function start() {
    if (!store.state.workspaceUri && sidecarObj && typeof sidecarObj.getWorkspaceUris === 'function') {
      try {
        const uris = await Promise.race([
          Promise.resolve(sidecarObj.getWorkspaceUris()),
          new Promise((resolve) => setTimeout(() => resolve(null), 50)),
        ]);
        if (Array.isArray(uris) && uris[0]) store.state.workspaceUri = String(uris[0]).trim();
      } catch (_) {}
    }
    if (sidecarObj && typeof sidecarObj.onWorkspaceChange === 'function') {
      try {
        sidecarObj.onWorkspaceChange((uris) => {
          const nextWs = Array.isArray(uris) && uris[0] ? String(uris[0]).trim() : '';
          if (nextWs && nextWs !== store.state.workspaceUri) {
            store.state.workspaceUri = nextWs;
            syncActiveTab();
          }
        });
      } catch (_) {}
    }
    if (!store.state.convId) {
      const wsQuery = store.state.workspaceUri ? `?workspaceUri=${encodeURIComponent(store.state.workspaceUri)}` : '';
      const ctx = await callApi(`/host/context${wsQuery}`, 'GET');
      if ((ctx?.conversationId || ctx?.convId) && (ctx?.workspaceMatched !== false || !store.state.workspaceUri)) {
        store.state.convId = ctx.conversationId || ctx.convId;
      }
    }
    const snap = await fetchStatus(store.state.convId);
    if (!Array.isArray(snap?.conversationsList)) {
      const convs = await callApi('/conversations', 'GET');
      if (Array.isArray(convs?.conversations)) {
        store.state.conversationsList = convs.conversations;
        store.revs.headerRev += 1;
      }
    }
    if (store.state.loadState === 'loading' && (!snap || snap.status === 'offline')) {
      store.setConnection('offline', snap?.error || '');
    }
    if (snap && snap.status !== 'offline') connectWs();
  }

  function destroy() {
    destroyed = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (ws) {
      closeSocket(ws);
      ws = null;
    }
  }

  return {
    start, fetchStatus, handleFrame, connectWs, switchConversation, syncActiveTab, destroy,
    getApi: (path) => callApi(path, 'GET'),
    postApi: (path, payload) => callApi(path, 'POST', payload),
  };
}
