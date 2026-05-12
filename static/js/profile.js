// ── Resume upload ─────────────────────────────────────────────────────────

const uploadZone   = document.getElementById('uploadZone');
const fileInput    = document.getElementById('resumeFile');
const uploadStatus = document.getElementById('uploadStatus');

uploadZone.addEventListener('dragover', e => { e.preventDefault(); uploadZone.classList.add('drag-over'); });
uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('drag-over'));
uploadZone.addEventListener('drop', e => {
  e.preventDefault();
  uploadZone.classList.remove('drag-over');
  if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => { if (fileInput.files[0]) handleFile(fileInput.files[0]); });

function handleFile(file) {
  if (file.size > 5 * 1024 * 1024) { showToast('File too large (max 5MB)', true); return; }

  uploadStatus.className = 'upload-status';
  uploadStatus.textContent = 'Reading resume and extracting profile…';
  uploadZone.style.opacity = '0.5';
  uploadZone.style.pointerEvents = 'none';

  const fd = new FormData();
  fd.append('resume', file);

  fetch('/api/upload-resume', { method: 'POST', body: fd })
    .then(r => r.json())
    .then(data => {
      uploadZone.style.opacity = '';
      uploadZone.style.pointerEvents = '';

      if (data.ok) {
        uploadStatus.textContent = 'Profile updated from your resume. Review the fields below, then click View Jobs.';
        uploadStatus.classList.add('status-ok');
        // Profile was already saved server-side — fill form from structured profile
        const p = data.profile || data.extracted;
        fillForm({
          name:                 p.name,
          experience_years:     p.experience_years,
          role_type:            p.role_type,
          target_titles:        p.target_titles,
          skills:               p.skills,
          location_preferred:   (p.location || {}).preferred || p.location_preferred,
          location_hard_no:     (p.location || {}).hard_no   || p.location_hard_no,
          salary_minimum:       (p.salary   || {}).minimum   || p.salary_minimum,
          salary_target:        (p.salary   || {}).target    || p.salary_target,
          industries_preferred: (p.industries || {}).preferred || p.industries_preferred,
          industries_avoid:     (p.industries || {}).avoid     || p.industries_avoid,
        });
        if (p.base_resume) document.getElementById('baseResumeText').value = p.base_resume;
        showSaveStatus('Saved from resume');
        showViewJobsBtn();
      } else {
        uploadStatus.textContent = 'Failed: ' + (data.error || 'unknown error');
        uploadStatus.classList.add('status-error');
      }
    })
    .catch(() => {
      uploadZone.style.opacity = '';
      uploadZone.style.pointerEvents = '';
      uploadStatus.textContent = 'Network error — try again.';
      uploadStatus.classList.add('status-error');
    });
}

function fillForm(d) {
  const set = (name, val) => {
    const el = document.querySelector(`[name="${name}"]`);
    if (!el || val === undefined || val === null) return;
    el.value = Array.isArray(val) ? val.join('\n') : val;
  };

  set('name',               d.name);
  set('experience_years',   d.experience_years);
  set('target_titles',      d.target_titles);
  set('skills',             d.skills);
  set('location_preferred', d.location_preferred);
  set('location_hard_no',   d.location_hard_no);
  set('industries_preferred', d.industries_preferred);
  set('industries_avoid',     d.industries_avoid);

  if (d.salary_minimum) set('salary_minimum', d.salary_minimum);
  if (d.salary_target)  set('salary_target',  d.salary_target);

  // role_type is a <select>
  if (d.role_type) {
    const sel = document.querySelector('[name="role_type"]');
    if (sel) sel.value = d.role_type;
  }
}

// ── Profile form save ─────────────────────────────────────────────────────

document.getElementById('profileForm').addEventListener('submit', async e => {
  e.preventDefault();
  const fd = new FormData(e.target);

  const payload = {
    name:             fd.get('name'),
    experience_years: parseInt(fd.get('experience_years')) || 0,
    role_type:        fd.get('role_type'),
    target_titles:    lines(fd.get('target_titles')),
    skills:           lines(fd.get('skills')),
    location: {
      preferred: lines(fd.get('location_preferred')),
      hard_no:   lines(fd.get('location_hard_no')),
    },
    salary: {
      minimum: parseInt(fd.get('salary_minimum')) || 0,
      target:  parseInt(fd.get('salary_target'))  || 0,
    },
    industries: {
      preferred: lines(fd.get('industries_preferred')),
      avoid:     lines(fd.get('industries_avoid')),
    },
    scoring_weights: {
      title_match:    parseFloat(fd.get('w_title'))    || 0.30,
      skills_match:   parseFloat(fd.get('w_skills'))   || 0.25,
      salary_match:   parseFloat(fd.get('w_salary'))   || 0.20,
      location_match: parseFloat(fd.get('w_location')) || 0.15,
      industry_match: parseFloat(fd.get('w_industry')) || 0.10,
    },
    minimum_score: parseInt(fd.get('minimum_score')) || 65,
    base_resume:   fd.get('base_resume'),
  };

  showSaveStatus('Saving…');

  try {
    const res  = await fetch('/api/save-profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.ok) {
      showSaveStatus('Saved');
      showToast('Profile saved');
      showViewJobsBtn();
    } else {
      showSaveStatus('Error: ' + (data.error || 'unknown'), true);
    }
  } catch {
    showSaveStatus('Network error', true);
  }
});

// ── Helpers ───────────────────────────────────────────────────────────────

function lines(str) {
  return (str || '').split('\n').map(s => s.trim()).filter(Boolean);
}

function showSaveStatus(msg, isError) {
  const el = document.getElementById('saveStatus');
  el.textContent = msg;
  el.className = 'save-status' + (isError ? ' status-error' : ' status-ok');
}

function showToast(msg, isError) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast' + (isError ? ' toast-error' : '');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.add('hidden'), 2500);
}

function showViewJobsBtn() {
  const btn = document.getElementById('viewJobsBtn');
  if (btn) btn.style.display = '';
}
