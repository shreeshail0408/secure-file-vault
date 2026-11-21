import { useEffect, useRef, useState } from "react";

const DEBOUNCE_MS = 300;

// Search box (debounced) + type filter. `search` and `type` come from the URL.
export default function SearchBar({ search, type, onSearch, onTypeChange }) {
  // What's in the box right now. The URL only gets it 300 ms after the last keystroke.
  const [text, setText] = useState(search);
  const timer = useRef(null);

  // If the URL changes from outside (Back button, "Clear filters"), show its value.
  // (React's "adjust state while rendering" pattern, so no extra effect is needed.)
  const [lastSearch, setLastSearch] = useState(search);
  if (search !== lastSearch) {
    setLastSearch(search);
    setText(search);
  }

  useEffect(() => () => clearTimeout(timer.current), []); // no late update after unmount

  function onChange(event) {
    const value = event.target.value;
    setText(value);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => onSearch(value), DEBOUNCE_MS);
  }

  return (
    <div className="row g-2 mb-3">
      <div className="col-md-8">
        <label htmlFor="file-search" className="visually-hidden">Search files</label>
        <div className="input-group">
          <span className="input-group-text"><i className="bi bi-search" aria-hidden="true" /></span>
          <input id="file-search" type="search" className="form-control" placeholder="Search by name..."
            value={text} onChange={onChange} />
        </div>
      </div>
      <div className="col-md-4">
        <label htmlFor="file-type" className="visually-hidden">File type</label>
        <select id="file-type" className="form-select" value={type} onChange={(e) => onTypeChange(e.target.value)}>
          <option value="">All types</option>
          <option value="pdf">PDF</option>
          <option value="image">Images</option>
        </select>
      </div>
    </div>
  );
}
