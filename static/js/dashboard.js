function decide(rowId, action) {
  fetch('/api/approve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ row_id: rowId, action: action }),
  })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        showToast('Updated → ' + data.status);
        const row = document.querySelector(`tr[data-row-id="${rowId}"]`);
        if (row) {
          row.style.opacity = '0.3';
          setTimeout(() => location.reload(), 900);
        }
      } else {
        showToast('Error: ' + (data.error || 'unknown'), true);
      }
    })
    .catch(() => showToast('Network error', true));
}

function showToast(msg, isError) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast' + (isError ? ' toast-error' : '');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.add('hidden'), 2500);
}

// ── Search modal ──────────────────────────────────────────────────────────────

const modal = document.getElementById('searchModal');

function openSearchModal() {
  modal.classList.remove('hidden');
  document.getElementById('searchResult').classList.add('hidden');
  document.getElementById('searchResult').innerHTML = '';
}

document.getElementById('triggerSearchBtn')?.addEventListener('click', openSearchModal);
document.getElementById('triggerSearchBtn2')?.addEventListener('click', openSearchModal);
document.getElementById('triggerSearchBtn3')?.addEventListener('click', openSearchModal);

const careerPilotButton = document.getElementById('runCareerPilotBtn');
const journey = window.CareerPilotJourney;
const journeyRoot = document.getElementById('careerPilotJourney');
const careerPilotResultsPanel = document.getElementById('careerPilotResults');
if (careerPilotResultsPanel?.classList.contains('hidden') && journey?.getState().draftReady) {
  // Drafts are intentionally not persisted in the browser; after reload, offer a fresh run.
  journey.setState({ draftReady: false });
}

