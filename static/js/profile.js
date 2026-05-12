// Resume upload
const uploadZone = document.getElementById('uploadZone');
const fileInput  = document.getElementById('resumeFile');
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
  uploadStatus.textContent = 'Parsing resume…';

  const fd = new FormData();
  fd.append('resume', file);

  fetch('/api/upload-resume', { method: 'POST', body: fd })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        uploadStatus.textContent = 'Resume parsed — fields updated below. Review and save.';
        uploadStatus.classList.add('status-ok');
        fillForm(data.extracted);
        if (data.extracted.base_resume) {
          document.getElementById('baseResumeText').value = data.extracted.base_resume;
        }
        showToast('Resume parsed successfully');
      } else {
        uploadStatus.textContent = 'Parse failed: ' + (data.error || 'unknown error');
        uploadStatus.classList.add('status-error');
      }
    })
    .catch(() => {
      uploadStatus.textContent = 'Network error';
      uploadStatus.classList.add('status-error');
    });
}

function fillForm(data) {
  const set = (name, val) => {
    const el = document.querySelector(`[name="${name}"]`);
    if (el && val !== undefined && val !== null && val !== '') el.value = val;
  };
  set('name', data.name);
  set('experience_years', data.experience_years);
  if (data.skills?.length) set('skills', data.skills.join('\n'));
  if (data.target_titles?.length) set('target_titles', data.target_titles.join('\n'));
}

// Profile form save
document.getElementById('profileForm').addEventListener('submit', async e => {
  e.preventDefault();
  const form = e.target;
  const fd = new FormData(form);
  const saveStatus = document.getElementById('saveStatus');

  const payload = {
    name:               fd.get('name'),
    experience_years:   parseInt(fd.get('experience_years')) || 0,
    role_type:          fd.get('role_type'),
    target_titles:      fd.get('target_titles').split('\n').map(s => s.trim()).filter(Boolean),
    skills:             fd.get('skills').split('\n').map(s => s.trim()).filter(Boolean),
    location: {
      preferred: fd.get('location_preferred').split('\n').map(s => s.trim()).filter(Boolean),
      hard_no:   fd.get('location_hard_no').split('\n').map(s => s.trim()).filter(Boolean),
    },
    salary: {
      minimum: parseInt(fd.get('salary_minimum')) || 0,
      target:  parseInt(fd.get('salary_target'))  || 0,
    },
    industries: {
      preferred: fd.get('industries_preferred').split('\n').map(s => s.trim()).filter(Boolean),
      avoid:     fd.get('industries_avoid').split('\n').map(s => s.trim()).filter(Boolean),
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

  saveStatus.textContent = 'Saving…';
  saveStatus.className = 'save-status';

  try {
    const res = await fetch('/api/save-profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.ok) {
      saveStatus.textContent = 'Saved';
      saveStatus.className = 'save-status status-ok';
      showToast('Profile saved to config/profile.yaml');
    } else {
      saveStatus.textContent = 'Error: ' + (data.error || 'unknown');
      saveStatus.className = 'save-status status-error';
    }
  } catch {
    saveStatus.textContent = 'Network error';
    saveStatus.className = 'save-status status-error';
  }
});

function showToast(msg, isError) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast' + (isError ? ' toast-error' : '');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.add('hidden'), 2500);
}
