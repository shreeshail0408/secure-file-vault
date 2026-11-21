import { useCallback, useState } from "react";
import { describeBlobError, downloadFile } from "../api/files";
import { useAuth } from "../auth/useAuth";
import BusyButton from "../components/BusyButton";
import FileResults from "../components/files/FileResults";
import PreviewModal from "../components/files/PreviewModal";
import SearchBar from "../components/files/SearchBar";
import Navbar from "../components/Navbar";
import { useFileFilters } from "../hooks/useFileFilters";
import { useFileList } from "../hooks/useFileList";

export default function Dashboard() {
  const { user } = useAuth();
  const filters = useFileFilters();
  const list = useFileList(filters.search, filters.type, filters.page);
  const [previewFile, setPreviewFile] = useState(null);
  const [actionError, setActionError] = useState(null); // download/export problems

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

  const closePreview = useCallback(() => setPreviewFile(null), []);

  return (
    <>
      <Navbar />
      <main className="container py-4">
        <div className="d-flex justify-content-between align-items-center mb-3">
          <h2 className="h4 mb-0">Files</h2>
          {user.is_staff && (
            <BusyButton className="btn btn-outline-dark btn-sm" onClick={exportAll}>
              <i className="bi bi-file-earmark-zip me-1" aria-hidden="true" />Export all
            </BusyButton>
          )}
        </div>

        <SearchBar search={filters.search} type={filters.type}
          onSearch={filters.setSearch} onTypeChange={filters.setType} />

        {actionError && (
          <div className="alert alert-danger alert-dismissible" role="alert">
            {actionError}
            <button type="button" className="btn-close" aria-label="Dismiss" onClick={() => setActionError(null)} />
          </div>
        )}

        <FileResults {...list} filters={filters} onPreview={setPreviewFile} onDownload={download} />
      </main>

      {previewFile && <PreviewModal file={previewFile} onClose={closePreview} onDownload={download} />}
    </>
  );
}
