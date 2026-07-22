import { type ReactNode } from 'react';

interface Column<T> {
  key: string;
  label: string;
  sortable?: boolean;
  render?: (row: T) => ReactNode;
  className?: string;
}

interface Props<T> {
  columns: Column<T>[];
  data: T[];
  onRowClick?: (row: T) => void;
  sortKey?: string;
  sortDir?: 'asc' | 'desc';
  onSort?: (key: string) => void;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function getVal(obj: any, key: string): unknown {
  return obj[key];
}

export function DataTable<T extends object>({
  columns,
  data,
  onRowClick,
  sortKey,
  sortDir,
  onSort,
}: Props<T>) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border">
            {columns.map((col) => (
              <th
                key={col.key}
                className={`px-3 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider ${
                  col.sortable ? 'cursor-pointer select-none hover:text-text-primary' : ''
                } ${col.className || ''}`}
                onClick={() => col.sortable && onSort?.(col.key)}
              >
                <span className="inline-flex items-center gap-1">
                  {col.label}
                  {col.sortable && sortKey === col.key && (
                    <span className="text-text-tertiary">
                      {sortDir === 'asc' ? '↑' : '↓'}
                    </span>
                  )}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {data.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="px-3 py-12 text-center text-sm text-text-tertiary"
              >
                No data
              </td>
            </tr>
          ) : (
            data.map((row, i) => (
              <tr
                key={(getVal(row, 'id') as string) || i}
                className={`transition-colors ${
                  onRowClick ? 'cursor-pointer hover:bg-surface-tertiary' : ''
                }`}
                onClick={() => onRowClick?.(row)}
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={`px-3 py-2.5 text-text-primary ${col.className || ''}`}
                  >
                    {col.render
                      ? col.render(row)
                      : (getVal(row, col.key) as ReactNode) ?? '—'}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
