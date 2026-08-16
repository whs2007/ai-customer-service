/** 用户端布局（12 §4.1）：顶部导航 + 内容区，独立于管理端侧边栏。 */

import { LogoutOutlined, MessageOutlined, ProfileOutlined, UserOutlined } from '@ant-design/icons';
import { Avatar, Dropdown, Layout, Menu, Space, Typography, message } from 'antd';
import { useEffect } from 'react';
import { Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom';

import { getUserAccessToken } from '../api/token';
import { useUserAuthStore } from '../stores/userAuth';

const { Header, Content } = Layout;

const MENU_ITEMS = [
  { key: '/user/chat', icon: <MessageOutlined />, label: '在线咨询' },
  { key: '/user/tickets', icon: <ProfileOutlined />, label: '我的工单' },
  { key: '/user/profile', icon: <UserOutlined />, label: '个人中心' },
];

export default function UserLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const user = useUserAuthStore((s) => s.user);
  const logout = useUserAuthStore((s) => s.logout);
  const loadMe = useUserAuthStore((s) => s.loadMe);

  useEffect(() => {
    if (getUserAccessToken() && !user) {
      loadMe().catch(() => {
        useUserAuthStore.getState().logout();
        navigate('/user/login', { replace: true });
      });
    }
  }, [user, loadMe, navigate]);

  if (!getUserAccessToken()) {
    return <Navigate to="/user/login" replace state={{ from: location.pathname }} />;
  }

  const selected = MENU_ITEMS.find(
    (item) => location.pathname === item.key || location.pathname.startsWith(`${item.key}/`),
  )?.key;

  const userMenu = {
    items: [
      {
        key: 'profile',
        label: '个人中心',
        onClick: () => navigate('/user/profile'),
      },
      {
        key: 'logout',
        icon: <LogoutOutlined />,
        label: '退出登录',
        onClick: () => {
          logout();
          message.success('已退出登录');
          navigate('/user/login', { replace: true });
        },
      },
    ],
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 10,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: '#fff',
          borderBottom: '1px solid #E5E7EB',
          padding: '0 24px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 32 }}>
          <Typography.Text strong style={{ fontSize: 17, cursor: 'pointer' }} onClick={() => navigate('/user/chat')}>
            AI 智能客服
          </Typography.Text>
          <Menu
            mode="horizontal"
            selectedKeys={selected ? [selected] : []}
            items={MENU_ITEMS.map(({ key, icon, label }) => ({
              key,
              icon,
              label,
              onClick: () => navigate(key),
            }))}
            style={{ minWidth: 360, borderBottom: 'none' }}
          />
        </div>
        <Dropdown menu={userMenu} placement="bottomRight">
          <Space style={{ cursor: 'pointer' }}>
            <Avatar size={32} icon={<UserOutlined />} style={{ background: '#3B82F6' }} />
            <span>{user?.display_name ?? ''}</span>
          </Space>
        </Dropdown>
      </Header>
      <Content style={{ padding: 0 }}>
        <Outlet />
      </Content>
    </Layout>
  );
}
