import { describeError } from "../../api/errors";
import FileCard from "./FileCard";
import LoadingGrid from "./LoadingGrid";
import Pagination from "./Pagination";

// The list area: loading → error → empty → grid + pagination.
export default function FileResults({ loading, data, error, retry, filters, onPreview, onDownload, onEdit, onDelete }) {
  if (loading) return <LoadingGrid />;

  if (error) {
    // e.g. ?page=9 after files were deleted: DRF answers 404 "Invalid page."
    if (error.response?.status === 404 && filters.page > 1) {
      return (
        <div className="alert alert-warning d-flex justify-content-between align-items-center">
          <span>Page {filters.page} doesn't exist.</span>
          <button type="button" className="btn btn-sm btn-warning" onClick={() => filters.setPage(1)}>
            Go to page 1
          </button>
        </div>
      );
    }
    return (
      <div className="alert alert-danger d-flex justify-content-between align-items-center" role="alert">
        <span>Could not load files. {describeError(error).message}</span>
        <button type="button" className="btn btn-sm btn-danger" onClick={retry}>Retry</button>
      </div>
    );
  }

  if (data.count === 0) {
    const filtered = filters.search.trim() || filters.type;
    return (
      <div className="text-center text-muted py-5">
        <i className="bi bi-folder2-open fs-1 d-block mb-2" aria-hidden="true" />
        {filters.search.trim()
          ? <p>No files match "{filters.search.trim()}"{filters.type && ` (type: ${filters.type})`}.</p>
          : <p>{filtered ? "No files of this type." : "No files yet."}</p>}
        {filtered && (
          <button type="button" className="btn btn-outline-primary btn-sm" onClick={filters.clear}>
            Clear filters
          </button>
        )}
      </div>
    );
  }

  return (
    <>
      <div className="row g-3">
        {data.results.map((file) => (
          <div className="col-sm-6 col-lg-4 col-xl-3" key={file.id}>
            <FileCard file={file} onPreview={onPreview} onDownload={onDownload} onEdit={onEdit} onDelete={onDelete} />
          </div>
        ))}
      </div>
      <Pagination page={filters.page} count={data.count} onPage={filters.setPage} />
    </>
  );
}
