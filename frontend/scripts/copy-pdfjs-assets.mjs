// Copies the pdf.js runtime assets (standard fonts, wasm decoders, ICC profile) into public/pdfjs
// so the in-app PDF viewer works fully offline and without any third-party requests.
import { cpSync, existsSync, mkdirSync, rmSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const source = join(root, 'node_modules', 'pdfjs-dist')
const target = join(root, 'public', 'pdfjs')

if (!existsSync(source)) {
  console.error('pdfjs-dist is not installed. Run `npm install` first.')
  process.exit(1)
}

rmSync(target, { recursive: true, force: true })
mkdirSync(target, { recursive: true })
for (const folder of ['standard_fonts', 'wasm', 'iccs']) {
  cpSync(join(source, folder), join(target, folder), { recursive: true })
}
console.log('Copied pdf.js assets to public/pdfjs')
