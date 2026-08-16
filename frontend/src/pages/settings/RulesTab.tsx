/** 客服规则 Tab（07 §2）：意图关键词规则 + 转人工阈值 + 工单优先级。 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Card, Form, InputNumber, Select, Space, message } from 'antd';
import { useEffect } from 'react';

import { ApiError } from '../../api/client';
import {
  getEscalationConfig,
  getIntentRules,
  getModerationWords,
  updateEscalationConfig,
  updateIntentRules,
  updateModerationWords,
} from '../../api/settings';
import { INTENT_LABELS } from '../../api/sessions';

const CATEGORIES = ['transfer', 'complaint', 'order_query', 'policy_query'];

export default function RulesTab() {
  const queryClient = useQueryClient();
  const [intentForm] = Form.useForm();
  const [escForm] = Form.useForm();
  const [modForm] = Form.useForm();

  const { data: intentRules } = useQuery({ queryKey: ['intent-rules'], queryFn: getIntentRules });
  const { data: escConfig } = useQuery({ queryKey: ['escalation-config'], queryFn: getEscalationConfig });
  const { data: modWords } = useQuery({ queryKey: ['moderation-words'], queryFn: getModerationWords });

  useEffect(() => {
    if (intentRules) intentForm.setFieldsValue({ keywords: intentRules.keywords });
    if (escConfig) escForm.setFieldsValue(escConfig);
    if (modWords) modForm.setFieldsValue({ words: modWords.words });
  }, [intentRules, escConfig, modWords, intentForm, escForm, modForm]);

  const intentMutation = useMutation({
    mutationFn: (values: { keywords: Record<string, string[]> }) => updateIntentRules(values),
    onSuccess: () => {
      message.success('意图规则已更新');
      queryClient.invalidateQueries({ queryKey: ['intent-rules'] });
    },
    onError: (err) => message.error(err instanceof ApiError ? err.message : '保存失败'),
  });
  const escMutation = useMutation({
    mutationFn: updateEscalationConfig,
    onSuccess: () => {
      message.success('转人工规则已更新');
      queryClient.invalidateQueries({ queryKey: ['escalation-config'] });
    },
    onError: (err) => message.error(err instanceof ApiError ? err.message : '保存失败'),
  });
  const modMutation = useMutation({
    mutationFn: (values: { words: string[] }) => updateModerationWords(values.words),
    onSuccess: () => {
      message.success('敏感词已更新');
      queryClient.invalidateQueries({ queryKey: ['moderation-words'] });
    },
    onError: (err) => message.error(err instanceof ApiError ? err.message : '保存失败'),
  });

  return (
    <Space direction="vertical" size={16} style={{ width: '100%', maxWidth: 760 }}>
      <Card title="意图分类标签与关键词规则">
        <Form form={intentForm} layout="vertical" onFinish={(v) => intentMutation.mutate(v)}>
          {CATEGORIES.map((cat) => (
            <Form.Item key={cat} name={['keywords', cat]} label={`${INTENT_LABELS[cat] ?? cat}`}>
              <Select
                mode="tags"
                placeholder="输入关键词后回车（如：退货、退款）"
                tokenSeparators={[',', '，']}
              />
            </Form.Item>
          ))}
          <Button type="primary" htmlType="submit" loading={intentMutation.isPending}>
            保存意图规则
          </Button>
        </Form>
      </Card>
      <Card title="转人工条件与工单优先级">
        <Form form={escForm} layout="vertical" onFinish={(v) => escMutation.mutate(v)}>
          <Form.Item name="threshold" label="连续兜底次数触发转人工（默认 2）">
            <InputNumber min={1} max={10} style={{ width: 160 }} />
          </Form.Item>
          {['complaint', 'transfer', 'other'].map((intent) => (
            <Form.Item key={intent} name={['priority_rules', intent]} label={`${INTENT_LABELS[intent] ?? intent} 工单优先级`}>
              <Select
                style={{ width: 200 }}
                options={[
                  { value: 'high', label: '高' },
                  { value: 'medium', label: '中' },
                  { value: 'low', label: '低' },
                ]}
              />
            </Form.Item>
          ))}
          <Button type="primary" htmlType="submit" loading={escMutation.isPending}>
            保存转人工规则
          </Button>
        </Form>
      </Card>
      <Card title="内容审核敏感词（本地兜底）">
        <Form form={modForm} layout="vertical" onFinish={(v) => modMutation.mutate(v)}>
          <Form.Item name="words" label="命中即拦截/替换（输入后回车，最多 200 条）">
            <Select
              mode="tags"
              placeholder="如：赌博、诈骗"
              tokenSeparators={[',', '，', '、']}
            />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={modMutation.isPending}>
            保存敏感词
          </Button>
        </Form>
      </Card>
    </Space>
  );
}
