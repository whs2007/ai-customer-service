/** 用户端登录页（12 §2）：独立入口，与管理端登录隔离。 */

import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { Button, Card, Form, Input, Typography, message } from 'antd';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { ApiError } from '../../api/client';
import { loginAndRoute } from '../../utils/login';

interface LoginForm {
  username: string;
  password: string;
}

export default function UserLogin() {
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const onFinish = async (values: LoginForm) => {
    setLoading(true);
    try {
      await loginAndRoute(values.username, values.password, navigate);
      message.success('登录成功');
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : '登录失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#F5F6FA',
      }}
    >
      <Card style={{ width: 400, borderRadius: 16, boxShadow: '0 1px 3px rgba(0,0,0,.06)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Typography.Title level={3} style={{ marginBottom: 4, fontSize: 20 }}>
            AI 智能客服
          </Typography.Title>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            用户端 · 在线咨询
          </Typography.Text>
        </div>
        <Form<LoginForm> onFinish={onFinish} size="large">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="密码"
              autoComplete="current-password"
            />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>
            登录
          </Button>
          <div style={{ textAlign: 'center', marginTop: 12 }}>
            <Link to="/user/register">没有账号？注册</Link>
          </div>
        </Form>
      </Card>
    </div>
  );
}
