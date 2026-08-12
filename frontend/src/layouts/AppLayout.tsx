/**
 * 全站布局（需求文档 01 §2）：
 * 左侧固定导航（系统 Logo + 9 个一级菜单）+ 右侧内容区（标题栏 + 页面内容）。
 */

import {
  AuditOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  HistoryOutlined,
  LogoutOutlined,
  MessageOutlined,
  ProfileOutlined,
  QuestionCircleOutlined,
  SearchOutlined,
  SettingOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { Avatar, Dropdown, Layout, Menu, Space, Typography } from 'antd';
import { useMemo } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';

import { useAuthStore } from '../stores/auth';

const { Sider, Header, Content } = Layout;

const MENU_ITEMS = [
  { key: '/dashboard', icon: <DashboardIcon />, label: '工作台' },
  { key: '/chat', icon: <MessageOutlined />, label: '智能客服' },
  { key: '/knowledge', icon: <DatabaseOutlined />, label: '知识库' },
  { key: '/recall-test', icon: <SearchOutlined />, label: '检索测试' },
  { key: '/tickets', icon: <ProfileOutlined />, label: '客服工单' },
  { key: '/evaluation', icon: <AuditOutlined />, label: '应用评测' },
  { key: '/sessions', icon: <HistoryOutlined />, label: '会话记录' },
  { key: '/settings', icon: <SettingOutlined />, label: '系统设置' },
  { key: '/help', icon: <QuestionCircleOutlined />, label: '帮助文档' },
];

function DashboardIcon() {
  return <ExperimentOutlined />;
}

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  // 菜单级权限（00 §3）：admin 全部；agent 隐藏设置/评测；viewer 仅工作台与帮助
  const visibleItems = MENU_ITEMS.filter((item) => {
    if (user?.role === 'admin') return true;
    if (user?.role === 'agent') {
      return !['/evaluation', '/settings'].includes(item.key);
    }
    return ['/dashboard', '/help'].includes(item.key);
  });

  const selectedKey = useMemo(() => {
    const match = visibleItems.find(
      (item) => location.pathname === item.key || location.pathname.startsWith(`${item.key}/`),
    );
    return match?.key ?? '/dashboard';
  }, [location.pathname, visibleItems]);

  const pageTitle = useMemo(
    () => visibleItems.find((item) => item.key === selectedKey)?.label ?? '工作台',
    [selectedKey, visibleItems],
  );

  const userMenu = {
    items: [
      {
        key: 'logout',
        icon: <LogoutOutlined />,
        label: '退出登录',
        onClick: () => {
          logout();
          navigate('/login');
        },
      },
    ],
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={240} style={{ borderRight: '1px solid #E5E7EB' }}>
        <div
          style={{
            padding: '24px 20px 16px',
            color: '#1F2937',
            lineHeight: 1.3,
          }}
        >
          <div style={{ fontSize: 18, fontWeight: 600 }}>AI 智能客服系统</div>
          <div style={{ fontSize: 12, color: '#9CA3AF', marginTop: 2 }}>
            LangGraph + RAG
          </div>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={visibleItems.map(({ key, icon, label }) => ({
            key,
            icon,
            label,
            onClick: () => navigate(key),
          }))}
          style={{ borderInlineEnd: 'none', padding: '8px 12px' }}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 24px',
            borderBottom: '1px solid #E5E7EB',
          }}
        >
          <Typography.Title level={4} style={{ margin: 0, fontSize: 18 }}>
            {pageTitle}
          </Typography.Title>
          <Dropdown menu={userMenu} placement="bottomRight">
            <Space style={{ cursor: 'pointer' }}>
              <Avatar size={32} icon={<UserOutlined />} style={{ background: '#3B82F6' }} />
              <span style={{ fontSize: 14, color: '#1F2937' }}>
                {user?.display_name ?? '未登录'}
              </span>
              <span style={{ fontSize: 12, color: '#9CA3AF' }}>{user?.role ?? ''}</span>
            </Space>
          </Dropdown>
        </Header>
        <Content style={{ padding: '24px 32px', overflow: 'auto' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
