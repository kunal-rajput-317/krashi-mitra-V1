const fs = require('fs');
const f = 'd:/GitHub repo/Farmerontop/prototype_01/tmp/krashi-mitra-V1/frontend/profile.html';
const lines = fs.readFileSync(f, 'utf8').split(/\r?\n/);
// Keep lines 1-618 (index 0-617) and lines 2109+ (index 2108+)
const keep = [...lines.slice(0, 618), ...lines.slice(2108)];
fs.writeFileSync(f, keep.join('\n'));
console.log('Done. Lines before:', lines.length, 'Lines after:', keep.length);
