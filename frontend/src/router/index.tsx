/** 路由表（需求文档 01 §3 / 00 §4.3）。 */

import { lazy, Suspense } from 'react';
import { Navigate, createBrowserRouter } from 'react-router-dom';
import { Spin } from 'antd';

import AppLayout from '../layouts/AppLayout';
import RequireAuth from '../layouts/RequireAuth';

const Login = lazy(() => import('../pages/Login'));
const Dashboard = lazy(() => import('../pages/Dashboard'));
const Chat = lazy(() => import('../pages/Chat'));
const KnowledgeLayout = lazy(() => import('../pages/knowledge/KnowledgeLayout'));
const KnowledgeEmpty = lazy(() => import('../pages/knowledge/KnowledgeEmpty'));
const DocumentsPanel = lazy(() => import('../pages/knowledge/DocumentsPanel'));
const ChunkDetailPage = lazy(() => import('../pages/knowledge/ChunkDetailPage'));
const RecallTest = lazy(() => import('../pages/RecallTest'));
const Tickets = lazy(() => import('../pages/Tickets'));
const Evaluation = lazy(() => import('../pages/Evaluation'));
const Sessions = lazy(() => import('../pages/Sessions'));
const SessionDetail = lazy(() => import('../pages/SessionDetail'));
const Settings = lazy(() => import('../pages/Settings'));
const Help = lazy(() => import('../pages/Help'));
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
          { path: 'dashboard', element: withSuspense(<Dashboard />) },
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
          { path: 'tickets', element: withSuspense(<Tickets />) },
          { path: 'evaluation', element: withSuspense(<Evaluation />) },
          { path: 'sessions', element: withSuspense(<Sessions />) },
          { path: 'sessions/:id', element: withSuspense(<SessionDetail />) },
          { path: 'settings', element: withSuspense(<Settings />) },
          { path: 'help', element: withSuspense(<Help />) },
          { path: '*', element: withSuspense(<NotFound />) },
        ],
      },
    ],
  },
]);
