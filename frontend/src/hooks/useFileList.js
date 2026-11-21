import { useEffect, useState } from "react";
import { listFiles } from "../api/files";

// Loads one page of files whenever search/type/page change.
//
// `loading` is derived, not stored: the last result remembers which request it
// belongs to (`key`), so when the filters change, the old result no longer
// matches and we're "loading" again until the new one arrives.
export function useFileList(search, type, page) {
  const [attempt, setAttempt] = useState(0); // bumped by retry()
  const [result, setResult] = useState({ key: null, data: null, error: null });
  const key = JSON.stringify([search, type, page, attempt]);

  useEffect(() => {
    const controller = new AbortController(); // cancel if filters change mid-request
    listFiles({ search, type, page }, { signal: controller.signal })
      .then((data) => setResult({ key, data, error: null }))
      .catch((error) => {
        if (!controller.signal.aborted) setResult({ key, data: null, error });
      });
    return () => controller.abort();
  }, [key, search, type, page]);

  const loading = result.key !== key;
  return {
    loading,
    data: loading ? null : result.data,
    error: loading ? null : result.error,
    retry: () => setAttempt((n) => n + 1),
  };
}
