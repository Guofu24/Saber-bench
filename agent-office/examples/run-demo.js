#!/usr/bin/env node
'use strict';
// One command demo: starts the mock LLM, then runs the Python team through agent-office.
//   node examples/run-demo.js [--open]
const { spawn } = require('child_process');
const path = require('path');

const MOCK_PORT = 9100;
const mock = spawn(process.execPath, [path.join(__dirname, 'mock-llm.js'), String(MOCK_PORT)], { stdio: 'inherit' });
const py = process.platform === 'win32' ? 'python' : 'python3';
const extra = process.argv.slice(2);

setTimeout(() => {
  const office = spawn(process.execPath, [path.join(__dirname, '..', 'bin', 'agent-office.js'), 'run', ...extra, '--', py, path.join(__dirname, 'demo-team', 'team.py')], {
    stdio: 'inherit',
    env: {
      ...process.env,
      OPENAI_BASE_URL: `http://127.0.0.1:${MOCK_PORT}/v1`,
      ANTHROPIC_BASE_URL: `http://127.0.0.1:${MOCK_PORT}`,
      OPENAI_API_KEY: 'sk-mock', ANTHROPIC_API_KEY: 'sk-ant-mock',
    },
  });
  office.on('exit', code => { mock.kill(); process.exit(code || 0); });
  for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => { office.kill('SIGINT'); setTimeout(() => { office.kill('SIGKILL'); mock.kill(); process.exit(0); }, 500); });
}, 400);
