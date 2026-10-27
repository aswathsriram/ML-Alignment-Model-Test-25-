'use strict';
/**
 * alignmentDecoyScorer.js — decoy detection engine for FORCED ALIGNMENT tasks
 *
 * Zero dependencies. CommonJS with an ESM-friendly default export.
 * Same shape and verdicts as decoyScorer.js (transcription); this one scores a
 * submitted alignment: a list of segments { word, start, end } in seconds, plus
 * the whole-file answer (entirely synthetic speech or not).
 *
 * ---------------------------------------------------------------------------
 * HOW LOCATION WORKS
 * ---------------------------------------------------------------------------
 * Annotators move edges, split, merge, add and delete segments, so nothing is
 * located by segment index. Every injection carries the GOLD time span of the
 * word(s) it targets. The scorer looks at the submitted segments that overlap
 * that span (and, for planted segments, the planted span) and inspects only
 * those. Each injection also ships left/right word anchors and a plain_offset,
 * as in the transcription corpus, for reporting and review.
 *
 * If nothing can be located the verdict is INDETERMINATE, never MISSED.
 *
 * ---------------------------------------------------------------------------
 * TIMING TOLERANCE
 * ---------------------------------------------------------------------------
 * An edge is CAUGHT when it is back within TOL_S (30 ms) of gold. It is MISSED
 * when at least half of the planted shift is still there, in the planted
 * direction. Anything in between (a partial or over-correction) is
 * INDETERMINATE: route to human review.
 */

// ---------------------------------------------------------------- constants
const TOL_S = 0.030;            // edge back within 30 ms of gold = fixed
const NEAR_S = 0.25;            // search margin around a gold span
const VERDICT = {
  CAUGHT: 'CAUGHT', MISSED: 'MISSED', INDETERMINATE: 'INDETERMINATE',
  EXCLUDED: 'EXCLUDED',          // not scored: the file was (correctly) marked entirely synthetic
};
const SYNTHETIC = 'synthetic_speech';

// Score groups and their share of the alignment points (see decoy_summary.xlsx).
const GROUP_OF = {
  'BND-MINOR': 'BOUNDARY', 'BND-MAJOR': 'BOUNDARY', 'BND-OVERLAP': 'BOUNDARY', 'BND-ZERO': 'BOUNDARY',
  WD: 'MISSING', WH: 'HALLUCINATED', WS: 'WRONG-WORD',
  'SEG-MERGE': 'SEGMENTATION', 'SEG-SPLIT': 'SEGMENTATION', 'SEG-LETTERS': 'SEGMENTATION', 'SEG-FILLER': 'SEGMENTATION',
  'G-NUM': 'GUIDELINE', 'G-CASE': 'GUIDELINE', 'G-HYPHEN': 'GUIDELINE', 'G-ACCENT': 'GUIDELINE',
  'G-CONTRACT': 'GUIDELINE', 'G-BACKCH': 'GUIDELINE', 'G-PUNCT': 'GUIDELINE',
  'CB-WHOLE': 'CHECKBOX',
};
const REPORT_FAMILIES = Object.keys(GROUP_OF);
const REPORT_GROUPS = ['BOUNDARY', 'MISSING', 'HALLUCINATED', 'WRONG-WORD', 'SEGMENTATION', 'GUIDELINE', 'CHECKBOX'];

// ---------------------------------------------------------------- input
/**
 * Accepts any of:
 *   [{word,start,end}, ...]
 *   { segments: [...], whole_audio_tag, discard_reason }
 *   an item of the pre-fill file: { transcript, source: { words: [...] } }
 */
function normaliseSubmission(sub) {
  if (Array.isArray(sub)) return { segments: cleanSegs(sub), whole_audio_tag: undefined, discard_reason: null };
  const s = sub || {};
  const segs = s.segments || (s.source && s.source.words) || s.words || [];
  return {
    segments: cleanSegs(segs),
    whole_audio_tag: s.whole_audio_tag ?? s['select-whole-audio-tag'],
    discard_reason: s.discard_reason || null,
  };
}

function cleanSegs(segs) {
  return segs
    .filter((x) => x && typeof x.start === 'number' && typeof x.end === 'number')
    .map((x) => ({ word: String(x.word ?? x.text ?? '').normalize('NFC').trim(), start: x.start, end: x.end }))
    .sort((a, b) => a.start - b.start || a.end - b.end);
}

