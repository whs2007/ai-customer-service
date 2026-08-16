/** 账号权限 Tab（07 §2）：用户管理 + 知识库可见范围配置。 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Button,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';

import { ApiError } from '../../api/client';
import { listKnowledgeBases } from '../../api/knowledge';
import {
  createUser,
  listUsers,
  resetUserPassword,
  updateUser,
  type AdminUser,
} from '../../api/users';

const ROLE_LABELS: Record<string, string> = {
  admin: '管理员',
  agent: '客服',
  viewer: '只读访客',
  user: '用户',
};

export default function AccessTab() {
  const queryClient = useQueryClient();
  const [userModal, setUserModal] = useState<{ open: boolean; editing?: AdminUser }>({ open: false });
  const [passwordTarget, setPasswordTarget] = useState<AdminUser | null>(null);
  const [kbTarget, setKbTarget] = useState<{ id: string; name: string } | null>(null);
  const [userForm] = Form.useForm();
  const [pwdForm] = Form.useForm();
  const [kbForm] = Form.useForm();

  const { data: usersPage } = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => listUsers({ page: 1, page_size: 100 }),
  });
  const { data: kbs = [] } = useQuery({ queryKey: ['knowledge-bases'], queryFn: listKnowledgeBases });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['admin-users'] });
    queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] });
  };
  const runMutation = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: () => {
      message.success('操作成功');
      invalidate();
    },
    onError: (err) => message.error(err instanceof ApiError ? err.message : '操作失败'),
  });

  const userColumns: ColumnsType<AdminUser> = [
    { title: '用户名', dataIndex: 'username' },
    { title: '显示名', dataIndex: 'display_name' },
    {
      title: '角色',
      dataIndex: 'role',
      width: 110,
      render: (v: string) => <Tag color={v === 'admin' ? 'red' : v === 'agent' ? 'blue' : 'default'}>{ROLE_LABELS[v] ?? v}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (v: string) => (v === 'active' ? <Tag color="green">启用</Tag> : <Tag color="red">停用</Tag>),
    },
    {
      title: '操作',
      key: 'actions',
      width: 260,
      render: (_, u) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            onClick={() => {
              setUserModal({ open: true, editing: u });
              userForm.setFieldsValue({ username: u.username, display_name: u.display_name, role: u.role, status: u.status });
            }}
          >
            编辑
          </Button>
          <Button type="link" size="small" onClick={() => { setPasswordTarget(u); pwdForm.resetFields(); }}>
            重置密码
          </Button>
          <Popconfirm
            title={u.status === 'active' ? '停用该账号？' : '启用该账号？'}
            onConfirm={() => runMutation.mutate(() => updateUser(u.id, { status: u.status === 'active' ? 'disabled' : 'active' }))}
          >
            <Button type="link" size="small">
              {u.status === 'active' ? '停用' : '启用'}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
          <strong>用户管理</strong>
          <Button
            type="primary"
            size="small"
            onClick={() => {
              setUserModal({ open: true });
              userForm.resetFields();
            }}
          >
            新增用户
          </Button>
        </div>
        <Table<AdminUser> rowKey="id" size="small" columns={userColumns} dataSource={usersPage?.items ?? []} pagination={false} />
      </div>

      <div>
        <strong>知识库可见范围</strong>
        <div style={{ fontSize: 12, color: '#9CA3AF', margin: '4px 0 8px' }}>
          设置后 agent/viewer 仅能看到被授权的知识库（00 §3）
        </div>
        <Table
          rowKey="id"
          size="small"
          dataSource={kbs}
          pagination={false}
          columns={[
            { title: '名称', dataIndex: 'name' },
            {
              title: '可见范围',
              dataIndex: 'visibility',
              width: 110,
              render: (v: string) => <Tag>{v === 'all' ? '全部可见' : v === 'role' ? '指定角色' : '指定用户'}</Tag>,
            },
            {
              title: '操作',
              key: 'actions',
              width: 100,
              render: (_, kb) => (
                <Button
                  type="link"
                  size="small"
                  onClick={() => {
                    setKbTarget({ id: kb.id, name: kb.name });
                    kbForm.setFieldsValue({
                      visibility: kb.visibility ?? 'all',
                      visible_roles: kb.visible_roles ?? [],
                      visible_user_ids: kb.visible_user_ids ?? [],
                    });
                  }}
                >
                  配置
                </Button>
              ),
            },
          ]}
        />
      </div>

      {/* 用户新增/编辑 */}
      <Modal
        title={userModal.editing ? '编辑用户' : '新增用户'}
        open={userModal.open}
        onCancel={() => setUserModal({ open: false })}
        onOk={() => userForm.submit()}
        width={460}
        destroyOnClose
      >
        <Form
          form={userForm}
          layout="vertical"
          onFinish={(values) => {
            runMutation.mutate(async () => {
              if (userModal.editing) {
                await updateUser(userModal.editing.id, values);
              } else {
                await createUser({ ...values, password: values.password });
              }
              setUserModal({ open: false });
            });
          }}
        >
          <Form.Item name="username" label="用户名" rules={[{ required: true, min: 2, max: 50 }]}>
            <Input disabled={Boolean(userModal.editing)} />
          </Form.Item>
          {!userModal.editing && (
            <Form.Item name="password" label="初始密码" rules={[{ required: true, min: 6 }]}>
              <Input.Password />
            </Form.Item>
          )}
          <Form.Item name="display_name" label="显示名" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true }]}>
            <Select options={Object.entries(ROLE_LABELS).map(([value, label]) => ({ value, label }))} />
          </Form.Item>
          <Form.Item name="status" label="状态" rules={[{ required: true }]}>
            <Select options={[{ value: 'active', label: '启用' }, { value: 'disabled', label: '停用' }]} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 重置密码 */}
      <Modal
        title={`重置密码 · ${passwordTarget?.username ?? ''}`}
        open={Boolean(passwordTarget)}
        onCancel={() => setPasswordTarget(null)}
        onOk={() => pwdForm.submit()}
        width={380}
        destroyOnClose
      >
        <Form
          form={pwdForm}
          layout="vertical"
          onFinish={(values) => {
            if (passwordTarget) {
              runMutation.mutate(async () => {
                await resetUserPassword(passwordTarget.id, values.password);
                setPasswordTarget(null);
              });
            }
          }}
        >
          <Form.Item name="password" label="新密码" rules={[{ required: true, min: 6 }]}>
            <Input.Password />
          </Form.Item>
        </Form>
      </Modal>

      {/* 知识库可见范围 */}
      <Modal
        title={`知识库可见范围 · ${kbTarget?.name ?? ''}`}
        open={Boolean(kbTarget)}
        onCancel={() => setKbTarget(null)}
        onOk={() => kbForm.submit()}
        width={520}
        destroyOnClose
      >
        <Form
          form={kbForm}
          layout="vertical"
          onFinish={(values) => {
            if (kbTarget) {
              runMutation.mutate(async () => {
                const { updateKnowledgeBase } = await import('../../api/knowledge');
                await updateKnowledgeBase(kbTarget.id, {
                  name: kbTarget.name,
                  description: '',
                  visibility: values.visibility,
                  visible_roles: values.visible_roles ?? [],
                  visible_user_ids: values.visible_user_ids ?? [],
                });
                setKbTarget(null);
              });
            }
          }}
        >
          <Form.Item name="visibility" label="可见范围" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'all', label: '全部可见' },
                { value: 'role', label: '指定角色可见' },
                { value: 'user', label: '指定用户可见' },
              ]}
            />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, cur) => prev.visibility !== cur.visibility}>
            {({ getFieldValue }) =>
              getFieldValue('visibility') === 'role' ? (
                <Form.Item name="visible_roles" label="可见角色">
                  <Select
                    mode="multiple"
                    options={[
                      { value: 'admin', label: '管理员' },
                      { value: 'agent', label: '客服' },
                      { value: 'viewer', label: '只读访客' },
                      { value: 'user', label: '用户' },
                    ]}
                  />
                </Form.Item>
              ) : getFieldValue('visibility') === 'user' ? (
                <Form.Item name="visible_user_ids" label="可见用户">
                  <Select
                    mode="multiple"
                    placeholder="选择用户"
                    options={(usersPage?.items ?? [])
                      .filter((u) => u.status === 'active')
                      .map((u) => ({ value: u.id, label: `${u.display_name}（${u.username}）` }))}
                  />
                </Form.Item>
              ) : null
            }
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
