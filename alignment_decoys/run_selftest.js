'use strict';
/**
 * run_selftest.js — verifies alignmentDecoyScorer.js against a decoy corpus.
 *
 *   node run_selftest.js decoy_corpus.json
 *
 * 1. decoy as served            -> every injection MISSED
 * 2. gold, file answered right  -> every injection CAUGHT (synthetic files: CB-WHOLE CAUGHT, the rest EXCLUDED)
 * 3. gold segments, tag "none"  -> every alignment injection CAUGHT (exercises the detectors on synthetic files too)
 * 4. gold with ±20 ms jitter    -> every alignment injection still CAUGHT (the 30 ms tolerance is fair)
 * 5. human file marked synthetic-> every injection MISSED, false_synthetic = true
 * Prints a report and, as its last line, a JSON summary. Exits 1 on any failure.
 */
const fs = require('fs');
const path = require('path');
const S = require(path.join(__dirname, 'alignmentDecoyScorer.js'));

const corpus = JSON.parse(fs.readFileSync(process.argv[2] || 'decoy_corpus.json', 'utf8')).filter((c) => c.status === 'ACTIVE');
let seed = 20261027;
const rnd = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
const jitter = (segs) => segs.map((s) => {
  const a = s.start + (rnd() * 0.04 - 0.02), b = s.end + (rnd() * 0.04 - 0.02);
  return { word: s.word, start: Math.max(0, Math.min(a, b - 0.01)), end: Math.max(a + 0.01, b) };
});

const fails = [];
const count = { injections: 0, alignment: 0, checkbox: 0, decoy_missed: 0, gold_caught: 0, jitter_caught: 0, false_syn_missed: 0, false_syn_checked: 0 };
const t0 = process.hrtime.bigint();
let calls = 0;
for (const e of corpus) {
  const syn = e.gold_whole_audio_tag === 'synthetic_speech';
  const r1 = S.scoreDecoy({ segments: e.decoy_segments, whole_audio_tag: 'none' }, e);
  const r2 = S.scoreDecoy({ segments: e.gold_segments, whole_audio_tag: e.gold_whole_audio_tag }, e);
  const r3 = S.scoreDecoy({ segments: e.gold_segments, whole_audio_tag: 'none' }, e);
  const r4 = S.scoreDecoy({ segments: jitter(e.gold_segments), whole_audio_tag: 'none' }, e);
  calls += 4;
  e.injections.forEach((inj, i) => {
    const cb = inj.family === 'CB-WHOLE';
    count.injections += 1; count[cb ? 'checkbox' : 'alignment'] += 1;
    const v1 = r1.injections[i].verdict, v2 = r2.injections[i].verdict, v3 = r3.injections[i].verdict, v4 = r4.injections[i].verdict;
    if (v1 === 'MISSED') count.decoy_missed += 1; else fails.push(`${inj.injection_id} ${inj.family}: decoy -> ${v1} ${JSON.stringify(r1.injections[i].evidence)}`);
    if (cb) {
      if (v2 === 'CAUGHT') count.gold_caught += 1; else fails.push(`${inj.injection_id} CB-WHOLE: gold -> ${v2}`);
    } else {
      if (syn && v2 !== 'EXCLUDED') fails.push(`${inj.injection_id}: synthetic file marked synthetic but ${v2}`);
      if (!syn && v2 !== 'CAUGHT') fails.push(`${inj.injection_id} ${inj.family}: gold -> ${v2} ${JSON.stringify(r2.injections[i].evidence)}`);
      if (v3 === 'CAUGHT') count.gold_caught += 1; else fails.push(`${inj.injection_id} ${inj.family}: gold(tag none) -> ${v3} ${JSON.stringify(r3.injections[i].evidence)}`);
      if (v4 === 'CAUGHT') count.jitter_caught += 1; else fails.push(`${inj.injection_id} ${inj.family}: gold±20ms -> ${v4} ${JSON.stringify(r4.injections[i].evidence)}`);
    }
  });
  if (!syn) {
    const r5 = S.scoreDecoy({ segments: [], whole_audio_tag: 'synthetic_speech' }, e); calls += 1;
    count.false_syn_checked += r5.injections.length;
    count.false_syn_missed += r5.injections.filter((x) => x.verdict === 'MISSED').length;
    if (!r5.false_synthetic) fails.push(`${e.decoy_id}: false_synthetic not flagged`);
  }
}
const ms = Number(process.hrtime.bigint() - t0) / 1e6 / calls;
if (count.false_syn_missed !== count.false_syn_checked) fails.push('human file marked synthetic: not every injection MISSED');

// daily report smoke test
const results = corpus.map((e, i) => S.scoreDecoy({ segments: i % 2 ? e.gold_segments : e.decoy_segments, whole_audio_tag: 'none' },
  e, { annotator_id: i % 3 ? 'annotatorA' : 'annotatorB', submitted_at: new Date(Date.UTC(2026, 9, 27, 9, i)).toISOString() }));
const report = S.buildDailyReport(results);
if (!report.length || !S.reportToCsv(report).includes('a1_miss_rate')) fails.push('daily report empty');
if (S.injectionsToRows(results).length !== count.injections) fails.push('injectionsToRows count mismatch');

console.log(`files                      : ${corpus.length}`);
console.log(`injections                 : ${count.injections} (${count.alignment} alignment + ${count.checkbox} CB-WHOLE)`);
console.log(`decoy as served   -> MISSED: ${count.decoy_missed}/${count.injections}`);
console.log(`gold              -> CAUGHT: ${count.gold_caught}/${count.injections}`);
console.log(`gold ±20 ms       -> CAUGHT: ${count.jitter_caught}/${count.alignment}`);
console.log(`human marked synthetic -> MISSED: ${count.false_syn_missed}/${count.false_syn_checked}`);
console.log(`daily report rows          : ${report.length}`);
console.log(`throughput                 : ${ms.toFixed(3)} ms per submission`);
if (fails.length) { console.log('FAILURES:'); fails.slice(0, 50).forEach((f) => console.log('  ' + f)); }
console.log(JSON.stringify({ ok: fails.length === 0, scored: count.injections, alignment: count.alignment, checkbox: count.checkbox,
  decoy_missed: count.decoy_missed, gold_caught: count.gold_caught, jitter_caught: count.jitter_caught, ms_per_submission: +ms.toFixed(3) }));
process.exit(fails.length ? 1 : 0);
