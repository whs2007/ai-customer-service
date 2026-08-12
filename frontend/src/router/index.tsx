/** 路由表（需求文档 01 §3 / 00 §4.3）。 */

import { lazy, Suspense } from 'react';
import { Navigate, createBrowserRouter } from 'react-router-dom';
import { Spin } from 'antd';

import AppLayout from '../layouts/AppLayout';
import RequireAuth from '../layouts/RequireAuth';

const Login = lazy(() => import('../pages/Login'));
const DashboardPage = lazy(() => import('../pages/DashboardPage'));
const Chat = lazy(() => import('../pages/Chat'));
const KnowledgeLayout = lazy(() => import('../pages/knowledge/KnowledgeLayout'));
const KnowledgeEmpty = lazy(() => import('../pages/knowledge/KnowledgeEmpty'));
const DocumentsPanel = lazy(() => import('../pages/knowledge/DocumentsPanel'));
const ChunkDetailPage = lazy(() => import('../pages/knowledge/ChunkDetailPage'));
const RecallTest = lazy(() => import('../pages/RecallTest'));
const TicketsPage = lazy(() => import('../pages/TicketsPage'));
const EvaluationPage = lazy(() => import('../pages/evaluation/EvaluationPage'));
const EvalReportPage = lazy(() => import('../pages/evaluation/ReportPage'));
const SessionsPage = lazy(() => import('../pages/SessionsPage'));
const SessionDetailPage = lazy(() => import('../pages/sessions/SessionDetailPage'));
const SettingsPage = lazy(() => import('../pages/SettingsPage'));
const HelpPage = lazy(() => import('../pages/HelpPage'));
const NotFound = lazy(() => import('../pages/NotFound'));

const withSuspense = (node: React.ReactNode) => (
  <Suspense fallback={<Spin style={{ display: 'block', margin: '120px auto' }} />}>
    {node}
  </Suspense>
);

export const router = createBrowserRouter([
  {
    path: '/login',
    element: withSuspense(<Login />),
  },
  {
    path: '/',
    element: <RequireAuth />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { index: true, element: <Navigate to="/dashboard" replace /> },
          { path: 'dashboard', element: withSuspense(<DashboardPage />) },
          { path: 'chat', element: withSuspense(<Chat />) },
          {
            path: 'knowledge',
            element: withSuspense(<KnowledgeLayout />),
            children: [
              { index: true, element: withSuspense(<KnowledgeEmpty />) },
              { path: ':kbId', element: withSuspense(<DocumentsPanel />) },
              {
                path: ':kbId/documents/:docId',
                element: withSuspense(<ChunkDetailPage />),
              },
            ],
          },
          { path: 'recall-test', element: withSuspense(<RecallTest />) },
          { path: 'tickets', element: withSuspense(<TicketsPage />) },
          { path: 'evaluation', element: withSuspense(<EvaluationPage />) },
          {
            path: 'evaluation/tasks/:taskId/report',
            element: withSuspense(<EvalReportPage />),
          },
          { path: 'sessions', element: withSuspense(<SessionsPage />) },
          { path: 'sessions/:id', element: withSuspense(<SessionDetailPage />) },
          { path: 'settings', element: withSuspense(<SettingsPage />) },
          { path: 'help', element: withSuspense(<HelpPage />) },
          { path: '*', element: withSuspense(<NotFound />) },
        ],
      },
    ],
  },
]);
