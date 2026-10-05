import test from 'node:test';
import assert from 'node:assert/strict';
import { renderEquation } from './mathRenderer.mjs';
test('formula renderer provides accessible fractions and subscripts rather than raw LaTeX',async()=>{
 const html=await renderEquation(String.raw`H_{\text{ф}}=\dfrac{13\cdot10^6}{1130\cdot9.81}`);
 assert.match(html,/<math/);assert.match(html,/<mfrac>/);assert.match(html,/<msub>/);
 assert.match(html,/katex-display/);
});
test('formula data cannot enable trusted links or HTML',async()=>{
 const html=await renderEquation(String.raw`\href{javascript:alert(1)}{x}`);
 assert.doesNotMatch(html,/<a\s/);assert.doesNotMatch(html,/<script/);
});
