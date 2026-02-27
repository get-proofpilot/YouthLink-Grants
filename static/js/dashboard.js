/* Grant Intelligence Dashboard — minimal interactivity */

// Clickable table rows
document.addEventListener("DOMContentLoaded", function() {
  document.querySelectorAll("tr[data-href]").forEach(function(row) {
    row.style.cursor = "pointer";
    row.addEventListener("click", function() {
      window.location.href = this.dataset.href;
    });
  });
});

// Confirm before destructive actions
document.addEventListener("click", function(e) {
  var btn = e.target.closest("[data-confirm]");
  if (btn) {
    if (!confirm(btn.dataset.confirm)) {
      e.preventDefault();
    }
  }
});

// Simple client-side table sorting
function sortTable(table, col, type) {
  var tbody = table.querySelector("tbody");
  if (!tbody) return;
  var rows = Array.from(tbody.rows);
  var asc = table.dataset.sortCol == col && table.dataset.sortDir != "asc";
  table.dataset.sortCol = col;
  table.dataset.sortDir = asc ? "asc" : "desc";

  rows.sort(function(a, b) {
    var aVal = a.cells[col].textContent.trim();
    var bVal = b.cells[col].textContent.trim();
    if (type === "num") {
      aVal = parseFloat(aVal.replace(/[^0-9.-]/g, "")) || 0;
      bVal = parseFloat(bVal.replace(/[^0-9.-]/g, "")) || 0;
    }
    if (aVal < bVal) return asc ? -1 : 1;
    if (aVal > bVal) return asc ? 1 : -1;
    return 0;
  });

  rows.forEach(function(row) { tbody.appendChild(row); });

  // Update sort indicators
  table.querySelectorAll("th[data-sort]").forEach(function(th) {
    th.classList.remove("sort-asc", "sort-desc");
  });
  var th = table.querySelector("th[data-sort][data-col='" + col + "']");
  if (th) th.classList.add(asc ? "sort-asc" : "sort-desc");
}

document.addEventListener("click", function(e) {
  var th = e.target.closest("th[data-sort]");
  if (th) {
    var table = th.closest("table");
    var col = parseInt(th.dataset.col);
    var type = th.dataset.sort;
    sortTable(table, col, type);
  }
});
