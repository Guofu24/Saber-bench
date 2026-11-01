'use strict';
// Turns raw LLM API traffic (OpenAI chat/responses, Anthropic messages) into
// "office" events: which agent exists, when it thinks, which tool it calls,
// and who hands work to whom.
const crypto = require('crypto');

const hash = s => crypto.createHash('sha1').update(String(s)).digest('hex').slice(0, 12);
const clip = (s, n) => { s = String(s || '').replace(/\s+/g, ' ').trim(); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
const norm = s => String(s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
const title = s => String(s).replace(/[_-]+/g, ' ').trim().replace(/\b\w/g, c => c.toUpperCase());

function text(content) {
  if (content == null) return '';
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) return content.map(p => (typeof p === 'string' ? p : p && (p.type === 'tool_result' ? '' : p.text || ''))).filter(Boolean).join('\n');
  if (typeof content === 'object' && content.text) return content.text;
  return '';
}

function extract(kind, body) {
  const info = { model: body.model || '', stream: !!body.stream, system: '', firstUser: '', lastUser: '', tools: [], prevId: null };
  if (kind === 'chat') {
    const msgs = Array.isArray(body.messages) ? body.messages : [];
    info.system = msgs.filter(m => m.role === 'system' || m.role === 'developer').map(m => text(m.content)).join('\n');
    const users = msgs.filter(m => m.role === 'user').map(m => text(m.content)).filter(Boolean);
    info.firstUser = users[0] || ''; info.lastUser = users[users.length - 1] || '';
    info.tools = (body.tools || []).map(t => (t.function && t.function.name) || t.name).filter(Boolean);
    info.len = msgs.length;
  } else if (kind === 'responses') {
    info.system = body.instructions || '';
    info.prevId = body.previous_response_id || null;
    if (typeof body.input === 'string') info.firstUser = info.lastUser = body.input;
    else if (Array.isArray(body.input)) {
      const users = [];
      for (const it of body.input) {
        if (it.role === 'system' || it.role === 'developer') info.system += '\n' + text(it.content);
        else if (it.role === 'user') { const t = text(it.content); if (t) users.push(t); }
      }
      info.firstUser = users[0] || ''; info.lastUser = users[users.length - 1] || '';
    }
    info.tools = (body.tools || []).map(t => t.name || (t.function && t.function.name) || t.type).filter(Boolean);
    info.len = Array.isArray(body.input) ? body.input.length : 1;
  } else if (kind === 'anthropic') {
    info.system = typeof body.system === 'string' ? body.system : text(body.system);
    const users = (body.messages || []).filter(m => m.role === 'user').map(m => text(m.content)).filter(Boolean);
    info.firstUser = users[0] || ''; info.lastUser = users[users.length - 1] || '';
    info.tools = (body.tools || []).map(t => t.name).filter(Boolean);
    info.len = (body.messages || []).length;
  }
  return info;
}

const NOT_NAMES = new Set(['A', 'An', 'The', 'This', 'That', 'Your', 'Our', 'Helpful', 'Expert', 'Senior', 'Professional', 'Smart', 'Highly', 'One', 'Một']);
function inferIdentity(system, config) {
  for (const rule of (config && config.agents) || []) {
    try {
      const hit = rule.regex ? new RegExp(rule.regex, 'i').test(system) : system.toLowerCase().includes(String(rule.match || '').toLowerCase());
      if (hit && (rule.match || rule.regex)) return { name: rule.name, role: rule.role || '', color: rule.color, confident: true };
    } catch (_) { /* bad regex in config */ }
  }
  let name = null, role = '';
  const m = system.match(/(?:[Yy]ou are|[Yy]ou're|[Yy]our name is|[Bb]ạn là|I am|I'm)\s+(?:called\s+|named\s+)?["“'`*]*([A-Z][A-Za-z0-9_-]{1,24})/);
  if (m && !NOT_NAMES.has(m[1])) name = m[1];
  const r = system.match(/(?:you are|you're|bạn là)\s+(?:[A-Z][\w-]+\s*[,—–-]\s*)?(?:an?\s+|the\s+|một\s+)?([^.,;:!\n]{3,48})/i);
  if (r) role = r[1].trim();
  if (name && role.startsWith(name)) role = role.slice(name.length).replace(/^[\s,—–-]+(an?\s+|the\s+)?/i, '');
  if (!name) {
    const n2 = system.match(/^\s*#*\s*([A-Z][A-Za-z0-9_-]{2,24})\s*[:\n—-]/); // "Planner:" / "# Planner"
    if (n2 && !NOT_NAMES.has(n2[1])) name = n2[1];
  }
  if (!name && role) { const w = role.split(/\s+/).filter(x => x.length > 1); name = title(w.slice(-2).join(' ')); return { name, role: clip(role, 40), confident: false }; }
  return { name, role: clip(role, 40), confident: !!name };
}

class Analyzer {
  constructor(emit, config = {}) {
    this.emit = emit; this.config = config;
    this.groups = new Map(); this.instances = []; this.byResp = new Map();
    this.n = 0;
    this.stats = { calls: 0, tools: 0, tokensIn: 0, tokensOut: 0 };
  }

  begin(provider, path, body, headers) {
    if (!body || typeof body !== 'object') return null;
    let kind = null;
    if (/chat\/completions\/?$/.test(path)) kind = 'chat';
    else if (/\/responses\/?$/.test(path)) kind = 'responses';
    else if (/\/messages\/?$/.test(path) && provider === 'anthropic') kind = 'anthropic';
    if (!kind) return null;
    const info = extract(kind, body);
    const inst = this.resolve(info, headers || {});
    return new Call(this, inst, kind, info);
  }

  group(info, hName) {
    const key = hName ? 'h:' + hName : info.system ? 's:' + hash(info.system.slice(0, 800)) : 't:' + info.model + ':' + info.tools.join(',');
    let g = this.groups.get(key);
    if (!g) {
      const idn = hName ? { name: hName, role: '', confident: true } : inferIdentity(info.system, this.config);
      const auto = !idn.confident;
      g = { key, name: idn.name || `Agent ${this.groups.size + 1}`, role: idn.role || (info.tools.length ? 'tools: ' + clip(info.tools.slice(0, 3).join(', '), 30) : ''), color: idn.color, auto, instances: [] };
      this.groups.set(key, g);
    }
    return g;
  }

  resolve(info, headers) {
    const hName = headers['x-agent-name'] || headers['x-office-agent'];
    const g = this.group(info, hName);
    const now = Date.now();
    const conv = hash(info.firstUser.slice(0, 500));
    let inst = info.prevId ? this.byResp.get(info.prevId) : null;
    if (!inst) inst = g.instances.find(i => i.conv === conv);
    if (!inst) inst = g.instances.find(i => i.inFlight === 0 && (!i.pending || now - i.pendingAt > 120000));
    if (!inst) {
      const k = g.instances.length;
      inst = { id: 'a' + (++this.n), group: g, idx: k, conv: null, inFlight: 0, pending: null, pendingAt: 0, calls: 0 };
      inst.name = k ? `${g.name} #${k + 1}` : g.name;
      g.instances.push(inst); this.instances.push(inst);
      this.emit({ type: 'agent', id: inst.id, name: inst.name, role: g.role, color: g.color, group: g.name });
    }
    // a new task = a different first prompt, or the same prompt restarted from scratch (shorter conversation)
    const restarted = inst.conv === conv && inst.inFlight === 0 && !inst.pending && info.len <= (inst.lastLen || 0);
    inst.lastLen = info.len || 0;
    if (!info.prevId && (inst.conv !== conv || restarted)) {
      inst.conv = conv;
      this.emit({ type: 'task', id: inst.id, title: clip(info.firstUser, 120) || '(không có prompt)' });
      this.detectHandoff(inst, now);
    }
    return inst;
  }

  detectHandoff(to, now) {
    const tn = norm(to.group.name);
    let best = null, bestScore = 0;
    // candidates: agents currently blocked on a tool call (the caller is waiting for this sub-agent)
    const cands = this.instances.filter(i => i !== to && i.pending && now - i.pendingAt < 60000);
    const newest = cands.reduce((m, c) => (!m || c.pendingAt > m.pendingAt ? c : m), null);
    for (const c of cands) {
      for (const t of c.pending) {
        let s = 0;
        const blob = norm(t.name + ' ' + t.args);
        if (tn.length >= 3 && blob.includes(tn)) s += 4;                       // tool/args mention the agent's name
        if (/transfer|handoff|delegate|assign|agent|ask|consult|dispatch|route/i.test(t.name)) s += 0.5;
        if (c === newest) s += 1.5;                                            // innermost caller is the most recent one
        if (s > bestScore) { bestScore = s; best = { from: c, via: t }; }
      }
    }
    if (!best || bestScore < 1) return;
    // Name unnamed agents after their handoff tool: transfer_to_billing_agent -> "Billing Agent"
    const m = best.via.name.match(/^(?:transfer|handoff|delegate|route)_?(?:to_)?(.+)$/i);
    if (to.group.auto && m) {
      to.group.auto = false; to.group.name = title(m[1]);
      for (const i of to.group.instances) { i.name = i.idx ? `${to.group.name} #${i.idx + 1}` : to.group.name; this.emit({ type: 'agent', id: i.id, name: i.name, role: to.group.role, group: to.group.name, update: true }); }
    }
    this.emit({ type: 'handoff', from: best.from.id, to: to.id, via: best.via.name });
  }
}

class Call {
  constructor(an, inst, kind, info) {
    this.an = an; this.inst = inst; this.kind = kind; this.info = info;
    this.t0 = Date.now(); this.tools = []; this.text = ''; this.usage = { in: 0, out: 0 }; this.respId = null; this.done = false; this.announced = new Set();
    inst.inFlight++; inst.calls++; inst.pending = null; an.stats.calls++;
    an.emit({ type: 'llm_start', id: inst.id, model: info.model, stream: info.stream });
  }
  announce(i) {
    const t = this.tools[i];
    if (!t || !t.name || this.announced.has(i)) return;
    this.announced.add(i); this.an.stats.tools++;
    this.an.emit({ type: 'tool', id: this.inst.id, name: t.name });
  }
  onSSE(event, data) {
    let d; try { d = JSON.parse(data); } catch (_) { return; }
    if (this.kind === 'chat') {
      const ch = d.choices && d.choices[0], delta = ch && ch.delta;
      if (delta) {
        if (typeof delta.content === 'string') this.text += delta.content;
        for (const tc of delta.tool_calls || []) {
          const i = tc.index || 0; const t = this.tools[i] || (this.tools[i] = { name: '', args: '' });
          if (tc.function && tc.function.name) t.name += tc.function.name;
          if (tc.function && tc.function.arguments) { t.args += tc.function.arguments; this.announce(i); }
        }
      }
      if (d.usage) this.usage = { in: d.usage.prompt_tokens || 0, out: d.usage.completion_tokens || 0 };
    } else if (this.kind === 'responses') {
      if (d.type === 'response.output_item.added' && d.item && d.item.type === 'function_call') { this.tools.push({ name: d.item.name || '', args: '' }); this.announce(this.tools.length - 1); }
      else if (d.type === 'response.function_call_arguments.delta' && this.tools.length) this.tools[this.tools.length - 1].args += d.delta || '';
      else if (d.type === 'response.output_text.delta') this.text += d.delta || '';
      else if (d.type === 'response.completed' && d.response) { this.respId = d.response.id; const u = d.response.usage || {}; this.usage = { in: u.input_tokens || 0, out: u.output_tokens || 0 }; }
    } else {
      const ev = event || d.type;
      if (ev === 'content_block_start' && d.content_block && d.content_block.type === 'tool_use') { this.tools[d.index] = { name: d.content_block.name, args: '' }; this.announce(d.index); }
      else if (ev === 'content_block_delta' && d.delta) {
        if (d.delta.type === 'text_delta') this.text += d.delta.text || '';
        else if (d.delta.type === 'input_json_delta' && this.tools[d.index]) this.tools[d.index].args += d.delta.partial_json || '';
      } else if (ev === 'message_start' && d.message && d.message.usage) this.usage.in = d.message.usage.input_tokens || 0;
      else if (ev === 'message_delta' && d.usage) this.usage.out = d.usage.output_tokens || 0;
    }
  }
  onJSON(b) {
    if (!b) return;
    if (this.kind === 'chat') {
      const msg = b.choices && b.choices[0] && b.choices[0].message;
      if (msg) { this.text = text(msg.content); this.tools = (msg.tool_calls || []).map(t => ({ name: t.function ? t.function.name : t.name, args: t.function ? t.function.arguments || '' : '' })); }
      if (b.usage) this.usage = { in: b.usage.prompt_tokens || 0, out: b.usage.completion_tokens || 0 };
    } else if (this.kind === 'responses') {
      this.respId = b.id;
      for (const it of b.output || []) {
        if (it.type === 'function_call') this.tools.push({ name: it.name, args: it.arguments || '' });
        else if (it.type === 'message') this.text += text(it.content);
      }
      if (b.usage) this.usage = { in: b.usage.input_tokens || 0, out: b.usage.output_tokens || 0 };
    } else {
      for (const c of b.content || []) {
        if (c.type === 'text') this.text += c.text;
        else if (c.type === 'tool_use') this.tools.push({ name: c.name, args: JSON.stringify(c.input || {}) });
      }
      if (b.usage) this.usage = { in: b.usage.input_tokens || 0, out: b.usage.output_tokens || 0 };
    }
    this.tools.forEach((_, i) => this.announce(i));
  }
  end(status, errMsg) {
    if (this.done) return; this.done = true;
    const inst = this.inst, an = this.an;
    inst.inFlight = Math.max(0, inst.inFlight - 1);
    this.tools = this.tools.filter(t => t && t.name);
    if (this.respId) an.byResp.set(this.respId, inst);
    an.stats.tokensIn += this.usage.in; an.stats.tokensOut += this.usage.out;
    if (status >= 400 || errMsg) {
      inst.pending = null;
      an.emit({ type: 'llm_error', id: inst.id, status, message: clip(errMsg || this.text || 'HTTP ' + status, 160) });
      return;
    }
    if (this.tools.length) { inst.pending = this.tools; inst.pendingAt = Date.now(); } else inst.pending = null;
    an.emit({ type: 'llm_end', id: inst.id, ms: Date.now() - this.t0, text: clip(this.text, 280), tools: this.tools.map(t => ({ name: t.name, args: clip(t.args, 160) })), usage: this.usage, stats: an.stats });
  }
}

module.exports = { Analyzer, inferIdentity, extract };
