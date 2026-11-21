export default function UploadProgress({ percent }) {
  return (
    <div className="progress mb-3" role="progressbar" aria-label="Upload progress"
      aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
      <div className="progress-bar progress-bar-striped progress-bar-animated" style={{ width: `${percent}%` }}>
        {percent}%
      </div>
    </div>
  );
}
