import { setupServer } from 'msw/node';
import { handlers } from './handlers';

/**
 * Shared msw server. Lifecycle is wired in ./setup.ts so every test file gets
 * listen/resetHandlers/close for free — tests only call `server.use(...)`.
 */
export const server = setupServer(...handlers);
