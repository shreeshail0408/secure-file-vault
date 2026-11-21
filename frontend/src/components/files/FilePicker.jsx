import { useRef, useState } from "react";
import { formatSize } from "../../utils/format";

// Click to choose a file, or drag one onto the box. Shows the chosen file and
// any error (from the browser check or the backend) under it.
export default function FilePicker({ file, onSelect, accept, errors = [], disabled = false }) {
  const input = useRef(null);
  const [dragging, setDragging] = useState(false);

  function onDrop(event) {
    event.preventDefault();
    setDragging(false);
    if (!disabled && event.dataTransfer.files.length > 0) onSelect(event.dataTransfer.files[0]);
  }

  const border = errors.length ? "border-danger" : dragging ? "border-primary bg-light" : "border-secondary";

  return (
    <div className="mb-3">
      <div
        className={`border border-2 rounded p-4 text-center ${border}`}
        style={{ borderStyle: "dashed", cursor: disabled ? "default" : "pointer" }}
        data-testid="drop-zone"
        onClick={() => !disabled && input.current.click()}
        onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <i className="bi bi-cloud-arrow-up fs-2 d-block mb-1" aria-hidden="true" />
        {file ? (
          <span><strong>{file.name}</strong> ({formatSize(file.size)})</span>
        ) : (
          <span>Drag a file here, or click to choose</span>
        )}
      </div>
      <label htmlFor="file-input" className="visually-hidden">Choose file</label>
      <input id="file-input" ref={input} type="file" accept={accept} hidden disabled={disabled}
        onChange={(event) => event.target.files[0] && onSelect(event.target.files[0])} />
      {errors.map((message) => (
        <div key={message} className="text-danger small mt-1" role="alert">{message}</div>
      ))}
    </div>
  );
}
