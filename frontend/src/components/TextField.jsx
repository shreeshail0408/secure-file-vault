// A labelled Bootstrap input that shows the backend's errors for this field under it.
export default function TextField({ label, name, type = "text", value, onChange, errors, ...rest }) {
  const hasErrors = errors && errors.length > 0;
  const id = `field-${name}`;

  return (
    <div className="mb-3">
      <label htmlFor={id} className="form-label">{label}</label>
      <input
        id={id}
        name={name}
        type={type}
        value={value}
        onChange={onChange}
        className={`form-control ${hasErrors ? "is-invalid" : ""}`}
        aria-describedby={hasErrors ? `${id}-errors` : undefined}
        {...rest}
      />
      {hasErrors && (
        <div id={`${id}-errors`} className="invalid-feedback">
          {errors.map((message) => <div key={message}>{message}</div>)}
        </div>
      )}
    </div>
  );
}
