import React, { useEffect, useMemo, useState } from "react";

export default function PaginatedList({
  items,
  pageSize = 6,
  className,
  itemLabel = "itens",
  renderItem,
}) {
  const [page, setPage] = useState(1);
  const safeItems = Array.isArray(items) ? items : [];
  const totalPages = Math.max(1, Math.ceil(safeItems.length / pageSize));

  useEffect(() => {
    setPage(1);
  }, [safeItems.length, pageSize]);

  const pagedItems = useMemo(() => {
    const start = (page - 1) * pageSize;
    return safeItems.slice(start, start + pageSize);
  }, [safeItems, page, pageSize]);

  const startIndex = safeItems.length === 0 ? 0 : (page - 1) * pageSize + 1;
  const endIndex = Math.min(page * pageSize, safeItems.length);

  return (
    <div>
      <div className={className}>
        {pagedItems.map((item, index) => renderItem(item, (page - 1) * pageSize + index))}
      </div>

      {totalPages > 1 && (
        <div className="pagination-controls">
          <button className="pagination-btn" type="button" onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={page === 1}>
            Anterior
          </button>
          <span className="pagination-status">
            {startIndex}-{endIndex} de {safeItems.length} {itemLabel} | Pagina {page}/{totalPages}
          </span>
          <button
            className="pagination-btn"
            type="button"
            onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
            disabled={page === totalPages}
          >
            Proxima
          </button>
        </div>
      )}
    </div>
  );
}
