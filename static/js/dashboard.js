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
