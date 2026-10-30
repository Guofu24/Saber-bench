#!/usr/bin/env node
'use strict';
// A fake LLM server speaking OpenAI (chat + responses) and Anthropic (messages),
// so the demo runs without API keys. It "plans" by calling the tools it is given.
const http = require('http');
const crypto = require('crypto');

const PORT = +(process.env.MOCK_PORT || process.argv[2] || 9100);
const hnum = s => parseInt(crypto.createHash('md5').update(String(s)).digest('hex').slice(0, 8), 16);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const id = p => p + crypto.randomBytes(8).toString('hex');
const clip = (s, n) => { s = String(s || '').replace(/\s+/g, ' ').trim(); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
const textOf = c => (typeof c === 'string' ? c : Array.isArray(c) ? c.map(p => (p && p.type !== 'tool_result' && p.text) || '').join(' ') : '');

const TASKS = {
  hermes: 'Tìm 5 bài viết mới về visualize hệ multi-agent',
  atlas: 'Phân tích số liệu sử dụng vault tháng 10',
  codex: 'Sửa bug đồng bộ vault và chạy lại test',
  scribe: 'Tóm tắt ghi chú tuần và viết báo cáo cho sếp',
};
const SAMPLE = { query: 'multi-agent visualization 2026', url: 'https://example.com/agentic-os', path: 'src/vault_sync.py', patch: '- retry=1\n+ retry=3', sql: 'SELECT date, notes FROM vault WHERE month = 10', title: 'Báo cáo tuần', content: 'Tóm tắt các ý chính…', text: 'ghi chú về MCP server', count: 6 };
function fill(schema, step, enumVal) {
  const out = {};
  for (const [k, p] of Object.entries((schema && schema.properties) || {})) {
    if (p.enum) out[k] = enumVal !== undefined ? enumVal : p.enum[step % p.enum.length];
    else if (p.type === 'integer' || p.type === 'number') out[k] = SAMPLE[k] || 3;
    else if (p.type === 'boolean') out[k] = true;
    else if (p.type === 'array') out[k] = [];
    else out[k] = (k === 'task' && enumVal && TASKS[enumVal]) || SAMPLE[k] || `${k} mẫu`;
  }
  return out;
}

// tools: [{name, schema}] ; step: how many tool rounds already happened
function decide({ system, firstUser, lastUser, tools, step }) {
  const enumTool = tools.find(t => Object.values((t.schema && t.schema.properties) || {}).some(p => p.enum));
  if (enumTool) { // orchestrator: fan out over the enum values, two at a time
    const key = Object.entries(enumTool.schema.properties).find(([, p]) => p.enum)[0];
    const vals = enumTool.schema.properties[key].enum;
    const chunk = vals.slice(step * 2, step * 2 + 2);
    if (chunk.length) return { calls: chunk.map(v => ({ name: enumTool.name, args: fill(enumTool.schema, step, v) })) };
    return { text: `Xong rồi sếp! Cả đội đã hoàn thành: ${clip(firstUser, 70)}` };
  }
  const k = tools.length ? 1 + (hnum(system + firstUser) % 3) : 0;
  if (step < k) { const t = tools[step % tools.length]; return { calls: [{ name: t.name, args: fill(t.schema, step) }] }; }
  return { text: `Đã xong: ${clip(lastUser || firstUser, 80)}` };
}

const tok = o => Math.ceil(JSON.stringify(o).length / 4);
function body(req) { return new Promise(r => { const c = []; req.on('data', d => c.push(d)); req.on('end', () => { try { r(JSON.parse(Buffer.concat(c).toString() || '{}')); } catch (_) { r({}); } }); }); }
function sseHead(res) { res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' }); }

async function chat(b, res) {
  const msgs = b.messages || [];
  const lastUserIdx = msgs.map(m => m.role).lastIndexOf('user');
  const step = msgs.slice(lastUserIdx + 1).filter(m => m.role === 'assistant' && m.tool_calls && m.tool_calls.length).length;
  const users = msgs.filter(m => m.role === 'user');
  const d = decide({ system: textOf((msgs.find(m => m.role === 'system') || {}).content), firstUser: textOf(users[0] && users[0].content), lastUser: textOf(users[users.length - 1] && users[users.length - 1].content),
    tools: (b.tools || []).map(t => ({ name: t.function.name, schema: t.function.parameters })), step });
  await sleep(600 + Math.random() * 1200);
  const calls = (d.calls || []).map(c => ({ id: id('call_'), type: 'function', function: { name: c.name, arguments: JSON.stringify(c.args) } }));
  const usage = { prompt_tokens: tok(b), completion_tokens: tok(d) + 12, total_tokens: 0 }; usage.total_tokens = usage.prompt_tokens + usage.completion_tokens;
  const base = { id: id('chatcmpl-'), object: 'chat.completion', created: Math.floor(Date.now() / 1000), model: b.model || 'mock' };
  if (!b.stream) {
    res.writeHead(200, { 'content-type': 'application/json' });
    return res.end(JSON.stringify({ ...base, choices: [{ index: 0, finish_reason: calls.length ? 'tool_calls' : 'stop', message: { role: 'assistant', content: d.text || null, tool_calls: calls.length ? calls : undefined } }], usage }));
  }
  sseHead(res);
  const send = (delta, fr = null, extra = {}) => res.write(`data: ${JSON.stringify({ ...base, object: 'chat.completion.chunk', choices: [{ index: 0, delta, finish_reason: fr }], ...extra })}\n\n`);
  send({ role: 'assistant', content: '' });
  if (calls.length) {
    for (const [i, c] of calls.entries()) {
      send({ tool_calls: [{ index: i, id: c.id, type: 'function', function: { name: c.function.name, arguments: '' } }] }); await sleep(60);
      send({ tool_calls: [{ index: i, function: { arguments: c.function.arguments } }] }); await sleep(60);
    }
  } else for (const w of d.text.split(/(?<= )/)) { send({ content: w }); await sleep(35); }
  send({}, calls.length ? 'tool_calls' : 'stop');
  if (b.stream_options && b.stream_options.include_usage) res.write(`data: ${JSON.stringify({ ...base, object: 'chat.completion.chunk', choices: [], usage })}\n\n`);
  res.write('data: [DONE]\n\n'); res.end();
}

async function responses(b, res) {
  const input = typeof b.input === 'string' ? [{ role: 'user', content: b.input }] : b.input || [];
  const users = input.filter(i => i.role === 'user');
  const step = new Set(input.filter(i => i.type === 'function_call').map(i => i.id || i.call_id)).size ? input.filter(i => i.type === 'function_call_output').length : 0;
  const d = decide({ system: b.instructions || '', firstUser: textOf(users[0] && users[0].content), lastUser: textOf(users[users.length - 1] && users[users.length - 1].content),
    tools: (b.tools || []).filter(t => t.type === 'function').map(t => ({ name: t.name, schema: t.parameters })), step });
  await sleep(600 + Math.random() * 1200);
  const output = d.calls ? d.calls.map(c => ({ type: 'function_call', id: id('fc_'), call_id: id('call_'), name: c.name, arguments: JSON.stringify(c.args), status: 'completed' }))
    : [{ type: 'message', id: id('msg_'), role: 'assistant', status: 'completed', content: [{ type: 'output_text', text: d.text, annotations: [] }] }];
  const usage = { input_tokens: tok(b), output_tokens: tok(d) + 12 }; usage.total_tokens = usage.input_tokens + usage.output_tokens;
  res.writeHead(200, { 'content-type': 'application/json' });
  res.end(JSON.stringify({ id: id('resp_'), object: 'response', created_at: Math.floor(Date.now() / 1000), status: 'completed', model: b.model || 'mock', output, usage, parallel_tool_calls: true, tool_choice: 'auto', tools: b.tools || [] }));
}

async function messages(b, res) {
  const msgs = b.messages || [];
  let lastText = -1; msgs.forEach((m, i) => { if (m.role === 'user' && textOf(m.content)) lastText = i; });
  const step = msgs.slice(lastText + 1).filter(m => m.role === 'assistant' && Array.isArray(m.content) && m.content.some(c => c.type === 'tool_use')).length;
  const users = msgs.filter(m => m.role === 'user' && textOf(m.content));
  const system = typeof b.system === 'string' ? b.system : textOf(b.system);
  const d = decide({ system, firstUser: textOf(users[0] && users[0].content), lastUser: textOf(users[users.length - 1] && users[users.length - 1].content), tools: (b.tools || []).map(t => ({ name: t.name, schema: t.input_schema })), step });
  await sleep(600 + Math.random() * 1200);
  const content = d.calls ? d.calls.map(c => ({ type: 'tool_use', id: id('toolu_'), name: c.name, input: c.args })) : [{ type: 'text', text: d.text }];
  const stop = d.calls ? 'tool_use' : 'end_turn';
  const usage = { input_tokens: tok(b), output_tokens: tok(d) + 12 };
  const msg = { id: id('msg_'), type: 'message', role: 'assistant', model: b.model || 'mock', stop_sequence: null };
  if (!b.stream) { res.writeHead(200, { 'content-type': 'application/json' }); return res.end(JSON.stringify({ ...msg, content, stop_reason: stop, usage })); }
  sseHead(res);
  const ev = (type, data) => res.write(`event: ${type}\ndata: ${JSON.stringify({ type, ...data })}\n\n`);
  ev('message_start', { message: { ...msg, content: [], stop_reason: null, usage: { input_tokens: usage.input_tokens, output_tokens: 1 } } });
  for (const [i, c] of content.entries()) {
    if (c.type === 'text') {
      ev('content_block_start', { index: i, content_block: { type: 'text', text: '' } });
      for (const w of c.text.split(/(?<= )/)) { ev('content_block_delta', { index: i, delta: { type: 'text_delta', text: w } }); await sleep(35); }
    } else {
      ev('content_block_start', { index: i, content_block: { type: 'tool_use', id: c.id, name: c.name, input: {} } }); await sleep(60);
      ev('content_block_delta', { index: i, delta: { type: 'input_json_delta', partial_json: JSON.stringify(c.input) } });
    }
    ev('content_block_stop', { index: i });
  }
  ev('message_delta', { delta: { stop_reason: stop, stop_sequence: null }, usage: { output_tokens: usage.output_tokens } });
  ev('message_stop', {});
  res.end();
}

http.createServer(async (req, res) => {
  const b = await body(req);
  const u = req.url.split('?')[0];
  try {
    if (u.endsWith('/chat/completions')) return await chat(b, res);
    if (u.endsWith('/responses')) return await responses(b, res);
    if (u.endsWith('/messages')) return await messages(b, res);
    res.writeHead(404, { 'content-type': 'application/json' }); res.end('{"error":{"message":"mock: not found"}}');
  } catch (e) { console.error(e); if (!res.headersSent) res.writeHead(500); res.end(); }
}).listen(PORT, '127.0.0.1', () => console.error(`[mock-llm] listening on http://127.0.0.1:${PORT}`));
