#!/usr/bin/env node
'use strict';
const { spawn, exec } = require('child_process');
const fs = require('fs');
const path = require('path');
const { createOffice } = require('../lib/server');
const { snapshotSource, watchSnapshots } = require('../lib/watch');

const HELP = `
agent-office — xem đội multi-agent của bạn làm việc trong một văn phòng 3D

Cách dùng:
  agent-office run [tuỳ chọn] -- <lệnh chạy repo của bạn>
  agent-office serve [tuỳ chọn]          chỉ bật viewer + proxy, tự set biến môi trường
  agent-office watch --world <dir>       xem office.json của world local/VM/server
  agent-office watch --bundle <dir>      đọc snapshot sandbox qua Docker, không mở mạng

Ví dụ:
  agent-office run -- python main.py
  agent-office run --open -- npm start

Tuỳ chọn:
  --port <n>                 cổng viewer/proxy (mặc định 7788)
  --openai-upstream <url>    nơi chuyển tiếp request OpenAI (mặc định: $OPENAI_BASE_URL hoặc https://api.openai.com/v1)
  --anthropic-upstream <url> nơi chuyển tiếp request Anthropic (mặc định: $ANTHROPIC_BASE_URL hoặc https://api.anthropic.com)
  --config <file>            file đặt tên agent (mặc định ./agent-office.json nếu có)
  --open                     tự mở trình duyệt
  --exit                     tắt viewer khi lệnh con kết thúc
  --quiet                    không in log của agent-office
`;

function parse(argv) {
  const o = { port: 7788, open: false, exit: false, quiet: false, cmd: [] };
  const dd = argv.indexOf('--');
  const head = dd >= 0 ? argv.slice(0, dd) : argv;
  o.cmd = dd >= 0 ? argv.slice(dd + 1) : [];
  o.mode = head[0];
  for (let i = 1; i < head.length; i++) {
    const a = head[i], v = head[i + 1];
    if (a === '--port') { o.port = +v; i++; }
    else if (a === '--listen') { o.listen = v; i++; }
    else if (a === '--openai-upstream') { o.openai = v; i++; }
    else if (a === '--anthropic-upstream') { o.anthropic = v; i++; }
    else if (a === '--config') { o.config = v; i++; }
    else if (a === '--world') { o.world = v; i++; }
    else if (a === '--bundle') { o.bundle = v; i++; }
    else if (a === '--open') o.open = true;
    else if (a === '--exit') o.exit = true;
    else if (a === '--quiet') o.quiet = true;
    else if (o.mode === 'run' && !o.cmd.length) { o.cmd = head.slice(i); break; }
  }
  return o;
}

function listen(server, port, host = '127.0.0.1') {
  return new Promise((resolve, reject) => {
    const tryPort = p => {
      server.once('error', e => (e.code === 'EADDRINUSE' && p < port + 20 ? tryPort(p + 1) : reject(e)));
      server.listen(p, host, () => resolve(p));
    };
    tryPort(port);
  });
}

async function main() {
  const o = parse(process.argv.slice(2));
  if (o.listen && (o.mode !== 'watch' || !['127.0.0.1', '0.0.0.0', '::1'].includes(o.listen))) throw new Error('--listen is restricted to the read-only watch viewer');
  if (!['run', 'serve', 'watch'].includes(o.mode) || (o.mode === 'run' && !o.cmd.length)) { process.stdout.write(HELP); process.exit(o.mode ? 1 : 0); }
  const say = (...a) => { if (!o.quiet) console.error('\x1b[33m[agent-office]\x1b[0m', ...a); };

  let config = {};
  const cfgPath = o.config || (fs.existsSync('agent-office.json') ? 'agent-office.json' : null);
  if (cfgPath) { try { config = JSON.parse(fs.readFileSync(cfgPath, 'utf8')); say('dùng config', cfgPath); } catch (e) { say('không đọc được config:', e.message); } }

  const upstreams = {
    openai: o.openai || process.env.OPENAI_BASE_URL || 'https://api.openai.com/v1',
    anthropic: o.anthropic || process.env.ANTHROPIC_BASE_URL || 'https://api.anthropic.com',
  };
  const readSnapshot = o.mode === 'watch' ? await snapshotSource(o) : null;
  const { server, emit } = createOffice({ upstreams, config, log: say, readOnly: o.mode === 'watch', readNative: readSnapshot?.native });
  const port = await listen(server, o.port, o.listen);
  const base = `http://127.0.0.1:${port}`;
  const env = {
    OPENAI_BASE_URL: `${base}/openai`,
    OPENAI_API_BASE: `${base}/openai`,
    ANTHROPIC_BASE_URL: `${base}/anthropic`,
    AGENT_OFFICE_URL: base,
  };
  say(`viewer: \x1b[36m${base}\x1b[0m`);
  if (!readSnapshot) say(`OpenAI → ${upstreams.openai} · Anthropic → ${upstreams.anthropic}`);
  if (o.open) exec(`${process.platform === 'darwin' ? 'open' : process.platform === 'win32' ? 'start ""' : 'xdg-open'} ${base}`);

  if (readSnapshot) {
    say('Read-only world monitor. No LLM calls or runtime control.');
    const stop = watchSnapshots(readSnapshot, emit, { log: say });
    const close = () => { stop(); server.close(); server.closeAllConnections(); process.exit(0); };
    process.on('SIGINT', close); process.on('SIGTERM', close);
    return;
  }

  if (o.mode === 'serve') {
    say('set các biến này cho repo của bạn:');
    for (const [k, v] of Object.entries(env)) console.log(`export ${k}=${v}`);
    return;
  }

  const noProxy = [process.env.NO_PROXY || process.env.no_proxy, '127.0.0.1', 'localhost'].filter(Boolean).join(',');
  const cmdText = o.cmd.join(' ');
  emit({ type: 'process', status: 'running', cmd: cmdText });
  const child = spawn(o.cmd[0], o.cmd.slice(1), {
    stdio: 'inherit',
    shell: process.platform === 'win32',
    env: { ...process.env, ...env, NO_PROXY: noProxy, no_proxy: noProxy },
  });
  const fwd = sig => () => child.kill(sig);
  process.on('SIGINT', fwd('SIGINT')); process.on('SIGTERM', fwd('SIGTERM'));
  child.on('error', e => { say('không chạy được lệnh:', e.message); emit({ type: 'process', status: 'error', cmd: cmdText, message: e.message }); });
  child.on('exit', code => {
    emit({ type: 'process', status: 'exited', code, cmd: cmdText });
    if (o.exit) { setTimeout(() => process.exit(code || 0), 300); return; }
    say(`lệnh đã kết thúc (code ${code}). Viewer vẫn mở ở ${base} — Ctrl+C để thoát.`);
    process.removeAllListeners('SIGINT'); process.on('SIGINT', () => process.exit(code || 0));
  });
}

main().catch(e => { console.error(e); process.exit(1); });