/** Spelled letters may carry an optional period (guideline 4.4): "a." equals "a". */
function same(a, b) {
  const n = (w) => String(w).normalize('NFC').trim().replace(/^([^\W\d_])\.$/u, '$1');
  return n(a) === n(b);
}

const overlap = (s, a, b) => Math.max(0, Math.min(s.end, b) - Math.max(s.start, a));
const r3 = (x) => Math.round(x * 1000) / 1000;

/**
 * Submitted segment with this text that best matches a span: one overlapping the span itself wins (most
 * overlap first), otherwise the nearest one within NEAR_S. Short words often repeat close together ("a ... a").
 */
function findWord(segs, word, a, b) {
  let best = null, bestKey = null;
  const mid = (a + b) / 2;
  for (const s of segs) {
    if (!same(s.word, word) || s.end < a - NEAR_S || s.start > b + NEAR_S) continue;
    const ov = overlap(s, a, b);
    const inside = ov > 0 || (s.end - s.start < 1e-6 && s.start >= a && s.start <= b);   // zero-length counts
    const key = [inside ? 1 : 0, ov, -Math.abs((s.start + s.end) / 2 - mid)];
    if (!bestKey || key[0] > bestKey[0] || (key[0] === bestKey[0] && (key[1] > bestKey[1]
        || (key[1] === bestKey[1] && key[2] > bestKey[2])))) { best = s; bestKey = key; }
  }
  return best;
}

/** Submitted segment (any text) with the largest overlap with a span. */
function dominant(segs, a, b) {
  let best = null, bestOv = 0;
  for (const s of segs) {
    const ov = overlap(s, a, b);
    if (ov > bestOv) { best = s; bestOv = ov; }
  }
  return best;
}

// ---------------------------------------------------------------- detectors
function edgeVerdict(got, gold, decoy) {
  const err = got - gold;
  const planted = decoy - gold;
  if (Math.abs(err) <= TOL_S) return VERDICT.CAUGHT;
  if (Math.sign(err) === Math.sign(planted) && Math.abs(err) >= 0.5 * Math.abs(planted)) return VERDICT.MISSED;
  return VERDICT.INDETERMINATE;
}

