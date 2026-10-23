// KD240 TSN Sync — Frontend Logic & Real-time Charting

document.addEventListener('DOMContentLoaded', () => {
  // DOM Elements
  const badgeMode = document.getElementById('badge-mode');
  const badgeStatus = document.getElementById('badge-status');
  const statusText = document.getElementById('status-text');
  const faultBanner = document.getElementById('fault-banner');
  const faultText = document.getElementById('fault-text');
  const btnBannerClear = document.getElementById('btn-banner-clear');

  const m1RpmSet = document.getElementById('m1-rpm-set');
  const m1Speed = document.getElementById('m1-speed');
  const m1Theta = document.getElementById('m1-theta');
  const m1Turns = document.getElementById('m1-turns');
  const m1ThetaTotal = document.getElementById('m1-theta-total');

  const m2Torque = document.getElementById('m2-torque');
  const m2Speed = document.getElementById('m2-speed');
  const m2Theta = document.getElementById('m2-theta');
  const m2Turns = document.getElementById('m2-turns');
  const m2ThetaTotal = document.getElementById('m2-theta-total');

  const syncError = document.getElementById('sync-error');
  const meterFillBar = document.getElementById('meter-fill-bar');
  const meterNeedle = document.getElementById('meter-needle');
  const meterBadge = document.getElementById('meter-badge');
  const syncSeq = document.getElementById('sync-seq');
  const syncLat = document.getElementById('sync-lat');
  const syncLatUs = document.getElementById('sync-lat-us');
  const syncJitter = document.getElementById('sync-jitter');

  // Telemetry panel elements (may not exist if section not yet rendered)
  const teleLatUs = document.getElementById('tele-lat-us');
  const teleLatMs = document.getElementById('tele-lat-ms');
  const teleJitterUs = document.getElementById('tele-jitter-us');
  const packetTbody = document.getElementById('packet-log-tbody');

  const legendM1Val = document.getElementById('legend-m1-val');
  const legendM2Val = document.getElementById('legend-m2-val');
  const legendErrVal = document.getElementById('legend-err-val');

  const speedSlider = document.getElementById('speed-slider');
  const speedInput = document.getElementById('speed-input');
  const btnApplySpeed = document.getElementById('btn-apply-speed');
  const btnEstop = document.getElementById('btn-estop');
  const btnClearFault = document.getElementById('btn-clear-fault');
  const presetButtons = document.querySelectorAll('.btn-preset');

  // Log pause toggle
  let logPaused = false;
  const btnToggleLog = document.getElementById('btn-toggle-log');
  const logToggleIcon = document.getElementById('log-toggle-icon');
  const logToggleText = document.getElementById('log-toggle-text');
  if (btnToggleLog) {
    btnToggleLog.addEventListener('click', () => {
      logPaused = !logPaused;
      if (logToggleIcon) {
        logToggleIcon.innerHTML = logPaused
          ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>'
          : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg>';
      }
      logToggleText.textContent = logPaused ? 'Pokračovať v logu' : 'Pozastaviť log';
    });
  }

  // Canvas Setup
  const canvas = document.getElementById('liveChart');
  const ctx = canvas.getContext('2d');
  const MAX_HISTORY = 120; // ~12 seconds of history at 10 Hz
  const history = {
    m1: [],
    m2: [],
    err: [],
  };

  // Synchronize inputs
  speedSlider.addEventListener('input', (e) => {
    speedInput.value = e.target.value;
  });

  speedInput.addEventListener('input', (e) => {
    speedSlider.value = e.target.value;
  });

  // Presets
  presetButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      const rpm = parseFloat(btn.getAttribute('data-rpm'));
      speedSlider.value = rpm;
      speedInput.value = rpm;
      setSpeed(rpm);
    });
  });

  // Apply Speed
  btnApplySpeed.addEventListener('click', () => {
    const rpm = parseFloat(speedInput.value);
    setSpeed(rpm);
  });

  // Emergency Stop
  btnEstop.addEventListener('click', () => {
    speedSlider.value = 0;
    speedInput.value = 0;
    fetch('/api/stop', { method: 'POST' });
  });

  // Clear Faults
  const handleClearFault = () => {
    speedSlider.value = 0;
    speedInput.value = 0;
    fetch('/api/clear_fault', { method: 'POST' });
  };
  btnClearFault.addEventListener('click', handleClearFault);
  btnBannerClear.addEventListener('click', handleClearFault);

  // Curve Visibility Toggles
  const visibleSeries = {
    m1: true,
    m2: true,
    err: true,
  };
  const toggleM1 = document.getElementById('toggle-m1');
  const toggleM2 = document.getElementById('toggle-m2');
  const toggleErr = document.getElementById('toggle-err');

  function bindToggle(btn, key) {
    if (!btn) return;
    btn.addEventListener('click', () => {
      visibleSeries[key] = !visibleSeries[key];
      btn.classList.toggle('inactive', !visibleSeries[key]);
      drawChart();
    });
  }
  bindToggle(toggleM1, 'm1');
  bindToggle(toggleM2, 'm2');
  bindToggle(toggleErr, 'err');

  // Real-time Tuning Elements
  const tuneKpSlider = document.getElementById('tune-kp-slider');
  const tuneKpInput = document.getElementById('tune-kp');
  const tuneKdSlider = document.getElementById('tune-kd-slider');
  const tuneKdInput = document.getElementById('tune-kd');
  const tuneKiSlider = document.getElementById('tune-ki-slider');
  const tuneKiInput = document.getElementById('tune-ki');
  const tuneLimitSlider = document.getElementById('tune-limit-slider');
  const tuneLimitInput = document.getElementById('tune-limit');
  const tuneSlewSlider = document.getElementById('tune-slew-slider');
  const tuneSlewInput = document.getElementById('tune-slew');
  const tuneMaxerrSlider = document.getElementById('tune-maxerr-slider');
  const tuneMaxerrInput = document.getElementById('tune-maxerr');
  const btnApplyTuning = document.getElementById('btn-apply-tuning');
  const btnResetTuning = document.getElementById('btn-reset-tuning');
  const tuningStatusBadge = document.getElementById('tuning-status-badge');

  const presetSimTune = document.getElementById('preset-sim-tune');
  const presetHwTune = document.getElementById('preset-hw-tune');
  const presetStrictTune = document.getElementById('preset-strict-tune');

  let isTuningDirty = false;
  let tuningInitialized = false;

  function syncPair(slider, input, stepDecimals = 3) {
    if (!slider || !input) return;
    slider.addEventListener('input', (e) => {
      input.value = parseFloat(e.target.value).toFixed(stepDecimals);
      isTuningDirty = true;
    });
    input.addEventListener('input', (e) => {
      slider.value = e.target.value;
      isTuningDirty = true;
    });
  }

  syncPair(tuneKpSlider, tuneKpInput, 3);
  syncPair(tuneKdSlider, tuneKdInput, 4);
  syncPair(tuneKiSlider, tuneKiInput, 4);
  syncPair(tuneLimitSlider, tuneLimitInput, 2);
  syncPair(tuneSlewSlider, tuneSlewInput, 0);
  syncPair(tuneMaxerrSlider, tuneMaxerrInput, 0);

  function applyTuningPreset(kp, kd, ki, limit, slew, maxErr) {
    if (tuneKpSlider) { tuneKpSlider.value = kp; tuneKpInput.value = kp.toFixed(3); }
    if (tuneKdSlider) { tuneKdSlider.value = kd; tuneKdInput.value = kd.toFixed(4); }
    if (tuneKiSlider) { tuneKiSlider.value = ki; tuneKiInput.value = ki.toFixed(4); }
    if (tuneLimitSlider) { tuneLimitSlider.value = limit; tuneLimitInput.value = limit.toFixed(2); }
    if (tuneSlewSlider) { tuneSlewSlider.value = slew; tuneSlewInput.value = slew.toFixed(0); }
    if (tuneMaxerrSlider) { tuneMaxerrSlider.value = maxErr; tuneMaxerrInput.value = maxErr.toFixed(0); }
    isTuningDirty = true;
    sendTuning();
  }

  if (presetSimTune) {
    presetSimTune.addEventListener('click', () => applyTuningPreset(0.080, 0.0020, 0.0020, 1.5, 500, 60));
  }
  if (presetHwTune) {
    presetHwTune.addEventListener('click', () => applyTuningPreset(0.011, 0.00045, 0.0000, 0.1, 20, 60));
  }
  if (presetStrictTune) {
    presetStrictTune.addEventListener('click', () => applyTuningPreset(0.120, 0.0030, 0.0050, 2.0, 800, 30));
  }
  if (btnResetTuning) {
    btnResetTuning.addEventListener('click', () => applyTuningPreset(0.080, 0.0020, 0.0020, 1.5, 500, 60));
  }

  async function sendTuning() {
    // parseFloat(..) || default by pretlacilo legitimnu hodnotu 0 (napr. Ki = 0)
    const num = (el, fallback) => {
      const v = parseFloat(el.value);
      return Number.isFinite(v) ? v : fallback;
    };
    const payload = {
      kp: num(tuneKpInput, 0.08),
      kd: num(tuneKdInput, 0.002),
      ki: num(tuneKiInput, 0.0),
      torque_limit_a: num(tuneLimitInput, 1.5),
      slew_a_s: num(tuneSlewInput, 500.0),
      max_error_deg: num(tuneMaxerrInput, 60.0),
    };
    try {
      const res = await fetch('/api/tune', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        isTuningDirty = false;
        if (btnApplyTuning) {
          const original = btnApplyTuning.innerHTML;
          btnApplyTuning.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg> <span>Nastavené</span>';
          btnApplyTuning.style.background = '#059669';
          setTimeout(() => {
            btnApplyTuning.innerHTML = original;
            btnApplyTuning.style.background = '';
          }, 1500);
        }
        if (tuningStatusBadge) {
          tuningStatusBadge.textContent = `Kp=${payload.kp} | Kd=${payload.kd} | Imax=${payload.torque_limit_a}A | emax=${payload.max_error_deg}°`;
        }
      }
    } catch (e) {
      console.error('Chyba zapisu parametrov:', e);
    }
  }

  if (btnApplyTuning) {
    btnApplyTuning.addEventListener('click', sendTuning);
  }

  function setSpeed(rpm) {
    if (!Number.isFinite(rpm)) return;
    fetch('/api/speed', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rpm }),
    });
  }

  // Real-time Polling Loop
  async function pollStatus() {
    try {
      const res = await fetch('/api/status');
      if (!res.ok) throw new Error('Network error');
      const data = await res.json();
      updateUI(data);
    } catch (err) {
      statusText.textContent = 'ODPOJENÉ';
      badgeStatus.style.background = 'rgba(239, 68, 68, 0.2)';
      badgeStatus.style.borderColor = 'rgba(239, 68, 68, 0.4)';
    } finally {
      setTimeout(pollStatus, 100); // 10 Hz refresh
    }
  }

  function updateUI(data) {
    // Mode badge
    badgeMode.textContent = `REŽIM: ${data.mode.toUpperCase()}`;

    // State badge
    const state = data.state || 'IDLE';
    statusText.textContent = state;

    if (state === 'RUN') {
      badgeStatus.style.background = 'rgba(16, 185, 129, 0.15)';
      badgeStatus.style.borderColor = 'rgba(16, 185, 129, 0.3)';
      badgeStatus.style.color = '#6ee7b7';
    } else if (state === 'WAIT') {
      badgeStatus.style.background = 'rgba(245, 158, 11, 0.15)';
      badgeStatus.style.borderColor = 'rgba(245, 158, 11, 0.3)';
      badgeStatus.style.color = '#fcd34d';
    } else if (state === 'FAULT') {
      badgeStatus.style.background = 'rgba(239, 68, 68, 0.15)';
      badgeStatus.style.borderColor = 'rgba(239, 68, 68, 0.3)';
      badgeStatus.style.color = '#fca5a5';
    }

    // Fault banner
    if (data.fault) {
      faultBanner.style.display = 'flex';
      faultText.textContent = data.fault;
    } else {
      faultBanner.style.display = 'none';
    }

    // Motor 1 metrics — zobraz normalizovany uhol (0-360°) nie kumulativny
    m1RpmSet.textContent = Math.round(data.motor1.rpm_set);
    m1Speed.textContent = data.motor1.speed_rpm.toFixed(1);
    const m1Mod = data.motor1.theta_mod != null ? data.motor1.theta_mod : (((data.motor1.theta_deg % 360) + 360) % 360);
    m1Theta.textContent = m1Mod.toFixed(1);
    if (m1Turns) m1Turns.textContent = (data.motor1.turns != null ? data.motor1.turns.toFixed(1) : '0.0');
    if (m1ThetaTotal) m1ThetaTotal.textContent = Math.round(Math.abs(data.motor1.theta_deg || 0));

    // Motor 2 metrics — zobraz normalizovany uhol (0-360°)
    m2Torque.textContent = (data.motor2.output_a || 0).toFixed(3);
    m2Speed.textContent = data.motor2.speed_rpm.toFixed(1);
    const m2Mod = data.motor2.theta_mod != null ? data.motor2.theta_mod : (((data.motor2.theta_deg % 360) + 360) % 360);
    m2Theta.textContent = m2Mod.toFixed(1);
    if (m2Turns) m2Turns.textContent = (data.motor2.turns != null ? data.motor2.turns.toFixed(1) : '0.0');
    if (m2ThetaTotal) m2ThetaTotal.textContent = Math.round(Math.abs(data.motor2.theta_deg || 0));

    // Sync metrics & Center-zero meter
    const err = data.sync.error_deg || 0;
    const absErr = Math.abs(err);
    // Clamp display value to ±15° range for the meter; show real value in numeric
    const displayErr = Math.max(-15, Math.min(15, err));
    syncError.textContent = (err >= 0 ? '+' : '') + err.toFixed(2) + '°';

    // Position needle on scale [-15° .. +15°], where 0° = 50%
    const needlePos = Math.max(0, Math.min(100, 50 + (displayErr / 15.0) * 50));
    meterNeedle.style.left = `${needlePos}%`;

    // Fill bar expands outward from center (50%)
    if (displayErr >= 0) {
      const span = Math.min(50, (displayErr / 15.0) * 50);
      meterFillBar.style.left = '50%';
      meterFillBar.style.width = `${span}%`;
    } else {
      const span = Math.min(50, (-displayErr / 15.0) * 50);
      meterFillBar.style.left = `${50 - span}%`;
      meterFillBar.style.width = `${span}%`;
    }

    // Visual feedback according to deviation threshold
    if (absErr <= 2.0) {
      syncError.style.color = '#10b981';
      meterNeedle.style.background = '#10b981';
      meterNeedle.style.color = '#10b981';
      meterNeedle.style.boxShadow = '0 0 10px #10b981, 0 0 4px #ffffff';
      meterFillBar.style.background = 'rgba(16, 185, 129, 0.75)';
      meterFillBar.style.boxShadow = '0 0 8px rgba(16, 185, 129, 0.5)';
      meterBadge.textContent = 'V TOLERANCII (±2.0°)';
      meterBadge.style.background = 'rgba(16, 185, 129, 0.15)';
      meterBadge.style.borderColor = 'rgba(16, 185, 129, 0.35)';
      meterBadge.style.color = '#6ee7b7';
    } else if (absErr <= 6.0) {
      syncError.style.color = '#f59e0b';
      meterNeedle.style.background = '#f59e0b';
      meterNeedle.style.color = '#f59e0b';
      meterNeedle.style.boxShadow = '0 0 10px #f59e0b, 0 0 4px #ffffff';
      meterFillBar.style.background = 'rgba(245, 158, 11, 0.8)';
      meterFillBar.style.boxShadow = '0 0 8px rgba(245, 158, 11, 0.5)';
      meterBadge.textContent = 'ZVÝŠENÁ ODCHÝLKA';
      meterBadge.style.background = 'rgba(245, 158, 11, 0.15)';
      meterBadge.style.borderColor = 'rgba(245, 158, 11, 0.35)';
      meterBadge.style.color = '#fcd34d';
    } else {
      syncError.style.color = '#ef4444';
      meterNeedle.style.background = '#ef4444';
      meterNeedle.style.color = '#ef4444';
      meterNeedle.style.boxShadow = '0 0 10px #ef4444, 0 0 4px #ffffff';
      meterFillBar.style.background = 'rgba(239, 68, 68, 0.85)';
      meterFillBar.style.boxShadow = '0 0 8px rgba(239, 68, 68, 0.5)';
      meterBadge.textContent = 'PREKROČENÁ CHYBA';
      meterBadge.style.background = 'rgba(239, 68, 68, 0.15)';
      meterBadge.style.borderColor = 'rgba(239, 68, 68, 0.35)';
      meterBadge.style.color = '#fca5a5';
    }

    // Sync tuning values if not dirty
    if (data.tuning && (!tuningInitialized || !isTuningDirty)) {
      const t = data.tuning;
      if (tuneKpSlider && document.activeElement !== tuneKpInput && document.activeElement !== tuneKpSlider) {
        tuneKpSlider.value = t.kp;
        tuneKpInput.value = (t.kp != null ? t.kp.toFixed(3) : '0.080');
      }
      if (tuneKdSlider && document.activeElement !== tuneKdInput && document.activeElement !== tuneKdSlider) {
        tuneKdSlider.value = t.kd;
        tuneKdInput.value = (t.kd != null ? t.kd.toFixed(4) : '0.0020');
      }
      if (tuneKiSlider && document.activeElement !== tuneKiInput && document.activeElement !== tuneKiSlider) {
        tuneKiSlider.value = t.ki;
        tuneKiInput.value = (t.ki != null ? t.ki.toFixed(4) : '0.0000');
      }
      if (tuneLimitSlider && document.activeElement !== tuneLimitInput && document.activeElement !== tuneLimitSlider) {
        tuneLimitSlider.value = t.torque_limit_a;
        tuneLimitInput.value = (t.torque_limit_a != null ? t.torque_limit_a.toFixed(2) : '1.50');
      }
      if (tuneSlewSlider && document.activeElement !== tuneSlewInput && document.activeElement !== tuneSlewSlider) {
        tuneSlewSlider.value = t.slew_a_s;
        tuneSlewInput.value = (t.slew_a_s != null ? t.slew_a_s.toFixed(0) : '500');
      }
      if (tuneMaxerrSlider && document.activeElement !== tuneMaxerrInput && document.activeElement !== tuneMaxerrSlider) {
        tuneMaxerrSlider.value = t.max_error_deg;
        tuneMaxerrInput.value = (t.max_error_deg != null ? t.max_error_deg.toFixed(0) : '60');
      }
      if (tuningStatusBadge) {
        tuningStatusBadge.textContent = `Aktívne: Kp=${t.kp} | Kd=${t.kd} | Limit=${t.torque_limit_a}A | emax=${t.max_error_deg}°`;
      }
      tuningInitialized = true;
    }

    syncSeq.textContent = data.sync.seq || 0;
    const latMs = data.sync.lat_ms || 0;
    const latUs = data.sync.lat_us || 0;
    const jitterUs = data.sync.jitter_us || 0;
    if (syncLat) syncLat.textContent = latMs.toFixed(3);
    if (syncLatUs) syncLatUs.textContent = Math.round(latUs);
    if (syncJitter) syncJitter.textContent = `±${jitterUs.toFixed(1)}`;

    // Telemetry KPI panel
    if (teleLatUs) teleLatUs.textContent = latUs.toFixed(1);
    if (teleLatMs) teleLatMs.textContent = latMs.toFixed(3);
    if (teleJitterUs) teleJitterUs.textContent = `±${jitterUs.toFixed(1)}`;

    // Packet timing table (last 25 packets, newest first)
    if (packetTbody && !logPaused && data.recent_packets && data.recent_packets.length) {
      const rows = [...data.recent_packets].reverse();
      packetTbody.innerHTML = rows.map(p => {
        const latClass = p.lat_us < 500 ? 'badge-lat-fast' : p.lat_us < 2000 ? 'badge-lat-med' : 'badge-lat-slow';
        const stBadge = p.status === 'OK' ? 'badge-status-ok' : 'badge-status-warn';
        const errStr = (p.err_deg >= 0 ? '+' : '') + p.err_deg.toFixed(2) + '°';
        return `<tr>
          <td>${p.seq}</td>
          <td>${p.tx_time}</td>
          <td>${p.rx_time}</td>
          <td><span class="${latClass}">${p.lat_us.toFixed(1)} µs</span> <span style="color:#475569">(${p.lat_ms.toFixed(3)} ms)</span></td>
          <td>${p.theta_m1.toFixed(1)}°</td>
          <td>${p.theta_m2.toFixed(1)}°</td>
          <td>${errStr}</td>
          <td>${p.speed_rpm.toFixed(1)}</td>
          <td><span class="${stBadge}">${p.status}</span></td>
        </tr>`;
      }).join('');
    }

    // Live Legend values — use 0-360° normalized angle
    legendM1Val.textContent = `${m1Mod.toFixed(1)}°`;
    legendM2Val.textContent = `${m2Mod.toFixed(1)}°`;
    legendErrVal.textContent = `${(err >= 0 ? '+' : '')}${err.toFixed(2)}°`;

    // History ring buffer — use theta_mod (0-360°) directly from server
    const m1Norm = m1Mod;
    const m2Norm = m2Mod;
    history.m1.push(m1Norm);
    history.m2.push(m2Norm);
    history.err.push(err);

    if (history.m1.length > MAX_HISTORY) {
      history.m1.shift();
      history.m2.shift();
      history.err.shift();
    }

    drawChart();
  }

  function drawChart() {
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;

    const dpr = window.devicePixelRatio || 1;
    const targetW = Math.floor(rect.width * dpr);
    const targetH = Math.floor(rect.height * dpr);

    if (canvas.width !== targetW || canvas.height !== targetH) {
      canvas.width = targetW;
      canvas.height = targetH;
    }

    ctx.save();
    ctx.scale(dpr, dpr);

    const w = rect.width;
    const h = rect.height;

    // Correctly clear entire visible canvas
    ctx.clearRect(0, 0, w, h);

    // Padding for industrial axes
    const padLeft = 44;   // for 0..360° angle labels
    const padRight = 44;  // for -10..+10° error labels
    const padTop = 22;
    const padBottom = 24;
    const plotW = w - padLeft - padRight;
    const plotH = h - padTop - padBottom;

    if (plotW <= 10 || plotH <= 10) {
      ctx.restore();
      return;
    }

    // Grid Y steps: 4 intervals (5 lines: 360°, 270°, 180°, 90°, 0°)
    const angleLabels = ['360°', '270°', '180°', '90°', '0°'];
    const errorLabels = ['+10°', '+5°', '0°', '-5°', '-10°'];

    // Draw ±2° error tolerance zone around center line (180° / 0° error)
    // 2° / 10° = 20% of half height (10% of plotH)
    const yCenter = padTop + plotH * 0.5;
    const tolBandH = (2.0 / 10.0) * (plotH * 0.5);

    ctx.fillStyle = 'rgba(16, 185, 129, 0.08)';
    ctx.fillRect(padLeft, yCenter - tolBandH, plotW, tolBandH * 2);

    // Tolerance zone borders
    ctx.strokeStyle = 'rgba(16, 185, 129, 0.25)';
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(padLeft, yCenter - tolBandH);
    ctx.lineTo(padLeft + plotW, yCenter - tolBandH);
    ctx.moveTo(padLeft, yCenter + tolBandH);
    ctx.lineTo(padLeft + plotW, yCenter + tolBandH);
    ctx.stroke();
    ctx.setLineDash([]);

    // Draw horizontal grid lines & labels
    ctx.font = '10px "Inter", -apple-system, sans-serif';
    ctx.textBaseline = 'middle';

    for (let i = 0; i <= 4; i++) {
      const y = padTop + (plotH / 4) * i;

      // Line
      ctx.beginPath();
      if (i === 2) {
        // Center line (Error 0.00°)
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
        ctx.lineWidth = 1.2;
      } else {
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.06)';
        ctx.lineWidth = 1;
      }
      ctx.moveTo(padLeft, y);
      ctx.lineTo(padLeft + plotW, y);
      ctx.stroke();

      // Left label (Angle)
      ctx.fillStyle = '#64748b';
      ctx.textAlign = 'right';
      ctx.fillText(angleLabels[i], padLeft - 8, y);

      // Right label (Error)
      ctx.fillStyle = (i === 2) ? '#10b981' : '#f59e0b';
      ctx.textAlign = 'left';
      ctx.fillText(errorLabels[i], padLeft + plotW + 8, y);
    }

    // Axis titles
    ctx.font = '9px "Inter", -apple-system, sans-serif';
    ctx.fillStyle = '#475569';
    ctx.textAlign = 'left';
    ctx.fillText('UHOL', 4, padTop - 10);
    ctx.textAlign = 'right';
    ctx.fillText('ODCHÝLKA', w - 4, padTop - 10);

    // Bottom time ticks
    ctx.fillStyle = '#475569';
    ctx.textAlign = 'left';
    ctx.fillText('-12 s', padLeft, h - 8);
    ctx.textAlign = 'center';
    ctx.fillText('-6 s', padLeft + plotW * 0.5, h - 8);
    ctx.textAlign = 'right';
    ctx.fillText('TERAZ', padLeft + plotW, h - 8);

    const n = history.m1.length;
    if (n < 2) {
      ctx.restore();
      return;
    }

    const dx = plotW / (MAX_HISTORY - 1);
    const startX = padLeft + (MAX_HISTORY - n) * dx;

    // Helper: Plot continuous line (0-360° with discontinuous wrap detection)
    function plotAngleSeries(arr, color, lineW) {
      ctx.strokeStyle = color;
      ctx.lineWidth = lineW || 2;
      // Shadow glow for visibility
      ctx.shadowBlur = 4;
      ctx.shadowColor = color;
      ctx.beginPath();
      let inPath = false;
      let lastDeg = null;

      for (let i = 0; i < n; i++) {
        const x = startX + i * dx;
        const deg = arr[i];
        // Map 0..360 -> plotH..0 in the plot area
        const y = padTop + plotH - (deg / 360.0) * plotH;

        // Detect wrap-around: if consecutive sample jumped more than 270°,
        // it's a 0/360 wrap — start a new sub-path instead of drawing a vertical spike
        const isWrap = lastDeg !== null && Math.abs(deg - lastDeg) > 270;

        if (!inPath || isWrap) {
          ctx.moveTo(x, y);
          inPath = true;
        } else {
          ctx.lineTo(x, y);
        }
        lastDeg = deg;
      }
      ctx.stroke();
      ctx.shadowBlur = 0;
      ctx.shadowColor = 'transparent';
    }

    // Helper: Plot Error series on [-10° .. +10°] scale around yCenter
    function plotErrorSeries(arr, color) {
      ctx.strokeStyle = color;
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      for (let i = 0; i < n; i++) {
        const x = startX + i * dx;
        const e = arr[i];
        // Clamped to [-10 .. +10] for clean visualization
        const clampedE = Math.max(-10, Math.min(10, e));
        const y = yCenter - (clampedE / 10.0) * (plotH * 0.5);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }

    // Render Motor 1 Angle (Cyan halo) if visible
    if (visibleSeries.m1) {
      plotAngleSeries(history.m1, '#00f0ff', 3.5);
    }

    // Render Motor 2 Angle (Emerald core) if visible
    if (visibleSeries.m2) {
      plotAngleSeries(history.m2, '#10b981', 1.8);
    }

    // Render Tracking Error (Amber) if visible
    if (visibleSeries.err) {
      plotErrorSeries(history.err, '#f59e0b');
    }

    ctx.restore();
  }

  // Handle window resizing cleanly
  window.addEventListener('resize', () => {
    drawChart();
  });

  // Start polling
  pollStatus();
});
