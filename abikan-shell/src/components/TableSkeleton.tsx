import "./Status.css";
import "./TableSkeleton.css";

interface TableSkeletonProps {
  headers: string[];
  rows?: number;
  label?: string;
}

export function TableSkeleton({ headers, rows = 5, label = "Loading…" }: TableSkeletonProps) {
  return (
    <div className="abikan-table-wrap abikan-table-wrap--skeleton" aria-busy="true">
      <table className="abikan-table">
        <caption className="abikan-status__sr">{label}</caption>
        <thead>
          <tr>
            {headers.map((header) => (
              <th key={header}>{header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }, (_, row) => (
            <tr key={row}>
              {headers.map((header) => (
                <td key={`${row}-${header}`}>
                  <span className="abikan-skeleton-bar" />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
