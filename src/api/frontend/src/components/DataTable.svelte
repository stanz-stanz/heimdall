<script>
  let { columns = [], rows = [], renderCell = null } = $props();
</script>

<div class="table-wrap">
  <table>
    <thead>
      <tr>
        {#each columns as col}
          <th>{col.label}</th>
        {/each}
      </tr>
    </thead>
    <tbody>
      {#each rows as row}
        <tr>
          {#each columns as col}
            <td class={col.class ?? (col.key === 'domain' ? 'domain' : '')}>
              {#if renderCell}
                {@html renderCell(row, col.key)}
              {:else}
                {row[col.key] ?? ''}
              {/if}
            </td>
          {/each}
        </tr>
      {/each}
      {#if rows.length === 0}
        <tr>
          <td colspan={columns.length}>
            <div class="empty-state">
              <span class="empty-state-text">No data</span>
            </div>
          </td>
        </tr>
      {/if}
    </tbody>
  </table>
</div>
