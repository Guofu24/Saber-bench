'use strict';
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');
const { normalizeSnapshot, MAX_BYTES } = require('./snapshot');
const execute = promisify(execFile);

async function readJSON(file) {
  const stat = await fs.lstat(file);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size > MAX_BYTES) throw new Error('Invalid snapshot file');
  const handle = await fs.open(file, 'r');
  try {
    const buffer = Buffer.alloc(MAX_BYTES + 1);
    const { bytesRead } = await handle.read(buffer, 0, buffer.length, 0);
    if (bytesRead > MAX_BYTES) throw new Error('Snapshot too large');
    return JSON.parse(buffer.subarray(0, bytesRead).toString('utf8'));
  } finally { await handle.close(); }
}

async function snapshotSource({ world, bundle, exec = execute }) {
  if (!!world === !!bundle) throw new Error('Choose exactly one of --world or --bundle');
  if (world) return async () => normalizeSnapshot(await readJSON(path.join(path.resolve(world), 'office.json')));
  const manifest = await readJSON(path.join(path.resolve(bundle), 'bundle-manifest.json'));
  if (manifest.schema_version !== 1 || manifest.profile !== 'sandbox' || !/^[a-z][a-z0-9-]{0,59}$/.test(manifest.project)) throw new Error('Expected sandbox bundle manifest');
  const docker = args => exec('docker', args, { timeout: 10000, windowsHide: true, maxBuffer: MAX_BYTES });
  return async () => {
    const result = await docker(['ps', '-a', '--filter', `label=com.docker.compose.project=${manifest.project}`, '--filter', 'label=com.docker.compose.service=world', '--format', '{{.ID}}']);
    const ids = result.stdout.trim().split(/\s+/).filter(Boolean);
    if (ids.length !== 1 || !/^[a-f0-9]{12,64}$/.test(ids[0])) throw new Error('Expected exactly one world container');
    const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'saber-office-'));
    const file = path.join(temp, 'office.json');
    try {
      // Read just the public snapshot; no exec, network, volume mount or key-file access.
      await docker(['cp', `${ids[0]}:/data/office.json`, file]);
      return normalizeSnapshot(await readJSON(file));
    } finally {
      await fs.unlink(file).catch(() => {});
      await fs.rmdir(temp).catch(() => {});
    }
  };
}

function watchSnapshots(read, emit, { interval = 2000, log = () => {} } = {}) {
  let stopped = false, timer, last = '', failed = false;
  async function poll() {
    try {
      const value = await read();
      if (stopped) return;
      const text = JSON.stringify(value);
      if (text !== last) { emit(value); last = text; }
      if (failed) log('World snapshot available again.');
      failed = false;
    } catch (_) {
      if (!failed && !stopped) log('Snapshot unavailable; waiting. Last data may be stale.');
      failed = true;
    } finally { if (!stopped) timer = setTimeout(poll, interval); }
  }
  poll();
  return () => { stopped = true; clearTimeout(timer); };
}
module.exports = { snapshotSource, watchSnapshots };
