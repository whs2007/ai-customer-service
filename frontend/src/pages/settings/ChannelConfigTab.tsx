/** 渠道配置 Tab（13 §3.3）：渠道 key 只读 + 默认知识库多选 + 允许转人工。 */

import { Button, Form, Select, Switch, message } from 'antd';
import { useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiError } from '../../api/client';
import { getChannelConfig, updateChannelConfig } from '../../api/agent';
import { listKnowledgeBases } from '../../api/knowledge';

export default function ChannelConfigTab() {
  const queryClient = useQueryClient();
  const [form] = Form.useForm();
  const { data: config } = useQuery({
    queryKey: ['channel-config'],
    queryFn: getChannelConfig,
  });
  const { data: kbs = [] } = useQuery({
    queryKey: ['knowledge-bases'],
    queryFn: listKnowledgeBases,
  });

  const saveMutation = useMutation({
    mutationFn: (values: { channel: string; default_kb_ids: string[]; allow_human: boolean }) =>
      updateChannelConfig({
        channel: values.channel,
        default_kb_ids: values.default_kb_ids,
        allow_human: values.allow_human,
        business_hours: null,
      }),
    onSuccess: () => {
      message.success('渠道配置已保存，用户端新会话立即生效');
      void queryClient.invalidateQueries({ queryKey: ['channel-config'] });
    },
    onError: (err) => message.error(err instanceof ApiError ? err.message : '保存失败'),
  });

  useEffect(() => {
    if (config) {
      form.setFieldsValue({
        channel: config.channel,
        default_kb_ids: config.default_kb_ids,
        allow_human: config.allow_human,
      });
    }
  }, [config, form]);

  return (
    <div style={{ maxWidth: 560 }}>
      <p style={{ color: '#6B7280', fontSize: 13 }}>
        用户端在线咨询默认使用的知识库与转人工开关（11 §8）。保存后新会话立即生效。
      </p>
      <Form
        form={form}
        layout="vertical"
        onFinish={(values) => saveMutation.mutate(values)}
        initialValues={{ allow_human: true, default_kb_ids: [] }}
      >
        <Form.Item name="channel" label="渠道标识">
          <Select
            disabled
            options={[{ value: 'web_user', label: 'web_user（用户端 Web）' }]}
          />
        </Form.Item>
        <Form.Item name="default_kb_ids" label="默认知识库（多选）">
          <Select
            mode="multiple"
            placeholder="选择用户端可见的知识库"
            options={kbs.map((kb) => ({ value: kb.id, label: kb.name }))}
          />
        </Form.Item>
        <Form.Item name="allow_human" label="允许转人工" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>
          保存配置
        </Button>
      </Form>
    </div>
  );
}
