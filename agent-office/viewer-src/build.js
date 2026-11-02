// Bundles three.js + the office scene into one self-contained viewer/index.html
const fs = require('fs'), path = require('path'), esbuild = require('esbuild');
const dir = __dirname;
fs.writeFileSync(path.join(dir, '.entry.js'), ['scene.js', 'world.js', 'live.js'].map(f => fs.readFileSync(path.join(dir, f), 'utf8')).join('\n'));
esbuild.buildSync({ entryPoints: [path.join(dir, '.entry.js')], bundle: true, minify: true, format: 'iife', outfile: path.join(dir, '.out.js'), logLevel: 'warning' });
const js = fs.readFileSync(path.join(dir, '.out.js'), 'utf8').replace(/<\/script/gi, '<\\/script');
const t = fs.readFileSync(path.join(dir, 'template.html'), 'utf8'), i = t.indexOf('/*BUNDLE*/');
fs.mkdirSync(path.join(dir, '..', 'viewer'), { recursive: true });
fs.writeFileSync(path.join(dir, '..', 'viewer', 'index.html'), t.slice(0, i) + js + t.slice(i + 10));
for (const f of ['.entry.js', '.out.js']) fs.unlinkSync(path.join(dir, f));
console.log('viewer/index.html built');
