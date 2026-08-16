/** 登录后按角色跳转（12 §1 / 开发文档 02 §1）。 */

export function redirectByRole(role: string): string {
  if (role === 'user') return '/user/chat';
  if (role === 'agent') return '/workbench';
  return '/dashboard';
}
