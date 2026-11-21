import { useSearchParams } from "react-router-dom";

// search / type / page live in the URL (?search=invoice&type=pdf&page=2), so a
// reload or the browser's Back button shows the same view.
export function useFileFilters() {
  const [params, setParams] = useSearchParams();

  const search = params.get("search") || "";
  const type = params.get("type") || "";
  const page = Math.max(1, parseInt(params.get("page"), 10) || 1);

  // Apply changes to the query string; empty values (and page 1) are removed.
  function update(changes, options) {
    setParams((current) => {
      const next = new URLSearchParams(current);
      for (const [key, value] of Object.entries(changes)) {
        const isEmpty = value == null || String(value).trim() === "" || (key === "page" && value === 1);
        if (isEmpty) next.delete(key);
        else next.set(key, String(value));
      }
      return next;
    }, options);
  }

  return {
    search,
    type,
    page,
    // A new search or type starts again at page 1.
    // Search uses `replace` so typing doesn't add one history entry per word.
    setSearch: (value) => update({ search: value, page: null }, { replace: true }),
    setType: (value) => update({ type: value, page: null }),
    setPage: (value) => update({ page: value }),
    clear: () => update({ search: null, type: null, page: null }),
  };
}
