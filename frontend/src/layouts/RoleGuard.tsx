/** 角色守卫（开发文档 02 §1）：角色不匹配时跳转对应首页。 */

import { Navigate } from 'react-router-dom';

import { useAuthStore } from '../stores/auth';
import { redirectByRole } from '../utils/redirect';

interface RoleGuardProps {
  roles: string[];
  children: React.ReactNode;
}

export default function RoleGuard({ roles, children }: RoleGuardProps) {
  const user = useAuthStore((s) => s.user);
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  if (!roles.includes(user.role)) {
    return <Navigate to={redirectByRole(user.role)} replace />;
  }
  return <>{children}</>;
}