document.getElementById('careerPilotJourneyAction')?.addEventListener('click', () => {
  const step = Number(journeyRoot?.dataset.currentStep || 0);
  if (step <= 2) {
    window.location.href = '/profile#careerPilotJourney';
  } else if (step === 3) {
    const searchButton = document.getElementById('triggerSearchBtn')
      || document.getElementById('triggerSearchBtn2')
      || document.getElementById('triggerSearchBtn3');
    searchButton?.click();
  } else if (step === 4) {
    careerPilotButton?.click();
  } else {
    document.getElementById('careerPilotResults')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
});

careerPilotButton?.addEventListener('click', async () => {
  const status = document.getElementById('careerPilotStatus');
  const results = careerPilotResultsPanel;
  const metricsPanel = document.getElementById('careerPilotMetrics');
  const activityPanel = document.getElementById('careerPilotActivity');
  careerPilotButton.disabled = true;
  status.textContent = 'Running job discovery, matching, and draft preparation on the configured vLLM endpoint…';
  journey?.setStatus('I’m coordinating the Collector, Scorekeeper, and AI coach. This request returns when the run finishes, so detailed activity will appear here afterward.', 'talk');
  results.replaceChildren();
  results.classList.add('hidden');
  metricsPanel.replaceChildren(); metricsPanel.classList.add('hidden');
  activityPanel.replaceChildren(); activityPanel.classList.add('hidden');

  try {
    const response = await fetch('/api/careerpilot/run', { method: 'POST' });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || 'CareerPilot run failed.');

    status.textContent = 'CareerPilot finished. Drafts require your review; nothing was submitted.';
    const draftReady = Boolean(data.application_package);
    journey?.setState({ matchesReady: true, draftReady });
    journey?.setStatus(draftReady
      ? 'The draft is ready. Check the evidence and unknowns below, then decide what to use. Nothing has been submitted.'
      : 'Matching finished, but no application draft was returned. Review the matches below and try CareerPilot again if you want a draft. Nothing has been submitted.', draftReady ? 'celebrate' : 'surprise');
    const summary = document.createElement('p');
    summary.textContent = data.answer?.summary || 'Match analysis complete.';
    results.appendChild(summary);

    const assessments = new Map((data.answer?.assessments || []).map(item => [item.job_id, item]));
    for (const job of data.matches || []) {
      const card = document.createElement('article');
      card.className = 'agent-result-card';
      const heading = document.createElement('h3');
      heading.textContent = `${job['Job Title'] || 'Role'} — ${job.Company || 'Company'} · ${job['Match Score'] || '—'}/100`;
      card.appendChild(heading);
      const details = assessments.get(String(job._row_id));
      const explanation = document.createElement('p');
      explanation.textContent = details?.explanation || job['Why It Fits'] || 'No explanation available.';
      card.appendChild(explanation);
      if (details?.evidence?.length || details?.gaps_or_unknowns?.length || details?.resume_recommendations?.length) {
        const list = document.createElement('ul');
        for (const text of [
          ...(details.evidence || []).map(value => `Evidence: ${value}`),
          ...(details.gaps_or_unknowns || []).map(value => `Gap or unknown: ${value}`),
          ...(details.resume_recommendations || []).map(value => `Resume suggestion: ${value}`),
        ]) {
          const item = document.createElement('li'); item.textContent = text; list.appendChild(item);
        }
        card.appendChild(list);
      }
      results.appendChild(card);
    }

    if (data.application_package) {
      const card = document.createElement('article');
      card.className = 'agent-result-card';
      const heading = document.createElement('h3');
      heading.textContent = 'Application package — human review required';
      card.appendChild(heading);
      const packageJob = (data.matches || []).find(job => String(job._row_id) === String(data.application_package.job_id));
      const postingUrl = safeHttpUrl(packageJob?.['Job URL']);
      if (postingUrl) {
        const link = document.createElement('a');
        link.href = postingUrl;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.textContent = 'Open original posting to apply yourself';
        card.appendChild(link);
      }
      for (const [label, value] of [['Tailored resume draft', data.application_package.resume_draft], ['Cover note draft', data.application_package.cover_note_draft]]) {
        const disclosure = document.createElement('details');
        const summary = document.createElement('summary'); summary.textContent = label;
        const pre = document.createElement('pre'); pre.textContent = value || '';
        disclosure.append(summary, pre); card.appendChild(disclosure);
      }
      results.appendChild(card);
    }
    results.classList.remove('hidden');

    const metrics = data.inference_metrics || {};
    const metricsTitle = document.createElement('h3'); metricsTitle.textContent = 'Inference performance';
    metricsPanel.appendChild(metricsTitle);
    const metricsLines = [
      `Model: ${metrics.model_name || 'unknown'}`,
      `Model requests this run: ${metrics.model_requests_this_run ?? 'unavailable'}`,
      `Application request average latency: ${metrics.application_request_latency_ms_average == null ? 'unavailable' : `${metrics.application_request_latency_ms_average} ms`}`,
      `Agent model latency: ${metrics.agent_model_latency_ms == null ? 'unavailable' : `${metrics.agent_model_latency_ms} ms (Strands measured)`}`,
      `Agent TTFT: ${metrics.time_to_first_token_ms_this_run == null ? 'unavailable' : `${metrics.time_to_first_token_ms_this_run} ms`} — ${metrics.time_to_first_token_note || ''}`,
      `Agent output tokens: ${metrics.agent_output_tokens ?? 'unavailable'}`,
      `Derived agent output throughput: ${metrics.agent_output_tokens_per_second_derived == null ? 'unavailable' : `${metrics.agent_output_tokens_per_second_derived} tokens/s (derived)`}`,
      `Task wall latency: ${metrics.task_wall_latency_ms ?? 'unavailable'} ms · ${metrics.task_status || 'unknown'}`,
    ];
    for (const line of metricsLines) { const p = document.createElement('p'); p.textContent = line; metricsPanel.appendChild(p); }
    const server = metrics.vllm_server_metrics || {};
    const serverLine = document.createElement('p');
    serverLine.textContent = server.available
      ? `vLLM server aggregate since start: TTFT ${server.time_to_first_token_ms_average ?? 'n/a'} ms; request latency ${server.request_latency_ms_average ?? 'n/a'} ms; generated tokens ${server.generated_tokens_total ?? 'n/a'}; throughput ${server.aggregate_tokens_per_second ?? 'n/a'} tokens/s.`
      : `vLLM /metrics unavailable (${server.reason || 'not reachable'}).`;
    metricsPanel.appendChild(serverLine);
    metricsPanel.classList.remove('hidden');

    const events = data.activity_log || [];
    const activityTitle = document.createElement('h3'); activityTitle.textContent = 'Agent activity';
    activityPanel.appendChild(activityTitle);
    const activityList = document.createElement('ul');
    for (const event of events) {
      const item = document.createElement('li');
      item.textContent = `${event.time || ''} · ${event.activity || 'activity'} · ${event.status || ''}`;
      activityList.appendChild(item);
    }
    activityPanel.appendChild(activityList);
    activityPanel.classList.remove('hidden');
  } catch (error) {
    status.textContent = error.message || 'CareerPilot run failed.';
    journey?.setStatus('I couldn’t finish this run. Check the message above; if the profile is not verified yet, review it on the Profile page first.', 'surprise');
    activityPanel.classList.add('hidden');
  } finally {
    careerPilotButton.disabled = false;
  }
});

