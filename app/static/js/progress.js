(() => {
  const card = document.querySelector('[data-progress-url]');
  if (!card) return;
  const status = document.querySelector('#progress-status');
  const error = document.querySelector('#progress-error');
  const poll = async () => {
    try {
      const response = await fetch(card.dataset.progressUrl, { headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error('status request failed');
      const data = await response.json();
      status.textContent = data.label;
      if (data.result_url) { window.location.assign(data.result_url); return; }
      if (data.status === 'FAILED') { error.hidden = false; return; }
    } catch (_) { error.hidden = false; }
    window.setTimeout(poll, 2000);
  };
  window.setTimeout(poll, 1200);
})();
