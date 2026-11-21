import { useCallback, useState } from "react";
import { describeBlobError, downloadFile } from "../api/files";
import { useAuth } from "../auth/useAuth";
import BusyButton from "../components/BusyButton";
import DeleteDialog from "../components/files/DeleteDialog";
import EditModal from "../components/files/EditModal";
import FileResults from "../components/files/FileResults";
import PreviewModal from "../components/files/PreviewModal";
import SearchBar from "../components/files/SearchBar";
import UploadModal from "../components/files/UploadModal";
import Navbar from "../components/Navbar";
import Toast from "../components/Toast";
import { useFileFilters } from "../hooks/useFileFilters";
import { useFileList } from "../hooks/useFileList";

export default function Dashboard() {
  const { user } = useAuth();
  const filters = useFileFilters();
  const list = useFileList(filters.search, filters.type, filters.page);

  // At most one dialog is open: { kind: "preview" | "edit" | "delete" | "upload", file }
  const [dialog, setDialog] = useState(null);
  const [actionError, setActionError] = useState(null); // download/export problems
  const [toast, setToast] = useState(null);

  const closeDialog = useCallback(() => setDialog(null), []);
  const dismissToast = useCallback(() => setToast(null), []);

  async function download(file) {
    setActionError(null);
    try {
      await downloadFile(`/files/${file.id}/download/`, file.original_name);
    } catch (error) {
      setActionError(`Download failed: ${await describeBlobError(error)}`);
    }
  }

  async function exportAll() {
    setActionError(null);
    try {
      await downloadFile("/files/export/", "vault-export.zip");
    } catch (error) {
      setActionError(`Export failed: ${await describeBlobError(error)}`);
    }
  }

  function afterUpload(saved) {
    setDialog(null);
    setToast(`Uploaded ${saved.original_name}`);
    // Newest files come first, so page 1 shows the new one. retry() reloads
    // even when we are already on page 1.
    filters.setPage(1);
    list.retry();
  }

  function afterEdit(saved, message) {
    setDialog(null);
    setToast(message);
    list.retry();
  }

  function afterDelete(file) {
    setDialog(null);
    setToast(`Deleted ${file.original_name}`);
    // The last card on this page is gone → that page no longer exists, go back one.
    // (Changing the page reloads the list by itself.)
    const wasLastOnPage = list.data?.results.length === 1;
    if (wasLastOnPage && filters.page > 1) filters.setPage(filters.page - 1);
    else list.retry();
  }

  return (
    <>
      <Navbar />
      <main className="container py-4">
        <div className="d-flex justify-content-between align-items-center mb-3 gap-2">
          <h2 className="h4 mb-0">Files</h2>
          <div className="d-flex gap-2">
            {user.is_staff && (
              <BusyButton className="btn btn-outline-dark btn-sm" onClick={exportAll}>
                <i className="bi bi-file-earmark-zip me-1" aria-hidden="true" />Export all
              </BusyButton>
            )}
            <button type="button" className="btn btn-primary btn-sm" onClick={() => setDialog({ kind: "upload" })}>
              <i className="bi bi-upload me-1" aria-hidden="true" />Upload
            </button>
          </div>
        </div>

        <SearchBar search={filters.search} type={filters.type}
          onSearch={filters.setSearch} onTypeChange={filters.setType} />

        {actionError && (
          <div className="alert alert-danger alert-dismissible" role="alert">
            {actionError}
            <button type="button" className="btn-close" aria-label="Dismiss" onClick={() => setActionError(null)} />
          </div>
        )}

        <FileResults {...list} filters={filters} onDownload={download}
          onPreview={(file) => setDialog({ kind: "preview", file })}
          onEdit={(file) => setDialog({ kind: "edit", file })}
          onDelete={(file) => setDialog({ kind: "delete", file })} />
      </main>

      {dialog?.kind === "preview" && <PreviewModal file={dialog.file} onClose={closeDialog} onDownload={download} />}
      {dialog?.kind === "upload" && <UploadModal onClose={closeDialog} onUploaded={afterUpload} />}
      {dialog?.kind === "edit" && <EditModal file={dialog.file} onClose={closeDialog} onSaved={afterEdit} />}
      {dialog?.kind === "delete" && <DeleteDialog file={dialog.file} onClose={closeDialog} onDeleted={afterDelete} />}
      {toast && <Toast message={toast} onDismiss={dismissToast} />}
    </>
  );
}
