// Bundles three.js + the office scene into one self-contained viewer/index.html
const fs = require('fs'), path = require('path'), { execSync } = require('child_process');
const dir = __dirname;
fs.writeFileSync(path.join(dir, '.entry.js'), fs.readFileSync(path.join(dir, 'scene.js'), 'utf8') + '\n' + fs.readFileSync(path.join(dir, 'live.js'), 'utf8'));
execSync(`npx esbuild ${path.join(dir, '.entry.js')} --bundle --minify --format=iife --outfile=${path.join(dir, '.out.js')} --log-level=warning`, { stdio: 'inherit' });
const js = fs.readFileSync(path.join(dir, '.out.js'), 'utf8').replace(/<\/script/gi, '<\\/script');
const t = fs.readFileSync(path.join(dir, 'template.html'), 'utf8'), i = t.indexOf('/*BUNDLE*/');
fs.mkdirSync(path.join(dir, '..', 'viewer'), { recursive: true });
fs.writeFileSync(path.join(dir, '..', 'viewer', 'index.html'), t.slice(0, i) + js + t.slice(i + 10));
for (const f of ['.entry.js', '.out.js']) fs.unlinkSync(path.join(dir, f));
console.log('viewer/index.html built');
