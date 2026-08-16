/** 用户端自助注册页（12 §2.1）：算术验证码 + 密码强度校验。 */

import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { Button, Card, Form, Input, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { ApiError } from '../../api/client';
import { getCaptcha } from '../../api/user';
import { useUserAuthStore } from '../../stores/userAuth';

interface RegisterForm {
  username: string;
  password: string;
  confirm_password: string;
  display_name?: string;
  captcha: string;
}

export default function UserRegister() {
  const [loading, setLoading] = useState(false);
  const [captcha, setCaptcha] = useState<{ captcha_id: string; question: string } | null>(null);
  const register = useUserAuthStore((s) => s.register);
  const navigate = useNavigate();
  const [form] = Form.useForm<RegisterForm>();

  const refreshCaptcha = async () => {
    try {
      setCaptcha(await getCaptcha());
      form.setFieldValue('captcha', '');
    } catch {
      // 验证码服务不可用时允许注册（限流兜底）
      setCaptcha(null);
    }
  };

  useEffect(() => {
    void refreshCaptcha();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onFinish = async (values: RegisterForm) => {
    if (!captcha) {
      message.warning('验证码未就绪，请重试');
      return;
    }
    setLoading(true);
    try {
      await register({
        username: values.username,
        password: values.password,
        confirm_password: values.confirm_password,
        display_name: values.display_name || undefined,
        captcha_id: captcha.captcha_id,
        captcha: values.captcha,
      });
      message.success('注册成功，已自动登录');
      navigate('/user/chat', { replace: true });
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : '注册失败，请稍后重试');
      void refreshCaptcha();
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
      <Card style={{ width: 420, borderRadius: 16, boxShadow: '0 1px 3px rgba(0,0,0,.06)' }}>
        <div style={{ textAlign: 'center', marginBottom: 20 }}>
          <Typography.Title level={3} style={{ marginBottom: 4, fontSize: 20 }}>
            注册账号
          </Typography.Title>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            注册即自动登录，开始在线咨询
          </Typography.Text>
        </div>
        <Form<RegisterForm> form={form} onFinish={onFinish} layout="vertical">
          <Form.Item
            name="username"
            label="用户名"
            rules={[
              { required: true, message: '请输入用户名' },
              { min: 4, max: 32, message: '用户名长度需为 4~32 位' },
              { pattern: /^[A-Za-z0-9_\u4e00-\u9fa5]+$/, message: '仅支持字母、数字、下划线与中文' },
            ]}
          >
            <Input prefix={<UserOutlined />} placeholder="4~32 位，字母/数字/下划线/中文" />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 8, max: 64, message: '密码长度需为 8~64 位' },
              { pattern: /^(?=.*[A-Za-z])(?=.*\d).+$/, message: '密码需同时包含字母和数字' },
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="8~64 位，含字母和数字" />
          </Form.Item>
          <Form.Item
            name="confirm_password"
            label="确认密码"
            dependencies={['password']}
            rules={[
              { required: true, message: '请再次输入密码' },
              ({ getFieldValue }) => ({
                validator: (_, value) =>
                  !value || getFieldValue('password') === value
                    ? Promise.resolve()
                    : Promise.reject(new Error('两次输入的密码不一致')),
              }),
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="再次输入密码" />
          </Form.Item>
          <Form.Item name="display_name" label="昵称（可选）">
            <Input placeholder="默认取用户名" maxLength={50} />
          </Form.Item>
          <Form.Item name="captcha" label="验证码" rules={[{ required: true, message: '请输入验证码答案' }]}>
            <div style={{ display: 'flex', gap: 8 }}>
              <Input placeholder={captcha?.question ?? '验证码加载中…'} />
              <Button onClick={() => void refreshCaptcha()} style={{ whiteSpace: 'nowrap' }}>
                换一题
              </Button>
            </div>
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>
            注册
          </Button>
          <div style={{ textAlign: 'center', marginTop: 12 }}>
            <Link to="/user/login">已有账号？去登录</Link>
          </div>
        </Form>
      </Card>
    </div>
  );
}
