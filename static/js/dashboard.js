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
          // Fade the row out and reload stats after a moment
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

// Run Search modal
const modal = document.getElementById('searchModal');

function openSearchModal() {
  modal.classList.remove('hidden');
  document.getElementById('searchResult').classList.add('hidden');
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
  const btn = document.getElementById('confirmSearchBtn');
  btn.disabled = true;
  btn.textContent = 'Starting…';

  fetch('/api/trigger-search', { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      resultEl.classList.remove('hidden');
      if (data.ok) {
        if (data.mode === 'standalone') {
          resultEl.textContent = `Done — scored ${data.count} jobs against your profile. Reloading…`;
          resultEl.style.borderColor = 'var(--green)';
          resultEl.style.color = 'var(--green)';
          setTimeout(() => location.reload(), 1500);
        } else {
          resultEl.textContent = `Search started (run ID: ${data.run_id}). You'll be alerted when strong matches are found.`;
          resultEl.style.borderColor = 'var(--green)';
          resultEl.style.color = 'var(--green)';
        }
      } else {
        resultEl.textContent = data.error + (data.hint ? ' — ' + data.hint : '');
        resultEl.style.borderColor = 'var(--red)';
        resultEl.style.color = 'var(--red)';
      }
      btn.disabled = false;
      btn.textContent = 'Start Search';
    })
    .catch(() => {
      resultEl.classList.remove('hidden');
      resultEl.textContent = 'Could not reach server.';
      resultEl.style.borderColor = 'var(--red)';
      resultEl.style.color = 'var(--red)';
      btn.disabled = false;
      btn.textContent = 'Start Search';
    });
});
