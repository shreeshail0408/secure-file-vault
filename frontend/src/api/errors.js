// Turns an axios error into something a form can show:
//   { message: "text for the alert" | null, fieldErrors: { username: ["..."], ... } }
//
// DRF sends 400 errors as { field: ["msg", ...], ... } and other errors as { detail: "..." }.

export function describeError(error) {
  if (!error.response) {
    return { message: "Cannot reach the server. Is the backend running?", fieldErrors: {} };
  }

  const { status, data } = error.response;

  if (status === 429) {
    return { message: "Too many attempts, wait a minute and try again.", fieldErrors: {} };
  }

  if (status === 400 && data && typeof data === "object") {
    const { detail, non_field_errors: general, ...fieldErrors } = data;
    return { message: detail || general?.join(" ") || null, fieldErrors };
  }

  return {
    message: data?.detail || `Something went wrong (error ${status}).`,
    fieldErrors: {},
  };
}

// Same as describeError, with clearer wording for rename / replace / delete.
export function describeChangeError(error) {
  const status = error.response?.status;
  if (status === 403) {
    return { message: "You can't modify this file: only its uploader or an admin can.", fieldErrors: {} };
  }
  if (status === 404) {
    return { message: "This file no longer exists (someone may have deleted it).", fieldErrors: {} };
  }
  return describeError(error);
}