function safeHttpUrl(value) {
  try {
    const url = new URL(value, window.location.origin);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
  } catch {
    return '';
  }
}

function closeModal() {
  modal.classList.add('hidden');
}

modal?.addEventListener('click', e => {
  if (e.target === modal) closeModal();
});

document.getElementById('confirmSearchBtn')?.addEventListener('click', () => {
  const resultEl = document.getElementById('searchResult');
  const btn      = document.getElementById('confirmSearchBtn');
  btn.disabled   = true;
  btn.textContent = 'Starting…';

  fetch('/api/trigger-search', { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      resultEl.classList.remove('hidden');
      if (data.ok) {
        if (data.mode === 'standalone') {
          resultEl.innerHTML = `<strong>Done</strong> — scored ${data.count} jobs. Reloading…`;
          resultEl.style.borderColor = 'var(--green)';
          resultEl.style.color = 'var(--green)';
          setTimeout(() => location.reload(), 1500);
        } else {
          // Temporal mode — poll the workflow for live progress
          _pollWorkflow(data.workflow_id, resultEl, btn);
        }
      } else {
        resultEl.textContent = data.error || 'Search failed.';
        resultEl.style.borderColor = 'var(--red)';
        resultEl.style.color = 'var(--red)';
        btn.disabled    = false;
        btn.textContent = 'Start Search';
      }
    })
    .catch(() => {
      resultEl.classList.remove('hidden');
      resultEl.textContent = 'Could not reach server.';
      resultEl.style.borderColor = 'var(--red)';
      resultEl.style.color = 'var(--red)';
      btn.disabled    = false;
      btn.textContent = 'Start Search';
    });
});

// ── Temporal workflow progress polling ────────────────────────────────────────

const _STAGE_LABELS = {
  starting:      '1 / 5 — Starting',
  scraping:      '2 / 5 — Scraping sources',
  deduplicating: '3 / 5 — Deduplicating',
  scoring:       '4 / 5 — AI scoring',
  saving:        '5 / 5 — Saving results',
  complete:      'Complete',
};

function _renderProgress(el, progress, wfStatus) {
  const stage   = progress.stage   || 'starting';
  const message = progress.message || 'Working…';
  const found   = progress.jobs_found     || 0;
  const scored  = progress.jobs_scored    || 0;
  const strong  = progress.strong_matches || 0;

  let html = `<div class="prog-stage">${_STAGE_LABELS[stage] || stage}</div>`;
  html    += `<div class="prog-msg">${message}</div>`;

  if (found > 0 || scored > 0) {
    html += `<div class="prog-stats">`;
    if (found)  html += `Scraped <strong>${found}</strong>`;
    if (scored) html += ` &middot; Scored <strong>${scored}</strong>`;
    if (strong) html += ` &middot; Matches <strong>${strong}</strong>`;
    html += `</div>`;
  }

  el.innerHTML          = html;
  el.style.borderColor  = stage === 'complete' ? 'var(--green)' : 'var(--border)';
  el.style.color        = 'var(--text)';
}

function _pollWorkflow(workflowId, resultEl, btn) {
  _renderProgress(resultEl, { stage: 'starting', message: 'Connecting to Temporal…' }, null);

  const interval = setInterval(async () => {
    try {
      const r    = await fetch(`/api/workflow-status/${workflowId}`);
      const data = await r.json();

      if (!data.ok) {
        clearInterval(interval);
        resultEl.textContent  = 'Workflow error: ' + data.error;
        resultEl.style.borderColor = 'var(--red)';
        resultEl.style.color  = 'var(--red)';
        btn.disabled    = false;
        btn.textContent = 'Start Search';
        return;
      }

      const progress = data.progress || {};
      _renderProgress(resultEl, progress, data.status);

      const done   = data.status === 'COMPLETED' || progress.stage === 'complete';
      const failed = ['FAILED', 'CANCELED', 'TERMINATED'].includes(data.status);

      if (done) {
        clearInterval(interval);
        resultEl.innerHTML = '<strong>Search complete!</strong> Loading your matches…';
        resultEl.style.borderColor = 'var(--green)';
        resultEl.style.color = 'var(--green)';
        setTimeout(() => location.reload(), 1500);
      } else if (failed) {
        clearInterval(interval);
        resultEl.textContent = `Workflow ${data.status.toLowerCase()} — check worker logs.`;
        resultEl.style.borderColor = 'var(--red)';
        resultEl.style.color = 'var(--red)';
        btn.disabled    = false;
        btn.textContent = 'Start Search';
      }
    } catch (_) {
      // Network blip — keep polling
    }
  }, 3000);
}
