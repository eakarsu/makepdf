(function (global) {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
  const title = key => String(key).replace(/([a-z])([A-Z])/g, '$1 $2').replace(/[_-]/g, ' ').replace(/^./, s => s.toUpperCase());
  const inline = text => esc(text).replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>');
  function prose(text, depth) {
    try { if (/^(?:\[|\{)/.test(text.trim())) return render(JSON.parse(text), depth + 1); } catch {}
    const lines = text.replace(/\r/g, '').split('\n'); let output = '', list = false;
    const close = () => { if (list) { output += '</ul>'; list = false; } };
    for (let index = 0; index < lines.length; index++) {
      const line = lines[index];
      if (/^\s*```/.test(line)) {
        close(); const language = line.trim().slice(3).toLowerCase(); const code = [];
        while (++index < lines.length && !/^\s*```/.test(lines[index])) code.push(lines[index]);
        if (language === 'json' || /^[\[{]/.test(code.join('\n').trim())) { try { output += render(JSON.parse(code.join('\n')), depth + 1); continue; } catch {} }
        output += '<pre class="browser-report-code"><code>' + esc(code.join('\n')) + '</code></pre>'; continue;
      }
      if (/^\s*\|/.test(line) && /^\s*\|?[\s:|-]+\|/.test(lines[index + 1] || '')) {
        close(); const cells = row => row.trim().replace(/^\||\|$/g, '').split('|').map(value => value.trim());
        const heads = cells(line); index++;
        let rows = ''; while (/^\s*\|/.test(lines[index + 1] || '')) rows += '<tr>' + cells(lines[++index]).map(value => '<td>' + inline(value) + '</td>').join('') + '</tr>';
        output += '<div class="browser-report-table"><table><thead><tr>' + heads.map(value => '<th>' + inline(value) + '</th>').join('') + '</tr></thead><tbody>' + rows + '</tbody></table></div>'; continue;
      }
      const heading = line.match(/^\s*#{1,6}\s+(.+)/);
      if (heading) { close(); output += '<h3>' + inline(heading[1]) + '</h3>'; }
      else if (/^\s*(?:[-*•]|\d+[.)])\s+/.test(line)) { if (!list) { output += '<ul>'; list = true; } output += '<li>' + inline(line.replace(/^\s*(?:[-*•]|\d+[.)])\s+/, '')) + '</li>'; }
      else { close(); if (/^\s*[-*_]{3,}\s*$/.test(line)) output += '<hr>'; else if (line.trim()) output += '<p>' + inline(line) + '</p>'; }
    }
    close(); return output;
  }
  function render(value, depth = 0) {
    if (depth > 10) return '<p>Further details omitted.</p>';
    if (value == null) return '<span class="muted">Not supplied</span>';
    if (typeof value === 'string') return value === '' ? '<span class="muted">(empty string)</span>' : prose(value, depth);
    if (typeof value !== 'object') return '<p>' + esc(value) + '</p>';
    if (Array.isArray(value)) {
      if (!value.length) return '<p>No items returned.</p>';
      if (value.every(row => row && typeof row === 'object' && !Array.isArray(row))) {
        const keys = [...new Set(value.flatMap(row => Object.keys(row)))];
        if (keys.length && keys.length <= 8 && value.every(row => Object.values(row).every(cell => cell == null || typeof cell !== 'object'))) return '<div class="browser-report-table"><table><thead><tr>' + keys.map(key => '<th>' + esc(title(key)) + '</th>').join('') + '</tr></thead><tbody>' + value.map(row => '<tr>' + keys.map(key => '<td>' + render(row[key], depth + 1) + '</td>').join('') + '</tr>').join('') + '</tbody></table></div>';
      }
      return '<ul>' + value.map(item => '<li>' + render(item, depth + 1) + '</li>').join('') + '</ul>';
    }
    return Object.entries(value).map(([key, item]) => '<section class="browser-report-section"><h3>' + esc(title(key)) + '</h3>' + render(item, depth + 1) + '</section>').join('');
  }
  global.BrowserAIReport = { render: value => '<div class="browser-ai-report">' + render(value) + '</div>', escape: esc };
})(window);

