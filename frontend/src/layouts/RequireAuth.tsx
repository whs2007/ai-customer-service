/** 路由守卫：未登录跳转登录页（B1 JWT 配套）。 */

import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { getAccessToken } from '../api/token';

export default function RequireAuth() {
  const location = useLocation();
  const token = getAccessToken();

  if (!token) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}