function scoreInjection(inj, sub, entry) {
  const m = inj.meta || {};
  const segs = sub.segments;
  const base = { injection_id: inj.injection_id, family: inj.family, group: GROUP_OF[inj.family],
    band: inj.band, weight: inj.weight, detect_rule: m.detect };
  const out = (verdict, evidence, confidence = 1) => ({ ...base, verdict, confidence, evidence });
  const g = m.gold || {};

  switch (m.detect) {
    // a start or end edge was moved (minor / major / into the neighbour word)
    case 'EDGE_AT_SLOT': {
      const seg = findWord(segs, m.word, Math.min(g.start, m.decoy.start), Math.max(g.end, m.decoy.end));
      if (!seg) return out(VERDICT.INDETERMINATE, { reason: 'WORD_NOT_FOUND', word: m.word }, 0);
      const got = seg[m.edge];
      const v = edgeVerdict(got, g[m.edge], m.decoy[m.edge]);
      return out(v, { word: m.word, edge: m.edge, gold_s: g[m.edge], planted_s: m.decoy[m.edge], submitted_s: got,
        remaining_error_ms: Math.round((got - g[m.edge]) * 1000), planted_shift_ms: m.shift_ms,
        submitted_segment: seg, ...(v === VERDICT.INDETERMINATE ? { reason: 'PARTIAL_OR_OVER_CORRECTION' } : {}) });
    }

    // we gave the word zero length; it must get its real length back
    case 'ZERO_LENGTH': {
      const seg = findWord(segs, m.word, g.start, g.end);
      if (!seg) return out(VERDICT.INDETERMINATE, { reason: 'WORD_NOT_FOUND', word: m.word }, 0);
      const dur = seg.end - seg.start, goldDur = g.end - g.start;
      const v = dur >= 0.5 * goldDur ? VERDICT.CAUGHT : dur < 0.02 ? VERDICT.MISSED : VERDICT.INDETERMINATE;
      return out(v, { word: m.word, gold_duration_ms: Math.round(goldDur * 1000), submitted_duration_ms: Math.round(dur * 1000),
        submitted_segment: seg });
    }

    // we removed a spoken word's segment; it must be back over the word
    case 'WORD_AT_SLOT_PRESENT': {
      const seg = findWord(segs, m.word, g.start, g.end);
      const ok = !!seg && overlap(seg, g.start, g.end) >= 0.3 * (g.end - g.start);
      return out(ok ? VERDICT.CAUGHT : VERDICT.MISSED, { expected_word: m.word, gold_span: g, restored: ok,
        submitted_segment: seg || null });
    }

    // we added a segment over a pause; no segment may still cover it
    case 'SEGMENT_AT_SLOT_ABSENT': {
      const a = m.decoy.start, b = m.decoy.end;
      const goldSpans = (entry.gold_segments || []);
      const still = segs.filter((s) => overlap(s, a, b) >= 0.5 * (b - a)
        && goldSpans.reduce((t, w) => t + overlap(s, w.start, w.end), 0) < 0.3 * Math.max(1e-6, s.end - s.start));
      return out(still.length ? VERDICT.MISSED : VERDICT.CAUGHT, { injected_word: m.word, planted_span: m.decoy,
        still_present: still.length > 0, covering_segments: still });
    }

    // we swapped the text of one segment (wrong word, digits, case, accent, filler spelling, punctuation)
    case 'WORD_AT_SLOT_SUBSTITUTED': {
      const seg = dominant(segs, g.start, g.end);
      if (!seg) return out(VERDICT.INDETERMINATE, { reason: 'NO_SEGMENT_AT_SLOT', expected_word: m.from }, 0);
      const v = same(seg.word, m.from) ? VERDICT.CAUGHT : same(seg.word, m.to) ? VERDICT.MISSED : VERDICT.INDETERMINATE;
      return out(v, { injected_word: m.to, expected_word: m.from, submitted_word: seg.word, submitted_segment: seg,
        ...(v === VERDICT.INDETERMINATE ? { reason: 'SLOT_HOLDS_THIRD_VALUE' } : {}) });
    }

    // we joined several words into one segment; each must be its own segment again
    case 'WORDS_SPLIT': {
      const parts = m.parts;                       // [{word,start,end}, ...] gold
      const a = parts[0].start, b = parts[parts.length - 1].end;
      const joined = segs.find((s) => same(s.word, m.joined) && overlap(s, a, b) > 0);
      const each = parts.map((p) => findWord(segs, p.word, p.start, p.end));
      const ok = !joined && each.every((s, i) => s && overlap(s, parts[i].start - NEAR_S, parts[i].end + NEAR_S) > 0);
      const v = ok ? VERDICT.CAUGHT : joined ? VERDICT.MISSED : VERDICT.INDETERMINATE;
      return out(v, { injected_segment: m.joined, expected_words: parts.map((p) => p.word), joined_still_present: !!joined,
        parts_found: each.map((s) => !!s) });
    }

    // we cut one word into pieces (compound, elision, contraction); it must be one segment again
    case 'WORD_MERGED': {
      const seg = findWord(segs, m.word, g.start, g.end);
      const ok = !!seg && overlap(seg, g.start, g.end) >= 0.5 * (g.end - g.start);
      const pieces = m.pieces.map((p) => segs.find((s) => same(s.word, p.word) && overlap(s, g.start - NEAR_S, g.end + NEAR_S) > 0));
      const v = ok ? VERDICT.CAUGHT : pieces.every(Boolean) ? VERDICT.MISSED : VERDICT.INDETERMINATE;
      return out(v, { expected_word: m.word, injected_pieces: m.pieces.map((p) => p.word), merged: ok,
        pieces_still_present: pieces.map(Boolean) });
    }

    // we hid a filler inside the next word's segment; it must have its own segment again
    case 'FILLER_PRESENT': {
      const f = findWord(segs, m.word, g.start, g.end);
      const hasFiller = !!f && overlap(f, g.start, g.end) >= 0.3 * (g.end - g.start);
      const nx = findWord(segs, m.next_word, m.next_gold.start, m.next_gold.end);
      const nextOk = !!nx && nx.start >= g.end - TOL_S;
      const v = hasFiller && nextOk ? VERDICT.CAUGHT : !hasFiller ? VERDICT.MISSED : VERDICT.INDETERMINATE;
      return out(v, { expected_filler: m.word, filler_restored: hasFiller, next_word: m.next_word,
        next_word_start_s: nx ? nx.start : null, filler_gold_end_s: g.end });
    }

    default:
      return out(VERDICT.INDETERMINATE, { reason: 'UNKNOWN_DETECT_RULE', detect: m.detect, family: inj.family }, 0);
  }
}

