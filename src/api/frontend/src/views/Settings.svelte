<script>
  import { fetchSettings, saveSettings } from '../lib/api.js';
  import { onMount } from 'svelte';

  let activeTab = $state('filters');
  let saving = $state(false);
  let saveStatus = $state('');
  let loaded = $state(false);

  // Filters state
  let buckets = $state({ A: true, B: true, C: false, D: false, E: true });

  // Interpreter state
  let interpreter = $state({
    backend: 'anthropic',
    model: 'claude-sonnet-4-6',
    max_output_tokens: 2048,
    temperature: 0.3,
    tone: 'balanced',
    language: 'en',
  });

  // Delivery state
  let delivery = $state({
    require_approval: true,
    retry_max: 3,
    retry_delay_seconds: 5,
    rate_limit_per_second: 1,
  });

  const tabs = [
    { key: 'filters', label: 'Filters' },
    { key: 'interpreter', label: 'Interpreter' },
    { key: 'delivery', label: 'Delivery' },
  ];

  const toneOptions = [
    { value: 'calm', label: 'Calm', desc: 'Reassuring, gentle language' },
    { value: 'balanced', label: 'Balanced', desc: 'Friendly professional tone' },
    { value: 'direct', label: 'Direct', desc: 'Concise, action-oriented' },
  ];

  const backendOptions = ['anthropic', 'ollama'];
  const languageOptions = [
    { value: 'en', label: 'English' },
    { value: 'da', label: 'Danish' },
  ];

  onMount(async () => {
    try {
      const data = await fetchSettings();

      if (data.filters?.post_scan_filters?.bucket) {
        const activeBuckets = data.filters.post_scan_filters.bucket;
        buckets = {
          A: activeBuckets.includes('A'),
          B: activeBuckets.includes('B'),
          C: activeBuckets.includes('C'),
          D: activeBuckets.includes('D'),
          E: activeBuckets.includes('E'),
        };
      }

      if (data.interpreter) {
        interpreter = {
          backend: data.interpreter.backend ?? interpreter.backend,
          model: data.interpreter.model ?? interpreter.model,
          max_output_tokens: data.interpreter.max_output_tokens ?? interpreter.max_output_tokens,
          temperature: data.interpreter.temperature ?? interpreter.temperature,
          tone: data.interpreter.tone ?? interpreter.tone,
          language: data.interpreter.language ?? interpreter.language,
        };
      }

      if (data.delivery) {
        delivery = {
          require_approval: data.delivery.require_approval ?? delivery.require_approval,
          retry_max: data.delivery.retry_max ?? delivery.retry_max,
          retry_delay_seconds: data.delivery.retry_delay_seconds ?? delivery.retry_delay_seconds,
          rate_limit_per_second: data.delivery.rate_limit_per_second ?? delivery.rate_limit_per_second,
        };
      }
    } catch (err) {
      console.error('Settings fetch failed:', err);
    }
    loaded = true;
  });

  async function handleSave() {
    saving = true;
    saveStatus = '';

    try {
      if (activeTab === 'filters') {
        const activeBuckets = Object.entries(buckets)
          .filter(([, v]) => v)
          .map(([k]) => k);
        await saveSettings('filters', { post_scan_filters: { bucket: activeBuckets } });
      } else if (activeTab === 'interpreter') {
        await saveSettings('interpreter', { ...interpreter });
      } else if (activeTab === 'delivery') {
        await saveSettings('delivery', { ...delivery });
      }
      saveStatus = 'saved';
      setTimeout(() => { saveStatus = ''; }, 2000);
    } catch (err) {
      saveStatus = 'error';
      console.error('Save failed:', err);
    }
    saving = false;
  }

  function toggleBucket(key) {
    buckets[key] = !buckets[key];
  }
</script>

