'use strict';
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');
const { normalizeSnapshot, normalizeNativePage, MAX_BYTES } = require('./snapshot');
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
  const nativeFile = actor => {
    if (!/^[a-zA-Z0-9_-]{1,48}$/.test(actor)) throw new Error('Invalid native actor');
    return `native-office/${actor}.json`;
  };
  if (world) {
    const directory = path.resolve(world);
    const read = async () => normalizeSnapshot(await readJSON(path.join(directory, 'office.json')));
    read.native = async actor => {
      const root = await fs.realpath(directory);
      const file = path.join(root, nativeFile(actor));
      if (await fs.realpath(file) !== file) throw new Error('Redirected native export');
      return normalizeNativePage(await readJSON(file));
    };
    return read;
  }
  const manifest = await readJSON(path.join(path.resolve(bundle), 'bundle-manifest.json'));
  if (manifest.schema_version !== 1 || manifest.profile !== 'sandbox' || !/^[a-z][a-z0-9-]{0,59}$/.test(manifest.project)) throw new Error('Expected sandbox bundle manifest');
  const docker = args => exec('docker', args, { timeout: 10000, windowsHide: true, maxBuffer: MAX_BYTES });
  const copyPublic = async relative => {
    const result = await docker(['ps', '-a', '--filter', `label=com.docker.compose.project=${manifest.project}`, '--filter', 'label=com.docker.compose.service=world', '--format', '{{.ID}}']);
    const ids = result.stdout.trim().split(/\s+/).filter(Boolean);
    if (ids.length !== 1 || !/^[a-f0-9]{12,64}$/.test(ids[0])) throw new Error('Expected exactly one world container');
    const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'saber-office-'));
    const file = path.join(temp, 'office.json');
    try {
      // Only fixed public exports; no exec, volume mount or credential-file access.
      await docker(['cp', `${ids[0]}:/data/${relative}`, file]);
      return await readJSON(file);
    } finally {
      await fs.unlink(file).catch(() => {});
      await fs.rmdir(temp).catch(() => {});
    }
  };
  const read = async () => normalizeSnapshot(await copyPublic('office.json'));
  read.native = async actor => normalizeNativePage(await copyPublic(nativeFile(actor)));
  return read;
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