/** The whole-file checkbox: is the file entirely synthetic speech? */
function scoreCheckbox(inj, sub) {
  const base = { injection_id: inj.injection_id, family: inj.family, group: GROUP_OF[inj.family],
    band: inj.band, weight: inj.weight, detect_rule: inj.detect };
  if (sub.whole_audio_tag === undefined) {
    return { ...base, verdict: VERDICT.INDETERMINATE, confidence: 0,
      evidence: { reason: 'ANSWER_NOT_SUPPLIED', field: inj.field } };
  }
  const v = sub.whole_audio_tag === inj.gold ? VERDICT.CAUGHT
    : sub.whole_audio_tag === inj.decoy ? VERDICT.MISSED : VERDICT.INDETERMINATE;
  return { ...base, verdict: v, confidence: 1,
    evidence: { field: inj.field, injected_value: inj.decoy, expected_value: inj.gold, submitted_value: sub.whole_audio_tag,
      rule: inj.rule, audio_required: true } };
}

// ---------------------------------------------------------------- public API
/**
 * Score one decoy submission against its corpus entry.
 *
 * @param {object|array} submission  segments, or { segments, whole_audio_tag, discard_reason }
 * @param {object} decoyEntry        an element of decoy_corpus.json
 * @param {object} [ctx]             { annotator_id, submitted_at, batch_id, seconds_spent }
 */
function scoreDecoy(submission, decoyEntry, ctx = {}) {
  const sub = normaliseSubmission(submission);
  const fileIsSynthetic = decoyEntry.gold_whole_audio_tag === SYNTHETIC;
  const markedSynthetic = sub.whole_audio_tag === SYNTHETIC;
  const discarded = !!sub.discard_reason;

  const injections = (decoyEntry.injections || []).map((inj) => {
    if (inj.family === 'CB-WHOLE') return scoreCheckbox(inj, sub);
    if (fileIsSynthetic && markedSynthetic) {      // guideline 2.5: mark it, leave the transcription empty
      return { injection_id: inj.injection_id, family: inj.family, group: GROUP_OF[inj.family], band: inj.band,
        weight: inj.weight, detect_rule: inj.meta.detect, verdict: VERDICT.EXCLUDED, confidence: 1,
        evidence: { reason: 'FILE_CORRECTLY_MARKED_SYNTHETIC' } };
    }
    if (!fileIsSynthetic && (markedSynthetic || discarded)) {
      return { injection_id: inj.injection_id, family: inj.family, group: GROUP_OF[inj.family], band: inj.band,
        weight: inj.weight, detect_rule: inj.meta.detect, verdict: VERDICT.MISSED, confidence: 1,
        evidence: { reason: markedSynthetic ? 'HUMAN_FILE_MARKED_SYNTHETIC' : 'HUMAN_FILE_DISCARDED',
          discard_reason: sub.discard_reason } };
    }
    return scoreInjection(inj, sub, decoyEntry);
  });

  const tally = { A1: { hit: 0, miss: 0, indet: 0 }, A2: { hit: 0, miss: 0, indet: 0 }, A3: { hit: 0, miss: 0, indet: 0 } };
  const byFamily = {}, byGroup = {};
  let possible = 0, lost = 0;
  for (const r of injections) {
    if (r.verdict === VERDICT.EXCLUDED) continue;
    const k = r.verdict === VERDICT.CAUGHT ? 'hit' : r.verdict === VERDICT.MISSED ? 'miss' : 'indet';
    (tally[r.band] || (tally[r.band] = { hit: 0, miss: 0, indet: 0 }))[k] += 1;
    (byFamily[r.family] || (byFamily[r.family] = { hit: 0, miss: 0, indet: 0 }))[k] += 1;
    (byGroup[r.group] || (byGroup[r.group] = { hit: 0, miss: 0, indet: 0 }))[k] += 1;
    if (k !== 'indet') { possible += r.weight || 0; if (k === 'miss') lost += r.weight || 0; }
  }
  const missed = injections.filter((r) => r.verdict === VERDICT.MISSED);
  return {
    decoy_id: decoyEntry.decoy_id,
    group: decoyEntry.group,
    file_id: decoyEntry.file_id,
    file_name: decoyEntry.file_name,
    annotator_id: ctx.annotator_id || null,
    submitted_at: ctx.submitted_at || null,
    batch_id: ctx.batch_id || null,
    seconds_spent: ctx.seconds_spent ?? null,
    file_is_synthetic: fileIsSynthetic,
    marked_synthetic: markedSynthetic,
    false_synthetic: !fileIsSynthetic && markedSynthetic,
    injection_count: injections.length,
    caught: injections.filter((r) => r.verdict === VERDICT.CAUGHT).length,
    missed: missed.length,
    indeterminate: injections.filter((r) => r.verdict === VERDICT.INDETERMINATE).length,
    excluded: injections.filter((r) => r.verdict === VERDICT.EXCLUDED).length,
    points_possible: r3(possible),
    points_lost: r3(lost),
    score_percent: possible ? r3(100 * (1 - lost / possible)) : null,
    missed_families: missed.map((r) => r.family),
    missed_bands: missed.map((r) => r.band),
    by_band: tally,
    by_family: byFamily,
    by_group: byGroup,
    injections,
  };
}

