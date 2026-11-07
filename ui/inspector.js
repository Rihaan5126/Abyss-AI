// Only public observations and inference evidence enter this inspector, never reveal files.
const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = v => Number.isFinite(v) ? v.toFixed(3) : 'Not recorded';
const image = path => /^[a-zA-Z0-9_./-]+$/.test(path || '') && !path.includes('..') ? esc(path) : '';

export function traceFor(log, stepNumber) {
  const index=log.steps.findIndex(s=>s.step===stepNumber);
  const current=log.steps[index], previous=log.steps[index-1], next=log.steps[index+1];
  if (!current?.observation) return null;
  const [r,c]=current.observation.waypoint;
  return {categories:current.observation.categories, richness:current.observation.richness,
    unknown:current.observation.unknown_flags.filter(Boolean).length,
    before:previous?.planner_diagnostics?.model?.observations ?? null,
    after:current.planner_diagnostics?.model?.observations ?? null,
    beforeRichness:previous?.planner_diagnostics?.predicted_richness?.[r]?.[c] ?? null,
    afterRichness:current.planner_diagnostics?.predicted_richness?.[r]?.[c] ?? null,
    nextTarget:next?.planned_target ?? null,
    utility:next?.planned_target==='HOME' ? null : next?.planner_diagnostics?.target_utility ?? null,
    mapsAvailable:!!current.planner_diagnostics?.predicted_richness};
}

