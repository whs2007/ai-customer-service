/** 模型配置 Tab（07 §2.1）：列表/新增/编辑/删除/测试连通/设为默认。 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';

import { ApiError } from '../../api/client';
import type { ModelProfile } from '../../api/chat';
import {
  activateModelProfile,
  createModelProfile,
  deleteModelProfile,
  listModelProfiles,
  testModelProfile,
  updateModelProfile,
} from '../../api/settings';

const ROLE_LABELS: Record<string, string> = { chat: '对话', embedding: 'Embedding', rerank: '重排' };
const PROVIDERS = [
  { value: 'zhipu', label: '智谱 GLM' },
  { value: 'openai', label: 'OpenAI 兼容' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'siliconflow', label: 'SiliconFlow' },
  { value: 'ollama', label: '本地 Ollama' },
];
// 后端对已配置的 Key 只返回掩码，编辑时用它作为“已配置”标记
const KEY_MASK = 'sk-***';

export default function ModelTab() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ModelProfile | null>(null);
  const [form] = Form.useForm();

  const { data: profiles = [] } = useQuery({
    queryKey: ['model-profiles'],
    queryFn: listModelProfiles,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['model-profiles'] });
  const runMutation = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: () => {
      message.success('操作成功');
      invalidate();
    },
    onError: (err) => message.error(err instanceof ApiError ? err.message : '操作失败'),
  });

  const test = async (p: ModelProfile) => {
    const result = await testModelProfile(p.id);
    if (result.ok) {
      message.success(`连接成功，耗时 ${result.latency_ms ?? '-'}ms`);
    } else {
      message.warning(result.message || '连接失败');
    }
  };

  const submit = (values: Record<string, unknown>) => {
    runMutation.mutate(async () => {
      let payload = values;
      if (editing) {
        const { api_key, ...rest } = values as { api_key?: string };
        // 未输入新 Key 或仍为掩码时，不提交 api_key，后端保持原 Key 不变
        if (api_key && api_key.trim() && api_key.trim() !== KEY_MASK) {
          payload = { ...rest, api_key: api_key.trim() };
        } else {
          payload = rest;
        }
      }
      if (editing) {
        await updateModelProfile(editing.id, payload);
      } else {
        await createModelProfile(payload as never);
      }
      setModalOpen(false);
    });
  };

  const hasRerank = profiles.some((p) => p.role === 'rerank' && p.enabled);

  const columns: ColumnsType<ModelProfile> = [
    { title: '名称', dataIndex: 'name' },
    {
      title: '提供商',
      dataIndex: 'provider',
      width: 110,
      render: (v: string) => PROVIDERS.find((p) => p.value === v)?.label ?? v,
    },
    { title: '模型', dataIndex: 'model' },
    {
      title: '用途',
      dataIndex: 'role',
      width: 100,
      render: (v: string) => <Tag color={v === 'chat' ? 'blue' : v === 'embedding' ? 'green' : 'purple'}>{ROLE_LABELS[v] ?? v}</Tag>,
    },
    { title: 'API Key', dataIndex: 'api_key', width: 90, render: (v: string) => v || '—' },
    {
      title: '默认',
      dataIndex: 'is_default',
      width: 70,
      render: (v: boolean) => (v ? <Tag color="gold">默认</Tag> : '—'),
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      width: 80,
      render: (v: boolean) => (v ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>),
    },
    {
      title: '操作',
      key: 'actions',
      width: 250,
      render: (_, p) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            onClick={() => {
              setEditing(p);
              form.setFieldsValue({ ...p, api_key: p.api_key || '' });
              setModalOpen(true);
            }}
          >
            编辑
          </Button>
          <Button type="link" size="small" onClick={() => void test(p)}>
            测试连接
          </Button>
          {!p.is_default && (
            <Button type="link" size="small" onClick={() => runMutation.mutate(() => activateModelProfile(p.id))}>
              设为默认
            </Button>
          )}
          <Popconfirm
            title="删除该模型配置？"
            onConfirm={() => runMutation.mutate(() => deleteModelProfile(p.id))}
          >
            <Button type="link" size="small" danger disabled={p.is_default}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      {!hasRerank && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="未配置启用的重排（Rerank）Profile：检索测试的“混合+重排”模式将自动降级为混合检索。"
        />
      )}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <Button
          type="primary"
          onClick={() => {
            setEditing(null);
            form.resetFields();
            setModalOpen(true);
          }}
        >
          新增模型配置
        </Button>
      </div>
      <Table<ModelProfile> rowKey="id" columns={columns} dataSource={profiles} pagination={false} />

      <Modal
        title={editing ? '编辑模型配置' : '新增模型配置'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={runMutation.isPending}
        width={560}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={submit}>
          <Form.Item name="name" label="配置名称" rules={[{ required: true, max: 50 }]}>
            <Input placeholder="如：智谱免费 GLM" />
          </Form.Item>
          <div style={{ display: 'flex', gap: 12 }}>
            <Form.Item name="provider" label="提供商" rules={[{ required: true }]} style={{ flex: 1 }}>
              <Select options={PROVIDERS} />
            </Form.Item>
            <Form.Item name="role" label="用途" rules={[{ required: true }]} style={{ flex: 1 }}>
              <Select options={Object.entries(ROLE_LABELS).map(([value, label]) => ({ value, label }))} />
            </Form.Item>
          </div>
          <Form.Item name="model" label="模型名" rules={[{ required: true }]}>
            <Input placeholder="glm-4-flash / bge-m3 / BAAI/bge-reranker-v2-m3" />
          </Form.Item>
          <Form.Item name="base_url" label="Base URL">
            <Input placeholder="留空使用提供商默认地址" />
          </Form.Item>
          <Form.Item
            name="api_key"
            label={editing ? 'API Key（留空不修改）' : 'API Key'}
            rules={editing ? [] : [{ required: true, message: '请输入 API Key' }]}
            extra={
              editing && editing.api_key
                ? '已配置 Key，留空保存将保持不变；如需更换请直接输入新 Key'
                : undefined
            }
          >
            <Input.Password
              placeholder={editing ? '留空不修改' : 'sk-***'}
              autoComplete="new-password"
            />
          </Form.Item>
          <div style={{ display: 'flex', gap: 12 }}>
            <Form.Item name="temperature" label="temperature" style={{ flex: 1 }}>
              <InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="top_p" label="top_p" style={{ flex: 1 }}>
              <InputNumber min={0} max={1} step={0.1} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="max_tokens" label="max_tokens" style={{ flex: 1 }}>
              <InputNumber min={1} max={100000} style={{ width: '100%' }} />
            </Form.Item>
          </div>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