// ---------------------------------------------------------------- residuals
/**
 * Category B: differences from gold that we did NOT inject. Advisory only:
 * gold timings are themselves accurate to about ±20–30 ms.
 */
function classifyResiduals(submission, decoyEntry) {
  const sub = normaliseSubmission(submission);
  const injected = [];
  for (const inj of decoyEntry.injections || []) {
    const m = inj.meta || {};
    const spans = [m.gold, m.decoy, ...(m.parts || [])].filter((s) => s && typeof s.start === 'number');
    for (const s of spans) injected.push([s.start - NEAR_S, s.end + NEAR_S]);
  }
  const inInjected = (w) => injected.some(([a, b]) => w.end > a && w.start < b);
  const findings = [];
  for (const w of decoyEntry.gold_segments || []) {
    if (inInjected(w)) continue;
    const seg = dominant(sub.segments, w.start, w.end);
    if (!seg) { findings.push({ category: 'B', severity: 'HARD', family: 'WD', detail: `no segment for: ${w.word}`, at_s: w.start }); continue; }
    if (!same(seg.word, w.word)) findings.push({ category: 'B', severity: 'HARD', family: 'WS', detail: `${w.word} -> ${seg.word}`, at_s: w.start });
    else {
      const e = Math.max(Math.abs(seg.start - w.start), Math.abs(seg.end - w.end));
      if (e > 0.1) findings.push({ category: 'B', severity: 'MEDIUM', family: 'BND', detail: `${w.word} edge off by ${Math.round(e * 1000)} ms`, at_s: w.start });
    }
  }
  return {
    decoy_id: decoyEntry.decoy_id,
    b_hard: findings.filter((f) => f.severity === 'HARD').length,
    b_medium: findings.filter((f) => f.severity === 'MEDIUM').length,
    findings,
    advisory: true,
    note: 'Category B is a diff against gold outside the injected regions. Use for coaching, not discipline.',
  };
}

// ---------------------------------------------------------------- reporting
/**
 * Daily per-annotator rollup.
 * @param {object[]} results  scoreDecoy() outputs
 * @param {object}  [opts]    { from, to, window } window = recent-N decoys per annotator
 */