export function installInspector({app}) {
  const panel=document.createElement('aside');panel.id='observation-inspector';panel.hidden=true;
  panel.setAttribute('aria-label','Observation inspector');document.body.append(panel);
  let token=0;
  const close=()=>{token++;panel.hidden=true;document.body.classList.remove('inspector-open');};
  const open=async(pane,stepNumber,index=0)=>{
    const serial=++token;
    const step=pane.log.steps.find(s=>s.step===stepNumber), obs=step?.observation;
    panel.hidden=false;document.body.classList.add('inspector-open');
    panel.scrollTop=0;
    panel.innerHTML=`<button class="inspector-close" aria-label="Close inspector">Close ×</button><h2>Observation inspector</h2><p>${esc(pane.entry.label)} · Survey ${stepNumber}</p><div class="inspector-content">Loading recorded evidence…</div>`;
    panel.querySelector('.inspector-close').onclick=close;
    const content=panel.querySelector('.inspector-content');
    if (!obs) {content.textContent='No survey observation at this step.';return;}
    if (!obs.image_refs.length) {
      content.textContent=obs.perception_mode==='ideal'
        ? 'Ideal perception: simulator labels were supplied, so no image inference occurred.'
        : 'Empty survey: no animal image was supplied.';return;
    }
    if (index>=obs.image_refs.length) index=0;
    let evidence;
    try {
      if (pane.entry.evidence) {
        pane.inferenceEvidence ||= await fetch(pane.entry.evidence).then(r=>{if(!r.ok)throw Error('Evidence unavailable');return r.json();});
        evidence=pane.inferenceEvidence[obs.evidence_ids?.[index]];
      }
    } catch (_) { /* old logs are still inspectable */ }
    if (serial!==token) return;
    const buttons=obs.image_refs.map((_,i)=>`<button data-image="${i}" ${i===index?'aria-pressed="true"':''}>Image ${i+1}</button>`).join('');
    const result=evidence?.result || {predicted_category:obs.image_labels[index],is_unknown:obs.unknown_flags[index],novelty_score:obs.novelty_scores[index]};
    const refs=evidence?.neighbors.map(n=>`<figure><img src="${image(n.image)}" alt="Reference crop"><figcaption>${esc(n.label)}<br>Similarity ${num(n.similarity)} · distance ${num(n.distance)}<br>Vote weight ${num(n.weight)}<br>${esc(n.credit?.attribution || 'Credit in manifest')} · ${esc(n.credit?.image_license || 'See source licence')}</figcaption></figure>`).join('') || '';
    const trace=traceFor(pane.log,stepNumber);
    const decision=trace.nextTarget==='HOME'?'Return home':trace.nextTarget ? JSON.stringify(trace.nextTarget) : 'No subsequent decision recorded';
    content.innerHTML=`<div class="inspector-images">${buttons}</div><p>Selected recorded observation. Scrubbing does not change this selection.</p>
      <img class="inspector-input" src="${image(obs.image_refs[index])}" alt="Exact image supplied to the model">
      <h3>${esc(result.is_unknown?'Reference-unfamiliar':result.predicted_category || 'No label')}</h3>
      <p>Recorded mission prediction · not live camera footage</p>
      <dl><dt>Nearest-reference similarity</dt><dd>${num(evidence?.result.similarity_score)}</dd><dt>Unfamiliarity distance</dt><dd>${num(result.novelty_score)}</dd><dt>Frozen threshold</dt><dd>${num(evidence?.threshold)}</dd></dl>
      ${evidence ? `<p>Distance ${result.is_unknown?'exceeded':'did not exceed'} the threshold. ${evidence.neighbors_used} reference${evidence.neighbors_used===1?'':'s'} used; vote winner: ${esc(evidence.vote_winner)}.</p>` : '<p>Reference details were not recorded in these older logs. Regenerate a vision replay to capture evidence.</p>'}
      <p>Similarity is visual resemblance, not confidence. Unfamiliar does not mean a new species.</p>
      <h3>Reference evidence</h3><div class="inspector-references">${refs || 'Not recorded'}</div>
      <p>${esc(evidence?.credit?.attribution || 'Attribution in source manifest')} · ${esc(evidence?.credit?.image_license || 'See source licence')}</p>
      <details><summary>How this entered the mission</summary><ol><li>Image classified as shown above.</li><li>Observation delivered: ${esc(trace.categories.join(', ') || 'No familiar labels')}; ${trace.unknown} unfamiliar-image flags; richness ${esc(trace.richness)}.</li><li>Habitat update count: ${esc(trace.before ?? 'Not recorded')} → ${esc(trace.after ?? 'No learned-model count recorded')}. Updated belief map ${trace.mapsAvailable?'recorded':'not recorded'}.</li><li>Next selected action: ${esc(decision)}. ${trace.utility?`Selection scores: ${esc(JSON.stringify(trace.utility))}`:''}</li></ol><p>These are chronological records, not proof that this single image caused a route change. Next-target scores come from the following step's decision record.</p></details>
      <p>Predicted richness at this waypoint before/after the update: ${num(trace.beforeRichness)} → ${num(trace.afterRichness)}. Missing prior values are not invented.</p>
      <details><summary>Technical provenance</summary><pre>${esc(evidence ? JSON.stringify({image_id:evidence.id,artifact:evidence.artifact_id,encoder:evidence.encoder,embedding_cached:evidence.embedding_cached,processing_ms:evidence.processing_ms,timing_scope:evidence.timing_scope},null,2) : 'Unavailable for this older log')}</pre></details>
      <h3>Optional fresh reanalysis</h3><p class="inspector-api">Checking local inference server…</p><button class="inspector-reanalyse" disabled>Reanalyse this image</button><div class="inspector-fresh"></div>`;
    content.querySelectorAll('[data-image]').forEach(b=>b.onclick=()=>open(pane,stepNumber,Number(b.dataset.image)));
    const status=content.querySelector('.inspector-api'), button=content.querySelector('.inspector-reanalyse');
    try {
      const response=await fetch('/api/inspector');
      if (!response.ok) throw Error('Static server');
      const capabilities=await response.json();
      if (serial!==token) return;
      if (!evidence) throw Error('Missing registered evidence');
      const mismatch=capabilities.artifact_id!==evidence.artifact_id;
      status.textContent=mismatch?'Different artifact loaded: reanalysis will use that model, not the recorded one.':'Matching artifact loaded. Fresh inference will not change the expedition.';
      button.disabled=false;
      button.onclick=async()=>{
        button.disabled=true;status.textContent='Running the actual encoder…';
        try {
          const r=await fetch('/api/reanalyse',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:evidence.id})});
          const data=await r.json();if(!r.ok)throw Error(data.error || 'Inference failed');
          if(serial!==token)return;
          content.querySelector('.inspector-fresh').textContent=`Fresh reanalysis: ${data.result.is_unknown?'Reference-unfamiliar':data.result.predicted_category}; similarity ${num(data.result.similarity_score)}, distance ${num(data.result.novelty_score)}, threshold ${num(data.threshold)}; ${num(data.processing_ms)} ms (encoding and matching, excludes loading). Artifact ${data.artifact_matches?'matches':'DIFFERS from'} the recording. Recorded results remain unchanged.`;
          status.textContent='Fresh inference complete; embedding cache bypassed.';
        } catch(error) {if(serial===token)status.textContent=error.message;}
        finally {if(serial===token)button.disabled=false;}
      };
    } catch (_) {if(serial===token)status.textContent='Recorded observations remain available. Fresh reanalysis requires: python -m perception.inspector_server (with the mission artifact and registry).';}
  };
  document.addEventListener('keydown',event=>{if(event.key==='Escape')close();});
  return {open,close};
}
