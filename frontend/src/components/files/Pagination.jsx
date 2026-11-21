import { PAGE_SIZE } from "../../api/files";

export default function Pagination({ page, count, onPage }) {
  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const first = (page - 1) * PAGE_SIZE + 1;
  const last = Math.min(page * PAGE_SIZE, count);

  return (
    <nav className="d-flex flex-wrap justify-content-between align-items-center gap-2 mt-4" aria-label="Pages">
      <span className="text-muted">Showing {first}–{last} of {count}</span>
      <div className="d-flex align-items-center gap-2">
        <button type="button" className="btn btn-outline-primary btn-sm" disabled={page <= 1}
          onClick={() => onPage(page - 1)}>
          ‹ Prev
        </button>
        <span>Page {page} of {totalPages}</span>
        <button type="button" className="btn btn-outline-primary btn-sm" disabled={page >= totalPages}
          onClick={() => onPage(page + 1)}>
          Next ›
        </button>
      </div>
    </nav>
  );
}
