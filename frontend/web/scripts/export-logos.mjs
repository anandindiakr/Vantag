// One-off: export favicon SVGs to PNG logos for presentations/social media.
// Usage: node scripts/export-logos.mjs
import sharp from 'sharp';
import { readdirSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const pub = join(dirname(fileURLToPath(import.meta.url)), '..', 'public');
const outDir = join(pub, 'logos');
mkdirSync(outDir, { recursive: true });

const sizes = [1024, 512, 192];
const svgs = readdirSync(pub).filter((f) => f.endsWith('.svg') && f.startsWith('favicon'));

for (const f of svgs) {
  const base = f.replace(/\.svg$/, '');
  for (const size of sizes) {
    const out = join(outDir, `${base}-${size}.png`);
    await sharp(join(pub, f), { density: 300 })
      .resize(size, size, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
      .png()
      .toFile(out);
    console.log('wrote', out);
  }
}
console.log('DONE');