<div class="section-header" style="margin-top: 0;">
  <span class="section-title">Configuration</span>
  <button
    class="btn btn-primary"
    onclick={handleSave}
    disabled={saving}
  >
    {#if saveStatus === 'saved'}
      Saved!
    {:else if saving}
      Saving...
    {:else}
      Save Changes
    {/if}
  </button>
</div>

<div class="config-editor">
  <div class="config-tabs">
    {#each tabs as tab}
      <button
        class="config-tab"
        class:active={activeTab === tab.key}
        onclick={() => { activeTab = tab.key; }}
      >
        {tab.label}
      </button>
    {/each}
  </div>

  <div class="config-body">
    {#if activeTab === 'filters'}
      <div class="form-section">
        <div class="form-group-label">Bucket Filter</div>
        <div class="form-desc">Select which prospect buckets to include in pipeline output</div>
        <div class="checkbox-group">
          {#each Object.entries(buckets) as [key, checked]}
            <label class="checkbox-item">
              <input
                type="checkbox"
                checked={checked}
                onchange={() => toggleBucket(key)}
              />
              <span class="checkbox-visual"></span>
              <span class="checkbox-label">{key}</span>
            </label>
          {/each}
        </div>
      </div>

    {:else if activeTab === 'interpreter'}
      <div class="form-grid">
        <div class="form-group">
          <label class="form-label" for="interp-backend">Backend</label>
          <select id="interp-backend" class="form-input" bind:value={interpreter.backend}>
            {#each backendOptions as opt}
              <option value={opt}>{opt}</option>
            {/each}
          </select>
        </div>

        <div class="form-group">
          <label class="form-label" for="interp-model">Model</label>
          <input id="interp-model" class="form-input" type="text" bind:value={interpreter.model} />
        </div>

        <div class="form-group">
          <label class="form-label" for="interp-tokens">Max Tokens</label>
          <input id="interp-tokens" class="form-input" type="number" bind:value={interpreter.max_output_tokens} min="256" max="8192" step="256" />
        </div>

        <div class="form-group">
          <label class="form-label" for="interp-temp">Temperature</label>
          <div class="range-row">
            <input
              id="interp-temp"
              type="range"
              class="form-range"
              min="0"
              max="1"
              step="0.1"
              bind:value={interpreter.temperature}
            />
            <span class="range-value">{interpreter.temperature}</span>
          </div>
        </div>

        <div class="form-group">
          <label class="form-label" for="interp-tone">Tone</label>
          <select id="interp-tone" class="form-input" bind:value={interpreter.tone}>
            {#each toneOptions as opt}
              <option value={opt.value}>{opt.label}</option>
            {/each}
          </select>
          {#each toneOptions as opt}
            {#if opt.value === interpreter.tone}
              <div class="form-hint">{opt.desc}</div>
            {/if}
          {/each}
        </div>

        <div class="form-group">
          <label class="form-label" for="interp-lang">Language</label>
          <select id="interp-lang" class="form-input" bind:value={interpreter.language}>
            {#each languageOptions as opt}
              <option value={opt.value}>{opt.label}</option>
            {/each}
          </select>
        </div>
      </div>

    {:else if activeTab === 'delivery'}
      <div class="form-grid">
        <div class="form-group">
          <label class="form-label" for="del-approval">Require Approval</label>
          <div class="toggle-row">
            <button
              id="del-approval"
              class="toggle"
              class:active={delivery.require_approval}
              onclick={() => { delivery.require_approval = !delivery.require_approval; }}
              type="button"
              aria-label="Toggle require approval"
            >
              <span class="toggle-thumb"></span>
            </button>
            <span class="toggle-label">
              {delivery.require_approval ? 'Operator must approve before delivery' : 'Auto-deliver without approval'}
            </span>
          </div>
        </div>

        <div class="form-group">
          <label class="form-label" for="del-retries">Max Retries</label>
          <input id="del-retries" class="form-input" type="number" bind:value={delivery.retry_max} min="0" max="10" />
        </div>

        <div class="form-group">
          <label class="form-label" for="del-delay">Retry Delay (seconds)</label>
          <input id="del-delay" class="form-input" type="number" bind:value={delivery.retry_delay_seconds} min="1" max="300" />
        </div>

        <div class="form-group">
          <label class="form-label" for="del-rate">Rate Limit (per second)</label>
          <input id="del-rate" class="form-input" type="number" bind:value={delivery.rate_limit_per_second} min="1" max="30" />
        </div>
      </div>
    {/if}
  </div>
</div>

<style>
  button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .form-section {
    margin-bottom: 24px;
  }

  .form-group-label {
    font-size: 14px;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 4px;
  }

  .form-desc {
    font-size: 12px;
    color: var(--text-muted);
    margin-bottom: 12px;
  }

  .form-grid {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .form-group {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .form-label {
    font-size: 12px;
    color: var(--text-dim);
    font-weight: 500;
  }

  .form-input {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: var(--radius-sm);
    padding: 8px 12px;
    font-family: var(--sans);
    font-size: 13px;
    max-width: 400px;
    transition: border-color var(--transition);
  }

  .form-input:focus {
    outline: none;
    border-color: var(--gold);
  }

  .form-hint {
    font-size: 11px;
    color: var(--text-muted);
    font-style: italic;
  }

  /* Checkbox group */
  .checkbox-group {
    display: flex;
    gap: 12px;
  }

  .checkbox-item {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
  }

  .checkbox-item input[type="checkbox"] {
    display: none;
  }

  .checkbox-visual {
    width: 20px;
    height: 20px;
    border-radius: var(--radius-xs);
    border: 1px solid var(--border);
    background: var(--bg-surface);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all var(--transition);
  }

  .checkbox-item input:checked + .checkbox-visual {
    background: var(--gold);
    border-color: var(--gold);
  }

  .checkbox-item input:checked + .checkbox-visual::after {
    content: '';
    width: 6px;
    height: 10px;
    border: solid var(--bg-deep);
    border-width: 0 2px 2px 0;
    transform: rotate(45deg);
    margin-top: -2px;
  }

  .checkbox-label {
    font-family: var(--mono);
    font-size: 14px;
    font-weight: 600;
    color: var(--text);
  }

  /* Range slider */
  .range-row {
    display: flex;
    align-items: center;
    gap: 12px;
    max-width: 400px;
  }

  .form-range {
    flex: 1;
    -webkit-appearance: none;
    appearance: none;
    height: 4px;
    background: var(--bg-surface);
    border-radius: 2px;
    outline: none;
  }

  .form-range::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--gold);
    cursor: pointer;
    border: 2px solid var(--bg-deep);
  }

  .form-range::-moz-range-thumb {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--gold);
    cursor: pointer;
    border: 2px solid var(--bg-deep);
  }

  .range-value {
    font-family: var(--mono);
    font-size: 13px;
    font-weight: 600;
    color: var(--gold);
    min-width: 32px;
    text-align: right;
  }

  /* Toggle switch */
  .toggle-row {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .toggle {
    position: relative;
    width: 44px;
    height: 24px;
    border-radius: 12px;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    cursor: pointer;
    transition: all var(--transition);
    flex-shrink: 0;
    padding: 0;
  }

  .toggle.active {
    background: var(--gold);
    border-color: var(--gold);
  }

  .toggle-thumb {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: var(--text-dim);
    transition: all var(--transition);
  }

  .toggle.active .toggle-thumb {
    left: 22px;
    background: var(--bg-deep);
  }

  .toggle-label {
    font-size: 12px;
    color: var(--text-muted);
  }
</style>
