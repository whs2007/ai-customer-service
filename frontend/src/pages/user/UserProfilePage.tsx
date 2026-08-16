/** 用户个人中心（12 §5）：账号信息 + 修改密码 + 退出。 */

import { Button, Card, Descriptions, Form, Input, Space, message } from 'antd';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { ApiError } from '../../api/client';
import { changePassword } from '../../api/user';
import { useUserAuthStore } from '../../stores/userAuth';

interface PwdForm {
  old_password: string;
  new_password: string;
  confirm_password: string;
}

export default function UserProfilePage() {
  const user = useUserAuthStore((s) => s.user);
  const logout = useUserAuthStore((s) => s.logout);
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm<PwdForm>();

  const onFinish = async (values: PwdForm) => {
    setLoading(true);
    try {
      await changePassword(values.old_password, values.new_password);
      message.success('密码已修改，请重新登录');
      logout();
      navigate('/user/login', { replace: true });
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : '修改失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 720, margin: '24px auto', padding: '0 16px' }}>
      <Card title="账号信息" style={{ marginBottom: 16 }}>
        <Descriptions column={1} size="small">
          <Descriptions.Item label="用户名">{user?.username}</Descriptions.Item>
          <Descriptions.Item label="昵称">{user?.display_name}</Descriptions.Item>
          <Descriptions.Item label="角色">用户</Descriptions.Item>
          <Descriptions.Item label="注册时间">
            {user?.created_at ? new Date(user.created_at).toLocaleString() : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="最后登录时间">
            {user?.last_login_at ? new Date(user.last_login_at).toLocaleString() : '-'}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="修改密码">
        <Form<PwdForm> form={form} layout="vertical" onFinish={onFinish} style={{ maxWidth: 420 }}>
          <Form.Item name="old_password" label="旧密码" rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item
            name="new_password"
            label="新密码"
            rules={[
              { required: true },
              { min: 8, max: 64, message: '密码长度需为 8~64 位' },
              { pattern: /^(?=.*[A-Za-z])(?=.*\d).+$/, message: '密码需同时包含字母和数字' },
            ]}
          >
            <Input.Password />
          </Form.Item>
          <Form.Item
            name="confirm_password"
            label="确认新密码"
            dependencies={['new_password']}
            rules={[
              { required: true },
              ({ getFieldValue }) => ({
                validator: (_, value) =>
                  !value || getFieldValue('new_password') === value
                    ? Promise.resolve()
                    : Promise.reject(new Error('两次输入的密码不一致')),
              }),
            ]}
          >
            <Input.Password />
          </Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" loading={loading}>
              修改密码
            </Button>
            <Button
              danger
              onClick={() => {
                logout();
                navigate('/user/login', { replace: true });
              }}
            >
              退出登录
            </Button>
          </Space>
        </Form>
      </Card>
    </div>
  );
}
