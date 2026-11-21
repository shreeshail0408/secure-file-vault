// Grey placeholder cards while the list loads (Bootstrap "placeholder" classes).
export default function LoadingGrid({ cards = 8 }) {
  return (
    <div className="row g-3" role="status" aria-label="Loading files">
      {Array.from({ length: cards }, (_, i) => (
        <div className="col-sm-6 col-lg-4 col-xl-3" key={i}>
          <div className="card h-100" aria-hidden="true">
            <div className="card-body placeholder-glow">
              <span className="placeholder col-2 me-2" style={{ height: 40 }} />
              <span className="placeholder col-8" />
              <span className="placeholder col-4 mt-3 d-block" />
              <span className="placeholder col-6 mt-1 d-block" />
              <span className="placeholder col-5 mt-1 d-block" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
