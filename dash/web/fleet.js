/* Orbit home lab: existing detailed gauges and controls still belong to the Pi. */
(() => {
  const target = document.getElementById('fleetMachines');
  if (!target) return;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c =>
    ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const bytes = value => {
    const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']; let n = Number(value) || 0, i = 0;
    while (n >= 1024 && i < 4) { n /= 1024; i++; }
    return `${n.toFixed(i > 1 ? 1 : 0)} ${units[i]}`;
  };
  const percent = value => Math.max(0, Math.min(100, Number(value) || 0));
  const bar = (label, value, detail) => `<div class="fleet-meter"><div><span>${escape(label)}</span><b>${Math.round(percent(value))}%</b></div><progress max="100" value="${percent(value)}" aria-label="${escape(label)}"></progress><small>${escape(detail)}</small></div>`;
  function card(machine) {
    const d = machine.metrics || {}, mem = d.mem || {};
    const online = machine.online === true;
    const stamp = machine.lastSuccess ? new Date(machine.lastSuccess * 1000).toLocaleTimeString() : 'No sample yet';
    const used = Math.max(0, (mem.total || 0) - (mem.avail || 0));
    const heading = `<div class="fleet-heading"><h3>${escape(machine.label)}</h3><span class="fleet-state ${online ? 'up' : 'down'}">${online ? 'ONLINE' : escape(machine.status || 'OFFLINE')}</span></div><p class="fleet-role">${escape(machine.role)}</p>`;
    if (!online) return `<article class="fleet-card">${heading}<p class="note">No current metrics. Last successful sample: ${escape(stamp)}.</p></article>`;
    const disks = (d.disks || []).map(disk => {
      if (disk.mounted === false) return `<div class="fleet-missing">${escape(disk.label || disk.mount)} · NOT MOUNTED</div>`;
      const total = disk.total || 0, free = disk.free || 0;
      return bar(disk.label || disk.mount, total ? (total-free)/total*100 : 0, `${bytes(free)} free · ${disk.mount}`);
    }).join('');
    const health = d.driveHealth;
    const smart = !health ? '' : !health.drives?.length ? '<p class="note">Drive health setup pending.</p>' : `<div class="fleet-smart"><h4>PHYSICAL DRIVE HEALTH</h4>${health.drives.map(drive => {
      const state = health.stale ? 'stale' : drive.status;
      const stateLabel = {passed:'SMART PASSED',attention:'REVIEW',failed:'FAILED',unavailable:'UNAVAILABLE',missing:'MISSING',stale:'STALE'}[state] || 'UNKNOWN';
      const details = [drive.temperature == null ? null : `${drive.temperature}°C`,drive.powerOnHours == null ? null : `${Number(drive.powerOnHours).toLocaleString()} power-on hours`].filter(Boolean).join(' · ');
      const errors = Object.entries(drive.errors || {}).map(([key,value]) => `${key}: ${value}`).join(' · ');
      return `<div class="fleet-drive"><div class="fleet-heading"><b>${escape(drive.label)}</b><span class="fleet-state ${state === 'passed' ? 'up' : 'down'}">${stateLabel}</span></div><small>${escape(drive.model || drive.device || '')}</small>${details ? `<p>${escape(details)}</p>` : ''}${errors ? `<p>${escape(errors)}</p>` : ''}${drive.message ? `<p>${escape(drive.message)}</p>` : ''}</div>`;
    }).join('')}<small>SMART checked ${escape(new Date(health.ts*1000).toLocaleTimeString())}. A passing check cannot guarantee future reliability.</small></div>`;
    const backup = !d.backup ? '' : `<div class="fleet-foot">Local backup: ${escape(d.backup.configured ? d.backup.status : 'not configured')}${d.backup.lastSuccess ? ` · last success ${escape(new Date(d.backup.lastSuccess*1000).toLocaleString())}` : ''}</div>`;
    return `<article class="fleet-card">${heading}<div class="fleet-summary"><span>${d.temp == null ? 'Temperature unavailable' : `${Number(d.temp).toFixed(1)}°C`}</span><span>Up ${Math.floor((d.uptime || 0)/3600)}h</span></div>${bar('CPU', d.cpu, `${(d.cores || []).length} cores`)}${bar('RAM', mem.total ? used/mem.total*100 : 0, `${bytes(used)} / ${bytes(mem.total)}`)}${disks}${smart}${backup}<div class="fleet-foot">Updated ${escape(stamp)}</div></article>`;
  }
  let pending = false;
  async function refresh() {
    if (pending) return;
    pending = true;
    try {
      const response = await fetch('api/fleet', {cache: 'no-store'});
      if (!response.ok) throw new Error('Unavailable');
      const data = await response.json();
      if (!Array.isArray(data.machines)) throw new Error('Invalid response');
      target.innerHTML = data.machines.map(card).join('');
      document.dispatchEvent(new CustomEvent('orbit-fleet', {detail: data}));
      document.getElementById('fleetStatus').textContent = `${data.machines.filter(m => m.online).length} / ${data.machines.length} online`;
    } catch {
      document.getElementById('fleetStatus').textContent = 'Connection lost';
      target.innerHTML = '<div class="note">Home lab metrics are unavailable. Reconnecting…</div>';
      document.dispatchEvent(new CustomEvent('orbit-fleet', {detail: {machines: []}}));
    } finally { pending = false; }
  }
  refresh();
  setInterval(() => { if (!document.hidden) refresh(); }, 3000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
})();
