import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="narrow">
      <h1>This screen is not built yet</h1>
      <p>
        AaharOS is being built one stage at a time. The <Link to="/guide">guided tour</Link> shows
        which screens are ready and which are coming next.
      </p>
      <Link to="/" className="btn btn-primary">
        Back to start
      </Link>
    </div>
  );
}
