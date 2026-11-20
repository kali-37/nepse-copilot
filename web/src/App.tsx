import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import { RootLayout } from './layouts/RootLayout';
import { LoadingSpinner } from './components/ui/LoadingSpinner';

const DashboardPage = lazy(() => import('./pages/Dashboard').then((m) => ({ default: m.DashboardPage })));
const SymbolsPage = lazy(() => import('./pages/Symbols').then((m) => ({ default: m.SymbolsPage })));
const SymbolDetailPage = lazy(() => import('./pages/SymbolDetail').then((m) => ({ default: m.SymbolDetailPage })));
const SignalsPage = lazy(() => import('./pages/Signals').then((m) => ({ default: m.SignalsPage })));
const PortfolioPage = lazy(() => import('./pages/Portfolio').then((m) => ({ default: m.PortfolioPage })));
const BacktestPage = lazy(() => import('./pages/Backtest').then((m) => ({ default: m.BacktestPage })));
const RashifalPage = lazy(() => import('./pages/Rashifal').then((m) => ({ default: m.RashifalPage })));
const JournalPage = lazy(() => import('./pages/Journal').then((m) => ({ default: m.JournalPage })));
const MeroSharePage = lazy(() => import('./pages/MeroShare').then((m) => ({ default: m.MeroSharePage })));
const ResearchPage = lazy(() => import('./pages/Research').then((m) => ({ default: m.ResearchPage })));
const DataPage = lazy(() => import('./pages/Data').then((m) => ({ default: m.DataPage })));
const AiPage = lazy(() => import('./pages/Ai').then((m) => ({ default: m.AiPage })));
const OperationsPage = lazy(() => import('./pages/Operations').then((m) => ({ default: m.OperationsPage })));
const SettingsPage = lazy(() => import('./pages/Settings').then((m) => ({ default: m.SettingsPage })));
const AuctionPage = lazy(() => import('./pages/Auction').then((m) => ({ default: m.AuctionPage })));
const HealthPage = lazy(() => import('./pages/Health').then((m) => ({ default: m.HealthPage })));
const AnalyticsPage = lazy(() => import('./pages/Analytics').then((m) => ({ default: m.AnalyticsPage })));

const MarketPage = lazy(() => import('./pages/Market').then(m => ({ default: m.MarketPage })));
const AdvancedAdvisorPage = lazy(() => import('./pages/AdvancedAdvisor').then(m => ({ default: m.AdvancedAdvisorPage })));
const HoldingsPage = lazy(() => import('./pages/Holdings').then(m => ({ default: m.HoldingsPage })));

export default function App() {
  return (
    <BrowserRouter>
      <RootLayout>
        <Suspense fallback={<LoadingSpinner text="Loading page..." />}>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/market" element={<MarketPage />} />
          <Route path="/holdings" element={<HoldingsPage />} />
          <Route path="/prescription" element={<AdvancedAdvisorPage />} />
          <Route path="/symbols" element={<SymbolsPage />} />
          <Route path="/symbols/:symbol" element={<SymbolDetailPage />} />
          <Route path="/signals" element={<SignalsPage />} />
          <Route path="/portfolio" element={<PortfolioPage />} />
          <Route path="/backtest" element={<BacktestPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/rashifal" element={<RashifalPage />} />
          <Route path="/journal" element={<JournalPage />} />
          <Route path="/auction" element={<AuctionPage />} />
          <Route path="/meroshare" element={<MeroSharePage />} />
          <Route path="/research" element={<ResearchPage />} />
          <Route path="/data" element={<DataPage />} />
          <Route path="/ai" element={<AiPage />} />
          <Route path="/operations" element={<OperationsPage />} />
          <Route path="/health" element={<HealthPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
        </Suspense>
      </RootLayout>
    </BrowserRouter>
  );
}
