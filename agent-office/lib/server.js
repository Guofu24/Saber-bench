'use strict';
const http = require('http');
const https = require('https');
const zlib = require('zlib');
const fs = require('fs');
const path = require('path');
const { Analyzer } = require('./analyzer');
const { normalizeSnapshot, MAX_BYTES } = require('./snapshot');

const VIEWER = path.join(__dirname, '..', 'viewer', 'index.html');
const EVENT_TYPES = new Set(['agent', 'task', 'llm_start', 'tool', 'llm_end', 'llm_error', 'handoff', 'process', 'message', 'status']);

function createOffice({ upstreams = {}, config = {}, log = () => {}, readOnly = false, readNative = null, readRange = null }) {
  const clients = new Set();
  const history = [];
  const agents = new Map();
  const worlds = new Map();
  let seq = 0;
  const boot = Date.now().toString(36);

  function emit(ev) {
    if (ev.type === 'world_snapshot') {
      ev = normalizeSnapshot(ev);
      const previous = worlds.get(ev.world_id);
      if (previous && ev.updated_at <= previous.updated_at) return;
      if (!worlds.has(ev.world_id) && worlds.size >= 16) worlds.delete(worlds.keys().next().value);
    }
    ev.seq = ++seq; ev.ts = Date.now();
    if (ev.type === 'world_snapshot') worlds.set(ev.world_id, ev);
    else if (ev.type === 'agent') agents.set(ev.id, { ...(agents.get(ev.id) || {}), ...ev });
    else { history.push(ev); if (history.length > 400) history.shift(); }
    const line = `data: ${JSON.stringify(ev)}\n\n`;
    for (const c of clients) c.write(line);
  }
  const analyzer = new Analyzer(emit, config);

  function sse(req, res) {
    res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache', connection: 'keep-alive', 'access-control-allow-origin': '*' });
    res.write(`data: ${JSON.stringify({ type: 'hello', boot })}\n\n`);
    for (const a of agents.values()) res.write(`data: ${JSON.stringify({ ...a, replay: true })}\n\n`);
    for (const e of history) res.write(`data: ${JSON.stringify({ ...e, replay: true })}\n\n`);
    for (const e of [...worlds.values()].sort((a, b) => a.seq - b.seq)) res.write(`data: ${JSON.stringify({ ...e, replay: true })}\n\n`);
    res.write(`data: ${JSON.stringify({ type: 'replay_done' })}\n\n`);
    clients.add(res);
    req.on('close', () => clients.delete(res));
  }

  function readBody(req, limit = Infinity) {
    return new Promise((resolve, reject) => { const ch = []; let size = 0; req.on('data', c => { size += c.length; if (size > limit) { ch.length = 0; reject(new Error('Body too large')); } else ch.push(c); }); req.on('end', () => resolve(Buffer.concat(ch))); req.on('error', reject); });
  }

  async function proxy(req, res, provider, rest) {
    const base = upstreams[provider];
    const body = await readBody(req);
    let json = null;
    if (body.length && /json/.test(req.headers['content-type'] || '')) { try { json = JSON.parse(body.toString('utf8')); } catch (_) { /* not json */ } }
    let call = null;
    try { call = json ? analyzer.begin(provider, rest.split('?')[0], json, req.headers) : null; } catch (e) { log('analyzer error: ' + e.message); }

    const target = new URL(base.replace(/\/+$/, '') + rest);
    const headers = { ...req.headers };
    delete headers.host; delete headers.connection; delete headers['content-length'];
    headers['accept-encoding'] = 'identity';
    if (body.length) headers['content-length'] = body.length;
    const mod = target.protocol === 'https:' ? https : http;
    const up = mod.request(target, { method: req.method, headers }, upRes => {
      const h = { ...upRes.headers }; delete h['transfer-encoding']; delete h.connection;
      res.writeHead(upRes.statusCode, h);
      const ct = upRes.headers['content-type'] || '';
      const enc = (upRes.headers['content-encoding'] || '').toLowerCase();
      let decoder = null;
      if (call) {
        decoder = enc.includes('gzip') ? zlib.createGunzip() : enc.includes('br') ? zlib.createBrotliDecompress() : enc.includes('deflate') ? zlib.createInflate() : null;
        const sink = [];
        let buf = '';
        const isSSE = ct.includes('event-stream');
        const feed = chunk => {
          if (!isSSE) { sink.push(chunk); return; }
          buf += chunk.toString('utf8');
          let i;
          while ((i = buf.search(/\r?\n\r?\n/)) >= 0) {
            const block = buf.slice(0, i); buf = buf.slice(i).replace(/^\r?\n\r?\n/, '');
            let event = '', data = '';
            for (const l of block.split(/\r?\n/)) { if (l.startsWith('event:')) event = l.slice(6).trim(); else if (l.startsWith('data:')) data += l.slice(5).trim(); }
            if (data && data !== '[DONE]') { try { call.onSSE(event, data); } catch (_) { /* ignore */ } }
          }
        };
        const finish = () => {
          try {
            if (!isSSE) { let parsed = null; try { parsed = JSON.parse(Buffer.concat(sink).toString('utf8')); } catch (_) { /* ignore */ } if (upRes.statusCode < 400) call.onJSON(parsed); else call.text = parsed && parsed.error ? (parsed.error.message || JSON.stringify(parsed.error)) : ''; }
            call.end(upRes.statusCode);
          } catch (e) { log('analyzer error: ' + e.message); }
        };
        if (decoder) { decoder.on('data', feed); decoder.on('end', finish); decoder.on('error', () => call.end(upRes.statusCode)); }
        upRes.on('data', c => { res.write(c); decoder ? decoder.write(c) : feed(c); });
        upRes.on('end', () => { res.end(); decoder ? decoder.end() : finish(); });
      } else {
        upRes.pipe(res);
      }
      upRes.on('error', () => { if (call) call.end(599, 'upstream stream error'); res.end(); });
    });
    up.on('error', e => {
      log(`upstream error (${provider}): ${e.message}`);
      if (call) call.end(502, e.message);
      if (!res.headersSent) res.writeHead(502, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ error: { message: 'agent-office proxy: ' + e.message } }));
    });
    req.on('aborted', () => up.destroy());
    up.end(body);
  }

  const server = http.createServer(async (req, res) => {
    try {
      const url = req.url || '/';
      if (readOnly && (req.method !== 'GET' || url.startsWith('/openai') || url.startsWith('/anthropic'))) { res.writeHead(405); return res.end('read-only monitor'); }
      if (url.startsWith('/openai/') || url === '/openai') return await proxy(req, res, 'openai', url.slice(7) || '/');
      if (url.startsWith('/anthropic/') || url === '/anthropic') return await proxy(req, res, 'anthropic', url.slice(10) || '/');
      if (req.method === 'GET' && url === '/events') return sse(req, res);
      if (req.method === 'POST' && url === '/ingest') {
        let raw;
        try { raw = (await readBody(req, MAX_BYTES)).toString('utf8'); } catch (_) { res.writeHead(413); return res.end('too large'); }
        let evs; try { evs = JSON.parse(raw); } catch (_) { res.writeHead(400); return res.end('bad json'); }
        try { for (const ev of [].concat(evs)) if (ev && (EVENT_TYPES.has(ev.type) || ev.type === 'world_snapshot')) emit(ev); }
        catch (_) { res.writeHead(400); return res.end('invalid snapshot'); }
        res.writeHead(204, { 'access-control-allow-origin': '*' }); return res.end();
      }
      if (req.method === 'GET' && url === '/state') { res.writeHead(200, { 'content-type': 'application/json', 'cache-control': 'no-store' }); return res.end(JSON.stringify({ worlds: [...worlds.values()] })); }
      if (req.method === 'GET' && url.startsWith('/range-events?')) {
        const query = new URL(url, 'http://localhost').searchParams;
        const world = worlds.get(query.get('world')), actor = query.get('actor');
        if (!readRange || !world || world.execution_mode !== 'range' || !world.actors.some(a => a.id === actor)) { res.writeHead(404); return res.end('Range evidence unavailable'); }
        try {
          const page = await readRange(actor);
          if (page.world_id !== world.world_id || page.actor_id !== actor) throw new Error('Wrong world');
          page.entries = page.entries.filter(e => e.tick <= world.tick);
          if (page.screen?.tick > world.tick) page.screen = null;
          page.through_tick = Math.min(page.through_tick, world.tick);
          res.writeHead(200, { 'content-type': 'application/json', 'cache-control': 'no-store' });
          return res.end(JSON.stringify(page));
        } catch (_) { res.writeHead(404); return res.end('Range evidence unavailable'); }
      }
      if (req.method === 'GET' && url.startsWith('/native-events?')) {
        const query = new URL(url, 'http://localhost').searchParams;
        const world = worlds.get(query.get('world')), actor = query.get('actor');
        if (!readNative || !world || world.execution_mode !== 'native' || !world.actors.some(a => a.id === actor)) {
          res.writeHead(404); return res.end('Native telemetry unavailable');
        }
        try {
          const page = await readNative(actor);
          if (page.world_id !== world.world_id || page.actor_id !== actor) throw new Error('Wrong world');
          // A file may be ahead of the most recently published snapshot during a tick.
          page.events = page.events.filter(e => e.tick <= world.tick);
          page.through_tick = Math.min(page.through_tick, world.tick);
          res.writeHead(200, { 'content-type': 'application/json', 'cache-control': 'no-store' });
          return res.end(JSON.stringify(page));
        } catch (_) { res.writeHead(404); return res.end('Native telemetry unavailable'); }
      }
      if (req.method === 'GET' && url === '/health') { res.writeHead(200, { 'content-type': 'application/json' }); return res.end(JSON.stringify({ ok: true, agents: agents.size, stats: analyzer.stats })); }
      if (req.method === 'GET' && (url === '/' || url.startsWith('/?'))) {
        res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
        return fs.createReadStream(VIEWER).pipe(res);
      }
      res.writeHead(404); res.end('not found');
    } catch (e) {
      log('server error: ' + e.message);
      if (!res.headersSent) res.writeHead(500); res.end();
    }
  });
  setInterval(() => { for (const c of clients) c.write(': ping\n\n'); }, 15000).unref();
  return { server, emit, analyzer };
}

module.exports = { createOffice };
