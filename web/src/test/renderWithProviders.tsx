import { type ReactElement } from 'react';
import { render, type RenderResult } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

interface Options {
  /** Initial URL. For route-param pages pass the concrete path, e.g. `/symbols/NABIL`. */
  route?: string;
  /** Route pattern the element is mounted at, e.g. `/symbols/:symbol`. Defaults to `route`. */
  path?: string;
}

/**
 * Renders a component inside the providers the app supplies in production —
 * currently just react-router-dom v7. Uses MemoryRouter (not BrowserRouter) so
 * each test gets an isolated history, and mounts through a real <Route> so
 * `useParams` resolves.
 */
export function renderWithProviders(
  ui: ReactElement,
  { route = '/', path }: Options = {}
): RenderResult {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path={path ?? route} element={ui} />
      </Routes>
    </MemoryRouter>
  );
}