function buildDailyReport(results, opts = {}) {
  const { from, to, window: win = null } = opts;
  const rows = results.filter((r) => {
    if (from && r.submitted_at && new Date(r.submitted_at) < new Date(from)) return false;
    if (to && r.submitted_at && new Date(r.submitted_at) > new Date(to)) return false;
    return true;
  });
  const byAnn = new Map();
  for (const r of rows) {
    const k = r.annotator_id || 'UNKNOWN';
    if (!byAnn.has(k)) byAnn.set(k, []);
    byAnn.get(k).push(r);
  }
  const rate = (o) => { const d = o.hit + o.miss; return d ? +(o.miss / d * 100).toFixed(1) : null; };
  const out = [];
  for (const [annotator, all] of byAnn) {
    const sorted = all.slice().sort((x, y) => new Date(x.submitted_at || 0) - new Date(y.submitted_at || 0));
    const list = win ? sorted.slice(-win) : sorted;
    const fam = {}, grp = {};
    for (const f of REPORT_FAMILIES) fam[f] = { hit: 0, miss: 0, indet: 0 };
    for (const g of REPORT_GROUPS) grp[g] = { hit: 0, miss: 0, indet: 0 };
    const band = { A1: { hit: 0, miss: 0, indet: 0 }, A2: { hit: 0, miss: 0, indet: 0 }, A3: { hit: 0, miss: 0, indet: 0 } };
    let secs = 0, secN = 0, possible = 0, lost = 0, falseSyn = 0;
    for (const r of list) {
      if (typeof r.seconds_spent === 'number') { secs += r.seconds_spent; secN += 1; }
      possible += r.points_possible || 0; lost += r.points_lost || 0; if (r.false_synthetic) falseSyn += 1;
      for (const inj of r.injections) {
        if (inj.verdict === VERDICT.EXCLUDED) continue;
        const b = inj.verdict === 'CAUGHT' ? 'hit' : inj.verdict === 'MISSED' ? 'miss' : 'indet';
        if (fam[inj.family]) fam[inj.family][b] += 1;
        if (grp[inj.group]) grp[inj.group][b] += 1;
        if (band[inj.band]) band[inj.band][b] += 1;
      }
    }
    const top = REPORT_GROUPS.map((g) => [g, grp[g].miss]).sort((a, b) => b[1] - a[1]);
    const row = {
      annotator,
      decoys_served: list.length,
      injections: Object.values(fam).reduce((s, o) => s + o.hit + o.miss + o.indet, 0),
      avg_seconds_per_file: secN ? Math.round(secs / secN) : null,
      points_possible: r3(possible), points_lost: r3(lost),
      score_percent: possible ? r3(100 * (1 - lost / possible)) : null,
      a1_missed: band.A1.miss, a1_attempted: band.A1.hit + band.A1.miss, a1_miss_rate: rate(band.A1),
      a2_missed: band.A2.miss, a2_attempted: band.A2.hit + band.A2.miss, a2_miss_rate: rate(band.A2),
      a3_missed: band.A3.miss, a3_attempted: band.A3.hit + band.A3.miss, a3_miss_rate: rate(band.A3),
      false_synthetic_marks: falseSyn,
      dominant_gap: top[0][1] === 0 ? 'clean' : (top[1][1] === top[0][1] ? 'MIXED' : top[0][0]),
      indeterminate: Object.values(fam).reduce((s, o) => s + o.indet, 0),
    };
    for (const g of REPORT_GROUPS) {
      row[`${g}_missed`] = grp[g].miss; row[`${g}_attempted`] = grp[g].hit + grp[g].miss; row[`${g}_miss_rate`] = rate(grp[g]);
    }
    for (const f of REPORT_FAMILIES) {
      row[`${f}_missed`] = fam[f].miss; row[`${f}_attempted`] = fam[f].hit + fam[f].miss; row[`${f}_miss_rate`] = rate(fam[f]);
    }
    out.push(row);
  }
  out.sort((a, b) => (b.a1_miss_rate ?? -1) - (a.a1_miss_rate ?? -1) || b.a1_missed - a.a1_missed
    || (b.a2_miss_rate ?? -1) - (a.a2_miss_rate ?? -1));
  return out;
}

/** Flatten a report to CSV for the daily pull. */
function reportToCsv(rows) {
  if (!rows.length) return '';
  const cols = Object.keys(rows[0]);
  const esc = (v) => { const s = v === null || v === undefined ? '' : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  return [cols.join(','), ...rows.map((r) => cols.map((c) => esc(r[c])).join(','))].join('\n');
}

/** Flatten per-injection detail for the audit table. */
function injectionsToRows(results) {
  const out = [];
  for (const r of results) {
    for (const inj of r.injections) {
      out.push({
        annotator_id: r.annotator_id, submitted_at: r.submitted_at, decoy_id: r.decoy_id, group: r.group,
        file_id: r.file_id, file_name: r.file_name, injection_id: inj.injection_id, family: inj.family,
        score_group: inj.group, band: inj.band, weight: inj.weight, verdict: inj.verdict, confidence: inj.confidence,
        submitted_word: inj.evidence?.submitted_segment?.word ?? inj.evidence?.submitted_word ?? null,
        submitted_start: inj.evidence?.submitted_segment?.start ?? null,
        submitted_end: inj.evidence?.submitted_segment?.end ?? null,
        evidence: JSON.stringify(inj.evidence),
      });
    }
  }
  return out;
}

/** Build an O(1) lookup keyed by both file_id and decoy_id. */
function indexCorpus(corpus) {
  const byFileId = new Map(), byDecoyId = new Map();
  for (const c of corpus) { byFileId.set(c.file_id, c); byDecoyId.set(c.decoy_id, c); }
  return { isDecoy: (fileId) => byFileId.has(fileId), get: (id) => byFileId.get(id) || byDecoyId.get(id) || null, size: corpus.length };
}

const api = {
  scoreDecoy, classifyResiduals, buildDailyReport, reportToCsv, injectionsToRows, indexCorpus,
  VERDICT, TOL_S, GROUP_OF, REPORT_FAMILIES, REPORT_GROUPS,
  _internal: { normaliseSubmission, findWord, dominant, edgeVerdict, same },
};
module.exports = api;
module.exports.default = api;
