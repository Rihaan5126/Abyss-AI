// Evaluator-facing report, generated only when the viewer requests hidden truth.
const esc = (v) => String(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

const STRATEGY = {
  abyss: 'Original ABYSS updates a habitat model after observations, then balances predicted richness, uncertainty, coverage and travel cost. It predicts richness rather than directly predicting previously unseen categories.',
  'abyss-discovery': 'ABYSS Discovery is experimental. It estimates occurrence of observed categories from terrain and spatial patterns, reduces the weight of frequent sightings, samples habitats early and compares short routes with a return reserve. Rare-category habitat is a clue to further discoveries, not a calibrated prediction of unseen species. Conservative image updates limit isolated labels and repeated unfamiliar images.',
  'abyss-discovery-nolearn': 'Discovery with biological learning disabled; it retains terrain coverage and navigation.',
  'abyss-discovery-norarity': 'Discovery without rarity weighting: frequent categories retain their full value.',
  'abyss-discovery-myopic': 'Discovery restricted to choosing one survey stop at a time.',
  'abyss-discovery-route': 'Discovery with three-stop route lookahead enabled. Development selected the one-stop variant; this alternative remains experimental.',
  'abyss-discovery-nowarmup': 'Discovery without its initial habitat sampling phase.',
  'abyss-discovery-unguarded': 'Discovery without conservative image updates. Unfamiliar flags count without capping or deduplication.',
  frontier: 'Frontier explores nearby unvisited locations.',
  lawnmower: 'Lawnmower follows a back-and-forth pattern planned before the mission.',
  heuristic: 'Heuristic follows a fixed preference for steep ground.',
  random: 'Random picks reachable locations at random.',
};

export function buildReport(panes) {
  const rows = panes.map(p => {
    if (!p.reveal) throw new Error('Load the evaluation record before generating a report.');
    const o = p.log.outcome;
    return {name:p.entry.label, perceived:o.distinct_categories, actual:p.reveal.true_distinct_count,
      available:p.reveal.categories_available_count, surveys:o.surveys,
      energy:o.energy_used, budget:p.log.energy.budget, safe:o.safe_return,
      unknown:o.unknown_encounters, known:o.discovered, world:p.log.world,
      vision:p.log.provenance.perception, planner:p.entry.planner};
  });
  const abyss = rows.find(r => r.planner === 'abyss-discovery') || rows.find(r => r.planner.startsWith('abyss'));
  const other = rows.find(r => r.planner === 'frontier' && r !== abyss) || rows.find(r => r !== abyss);
  let finding = 'Each explorer is scored on the true categories encountered within its energy allowance.';
  if (abyss && other) {
    const delta = abyss.actual - other.actual;
    finding = delta === 0
      ? `${abyss.name} and ${other.name} encountered the same number of actual organism categories: ${abyss.actual}.`
      : `${abyss.name} encountered ${Math.abs(delta)} ${delta > 0 ? 'more' : 'fewer'} actual organism ${Math.abs(delta) === 1 ? 'category' : 'categories'} than ${other.name} (${abyss.actual} versus ${other.actual}).`;
    finding += ` ${abyss.name} made ${abyss.surveys} survey stops and used ${abyss.energy.toFixed(1)} energy; ${other.name} made ${other.surveys} stops and used ${other.energy.toFixed(1)} energy.`;
  }
  const otherStrategy = other ? (STRATEGY[other.planner] || `${other.name} follows its recorded strategy.`) : '';
  const strategies = [otherStrategy, ...rows.filter(r => r !== other).map(r => STRATEGY[r.planner] || `${r.name} follows its recorded strategy.`)].filter(Boolean).join(' ');
  const body = rows.map(r => `<tr><th>${esc(r.name)}</th><td>${r.actual}/${r.available}</td><td>${r.perceived}</td><td>${r.surveys}</td><td>${r.energy.toFixed(1)}/${r.budget}</td><td>${r.unknown}</td><td>${r.safe?'Yes':'No'}</td></tr>`).join('');
  const inventory = rows.map(r=>`<p><strong>${esc(r.name)} — reported labels:</strong> ${r.known.map(esc).join(', ') || 'None'}.</p>`).join('');
  const provenance = rows.map(r=>`<li>${esc(r.name)}: ${esc(r.world.id)}; perception ${esc(r.vision)}.</li>`).join('');
  return `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ABYSS expedition findings</title><style>body{font:17px system-ui;max-width:1000px;margin:40px auto;padding:24px;line-height:1.6;color:#102c38}h1{font-size:32px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border-bottom:1px solid #ccd;padding:10px;text-align:left}.finding{background:#eaf6f2;padding:20px;border-radius:12px}small{color:#456}@media print{button{display:none}body{margin:0}}</style>
<h1>ABYSS — expedition findings</h1>
<p><strong>Question:</strong> Does learning from animal observations help an underwater explorer find more different organism categories within a limited energy allowance?</p>
<div class="finding"><strong>What happened in this expedition</strong><p>${esc(finding)}</p><p>${rows.every(r=>r.safe)?'Both robots returned home safely.':'Check the return status below; at least one safe return was not verified.'}</p></div>
<h2>The results</h2><table><tr><th>Explorer</th><th>Actual categories encountered</th><th>Categories perceived</th><th>Survey stops</th><th>Energy used / budget</th><th>Unfamiliar images</th><th>Safe home</th></tr>${body}</table>
<h2>What these numbers mean</h2><p><strong>Actual categories</strong> come from the simulator's hidden answer sheet. <strong>Perceived categories</strong> are labels reported by the robot's observation system, which can make mistakes. Finding the same category repeatedly counts only once.</p>
<p><strong>Survey stops</strong> are locations where the robot looked for animals. Fewer stops alone does not mean a better expedition. Travel and surveys both spend energy, and both robots must reserve enough energy to return home. Energy is simulated, not measured battery consumption.</p>
<p><strong>Unfamiliar images</strong> are distinct images flagged as insufficiently similar to familiar references. They are not a count of new species; repeated or different images can represent the same category.</p>
<h2>What did the robots recognise?</h2>${inventory}
<h2>How the exploration works</h2><p>${esc(strategies)} This report does not establish which component caused a difference.</p>
<h2>What we can conclude</h2><p>This report describes one paired simulated expedition. A tie, win or loss here does not prove that one explorer is generally better. That requires repeated matched worlds and separately reported benchmark results. These numbers are not the published 6,300-mission ideal-perception benchmark.</p>
<p>The seabed uses the terrain source recorded in the mission. Biology is simulated. Animal photographs represent simulated encounters, not sightings at these coordinates. The 3D animation replays computed routes; the image model classifies supplied crops and does not detect animals inside the animated scene.</p>
<details><summary>Experiment details</summary><ul>${provenance}</ul><p>Counts and routes come from the saved mission logs and private evaluation records. This report contains no animal image crops.</p></details>
<p><button onclick="window.print()">Print / save as PDF</button></p></html>`;
}
